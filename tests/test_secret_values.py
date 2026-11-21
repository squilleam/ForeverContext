"""Respect game-restricted values; never recover or encode their contents."""
import json
import unittest


class SecretValueTests(unittest.TestCase):
    def setUp(self):
        from test_addon import AddonTests
        self.h=AddonTests('test_root_json_unicode_escaping_and_empty_arrays')
        self.h.setUp()
        self.h.do("function issecretvalue(v) return v==987654 or v=='SYNTHETIC RESTRICTED TEXT' end")

    def test_serializer_replaces_restricted_values_with_null(self):
        self.assertEqual(self.h.do('return ForeverContext.JSON(987654)'), 'null')
        self.assertEqual(self.h.do("return ForeverContext.JSON('SYNTHETIC RESTRICTED TEXT')"), 'null')
        result=json.loads(self.h.do('return ForeverContext.JSON({normal=12,nested={restricted=987654}})'))
        self.assertEqual(result,{'normal':12,'nested':{'restricted':None}})

    def test_api_results_and_tooltip_text_are_not_inspected(self):
        self.assertIsNone(self.h.do('local value=ForeverContext.Call(function() return 987654 end); return value'))
        self.assertIsNone(self.h.do("return ForeverContext.Clean('SYNTHETIC RESTRICTED TEXT')"))
        self.h.do('function UnitHealthMax() return 987654 end')
        data=self.h.snapshot()
        self.assertNotIn('healthMax',data['stats'])
        self.assertTrue(any('restricted' in w.lower() for w in data['warnings']))
        self.assertFalse(self.h.lua.globals().ForeverContext.lastError)


if __name__=='__main__':
    unittest.main()
