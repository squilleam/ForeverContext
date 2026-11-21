local F = ForeverContext
function F.Print(text)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage('|cff67d9bdForeverContext:|r ' .. text) end
end
function F.ShowExport()
    if not F.window then
        local frame=CreateFrame('Frame','ForeverContextWindow',UIParent,'BackdropTemplate')
        frame:SetSize(760,520)
        frame:SetPoint('CENTER')
        frame:SetFrameStrata('DIALOG')
        frame:SetClampedToScreen(true)
        frame:SetMovable(true)
        frame:EnableMouse(true)
        frame:RegisterForDrag('LeftButton')
        frame:SetScript('OnDragStart',frame.StartMoving)
        frame:SetScript('OnDragStop',frame.StopMovingOrSizing)
        frame:SetBackdrop({bgFile='Interface/Buttons/WHITE8X8',edgeFile='Interface/Tooltips/UI-Tooltip-Border',tile=false,edgeSize=16,insets={left=4,right=4,top=4,bottom=4}})
        frame:SetBackdropColor(0.035,0.055,0.07,0.98)
        local title=frame:CreateFontString(nil,'OVERLAY','GameFontNormalLarge')
        title:SetPoint('TOPLEFT',20,-18)
        title:SetText('ForeverContext  |  Snapshot JSON')
        local hint=frame:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
        hint:SetPoint('TOPLEFT',20,-48)
        hint:SetText('Click Select all, then Ctrl+C. Escape closes. /fctx save + manual /reload flushes to disk.')
        local close=CreateFrame('Button',nil,frame,'UIPanelCloseButton')
        close:SetPoint('TOPRIGHT',-4,-4)
        close:SetScript('OnClick',function() frame:Hide() end)
        local scroll=CreateFrame('ScrollFrame','ForeverContextScroll',frame,'UIPanelScrollFrameTemplate')
        scroll:SetPoint('TOPLEFT',20,-75)
        scroll:SetPoint('BOTTOMRIGHT',-42,58)
        local edit=CreateFrame('EditBox','ForeverContextEdit',scroll)
        edit:SetMultiLine(true)
        edit:SetAutoFocus(false)
        edit:SetFontObject(ChatFontNormal)
        edit:SetWidth(680)
        edit:SetHeight(360)
        edit:SetMaxLetters(0)
        edit:SetHyperlinksEnabled(false)
        edit:SetScript('OnEscapePressed',function() frame:Hide() end)
        edit:SetScript('OnTextChanged',function() scroll:UpdateScrollChildRect() end)
        edit:SetScript('OnCursorChanged',function(_,x,y,width,height)
            local current=scroll:GetVerticalScroll()
            local position=-y
            if position<current then scroll:SetVerticalScroll(position)
            elseif position+height>current+360 then scroll:SetVerticalScroll(position+height-360) end
        end)
        scroll:SetScrollChild(edit)
        local select=CreateFrame('Button',nil,frame,'UIPanelButtonTemplate')
        select:SetSize(110,26)
        select:SetPoint('BOTTOMLEFT',20,18)
        select:SetText('Select all')
        select:SetScript('OnClick',function() edit:SetFocus(); edit:HighlightText() end)
        local footer=frame:CreateFontString(nil,'OVERLAY','GameFontHighlightSmall')
        footer:SetPoint('LEFT',select,'RIGHT',12,0)
        footer:SetText('In-memory export only. The box is editable; edits do not change the saved snapshot.')
        frame:SetScript('OnHide',function() edit:ClearFocus() end)
        UISpecialFrames[#UISpecialFrames+1]='ForeverContextWindow'
        F.window,F.edit,F.scroll=frame,edit,scroll
    end
    F.window:Show()
    F.edit:SetText(ForeverContextExport or '')
    F.scroll:SetVerticalScroll(0)
    F.edit:SetFocus()
    F.edit:HighlightText()
end
function F.Status()
    if F.lastError then F.Print('Last capture failed; previous export retained. '..F.lastError); return end
    if not F.last then F.Print('No scan yet. Use /fctx export.'); return end
    local last=F.last
    local missing=0
    for _,group in ipairs({last.equipment,last.bags,last.bank.items}) do
        for _,item in ipairs(group) do if item.pending then missing=missing+1 end end
    end
    local now=F.Call(time) or last.capturedAt
    local bank=last.bank.known and ('last seen '..tostring(now-last.bank.capturedAt)..'s ago') or 'unknown (visit a banker)'
    F.Print('Scan '..tostring(now-last.capturedAt)..'s ago; missing cached items: '..missing..
        '; bank: '..bank..'; export '..tostring(#(ForeverContextExport or ''))..' bytes in memory. /reload saves to disk.')
end
SLASH_FOREVERCONTEXT1='/fctx'
SlashCmdList.FOREVERCONTEXT=function(command)
    local cmd=(command or ''):match('^%s*(.-)%s*$'):lower()
    if cmd=='' or cmd=='export' then
        F.Capture(); F.ShowExport()
    elseif cmd=='save' then
        F.Capture()
        if F.lastError then F.Status(); return end
        F.Print('Snapshot refreshed in memory. Use /reload manually (or log out) to flush SavedVariables to disk; no reload performed.')
    elseif cmd=='status' then F.Status()
    elseif cmd=='live on' or cmd=='live off' or cmd=='live status' then
        if not F.Live then F.Print('Live module unavailable; reload the updated addon.'); return end
        if cmd~='live status' then F.Live.SetEnabled(cmd=='live on') end
        F.Print(F.Live.Status())
    else
        F.Print('/fctx [export] - copy JSON; /fctx save - refresh; /fctx status - age/cache; /fctx live on|off|status - opt-in pixels; /fctx help - this list.')
    end
end
