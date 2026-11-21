"""Lua-produced profession JSON must remain readable even on partial API data."""
import json
import unittest
from tools.read_snapshot import validate_snapshot


class ProfessionPipelineTests(unittest.TestCase):
    def test_incomplete_lua_profession_data_does_not_block_valid_gear_snapshot(self):
        from test_addon import AddonTests
        harness=AddonTests('test_root_json_unicode_escaping_and_empty_arrays')
        harness.setUp()
        for values in ("'Mining',1,80,75,nil,nil,186", "'   ',1,125,150,nil,nil,186",
                       "'Mining',1,2147483648,2147483649,nil,nil,186",
                       "'Mining',1,125,150,nil,nil,2147483648"):
            with self.subTest(values=values):
                harness.do('GetProfessions=function() return 11 end; GetProfessionInfo=function() return '+values+' end')
                raw=harness.snapshot()
                canonical=validate_snapshot(json.dumps(raw))
                self.assertFalse(canonical['professionsKnown'])
                self.assertTrue(canonical['equipmentKnown'])
                self.assertTrue(canonical['bagsKnown'])
                self.assertIsNone(harness.do('return ForeverContext.lastError'))

    def test_unicode_whitespace_names_are_unknown_without_changing_real_names(self):
        from test_addon import AddonTests
        harness=AddonTests('test_root_json_unicode_escaping_and_empty_arrays')
        harness.setUp()
        # NBSP is the reported regression; cover every Python isspace code point.
        codepoints=[160, *range(9,14), *range(28,33), 133, 5760,
                    *range(8192,8203), 8232, 8233, 8239, 8287, 12288]
        whitespace=[chr(codepoint) for codepoint in codepoints]
        for name in whitespace+[''.join(whitespace)]:
            with self.subTest(blank=repr(name)):
                self.assertTrue(name.isspace())
                encoded=','.join(str(byte) for byte in name.encode('utf-8'))
                harness.do('GetProfessions=function() return 11 end; '
                           'GetProfessionInfo=function() return string.char('+encoded+'),1,125,150,nil,nil,186 end')
                raw=harness.snapshot()
                canonical=validate_snapshot(json.dumps(raw))
                self.assertNotIn('name',raw['professions'][0])
                self.assertFalse(raw['professions'][0]['known'])
                self.assertFalse(raw['professionsKnown'])
                self.assertFalse(canonical['professionsKnown'])
                self.assertTrue(canonical['equipmentKnown'])
                self.assertTrue(canonical['bagsKnown'])
                self.assertIsNone(harness.do('return ForeverContext.lastError'))
        for space in whitespace:
            name=space+'采矿'+space+'Bergbau'+space
            with self.subTest(real_name=repr(name)):
                encoded=','.join(str(byte) for byte in name.encode('utf-8'))
                harness.do('GetProfessionInfo=function() return string.char('+encoded+'),1,125,150,nil,nil,186 end')
                raw=harness.snapshot()
                canonical=validate_snapshot(json.dumps(raw))
                self.assertEqual(raw['professions'][0]['name'],name)
                self.assertEqual(canonical['professions'][0]['name'],name)
                self.assertTrue(raw['professions'][0]['known'])
                self.assertTrue(canonical['professionsKnown'])


if __name__=='__main__':
    unittest.main()
