"""Execute the real addon in Lua 5.1; mocked WoW APIs live only here."""
import json
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'addon' / 'ForeverContext'

MOCK = r'''
_G = _G or _ENV
NOW=1700000000
function time() return NOW end
function GetTime() return NOW end
function UnitGUID() return GUID or 'Player-1' end
function UnitName() return 'Tést"Hero' end
function GetRealmName() return 'Realm' end
function UnitClass() return 'Warrior','WARRIOR',1 end
function UnitRace() return 'Human' end
function UnitFactionGroup() return 'Alliance' end
function UnitLevel() return 25 end
function GetLocale() return 'enUS' end
function GetZoneText() return 'Stormwind' end
function GetMoney() return 12345 end
function GetBuildInfo() return '1.16.0','60000','date',16001 end
messages={}; DEFAULT_CHAT_FRAME={AddMessage=function(self,s) table.insert(messages,s) end}
SlashCmdList={}; UISpecialFrames={}; frames={}; timers={}
C_Timer={After=function(delay,fn) table.insert(timers,fn) end}
function RunTimers() local old=timers;timers={};for _,fn in ipairs(old) do fn() end end
function CreateFrame(kind,name,parent,template)
 local f={scripts={},events={},shown=false,text='',name=name,kind=kind,children={}}
 if name then _G[name]=f end
 function f:SetScript(k,v) self.scripts[k]=v end
 function f:HookScript(k,v) self.scripts[k]=v end
 function f:RegisterEvent(e) self.events[e]=true end
 function f:Show() self.shown=true end
 function f:Hide() self.shown=false end
 function f:IsShown() return self.shown end
 function f:SetText(s) self.text=s; if self.scripts.OnTextChanged then self.scripts.OnTextChanged(self,false) end end
 function f:GetText() return self.text end
 function f:HighlightText() self.highlight=true end
 function f:SetFocus() self.focus=true end
 function f:ClearFocus() self.focus=false end
 function f:SetScrollChild(c) self.child=c end
 function f:CreateFontString() return CreateFrame('FontString') end
 function f:GetWidth() return 660 end
 function f:GetVerticalScroll() return 0 end
 function f:GetVerticalScrollRange() return 500 end
 function f:SetHyperlink(link)
   self.lastLink=link; self.lines=FALLBACK_LINES or {}; self.cleared=false
   for i,line in ipairs(self.lines) do
     _G[name..'TextLeft'..i]={GetText=function() return line.left end}
     _G[name..'TextRight'..i]={GetText=function() return line.right end,IsShown=function() return not line.rightHidden end}
   end
 end
 function f:ClearLines() self.lines={}; self.cleared=true end
 function f:NumLines() return #(self.lines or {}) end
 setmetatable(f,{__index=function(t,k) return function() end end})
 table.insert(frames,f);return f
end
UIParent={}
C_Container={GetContainerNumSlots=function(bag) return 0 end,GetContainerItemInfo=function() end}
function GetInventoryItemLink() end
function GetInventoryItemID() end
function GetInventoryItemCount() return 1 end
function GetInventorySlotInfo(name) return 1 end
C_Item={GetItemInfo=function() end,GetItemStats=function() end}
'''


class AddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        for path in ('Core.lua', 'UI.lua'):
            source = ADDON / path
            if source.exists():
                self.lua.execute(source.read_text(encoding='utf-8'), name=path)

    def do(self, code):
        return self.lua.execute(code)

    def snapshot(self):
        self.do('ForeverContext.Capture()')
        return json.loads(self.lua.globals().ForeverContextExport)

    def test_copy_json_has_no_renderable_pipes_and_roundtrips_item_string(self):
        self.do(r'''
LINK='|cff0070dd|Hitem:123:456:0:0:0:0:-77:888:25|h[Blade]|h|r'
function GetInventoryItemLink(unit,slot) if slot==16 then return LINK end end
''')
        self.do("SlashCmdList.FOREVERCONTEXT('export')")
        raw = self.do('return ForeverContext.edit:GetText()')
        self.assertNotIn('|', raw)
        self.assertIn(r'\u007cHitem:', raw)
        item = json.loads(raw)['equipment'][0]
        self.assertEqual(item['link'], self.lua.globals().LINK)
        self.assertEqual(item['itemString'], 'item:123:456:0:0:0:0:-77:888:25')
        self.do("GetInventoryItemLink=function(unit,slot) if slot==16 then return '[Blade]' end end")
        item = self.snapshot()['equipment'][0]
        self.assertNotIn('itemString', item)
        self.assertEqual(item['link'], '[Blade]')

    def test_hidden_realm_is_explicit_unknown_without_guessing(self):
        for result in ("''", 'nil'):
            self.do('GetRealmName=function() return ' + result + ' end')
            data = self.snapshot()
            self.assertEqual(data['character']['realm'], '')
            self.assertFalse(data['character']['realmKnown'])
            self.assertTrue(any('realm' in w.lower() and 'unknown' in w.lower() for w in data['warnings']))
        self.do("GetRealmName=function() return 'Realm' end")
        self.assertTrue(self.snapshot()['character']['realmKnown'])

    def setup_trait_api(self):
        self.do(r'''
C_ClassTalents={GetActiveConfigID=function() return 42 end}
C_Traits={
 GetConfigInfo=function(id) assert(id==42); return {treeIDs={90}} end,
 GetGroupDisplayInfoByTreeID=function(id) assert(id==90); return {
  {groupID=8,displayName='Ret',orderIndex=2},{groupID=7,displayName='Prot',orderIndex=1}} end,
 GetGroupCurrencyInfo=function(cfg,ids) assert(cfg==42); return {
  {traitNodeGroupID=7,currencyInfos={{spent=3}}},{traitNodeGroupID=8,currencyInfos={{spent=0}}}} end,
 GetTreeCurrencyInfo=function(cfg,tree,exclude) assert(cfg==42 and tree==90 and exclude==false); return {{quantity=2}} end,
 GetTreeNodes=function(tree) assert(tree==90); return {101,102} end,
 GetNodeInfo=function(cfg,node) assert(cfg==42); return {ranksPurchased=node==101 and 3 or 0,
  maxRanks=5,activeEntry={entryID=node+100},groupIDs={node==101 and 7 or 8},posX=1200,posY=600} end,
 GetEntryInfo=function(cfg,entry) assert(cfg==42); return {definitionID=entry+100} end,
 GetDefinitionInfo=function(def) return {spellID=def+100} end
}
C_Spell={GetSpellName=function(id) assert(id==401); return 'Observed talent' end}
''')

    def test_forever_trait_api_reads_actual_groups_nodes_and_currency(self):
        self.setup_trait_api()
        data = self.snapshot()
        self.assertEqual([t['name'] for t in data['talents']], ['Prot','Ret'])
        first = data['talents'][0]
        self.assertEqual((first['treeId'],first['groupId'],first['points']), (90,7,3))
        self.assertTrue(first['known'])
        self.assertEqual(first['talents'][0], {'nodeId':101,'entryId':201,'spellId':401,
                         'name':'Observed talent','rank':3,'maxRank':5,'posX':1200,'posY':600})
        self.assertEqual(data['talents'][1]['talents'], [])
        self.assertEqual(data['unspentTalentPoints'], 2)
        self.assertFalse(any('talents unknown' in w.lower() for w in data['warnings']))

    def test_trait_read_failures_are_unknown_not_zero_or_silently_empty(self):
        cases = [
            ('C_Traits.GetTreeNodes=nil', 'GetTreeNodes'),
            ("C_Traits.GetNodeInfo=function() error('unavailable') end", 'GetNodeInfo'),
            ('C_Traits.GetGroupCurrencyInfo=nil', 'GetGroupCurrencyInfo'),
            ('C_Spell.GetSpellName=nil', 'definition/name'),
            ('C_Traits.GetGroupDisplayInfoByTreeID=nil', 'GetGroupDisplayInfoByTreeID'),
        ]
        for change, diagnostic in cases:
            with self.subTest(change=change):
                self.setup_trait_api()
                self.do(change)
                data = self.snapshot()
                self.assertTrue(data['talents'])
                self.assertTrue(any(not t['known'] for t in data['talents']))
                self.assertTrue(any(diagnostic in w for w in data['warnings']))
                if 'Currency' in change:
                    self.assertTrue(all('points' not in t for t in data['talents']))
                if 'Display' in change or 'SpellName' in change:
                    learned = [n for t in data['talents'] for n in t['talents']]
                    self.assertEqual(learned[0]['rank'], 3)
                    self.assertEqual(learned[0]['nodeId'], 101)

    def test_trait_events_refresh_silently_and_version_matches_toc(self):
        version = self.do('return ForeverContext.version')
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertIn('## Version: ' + version, (ADDON/'ForeverContext.toc').read_text())
        for event in ('TRAIT_CONFIG_UPDATED','TRAIT_NODE_CHANGED','TRAIT_TREE_CURRENCY_INFO_UPDATED','ACTIVE_COMBAT_CONFIG_CHANGED'):
            self.assertTrue(self.lua.globals().ForeverContext.events.events[event])
        self.do("local f=ForeverContext.events; f.scripts.OnEvent(f,'TRAIT_CONFIG_UPDATED',42); RunTimers()")
        self.assertIsNotNone(self.lua.globals().ForeverContextExport)
        self.assertEqual(list(self.lua.globals().messages.values()), [])

    def test_trait_staged_changes_are_not_claimed_as_confirmed_build(self):
        self.setup_trait_api()
        self.do('C_Traits.ConfigHasStagedChanges=function(cfg) assert(cfg==42); return true end')
        data = self.snapshot()
        self.assertTrue(any('staged' in w.lower() for w in data['warnings']))
        self.assertTrue(all(not tree['known'] for tree in data['talents']))

    def test_root_json_unicode_escaping_and_empty_arrays(self):
        data = self.snapshot()
        self.assertEqual(data['schemaVersion'], 1)
        self.assertEqual(data['character']['name'], 'Tést"Hero')
        self.assertEqual(data['character']['classId'], 1)
        self.assertEqual(data['client']['interfaceVersion'], 16001)
        for key in ('equipment', 'bags', 'talents', 'warnings'):
            self.assertIsInstance(data[key], list)
        self.assertFalse(data['bank']['known'])
        self.assertEqual(data['bank']['items'], [])
        self.assertNotIn('capturedAt', data['bank'])
        self.assertEqual(self.do('return ForeverContext.JSON({s="a\\n\\t\\r\\b\\f\\\\\\\""})'), '{"s":"a\\n\\t\\r\\b\\f\\\\\\\""}')

    def test_items_preserve_links_uncached_slots_and_full_tooltips(self):
        self.do(r'''
LINK='|cff0070dd|Hitem:123:456:0:0:0:0:-77:888:25|h[Blade]|h|r'
function GetInventoryItemLink(unit,slot) if slot==16 then return LINK end end
function GetInventoryItemID(unit,slot) if slot==16 then return 123 end end
C_Container.GetContainerNumSlots=function(bag) if bag==0 then return 2 else return 0 end end
C_Container.GetContainerItemInfo=function(bag,slot)
 if slot==1 then return {itemID=999,stackCount=3,quality=2} end
 if slot==2 then return {itemID=123,hyperlink=LINK,stackCount=1} end
end
C_Item.GetItemInfo=function(link)
 if link==LINK then return 'Blade',LINK,3,30,20,'Weapon','Sword',1,'INVTYPE_WEAPON' end
end
C_Item.GetItemStats=function(link) if link==LINK then return {ITEM_MOD_STRENGTH_SHORT=5} end end
C_TooltipInfo={GetHyperlink=function(link)
 return {lines={{leftText='|cff00ff00Blade|r',rightText='|Ticon:12|tOne-Hand'},
 {leftText='|Hspell:1|hEquip: real effect|h'}, {leftText='Damage 10–20'}, {rightText='Speed 2.0'}}}
end}
''')
        data = self.snapshot()
        weapon = data['equipment'][0]
        self.assertEqual(weapon['slot'], 16)
        self.assertEqual(weapon['slotName'], 'MainHandSlot')
        self.assertEqual(weapon['link'], self.lua.globals().LINK)
        self.assertEqual(weapon['requiredLevel'], 20)
        self.assertEqual(weapon['stats']['ITEM_MOD_STRENGTH_SHORT'], 5)
        self.assertEqual(weapon['tooltip'], [
            {'left': 'Blade', 'right': 'One-Hand'}, {'left': 'Equip: real effect'},
            {'left': 'Damage 10–20'}, {'right': 'Speed 2.0'}])
        self.assertEqual(len(data['bags']), 2)
        unknown = data['bags'][0]
        self.assertEqual((unknown['itemId'], unknown['count']), (999, 3))
        self.assertTrue(unknown['pending'])
        self.assertEqual(unknown['tooltip'], [])
        self.assertTrue(any('999' in w for w in data['warnings']))
        self.assertEqual(data['bags'][1]['link'], weapon['link'])

    def test_tooltip_fallback_is_private_cleared_and_not_cross_contaminated(self):
        self.do(r'''
C_TooltipInfo={GetHyperlink=function() error('not supported') end}
FALLBACK_LINES={{left='|cffffffffFirst|r',right='Right'},{left='Equip: Bonus'}}
''')
        lines = json.loads(self.do("return ForeverContext.JSON(ForeverContext.Tooltip('item:1'))"))
        self.assertEqual(lines, [{'left':'First','right':'Right'}, {'left':'Equip: Bonus'}])
        self.do('FALLBACK_LINES={}')
        self.assertEqual(self.do("return ForeverContext.JSON(ForeverContext.Tooltip('item:2'))"), '[]')
        self.assertEqual(self.do('return ForeverContextTooltip.cleared'), True)
        self.assertFalse(self.do('return ForeverContextTooltip:IsShown()'))
        self.assertIsNone(self.lua.globals().GameTooltip)
        self.do('FALLBACK_LINES={{left="stale"}}')
        self.assertEqual(self.do('return ForeverContext.JSON(ForeverContext.Tooltip(nil))'), '[]')

    def test_bank_cache_guid_isolation_closed_staleness_and_failed_reads(self):
        first = self.snapshot()
        self.assertFalse(first['bank']['known'])
        self.do('ForeverContext.bankOpen=true')
        seen = self.snapshot()
        self.assertTrue(seen['bank']['known'])
        self.assertTrue(seen['bank']['accessible'])
        self.assertEqual(seen['bank']['items'], [])
        self.do(r'''
C_Container.GetContainerNumSlots=function(bag) if bag==-1 then return 1 else return 0 end end
C_Container.GetContainerItemInfo=function() return {itemID=321,hyperlink='item:321',stackCount=2} end
''')
        filled = self.snapshot()
        self.assertEqual(filled['bank']['items'][0]['itemId'], 321)
        self.do("NOW=NOW+60; ForeverContext.bankOpen=false; C_Container.GetContainerNumSlots=function() error('closed bank must never be queried') end")
        stale = self.snapshot()
        self.assertTrue(stale['bank']['known'])
        self.assertFalse(stale['bank']['accessible'])
        self.assertEqual(stale['bank']['capturedAt'], filled['bank']['capturedAt'])
        self.assertTrue(any('last seen' in w.lower() for w in stale['warnings']))
        self.do("GUID='Player-2'")
        self.assertFalse(self.snapshot()['bank']['known'])
        self.do("GUID='Player-1'; ForeverContext.bankOpen=true")
        failed = self.snapshot()
        self.assertEqual(failed['bank']['capturedAt'], filled['bank']['capturedAt'])
        self.assertEqual(failed['bank']['items'][0]['itemId'], 321)
        self.assertTrue(any('failed' in w.lower() for w in failed['warnings']))
        self.do("C_Container.GetContainerNumSlots=function(b) if b==-1 then return 1 else return 0 end end; C_Container.GetContainerItemInfo=function() error('slot failure') end")
        self.assertEqual(self.snapshot()['bank']['capturedAt'], filled['bank']['capturedAt'])
        self.do("GUID=nil; UnitGUID=function() return nil end; ForeverContext.bankOpen=false")
        self.assertFalse(self.snapshot()['bank']['known'])

    def test_talents_stats_real_zero_and_missing_api_omission(self):
        self.do(r'''
function GetNumTalentTabs() return 2 end
function GetTalentTabInfo(i) return i==1 and 'Arms' or 'Fury','icon',i==1 and 3 or 0 end
function GetNumTalents() return 2 end
function GetTalentInfo(tree,index)
 return index==1 and 'Deflection' or 'Unlearned','icon',1,2,(tree==1 and index==1) and 3 or 0,5
end
function GetUnspentTalentPoints() return 1 end
function UnitStat(unit,index) return 10,20,12,-2 end
function UnitArmor() return 100,110,110,10,0 end
function UnitHealthMax() return 200 end
function UnitPowerMax() return 100 end
function UnitPowerType() return 1,'RAGE' end
function GetCritChance() return 0 end
function GetDodgeChance() return 5 end
function GetSpellCritChance() error('unavailable') end
function UnitAttackPower() return 50,5,-1 end
function UnitDamage() return 10,20,1,2,3,-1,1.1 end
function UnitAttackSpeed() return 2.5,1.8 end
''')
        data = self.snapshot()
        self.assertEqual(data['talents'][0]['name'], 'Arms')
        self.assertEqual(data['talents'][0]['points'], 3)
        self.assertEqual(data['talents'][0]['talents'], [{'name':'Deflection','rank':3,'maxRank':5,'tier':1,'column':2}])
        self.assertEqual(data['talents'][1]['talents'], [])
        self.assertEqual(data['unspentTalentPoints'], 1)
        stats = data['stats']
        self.assertEqual(stats['strength']['effective'], 20)
        self.assertEqual(stats['armor']['effective'], 110)
        self.assertEqual(stats['meleeCritPercent'], 0)
        self.assertEqual(stats['healthMax'], 200)
        self.assertEqual(stats['attackPower']['base'], 50)
        self.assertEqual(stats['damage']['mainMax'], 20)
        self.assertNotIn('parryPercent', stats)
        self.assertNotIn('spellCritPercent', stats)
        self.do("GetTalentTabInfo=function(i) return i,'ModernTree','description','icon',7 end")
        modern = self.snapshot()['talents'][0]
        self.assertEqual((modern['name'], modern['points']), ('ModernTree',7))
        self.do('GetNumTalentTabs=nil; UnitStat=nil')
        missing = self.snapshot()
        self.assertEqual(missing['talents'], [])
        self.assertNotIn('strength', missing['stats'])
        self.assertTrue(any('talent' in w.lower() for w in missing['warnings']))

    def test_slash_commands_copy_window_status_save_and_toc(self):
        self.assertEqual(self.lua.globals().SLASH_FOREVERCONTEXT1, '/fctx')
        self.do("SlashCmdList.FOREVERCONTEXT('')")
        self.assertTrue(self.do('return ForeverContext.window:IsShown()'))
        self.assertEqual(self.do('return ForeverContext.edit:GetText()'), self.lua.globals().ForeverContextExport)
        self.assertTrue(self.do('return ForeverContext.edit.highlight'))
        self.assertTrue(self.do('return ForeverContext.edit.focus'))
        self.assertIn('ForeverContextWindow', list(self.lua.globals().UISpecialFrames.values()))
        self.do("ForeverContext.edit.scripts.OnEscapePressed(ForeverContext.edit)")
        self.assertFalse(self.do('return ForeverContext.window:IsShown()'))
        self.do("NOW=NOW+1; SlashCmdList.FOREVERCONTEXT('save'); SlashCmdList.FOREVERCONTEXT('status'); SlashCmdList.FOREVERCONTEXT('help')")
        text = '\n'.join(self.lua.globals().messages.values())
        self.assertIn('/reload', text)
        self.assertIn('memory', text.lower())
        self.assertIn('bank', text.lower())
        self.assertIn('missing', text.lower())
        self.assertEqual(json.loads(self.lua.globals().ForeverContextExport)['capturedAt'],1700000001)
        toc = (ADDON/'ForeverContext.toc').read_text()
        self.assertIn('## Interface: 16001', toc)
        self.assertIn('## SavedVariables: ForeverContextExport, ForeverContextDB', toc)
        self.assertLess(toc.index('Core.lua'), toc.index('UI.lua'))

    def test_events_debounce_filter_bank_close_and_item_recursion(self):
        self.assertIsNotNone(self.lua.globals().ForeverContext.events)
        self.do(r'''
function Fire(event,...) local f=ForeverContext.events; f.scripts.OnEvent(f,event,...) end
captures=0; local real=ForeverContext.Capture
ForeverContext.Capture=function() captures=captures+1; return real() end
Fire('PLAYER_LOGIN'); Fire('BAG_UPDATE',0); Fire('PLAYER_EQUIPMENT_CHANGED',16)
''')
        self.assertEqual(self.do('return #timers'), 1)
        self.assertEqual(self.do('return captures'), 0)
        self.do('RunTimers()')
        self.assertEqual(self.do('return captures'), 1)
        self.do("Fire('UNIT_STATS','target'); Fire('GET_ITEM_INFO_RECEIVED',123,true)")
        self.assertEqual(self.do('return #timers'), 0)
        self.do("Fire('BANKFRAME_OPENED'); RunTimers()")
        self.assertTrue(json.loads(self.lua.globals().ForeverContextExport)['bank']['accessible'])
        self.do("Fire('BANKFRAME_CLOSED'); RunTimers()")
        self.assertFalse(json.loads(self.lua.globals().ForeverContextExport)['bank']['accessible'])
        self.do(r'''
function GetInventoryItemID(unit,slot) if slot==1 then return 999 end end
C_Item.GetItemInfo=function() Fire('GET_ITEM_INFO_RECEIVED',999,true) end
Fire('PLAYER_EQUIPMENT_CHANGED'); RunTimers()
''')
        self.assertEqual(self.do('return #timers'), 0)
        self.do("Fire('GET_ITEM_INFO_RECEIVED',999,true); RunTimers(); Fire('GET_ITEM_INFO_RECEIVED',999,true)")
        self.assertEqual(self.do('return #timers'), 0)
        self.do("C_Timer=nil; NOW=NOW+1; Fire('BAG_UPDATE'); ForeverContext.events.scripts.OnUpdate(ForeverContext.events,0.5)")
        self.assertIsNone(self.do('return ForeverContext.events.scripts.OnUpdate'))

    def test_forever_enum_bank_tabs_reagent_bag_and_no_account_bank(self):
        self.do(r'''
Enum={BagIndex={ReagentBag=5,Keyring=-2,CharacterBankTab_1=100,CharacterBankTab_2=101,AccountBankTab_1=200}}
queried={}
C_Container.GetContainerNumSlots=function(bag)
 queried[bag]=(queried[bag] or 0)+1
 if bag==5 or bag==-2 or bag==100 then return 1 else return 0 end
end
C_Container.GetContainerItemInfo=function(bag,slot)
 return {itemID=bag+1000,hyperlink='item:'..(bag+1000),stackCount=1}
end
ForeverContext.bankOpen=true
''')
        data = self.snapshot()
        self.assertEqual({i['bag'] for i in data['bags']}, {5,-2})
        self.assertEqual([i['bag'] for i in data['bank']['items']], [100])
        self.assertIsNone(self.do('return queried[200]'))
        self.assertIsNone(self.do('return queried[-1]'))
        self.assertEqual(self.do('return queried[5]'), 1)
        self.do('ForeverContext.bankOpen=false; queried={}')
        self.snapshot()
        self.assertIsNone(self.do('return queried[100]'))

    def test_forever_keyring_size_retains_occupied_slot_and_failed_reads_are_unknown(self):
        self.do(r'''
Enum={BagIndex={Keyring=-2}}
function GetKeyRingSize() return 1 end
C_Container.GetContainerNumSlots=function() return 0 end
C_Container.GetContainerItemInfo=function(bag,slot)
 if bag==-2 and slot==1 then return {itemID=88,hyperlink='item:88',stackCount=1} end
end
''')
        good = self.snapshot()
        self.assertTrue(good['bagsKnown'])
        self.assertEqual([(i['bag'], i['slot'], i['itemId']) for i in good['bags']], [(-2, 1, 88)])
        for failure in ('return nil', "error('keyring unavailable')"):
            with self.subTest(failure=failure):
                self.do("GUID='Player-1'; NOW=NOW+1; GetKeyRingSize=function() " + failure + ' end')
                failed = self.snapshot()
                self.assertFalse(failed['bagsKnown'])
                self.assertEqual(failed['bags'], good['bags'])
                self.assertEqual(failed['bagsCapturedAt'], good['bagsCapturedAt'])
                self.do("GUID='Player-2'")
                unknown = self.snapshot()
                self.assertFalse(unknown['bagsKnown'])
                self.assertEqual(unknown['bags'], [])
                self.assertNotIn('bagsCapturedAt', unknown)

    def test_hidden_tooltip_right_text_is_not_exported_as_stale_content(self):
        self.do("FALLBACK_LINES={{left='Second item',right='stale right',rightHidden=true}}")
        self.assertEqual(json.loads(self.do("return ForeverContext.JSON(ForeverContext.Tooltip('item:2'))")), [{'left':'Second item'}])

    def test_spell_schools_resistances_ranged_defense_and_ratings(self):
        self.do(r'''
function GetSpellBonusDamage(school) return school*10 end
function GetSpellCritChance(school) return school+0.5 end
function GetSpellBonusHealing() return 40 end
function UnitResistance(unit,school) return school,school+1,2,-1 end
function UnitRangedDamage() return 2,11,22,3,-1,1.1 end
function UnitDefense() return 120,5 end
CR_HIT_MELEE=6
function GetCombatRating(id) return 12 end
function GetCombatRatingBonus(id) return 1.2 end
''')
        stats = self.snapshot()['stats']
        self.assertEqual(stats['spellSchools'][1], {'id':2,'name':'Holy','damageBonus':20,'critPercent':2.5})
        self.assertEqual(stats['healingBonus'], 40)
        self.assertEqual(stats['resistances'][0]['base'], 0)
        self.assertEqual(stats['resistances'][6]['effective'], 7)
        self.assertEqual(stats['rangedDamage']['min'], 11)
        self.assertEqual(stats['defense'], {'base':120,'modifier':5})
        self.assertEqual(stats['combatRatings']['meleeHit'], {'rating':12,'bonus':1.2})
        self.assertNotIn('spellHit', stats['combatRatings'])

    def test_failed_inventory_reads_keep_guid_cache_not_false_empty(self):
        self.do(r'''
C_Container.GetContainerNumSlots=function(bag) if bag==0 then return 1 else return 0 end end
C_Container.GetContainerItemInfo=function() return {itemID=44,hyperlink='item:44',stackCount=1} end
function GetInventoryItemID(unit,slot) if slot==1 then return 55 end end
''')
        good = self.snapshot()
        self.do("NOW=NOW+1; C_Container.GetContainerItemInfo=function() error('bad bag read') end; GetInventoryItemLink=function() error('bad gear read') end")
        failed = self.snapshot()
        self.assertEqual(failed['bags'][0]['itemId'],44)
        self.assertEqual(failed['equipment'][0]['itemId'],55)
        self.assertFalse(failed['bagsKnown'])
        self.assertFalse(failed['equipmentKnown'])
        self.assertEqual(failed['bagsCapturedAt'],good['capturedAt'])
        self.assertTrue(any('bag' in w.lower() and 'failed' in w.lower() for w in failed['warnings']))
        self.do("GUID='Player-2'")
        other = self.snapshot()
        self.assertEqual(other['bags'],[])
        self.assertEqual(other['equipment'],[])
        self.assertFalse(other['bagsKnown'])
        self.assertIsNone(other.get('bagsCapturedAt'))

    def test_missing_tooltip_is_explicit_then_cache_event_resolves(self):
        self.do(r'''
function GetInventoryItemLink(unit,slot) if slot==1 then return 'item:99:0:0:0:0:0:-9' end end
C_Item.GetItemInfo=function(link) return 'Known Name',link,2,10,5,'Armor','Cloth',1,'INVTYPE_HEAD' end
''')
        pending = self.snapshot()
        self.assertTrue(pending['equipment'][0]['tooltipPending'])
        self.assertTrue(any('tooltip' in w.lower() for w in pending['warnings']))
        self.do(r'''
C_TooltipInfo={GetHyperlink=function() return {lines={{leftText='Known Name'},{leftText='Use: actual effect'}}} end}
local frame=ForeverContext.events
frame.scripts.OnEvent(frame,'GET_ITEM_INFO_RECEIVED',99,true)
RunTimers()
''')
        ready = json.loads(self.lua.globals().ForeverContextExport)
        self.assertEqual(ready['equipment'][0]['tooltip'][1]['left'],'Use: actual effect')
        self.assertFalse(ready['equipment'][0].get('pending',False))
        self.assertFalse(ready['equipment'][0].get('tooltipPending',False))

    def test_explicit_status_is_one_compact_message_and_success_events_silent(self):
        self.do("local f=ForeverContext.events; for i=1,20 do f.scripts.OnEvent(f,'BAG_UPDATE',0) end; RunTimers()")
        self.assertEqual(list(self.lua.globals().messages.values()), [])
        self.do("SlashCmdList.FOREVERCONTEXT('status')")
        self.assertEqual(len(list(self.lua.globals().messages.values())), 1)

    def test_failed_automatic_captures_and_event_bursts_are_silent(self):
        self.snapshot()
        self.do(r'''
messages={}
ForeverContext.Stats=function() error('repeated failure') end
for n=1,4 do
 local f=ForeverContext.events
 for i=1,20 do f.scripts.OnEvent(f,'BAG_UPDATE',0) end
 RunTimers()
end
SlashCmdList.FOREVERCONTEXT('export')
''')
        self.assertEqual(list(self.lua.globals().messages.values()), [])
        self.assertIn('repeated failure', self.do('return ForeverContext.lastError'))
        self.do("SlashCmdList.FOREVERCONTEXT('status')")
        messages = list(self.lua.globals().messages.values())
        self.assertEqual(len(messages), 1)
        self.assertIn('failed', messages[0].lower())

    def test_capture_failure_keeps_good_export_and_save_does_not_claim_success(self):
        good = self.snapshot()
        old = self.lua.globals().ForeverContextExport
        self.do("ForeverContext.Stats=function() error('forced capture failure') end; NOW=NOW+100; messages={}; SlashCmdList.FOREVERCONTEXT('save')")
        self.assertEqual(self.lua.globals().ForeverContextExport, old)
        self.assertEqual(self.do('return ForeverContext.last.capturedAt'),good['capturedAt'])
        self.assertFalse(self.do('return ForeverContext.capturing'))
        text = '\n'.join(self.lua.globals().messages.values())
        self.assertIn('failed',text.lower())
        self.assertNotIn('refreshed',text.lower())
        self.do("messages={}; SlashCmdList.FOREVERCONTEXT('status')")
        self.assertIn('failed','\n'.join(self.lua.globals().messages.values()).lower())

    def test_unavailable_talent_entries_and_stats_are_explicit_unknown(self):
        self.do(r'''
function GetNumTalentTabs() return 1 end
function GetTalentTabInfo() return 'Arms','icon',3 end
function GetNumTalents() return 1 end
function GetTalentInfo() error('cache not ready') end
''')
        data = self.snapshot()
        self.assertTrue(any('talent entry' in w.lower() for w in data['warnings']))
        self.assertTrue(any('stats' in w.lower() and 'unavailable' in w.lower() for w in data['warnings']))
        self.assertFalse(data['talents'][0]['known'])
        self.assertEqual(data['stats'],{})

    def test_container_info_nil_keeps_occupied_slot_using_id_or_link(self):
        self.do(r'''
C_Container.GetContainerNumSlots=function(bag) if bag==0 then return 1 else return 0 end end
C_Container.GetContainerItemInfo=function() return nil end
C_Container.GetContainerItemID=function() return 88 end
C_Container.GetContainerItemLink=function() return '|Hitem:88:5:0:0:0:0:-8|h[Unknown]|h' end
''')
        data = self.snapshot()
        self.assertEqual(len(data['bags']),1)
        item=data['bags'][0]
        self.assertEqual(item['itemId'],88)
        self.assertIn(':-8',item['link'])
        self.assertTrue(item['pending'])

    def test_future_bank_cache_is_unknown_not_invalid_snapshot(self):
        self.do('ForeverContext.bankOpen=true')
        self.snapshot()
        self.do('ForeverContext.bankOpen=false; NOW=NOW-100')
        data=self.snapshot()
        self.assertFalse(data['bank']['known'])
        self.assertNotIn('capturedAt',data['bank'])


if __name__ == '__main__':
    unittest.main()
