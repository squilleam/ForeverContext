-- ForeverContext: read-only character context. No protected actions or disk IO.
ForeverContext = {version = "1.1.3", bankOpen = false}
local F = ForeverContext
local arrayMT = {}
function F.Array(t) return setmetatable(t or {}, arrayMT) end
-- Match the client-supported guard used by installed PawnForever. Never inspect,
-- compare, format or attempt to recover a value the game marks restricted.
function F.Plain(value)
    if issecretvalue and issecretvalue(value) then
        F.secretOmissions=true
        return nil
    end
    return value
end
local function quote(s)
    -- JSON unicode escaping prevents WoW's EditBox from rendering/stripping links.
    return '"' .. s:gsub('[%z\1-\31\\"|]', function(c)
        local escapes = {['|']='\\u007c', ['"']='\\"', ['\\']='\\\\', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t', ['\b']='\\b', ['\f']='\\f'}
        return escapes[c] or string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
function F.JSON(value)
    value=F.Plain(value)
    local kind = type(value)
    if kind == 'string' then return quote(value) end
    if kind == 'number' then
        if value ~= value or value == math.huge or value == -math.huge then return 'null' end
        return tostring(value)
    end
    if kind == 'boolean' then return tostring(value) end
    if kind ~= 'table' then return 'null' end
    local out = {}
    if getmetatable(value) == arrayMT then
        for i = 1, #value do out[i] = F.JSON(value[i]) end
        return '[' .. table.concat(out, ',') .. ']'
    end
    local keys = {}
    for key in pairs(value) do
        if F.Plain(key)~=nil then keys[#keys+1] = tostring(key) end
    end
    table.sort(keys)
    for _, key in ipairs(keys) do out[#out+1] = quote(key) .. ':' .. F.JSON(value[key]) end
    return '{' .. table.concat(out, ',') .. '}'
end
-- Protected API reads are deliberately separate from protected game actions.
function F.Call(fn, ...)
    if type(fn) ~= 'function' then return nil end
    local result = {pcall(fn, ...)}
    if not result[1] then return nil end
    for i=2,20 do result[i]=F.Plain(result[i]) end
    return unpack(result, 2, 20)
end
local slotNames = {'HeadSlot','NeckSlot','ShoulderSlot','ShirtSlot','ChestSlot','WaistSlot','LegsSlot','FeetSlot','WristSlot','HandsSlot','Finger0Slot','Finger1Slot','Trinket0Slot','Trinket1Slot','BackSlot','MainHandSlot','SecondaryHandSlot','RangedSlot','TabardSlot'}
function F.Clean(text)
    text=F.Plain(text)
    if type(text) ~= 'string' then return nil end
    return (text:gsub('|c%x%x%x%x%x%x%x%x',''):gsub('|r',''):gsub('|H.-|h(.-)|h','%1'):gsub('|T.-|t',''):gsub('|A.-|a',''):gsub('[%z\1-\8\11\12\14-\31]',''))
end
function F.Tooltip(link)
    local lines = F.Array()
    local data = link and F.Call(C_TooltipInfo and C_TooltipInfo.GetHyperlink, link)
    if type(data) == 'table' and type(data.lines) == 'table' then
        for _, line in ipairs(data.lines) do
            local left, right = F.Clean(line.leftText), F.Clean(line.rightText)
            if left or right then lines[#lines+1] = {left=left,right=right} end
        end
    end
    if #lines == 0 and link and CreateFrame then
        if not F.tooltip then
            F.tooltip = CreateFrame('GameTooltip','ForeverContextTooltip',UIParent,'GameTooltipTemplate')
        end
        local tip = F.tooltip
        tip:SetOwner(UIParent,'ANCHOR_NONE')
        tip:ClearLines()
        local ok = pcall(tip.SetHyperlink,tip,link)
        if ok then
            for i=1,tip:NumLines() do
                local l, r = _G['ForeverContextTooltipTextLeft'..i], _G['ForeverContextTooltipTextRight'..i]
                local left = l and F.Clean(l:GetText())
                local right = (r and r:IsShown()) and F.Clean(r:GetText()) or nil
                if left or right then lines[#lines+1] = {left=left,right=right} end
            end
        end
        tip:ClearLines()
        tip:Hide()
    end
    return lines
end
function F.Item(source, warnings)
    local item = source
    if type(item.link)=='string' then
        item.itemString = item.link:match('|H(item:[^|]+)|h') or item.link:match('^(item:[%d:%-]+)$')
    end
    local query = item.link or item.itemId
    local name, _, quality, level, required, _, _, _, equip = F.Call(C_Item and C_Item.GetItemInfo or GetItemInfo, query)
    item.name, item.quality = name, quality or item.quality
    item.itemLevel, item.requiredLevel, item.equipLoc = level, required, equip
    item.stats = F.Call(C_Item and C_Item.GetItemStats or GetItemStats, query)
    item.tooltip = F.Tooltip(item.link)
    if not name then
        item.pending = true
        warnings[#warnings+1] = 'Item ' .. tostring(item.itemId or item.link or 'unknown') .. ' is not cached; occupied slot retained.'
    end
    if #item.tooltip==0 then
        item.pending,item.tooltipPending=true,true
        warnings[#warnings+1]='Item '..tostring(item.itemId or 'unknown')..' tooltip unavailable/pending; no effects inferred.'
    end
    if item.pending and item.itemId and F.waiting then F.waiting[item.itemId]=true end
    return item
end
function F.Equipment(warnings)
    local items = F.Array()
    if type(GetInventoryItemLink)~='function' and type(GetInventoryItemID)~='function' then return nil end
    for slot, name in ipairs(slotNames) do
        local link,id
        if type(GetInventoryItemLink)=='function' then
            local ok,value=pcall(GetInventoryItemLink,'player',slot)
            if not ok then return nil end
            link=value
        end
        if type(GetInventoryItemID)=='function' then
            local ok,value=pcall(GetInventoryItemID,'player',slot)
            if not ok then return nil end
            id=value
        end
        id=id or (link and tonumber(link:match('item:(%d+)')))
        if link or id then
            items[#items+1] = F.Item({slot=slot,slotName=name,link=link,itemId=id,count=F.Call(GetInventoryItemCount,'player',slot) or 1},warnings)
        end
    end
    return items
end
function F.Containers(ids, warnings)
    local items = F.Array()
    for _, bag in ipairs(ids) do
        local count
        if Enum and Enum.BagIndex and bag == Enum.BagIndex.Keyring and type(GetKeyRingSize) == 'function' then
            count = F.Call(GetKeyRingSize)
        else
            count = F.Call(C_Container and C_Container.GetContainerNumSlots or GetContainerNumSlots,bag)
        end
        if type(count) ~= 'number' then return nil end
        for slot=1,count do
            local reader = C_Container and C_Container.GetContainerItemInfo
            if type(reader) ~= 'function' then return nil end
            local ok, info = pcall(reader,bag,slot)
            if not ok then return nil end
            if type(info)~='table' then
                local id=F.Call(C_Container and C_Container.GetContainerItemID,bag,slot)
                local link=F.Call(C_Container and C_Container.GetContainerItemLink,bag,slot)
                if id or link then info={itemID=id,hyperlink=link} end
            end
            if type(info)=='table' then
                local link = info.hyperlink or F.Call(C_Container and C_Container.GetContainerItemLink,bag,slot)
                local id = info.itemID or (link and tonumber(link:match('item:(%d+)')))
                items[#items+1] = F.Item({bag=bag,slot=slot,itemId=id,link=link,count=info.stackCount or 1,quality=info.quality},warnings)
            end
        end
    end
    return items
end
function F.ContainerIDs(bank)
    local indexes = Enum and Enum.BagIndex or {}
    local ids,seen = {},{}
    local function add(id)
        if type(id)=='number' and not seen[id] then ids[#ids+1]=id; seen[id]=true end
    end
    if bank then
        -- Installed Forever Syndicator uses character bank tabs, not legacy bank bags.
        if indexes.CharacterBankTab_1 then
            for i=1,9 do add(indexes['CharacterBankTab_'..i]) end
        else
            add(indexes.Bank or -1)
            for bag=(NUM_BAG_SLOTS or 4)+1,(NUM_BAG_SLOTS or 4)+(NUM_BANKBAGSLOTS or 7) do add(bag) end
        end
    else
        for bag=0,NUM_BAG_SLOTS or 4 do add(bag) end
        add(indexes.ReagentBag)
        add(indexes.Keyring)
    end
    return ids
end
function F.CharacterCache(guid)
    if type(ForeverContextDB) ~= 'table' then ForeverContextDB = {} end
    if type(ForeverContextDB.characters) ~= 'table' then ForeverContextDB.characters = {} end
    local cache = guid and ForeverContextDB.characters[guid]
    if type(cache) ~= 'table' then
        cache = {}
        if guid then ForeverContextDB.characters[guid]=cache end
    end
    return cache
end
function F.RestoreItems(items)
    F.Array(items)
    for _,item in ipairs(items) do item.tooltip=F.Array(item.tooltip or {}) end
    return items
end
function F.Inventory(snapshot,key,items)
    local cache=F.CharacterCache(snapshot.character.guid)
    snapshot[key..'Known']=items~=nil
    if items then
        snapshot[key]=items
        snapshot[key..'CapturedAt']=snapshot.capturedAt
    else
        local previous=cache.latestSnapshot
        snapshot[key]=F.RestoreItems(previous and previous[key] or {})
        snapshot[key..'CapturedAt']=previous and previous[key..'CapturedAt']
        snapshot.warnings[#snapshot.warnings+1]=key..' read failed/unavailable; data is unknown or last seen, not a known empty inventory.'
    end
end
function F.Bank(guid, warnings, now)
    local cache = F.CharacterCache(guid)
    if F.bankOpen then
        local items = F.Containers(F.ContainerIDs(true),warnings)
        if items then
            cache.bank = {capturedAt=now,items=items}
            if guid then ForeverContextDB.characters[guid] = cache end
        else
            warnings[#warnings+1] = 'Bank read failed; last successful cache retained (if any).'
        end
    end
    local bank = cache.bank
    if type(bank)=='table' and type(bank.items)=='table' and type(bank.capturedAt)=='number' and bank.capturedAt<=now then
        -- SavedVariables do not preserve metatables; restore array identity after login.
        F.Array(bank.items)
        for _,item in ipairs(bank.items) do item.tooltip=F.Array(item.tooltip or {}) end
        if not F.bankOpen or bank.capturedAt ~= now then
            warnings[#warnings+1] = 'Bank is last seen data, not live; captured at ' .. tostring(bank.capturedAt) .. '.'
        end
        return {known=true,accessible=F.bankOpen,capturedAt=bank.capturedAt,items=bank.items}
    end
    warnings[#warnings+1] = 'Bank unknown; visit a banker to capture it.'
    return {known=false,accessible=F.bankOpen,items=F.Array()}
end
-- Forever's C_Traits signatures verified in installed ClassicUIForever/UI/TraitTree.lua
-- and PawnForever/Scales.lua. No static class trees or inferred point allocations.
function F.TraitTalents(warnings)
    local trees,unspent = F.Array(),nil
    local api = C_Traits or {}
    local configID = F.Call(C_ClassTalents and C_ClassTalents.GetActiveConfigID)
    local config = configID and F.Call(api.GetConfigInfo,configID)
    if type(config)~='table' or type(config.treeIDs)~='table' or #config.treeIDs==0 then
        warnings[#warnings+1]='Talent API unavailable/not ready: C_ClassTalents.GetActiveConfigID / C_Traits.GetConfigInfo; talents unknown.'
        return trees
    end
    for _,treeID in ipairs(config.treeIDs) do
        local displays=F.Call(api.GetGroupDisplayInfoByTreeID,treeID)
        local groups,ids={},{}
        local function unknown(reason)
            for _,entry in ipairs(trees) do if entry.treeId==treeID then entry.known=false end end
            warnings[#warnings+1]='Talent tree '..treeID..' incomplete: '..reason..'; missing values unknown.'
        end
        local function ungrouped()
            if not groups.unknown then
                groups.unknown={index=#trees+1,treeId=treeID,known=false,talents=F.Array()}
                trees[#trees+1]=groups.unknown
            end
            return groups.unknown
        end
        if type(displays)=='table' then
            table.sort(displays,function(a,b) return (a.orderIndex or 0)<(b.orderIndex or 0) end)
            for _,display in ipairs(displays) do
                local entry={index=#trees+1,treeId=treeID,groupId=display.groupID,name=display.displayName,known=true,talents=F.Array()}
                trees[#trees+1]=entry
                groups[display.groupID]=entry
                ids[#ids+1]=display.groupID
            end
        end
        if #ids==0 then ungrouped(); unknown('C_Traits.GetGroupDisplayInfoByTreeID unavailable/empty') end
        local currencies=F.Call(api.GetGroupCurrencyInfo,configID,ids)
        for _,group in ipairs(type(currencies)=='table' and currencies or {}) do
            local entry=groups[group.traitNodeGroupID]
            local currency=group.currencyInfos and group.currencyInfos[1]
            if entry and currency then entry.points=currency.spent end
        end
        for _,groupID in ipairs(ids) do
            if type(groups[groupID].points)~='number' then unknown('C_Traits.GetGroupCurrencyInfo unavailable/incomplete'); break end
        end
        local currency=F.Call(api.GetTreeCurrencyInfo,configID,treeID,false)
        if #config.treeIDs==1 and type(currency)=='table' and currency[1] then unspent=currency[1].quantity end
        local nodes=F.Call(api.GetTreeNodes,treeID)
        if type(nodes)~='table' then unknown('C_Traits.GetTreeNodes unavailable') end
        for _,nodeID in ipairs(type(nodes)=='table' and nodes or {}) do
            local node=F.Call(api.GetNodeInfo,configID,nodeID)
            local rank=type(node)=='table' and (node.ranksPurchased or node.activeRank or node.currentRank)
            if type(rank)~='number' then unknown('C_Traits.GetNodeInfo rank unavailable: '..nodeID) end
            if type(rank)=='number' and rank>0 then
                local group
                for _,groupID in ipairs(node.groupIDs or {}) do if groups[groupID] then group=groups[groupID]; break end end
                local entryID=node.activeEntry and node.activeEntry.entryID or (node.entryIDs and node.entryIDs[1])
                local entry=entryID and F.Call(api.GetEntryInfo,configID,entryID)
                local definition=entry and entry.definitionID and F.Call(api.GetDefinitionInfo,entry.definitionID)
                local spellID=definition and (definition.overriddenSpellID or definition.spellID)
                local name=definition and definition.overrideName or (spellID and F.Call(C_Spell and C_Spell.GetSpellName,spellID))
                if type(name)~='string' or name=='' then unknown('C_Traits definition/name unavailable: '..nodeID) end
                if not group then group=ungrouped(); unknown('C_Traits node group unavailable: '..nodeID) end
                group.talents[#group.talents+1]={nodeId=nodeID,entryId=entryID,spellId=spellID,
                    name=name,rank=rank,maxRank=node.maxRanks,posX=node.posX,posY=node.posY}
            end
        end
    end
    if F.Call(api.ConfigHasStagedChanges,configID) then
        for _,entry in ipairs(trees) do entry.known=false end
        warnings[#warnings+1]='Talent configuration has staged changes; exported ranks may be uncommitted, not a confirmed build.'
    end
    return trees,unspent
end
function F.Talents(warnings)
    local trees = F.Array()
    local tabs = F.Call(GetNumTalentTabs,false)
    if type(tabs)~='number' then return F.TraitTalents(warnings) end
    for tree=1,tabs do
        local a,b,c,_,e=F.Call(GetTalentTabInfo,tree)
        local name,points
        if type(a)=='number' then name,points=b,e else name,points=a,c end
        local entry={index=tree,name=name,points=points,talents=F.Array(),known=true}
        local count=F.Call(GetNumTalents,tree)
        if type(count)~='number' then entry.known=false; warnings[#warnings+1]='Talent tree read failed: '..tree end
        for index=1,count or 0 do
            local n,_,tier,column,rank,maxRank=F.Call(GetTalentInfo,tree,index)
            if not n or type(rank)~='number' then
                entry.known=false
                warnings[#warnings+1]='Talent entry unavailable: tree '..tree..', index '..index..'.'
            end
            if type(rank)=='number' and rank>0 then
                entry.talents[#entry.talents+1]={name=n,rank=rank,maxRank=maxRank,tier=tier,column=column}
            end
        end
        trees[#trees+1]=entry
    end
    return trees
end
function F.Stats()
    local stats={}
    for i,name in ipairs({'strength','agility','stamina','intellect','spirit'}) do
        local base,effective,positive,negative=F.Call(UnitStat,'player',i)
        if base~=nil then stats[name]={base=base,effective=effective,positive=positive,negative=negative} end
    end
    local base,effective,armor,positive,negative=F.Call(UnitArmor,'player')
    if base~=nil then stats.armor={base=base,effective=effective,armor=armor,positive=positive,negative=negative} end
    for key,fn in pairs({healthMax=UnitHealthMax or false,powerMax=UnitPowerMax or false}) do
        stats[key]=F.Call(fn,'player')
    end
    local powerId,powerToken=F.Call(UnitPowerType,'player')
    if powerId~=nil then stats.powerType={id=powerId,token=powerToken} end
    for key,fn in pairs({meleeCritPercent=GetCritChance or false,rangedCritPercent=GetRangedCritChance or false,
        dodgePercent=GetDodgeChance or false,parryPercent=GetParryChance or false,blockPercent=GetBlockChance or false}) do
        stats[key]=F.Call(fn)
    end
    local ap,pos,neg=F.Call(UnitAttackPower,'player')
    if ap~=nil then stats.attackPower={base=ap,positive=pos,negative=neg} end
    local rap,rpos,rneg=F.Call(UnitRangedAttackPower,'player')
    if rap~=nil then stats.rangedAttackPower={base=rap,positive=rpos,negative=rneg} end
    local mn,mx,omn,omx,dp,dn,pct=F.Call(UnitDamage,'player')
    if mn~=nil then stats.damage={mainMin=mn,mainMax=mx,offMin=omn,offMax=omx,positive=dp,negative=dn,multiplier=pct} end
    local main,off=F.Call(UnitAttackSpeed,'player')
    if main~=nil then stats.attackSpeed={main=main,off=off} end
    stats.healingBonus=F.Call(GetSpellBonusHealing)
    local schools,resistances=F.Array(),F.Array()
    for id,name in ipairs({'Physical','Holy','Fire','Nature','Frost','Shadow','Arcane'}) do
        local bonus,crit=F.Call(GetSpellBonusDamage,id),F.Call(GetSpellCritChance,id)
        if bonus~=nil or crit~=nil then schools[#schools+1]={id=id,name=name,damageBonus=bonus,critPercent=crit} end
        local rb,re,rp,rn=F.Call(UnitResistance,'player',id-1)
        if rb~=nil then resistances[#resistances+1]={id=id-1,name=name,base=rb,effective=re,positive=rp,negative=rn} end
    end
    if #schools>0 then stats.spellSchools=schools end
    if #resistances>0 then stats.resistances=resistances end
    local speed,rmin,rmax,positiveR,negativeR,mult=F.Call(UnitRangedDamage,'player')
    if speed~=nil then stats.rangedDamage={speed=speed,min=rmin,max=rmax,positive=positiveR,negative=negativeR,multiplier=mult} end
    local defense,mod=F.Call(UnitDefense,'player')
    if defense~=nil then stats.defense={base=defense,modifier=mod} end
    local regen,casting=F.Call(GetManaRegen)
    if regen~=nil then stats.manaRegen={normal=regen,casting=casting} end
    local ratings={}
    for key,constant in pairs({meleeHit='CR_HIT_MELEE',rangedHit='CR_HIT_RANGED',spellHit='CR_HIT_SPELL',
        meleeCrit='CR_CRIT_MELEE',rangedCrit='CR_CRIT_RANGED',spellCrit='CR_CRIT_SPELL',
        meleeHaste='CR_HASTE_MELEE',rangedHaste='CR_HASTE_RANGED',spellHaste='CR_HASTE_SPELL',
        defense='CR_DEFENSE_SKILL',dodge='CR_DODGE',parry='CR_PARRY',block='CR_BLOCK',expertise='CR_EXPERTISE'}) do
        local id=_G[constant]
        if type(id)=='number' then
            local value,bonus=F.Call(GetCombatRating,id),F.Call(GetCombatRatingBonus,id)
            if value~=nil or bonus~=nil then ratings[key]={rating=value,bonus=bonus} end
        end
    end
    if next(ratings) then stats.combatRatings=ratings end
    return stats
end
function F.Professions(warnings)
    local entries=F.Array()
    if type(GetProfessions)~='function' or type(GetProfessionInfo)~='function' then
        warnings[#warnings+1]='Profession APIs unavailable; professions unknown.'
        return entries,false
    end
    local result={pcall(GetProfessions)}
    if not result[1] then
        warnings[#warnings+1]='GetProfessions failed; professions unknown.'
        return entries,false
    end
    local known=true
    local seenIndices,seenIDs={},{}
    local function integer(value,minimum)
        if type(value)=='number' and value==value and value~=math.huge and value~=-math.huge
            and value%1==0 and value>=-2147483647 and value<=2147483647
            and (minimum==nil or value>=minimum) then return value end
    end
    -- Installed ClassicUIForever/Skills/ProfessionsBook.lua verifies five sparse
    -- slots (two primary, then secondary) and skillLine/rankModifier at 7/8.
    for slot=1,5 do
        local raw=result[slot+1]
        local index=F.Plain(raw)
        if issecretvalue and issecretvalue(raw) then
            known=false
            warnings[#warnings+1]='Profession index restricted; professions unknown.'
        elseif index~=nil and not integer(index,1) then
            known=false
            warnings[#warnings+1]='Profession index invalid; professions unknown.'
        elseif index~=nil and not seenIndices[index] then
            seenIndices[index]=true
            local name,_,rank,cap,_,_,id,modifier=F.Call(GetProfessionInfo,index)
            if type(name)=='string' then
                -- Match Python str.isspace() via exact UTF-8 sequences, only for
                -- the blank check; preserve all bytes of nonblank localized names.
                local nonWhitespace=name:gsub('[\009-\013\028-\032]','')
                    :gsub('\194[\133\160]',''):gsub('\225\154\128','')
                    :gsub('\226\128[\128-\138\168\169\175]','')
                    :gsub('\226\129\159',''):gsub('\227\128\128','')
                if nonWhitespace=='' then name=nil end
            else name=nil end
            rank,cap,id=integer(rank,0),integer(cap,1),integer(id,1)
            -- A contradictory API pair must not invalidate the whole gear export.
            if rank and cap and rank>cap then rank=nil end
            modifier=integer(modifier)
            local skillInfo=id and F.Call(C_SkillInfo and C_SkillInfo.GetSkillLineInfoByID,id)
            if type(skillInfo)=='table' then
                modifier=integer(F.Plain(skillInfo.modifier)) or modifier
            end
            local entry={name=name,category=slot<=2 and 'primary' or 'secondary',
                skillLineId=id,skillLevel=rank,maxSkillLevel=cap,skillModifier=modifier}
            entry.known=name~=nil and id~=nil and rank~=nil and cap~=nil and rank<=cap
            if not entry.known then
                known=false
                warnings[#warnings+1]='Profession entry incomplete; missing/invalid values unknown.'
            end
            if not id or not seenIDs[id] then
                entries[#entries+1]=entry
                if id then seenIDs[id]=true end
            end
        end
    end
    return entries,known
end
local function collect()
    F.secretOmissions=false
    local _, class, classId = F.Call(UnitClass, 'player')
    local version, build, _, interface = F.Call(GetBuildInfo)
    local snapshot = {
        schemaVersion=1, addonVersion=F.version, capturedAt=F.Call(time),
        character={guid=F.Call(UnitGUID,'player'), name=F.Call(UnitName,'player'), realm=F.Call(GetRealmName),
            class=class, classId=classId or class, race=F.Call(UnitRace,'player'), faction=F.Call(UnitFactionGroup,'player'),
            level=F.Call(UnitLevel,'player'), locale=F.Call(GetLocale), zone=F.Call(GetZoneText), goldCopper=F.Call(GetMoney)},
        client={version=version,build=build,interfaceVersion=interface},
        equipment=F.Array(), bags=F.Array(), talents=F.Array(), stats={}, warnings=F.Array(),
        bank={known=false, accessible=false, items=F.Array()}
    }
    snapshot.character.realm = snapshot.character.realm or ''
    snapshot.character.realmKnown = snapshot.character.realm ~= ''
    if not snapshot.character.realmKnown then
        snapshot.warnings[#snapshot.warnings+1]='Realm hidden/unavailable; realm unknown, identity uses player GUID.'
    end
    F.Inventory(snapshot,'equipment',F.Equipment(snapshot.warnings))
    F.Inventory(snapshot,'bags',F.Containers(F.ContainerIDs(false),snapshot.warnings))
    snapshot.bank = F.Bank(snapshot.character.guid,snapshot.warnings,snapshot.capturedAt)
    snapshot.talents,snapshot.unspentTalentPoints = F.Talents(snapshot.warnings)
    snapshot.unspentTalentPoints = snapshot.unspentTalentPoints or F.Call(GetUnspentTalentPoints)
    snapshot.professions,snapshot.professionsKnown = F.Professions(snapshot.warnings)
    snapshot.professionsCapturedAt = snapshot.capturedAt
    snapshot.stats = F.Stats()
    if not next(snapshot.stats) then snapshot.warnings[#snapshot.warnings+1]='Character stats API unavailable; missing values are unknown, not zero.' end
    local json=F.JSON(snapshot)
    if F.secretOmissions then
        snapshot.warnings[#snapshot.warnings+1]='Game-restricted values omitted or exported as null; unavailable is not zero.'
        json=F.JSON(snapshot)
    end
    F.last = snapshot
    if snapshot.character.guid then F.CharacterCache(snapshot.character.guid).latestSnapshot=snapshot end
    ForeverContextExport = json
    return snapshot
end
function F.Capture()
    if F.capturing then return F.last end
    F.capturing=true
    F.waiting={}
    local ok,result=pcall(collect)
    F.capturing=false
    if not ok then
        -- Automatic captures and export are silent; explicit /fctx status reads this.
        F.lastError=tostring(result)
        return F.last
    end
    F.lastError=nil
    return result
end
function F.Schedule()
    if F.scheduled or F.capturing then return end
    F.scheduled=true
    local function run()
        F.scheduled=false
        F.Capture()
    end
    if C_Timer and C_Timer.After then C_Timer.After(0.35,run)
    else
        local elapsed=0
        F.events:SetScript('OnUpdate',function(self,delta)
            elapsed=elapsed+delta
            if elapsed>=0.35 then self:SetScript('OnUpdate',nil); run() end
        end)
    end
end
F.events=CreateFrame('Frame')
F.itemEvents={}
F.events:SetScript('OnEvent',function(self,event,arg1,arg2)
    if event=='BANKFRAME_OPENED' then F.bankOpen=true
    elseif event=='BANKFRAME_CLOSED' then F.bankOpen=false
    elseif event=='GET_ITEM_INFO_RECEIVED' then
        if F.capturing or not arg2 or not (F.waiting and F.waiting[arg1]) then return end
        local now=F.Call(GetTime) or F.Call(time) or 0
        if F.itemEvents[arg1] and now-F.itemEvents[arg1]<5 then return end
        F.itemEvents[arg1]=now
    elseif event:match('^UNIT_') and arg1~='player' then return end
    F.Schedule()
end)
for _,event in ipairs({'PLAYER_LOGIN','PLAYER_ENTERING_WORLD','PLAYER_EQUIPMENT_CHANGED','BAG_UPDATE','BAG_UPDATE_DELAYED',
    'SKILL_LINES_CHANGED','CHARACTER_POINTS_CHANGED','PLAYER_TALENT_UPDATE','TRAIT_CONFIG_UPDATED','TRAIT_NODE_CHANGED',
    'TRAIT_TREE_CURRENCY_INFO_UPDATED','ACTIVE_COMBAT_CONFIG_CHANGED','UNIT_STATS','UNIT_AURA','UNIT_LEVEL','UNIT_INVENTORY_CHANGED',
    'PLAYER_MONEY','ZONE_CHANGED_NEW_AREA','BANKFRAME_OPENED','BANKFRAME_CLOSED','PLAYERBANKSLOTS_CHANGED','GET_ITEM_INFO_RECEIVED'}) do
    -- Some Classic/Forever builds omit events. Unsupported registration must not prevent loading.
    pcall(F.events.RegisterEvent,F.events,event)
end
