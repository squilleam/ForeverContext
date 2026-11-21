"""Synthetic profession APIs exercising the real Lua 5.1 addon."""
import json
import unittest
import test_addon as harness
from test_addon import ADDON


class ProfessionAddonTests(unittest.TestCase):
    lua: harness.LuaRuntime
    setUp = harness.AddonTests.setUp
    do = harness.AddonTests.do
    snapshot = harness.AddonTests.snapshot

    def test_successful_no_learned_professions_is_known_empty(self):
        self.do('GetProfessions=function() return nil,nil,nil,nil,nil end; GetProfessionInfo=function() error("no learned professions") end')
        data = self.snapshot()
        self.assertEqual(data['professions'], [])
        self.assertTrue(data['professionsKnown'])
        self.assertEqual(data['professionsCapturedAt'], data['capturedAt'])
        self.assertEqual(data['schemaVersion'], 1)
        self.assertFalse(any('profession' in w.lower() for w in data['warnings']))

    def test_unavailable_or_failed_primary_apis_are_unknown_not_empty(self):
        for api in ('GetProfessions=nil', 'GetProfessions=function() error("unavailable") end',
                    'GetProfessionInfo=nil'):
            with self.subTest(api=api):
                self.do('GetProfessions=function() end; GetProfessionInfo=function() end; ' + api)
                data = self.snapshot()
                self.assertFalse(data['professionsKnown'])
                self.assertEqual(data['professions'], [])
                self.assertEqual(data['professionsCapturedAt'], data['capturedAt'])
                self.assertTrue(any('profession' in w.lower() and 'unknown' in w.lower() for w in data['warnings']))
                self.assertTrue(data['equipmentKnown'])
                self.assertIsNone(self.do('return ForeverContext.lastError'))

    def test_learned_primary_and_sparse_secondary_preserve_actual_slots(self):
        self.do('''
GetProfessions=function() return 11,22,nil,44,55 end
local skills={[11]={'Mining',186,125,150},[22]={'Blacksmithing',164,99,150},
 [44]={'Fishing',356,0,75},[55]={'Cooking',185,70,75}}
GetProfessionInfo=function(index)
 local s=assert(skills[index]); return s[1],'icon',s[3],s[4],nil,nil,s[2]
end
''')
        data = self.snapshot()
        self.assertTrue(data['professionsKnown'])
        self.assertEqual(data['professions'], [
            dict(name=name, category=category, skillLineId=id, skillLevel=rank,
                 maxSkillLevel=cap, known=True)
            for name, category, id, rank, cap in [
                ('Mining','primary',186,125,150),('Blacksmithing','primary',164,99,150),
                ('Fishing','secondary',356,0,75),('Cooking','secondary',185,70,75)]])
        self.do('GetProfessions=function() return nil,22,11,nil,55 end')
        data = self.snapshot()
        self.assertEqual([p['category'] for p in data['professions']], ['primary','secondary','secondary'])
        self.assertEqual([p['name'] for p in data['professions']], ['Blacksmithing','Mining','Cooking'])

    def test_incomplete_entries_retain_only_valid_public_fields(self):
        cases = [
            ('nil,1,12,75,nil,nil,186', {'skillLevel':12,'maxSkillLevel':75,'skillLineId':186}),
            ("'Mining',1,nil,75,nil,nil,186", {'name':'Mining','maxSkillLevel':75,'skillLineId':186}),
            ("'Mining',1,12,nil,nil,nil,186", {'name':'Mining','skillLevel':12,'skillLineId':186}),
            ("'Mining',1,12,75,nil,nil,nil", {'name':'Mining','skillLevel':12,'maxSkillLevel':75}),
            ("'',1,-1,0,nil,nil,-186", {}),
            ("12,1,1.5,0/0,nil,nil,math.huge", {}),
            ("'Mining',1,80,75,nil,nil,186", {'name':'Mining','maxSkillLevel':75,'skillLineId':186}),
        ]
        for values, fields in cases:
            with self.subTest(values=values):
                self.do('GetProfessions=function() return 11 end; GetProfessionInfo=function() return ' + values + ' end')
                data = self.snapshot()
                self.assertFalse(data['professionsKnown'])
                self.assertEqual(data['professions'], [dict(category='primary',known=False,**fields)])
                self.assertTrue(any('profession' in w.lower() and 'unknown' in w.lower() for w in data['warnings']))
        self.do('GetProfessionInfo=function() error("detail failure") end')
        data = self.snapshot()
        self.assertFalse(data['professionsKnown'])
        self.assertEqual(data['professions'], [dict(category='primary',known=False)])
        self.assertTrue(data['equipmentKnown'])
        self.assertIsNone(self.do('return ForeverContext.lastError'))

    def test_bonus_is_separate_and_verified_skill_info_modifier_overrides(self):
        self.do('''
GetProfessions=function() return 11 end
GetProfessionInfo=function() return 'Mining',1,125,150,nil,nil,186,10 end
''')
        self.assertEqual(self.snapshot()['professions'][0]['skillModifier'], 10)
        self.do('C_SkillInfo={GetSkillLineInfoByID=function(id) assert(id==186); return {modifier=-3} end}')
        entry = self.snapshot()['professions'][0]
        self.assertEqual((entry['skillLevel'], entry['maxSkillLevel'], entry['skillModifier']), (125,150,-3))
        for result in ('{modifier=0}', '{modifier=1.5}', '{}', 'nil', 'false'):
            self.do('C_SkillInfo.GetSkillLineInfoByID=function() return ' + result + ' end')
            self.assertEqual(self.snapshot()['professions'][0]['skillModifier'], 0 if result=='{modifier=0}' else 10)
        self.do('C_SkillInfo.GetSkillLineInfoByID=function() error("not ready") end')
        self.assertEqual(self.snapshot()['professions'][0]['skillModifier'], 10)
        for bonus in ('nil', '1.5', 'math.huge', '"10"'):
            self.do("GetProfessionInfo=function() return 'Mining',1,125,150,nil,nil,186," + bonus + ' end')
            data = self.snapshot()
            self.assertNotIn('skillModifier', data['professions'][0])
            self.assertTrue(data['professionsKnown'])

    def test_native_secret_slots_are_unknown_without_inspection_or_api_arguments(self):
        self.do('''
SECRET=setmetatable({}, {__tostring=function() error('inspected secret') end,
 __eq=function() error('compared secret') end,__lt=function() error('ordered secret') end,
 __index=function() error('indexed secret') end})
issecretvalue=function(value) return rawequal(value,SECRET) end
GetProfessions=function() return SECRET,nil,nil,44 end
GetProfessionInfo=function(index)
 assert(index==44, 'restricted index passed to API'); return 'Fishing',1,0,75,nil,nil,356
end
''')
        data = self.snapshot()
        self.assertFalse(data['professionsKnown'])
        self.assertEqual(data['professions'], [dict(name='Fishing',category='secondary',skillLineId=356,
                                                   skillLevel=0,maxSkillLevel=75,known=True)])
        self.assertTrue(any('profession' in w.lower() and 'unknown' in w.lower() for w in data['warnings']))
        self.assertTrue(data['equipmentKnown'])
        self.assertIsNone(self.do('return ForeverContext.lastError'))
        self.assertEqual(list(self.lua.globals()['messages'].values()), [])

    def test_native_secret_details_are_omitted_before_validation(self):
        self.do('SECRET={}; issecretvalue=function(v) return rawequal(v,SECRET) end; GetProfessions=function() return 11 end')
        for field in (0,2,3,6):
            values = ["'Mining'", '1', '125', '150', 'nil', 'nil', '186', '10']
            values[field] = 'SECRET'
            self.do('GetProfessionInfo=function() return ' + ','.join(values) + ' end')
            data = self.snapshot()
            self.assertFalse(data['professionsKnown'])
            self.assertFalse(data['professions'][0]['known'])
            self.assertNotIn({0:'name',2:'skillLevel',3:'maxSkillLevel',6:'skillLineId'}[field], data['professions'][0])
            self.assertIsNone(self.do('return ForeverContext.lastError'))
        self.do("GetProfessionInfo=function() return 'Mining',1,125,150,nil,nil,186,SECRET end; C_SkillInfo={GetSkillLineInfoByID=function() return {modifier=SECRET} end}")
        data = self.snapshot()
        self.assertTrue(data['professionsKnown'])
        self.assertNotIn('skillModifier',data['professions'][0])
        self.do("GetProfessionInfo=function() return 'Mining',1,125,150,nil,nil,186,10 end")
        self.assertEqual(self.snapshot()['professions'][0]['skillModifier'],10)
        self.do('C_SkillInfo.GetSkillLineInfoByID=function() return SECRET end')
        self.assertEqual(self.snapshot()['professions'][0]['skillModifier'],10)

    def test_invalid_indices_are_not_passed_to_profession_api(self):
        for value in ('0','-1','1.5','"11"','false','{}','math.huge','0/0'):
            with self.subTest(value=value):
                self.do('GetProfessions=function() return ' + value + ' end; calls=0; GetProfessionInfo=function() calls=calls+1 end')
                data = self.snapshot()
                self.assertFalse(data['professionsKnown'])
                self.assertEqual(data['professions'], [])
                self.assertEqual(self.do('return calls'), 0)
                self.assertTrue(any('profession' in w.lower() and 'unknown' in w.lower() for w in data['warnings']))

    def test_duplicate_indices_and_ids_export_once_without_guessing(self):
        self.do('''
GetProfessions=function() return 11,11,33,44,55 end
calls={}
GetProfessionInfo=function(index)
 calls[index]=(calls[index] or 0)+1
 if index==11 or index==33 then return 'Mining',1,125,150,nil,nil,186 end
 return 'Same localized name',1,0,75,nil,nil,index
end
''')
        data = self.snapshot()
        self.assertTrue(data['professionsKnown'])
        self.assertEqual([p['skillLineId'] for p in data['professions']], [186,44,55])
        self.assertEqual([p['category'] for p in data['professions']], ['primary','secondary','secondary'])
        self.assertEqual(self.do('return calls[11]'),1)
        self.do('GetProfessions=function() return 11,11 end; GetProfessionInfo=function() return nil,nil,0,75 end')
        data = self.snapshot()
        self.assertFalse(data['professionsKnown'])
        self.assertEqual(len(data['professions']),1)

    def test_skill_change_event_refreshes_saved_snapshot_silently(self):
        self.assertTrue(self.do("return ForeverContext.events.events.SKILL_LINES_CHANGED"))
        self.do('''
RANK=1
GetProfessions=function() return 11 end
GetProfessionInfo=function() return 'Mining',1,RANK,75,nil,nil,186 end
ForeverContext.Capture()
NOW=NOW+1; RANK=2
local f=ForeverContext.events
for i=1,20 do f.scripts.OnEvent(f,'SKILL_LINES_CHANGED') end
''')
        self.assertEqual(self.do('return #timers'),1)
        self.do('RunTimers()')
        data = json.loads(self.lua.globals()['ForeverContextExport'])
        self.assertEqual(data['professions'][0]['skillLevel'],2)
        self.assertEqual(data['professionsCapturedAt'],data['capturedAt'])
        self.assertEqual(self.do("return ForeverContextDB.characters['Player-1'].latestSnapshot.professions[1].skillLevel"),2)
        self.do("C_Timer=nil; NOW=NOW+1; RANK=3; local f=ForeverContext.events; f.scripts.OnEvent(f,'SKILL_LINES_CHANGED'); f.scripts.OnUpdate(f,.5)")
        data = json.loads(self.lua.globals()['ForeverContextExport'])
        self.assertEqual(data['professions'][0]['skillLevel'],3)
        self.assertEqual(list(self.lua.globals()['messages'].values()), [])

    def test_unsupported_skill_event_registration_does_not_prevent_loading(self):
        self.do('''
local original=CreateFrame
function CreateFrame(...)
 local frame=original(...)
 local register=frame.RegisterEvent
 frame.RegisterEvent=function(self,event)
  if event=='SKILL_LINES_CHANGED' then error('unsupported event') end
  return register(self,event)
 end
 return frame
end
''')
        self.lua.execute((ADDON/'Core.lua').read_text(encoding='utf-8'))
        self.assertTrue(self.do('return ForeverContext.events.events.PLAYER_LOGIN'))
        self.assertIsNotNone(self.snapshot())
        self.assertEqual(list(self.lua.globals()['messages'].values()), [])


if __name__ == '__main__':
    unittest.main()
