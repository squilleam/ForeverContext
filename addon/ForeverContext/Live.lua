-- Passive, opt-in pixel transport. No input, network, or disk APIs.
local F = ForeverContext
local L = {enabled=false, sequence=0}
F.Live = L
local floor = math.floor
local function uint(n, max)
    return type(n)=='number' and n==n and n>=0 and n<=max and n==floor(n)
end
local function u16(n) return string.char(floor(n/256)%256,n%256) end
local function u32(n) return u16(floor(n/65536))..u16(n%65536) end
local function adler(raw)
    local a,b=1,0
    for i=1,#raw do a=(a+raw:byte(i))%65521; b=(b+a)%65521 end
    return b*65536+a
end
local sessionNonce = ((F.Call(time) or 0) + floor((F.Call(GetTime) or 0)*1000) + math.random(0,16777215))%4294967296
local function newSession()
    sessionNonce=(sessionNonce+1)%4294967296
    return sessionNonce
end
function L.BuildFrames(raw,session,sequence,capturedAt)
    if type(raw)~='string' or #raw<1 or #raw>1048576 then error('live payload length out of bounds') end
    if not uint(session,4294967295) or not uint(sequence,4294967295) or not uint(capturedAt,4294967295) then
        error('live metadata must be uint32')
    end
    local count=floor((#raw+1047)/1048)
    local checksum=adler(raw)
    local frames={}
    for index=0,count-1 do
        local chunk=raw:sub(index*1048+1,(index+1)*1048)
        local header='FCX1'..string.char(1,0)..u16(40)..u32(session)..u32(sequence)..u16(index)..u16(count)..u32(#raw)..u16(#chunk)..u16(0)..u32(checksum)..u32(capturedAt)
        frames[index+1]=header..u32(adler(header..chunk))..chunk
    end
    return frames
end
function L.Begin()
    L.frames=nil
    L.index=1
    local ok,result=pcall(function()
        if F.capturing then error('capture already in progress') end
        local snapshot=F.Capture()
        if F.lastError or not snapshot then error(F.lastError or 'snapshot unavailable') end
        local sequence=(L.sequence+1)%4294967296
        if sequence==0 or not L.session then L.session=newSession() end
        local frames=L.BuildFrames(F.JSON(snapshot),L.session,sequence,snapshot.capturedAt)
        L.sequence=sequence
        return frames
    end)
    if not ok then L.lastError=tostring(result); return false end
    L.frames=result
    L.lastError=nil
    return true
end
function L.NextFrame()
    if not L.frames or L.index>#L.frames then
        if not L.Begin() then return nil end
    end
    local raw=L.frames[L.index]
    L.index=L.index+1
    return raw
end
local anchors={{1,0,1},{0,1,1},{1,1,0},{1,0,1},{0,0,0},{1,1,1},{0,1,1},{1,0,0}}
local function settings()
    if type(ForeverContextDB)~='table' then ForeverContextDB={} end
    if type(ForeverContextDB.settings)~='table' then ForeverContextDB.settings={} end
    return ForeverContextDB.settings
end
function L.Status()
    local state=L.enabled and (L.lastError and 'error' or 'on') or 'off'
    local detail=L.lastError and ('; '..L.lastError:gsub('[%c|]',' '):sub(1,180)) or ''
    return 'Live '..state..'; sequence '..tostring(L.sequence)..detail
end
local function layout()
    local _,physicalHeight=F.Call(GetPhysicalScreenSize)
    local height=UIParent and F.Call(UIParent.GetHeight,UIParent)
    local effective=UIParent and F.Call(UIParent.GetEffectiveScale,UIParent)
    if not physicalHeight or not height or not effective or physicalHeight<=0 then error('physical UI scale unavailable') end
    local scale=height*effective/physicalHeight
    L.frame:SetIgnoreParentScale(true)
    L.frame:SetScale(scale)
    L.frame:ClearAllPoints()
    L.frame:SetPoint('TOPRIGHT',UIParent,'TOPRIGHT',0,0)
end
local function createStrip()
    if L.frame and L.cells and #L.cells==2304 then layout(); return end
    local frame=L.frame or CreateFrame('Frame','ForeverContextLive',UIParent)
    L.frame=frame
    frame:Hide()
    frame:SetSize(256,36)
    frame:SetFrameStrata('TOOLTIP')
    frame:EnableMouse(false)
    layout()
    L.cells={}
    for row=0,17 do
        for col=0,127 do
            local cell=frame:CreateTexture(nil,'OVERLAY')
            cell:SetSize(2,2)
            cell:SetPoint('TOPLEFT',frame,'TOPLEFT',col*2,-row*2)
            if cell.SetSnapToPixelGrid then cell:SetSnapToPixelGrid(false) end
            if cell.SetTexelSnappingBias then cell:SetTexelSnappingBias(0) end
            cell:SetColorTexture(0,0,0,1)
            L.cells[#L.cells+1]=cell
        end
    end
    for i,color in ipairs(anchors) do L.cells[i]:SetColorTexture(color[1],color[2],color[3],1) end
    for n=0,15 do local v=(8+16*n)/255; L.cells[9+n]:SetColorTexture(v,v,v,1) end

end
local function halt(reason)
    L.lastError=tostring(reason)
    L.frames=nil
    if L.frame then L.frame:Hide(); L.frame:SetScript('OnUpdate',nil) end

end
local function render()
    local raw=L.NextFrame()
    if not raw then error(L.lastError or 'no live frame') end
    for i=1,1088 do
        local byte=raw:byte(i) or 0
        local high=(8+16*floor(byte/16))/255
        local low=(8+16*(byte%16))/255
        L.cells[128+i*2-1]:SetColorTexture(high,high,high,1)
        L.cells[128+i*2]:SetColorTexture(low,low,low,1)
    end

end
function L.SetEnabled(enabled)
    enabled=enabled==true
    settings().liveEnabled=enabled
    if not enabled then
        L.enabled=false; L.frames=nil; L.lastError=nil
        if L.frame then L.frame:Hide(); L.frame:SetScript('OnUpdate',nil) end
        return true
    end
    if L.enabled and not L.lastError then return true end
    L.enabled=true; L.lastError=nil; L.session=newSession(); L.sequence=0; L.frames=nil; L.elapsed=0
    local ok,reason=pcall(function()
        createStrip()
        render()
        L.frame:Show()
        L.frame:SetScript('OnUpdate',function(_,delta)
            L.elapsed=L.elapsed+delta
            if L.elapsed<.1 then return end
            -- Never skip chunks or race through missed frames after a stalled UI.
            L.elapsed=0
            local success,err=pcall(render)
            if not success then halt(err) end
        end)
    end)
    if not ok then halt(reason); return false end
    return true
end
L.events=CreateFrame('Frame')
L.events:SetScript('OnEvent',function(_,event)
    if event=='PLAYER_LOGIN' then
        if settings().liveEnabled==true then L.SetEnabled(true) end
    elseif L.enabled and L.frame then
        local ok,reason=pcall(layout)
        if not ok then halt(reason) end
    end
end)
for _,event in ipairs({'PLAYER_LOGIN','DISPLAY_SIZE_CHANGED','UI_SCALE_CHANGED'}) do pcall(L.events.RegisterEvent,L.events,event) end
