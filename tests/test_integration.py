"""Cross-language integration: real addon Lua -> Lua SavedVariables literal -> Python.

Only mocked-client synthetic fixtures are used, entirely under Hermes scratch.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from lupa.lua51 import LuaRuntime
from test_addon import MOCK

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path.home()/'AppData'/'Local'/'hermes'/'cache'/'scratch'


class PipelineTests(unittest.TestCase):
    def test_real_lua_export_imports_with_unicode_suffixes_and_pending_items(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(MOCK)
        for filename in ('Core.lua','UI.lua'):
            lua.execute((ROOT/'addon'/'ForeverContext'/filename).read_text(encoding='utf-8'))
        lua.execute(r'''
        LINK='|cff0070dd|Hitem:123:456:0:0:0:0:-77:888:38|h[Synthetic Équipement]|h|r'
        function GetInventoryItemLink(_,slot) if slot==16 then return LINK end end
        function GetInventoryItemID(_,slot) if slot==16 then return 123 end end
        C_Item.GetItemInfo=function(link)
          if link==LINK then return 'Synthetic Équipement',LINK,3,40,37,'Weapon','Sword',1,'INVTYPE_WEAPON' end
        end
        C_TooltipInfo={GetHyperlink=function() return {lines={{leftText='Synthetic only: +4 Spell Power'}}} end}
        C_Container.GetContainerNumSlots=function(bag) if bag==0 then return 1 else return 0 end end
        C_Container.GetContainerItemInfo=function() return {itemID=999,stackCount=2} end
        ForeverContext.Capture()
        ''')
        spec=importlib.util.spec_from_file_location('pipeline_reader',ROOT/'tools'/'read_snapshot.py')
        reader=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        # Lua5.1's own literal quoting matches the language of WoW SavedVariables.
        saved='ForeverContextDB = {}\nForeverContextExport = '+lua.eval('string.format("%q",ForeverContextExport)')
        data=reader.validate_snapshot(reader.extract_export(saved))
        self.assertEqual(data['equipment'][0]['link'],lua.globals().LINK)
        self.assertTrue(data['bags'][0]['pending'])
        self.assertFalse(data['bank']['known'])
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            root=Path(directory)
            src=root/'ForeverContext.lua'
            src.write_text(saved,encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code=reader.main(['--input',str(src),'--output-dir',str(root/'out')])
            self.assertEqual(code,0)
            loaded=json.loads((root/'out'/'latest.json').read_text(encoding='utf-8'))
            self.assertEqual(loaded['equipment'][0]['link'],lua.globals().LINK)
            self.assertIn('Tést',(root/'out'/'latest.md').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
