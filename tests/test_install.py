import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path.home()/'AppData'/'Local'/'hermes'/'cache'/'scratch'


def installer():
    path = ROOT/'tools'/'install_addon.py'
    if not path.exists():
        raise AssertionError('Missing installer implementation')
    spec = importlib.util.spec_from_file_location('forever_installer',path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallTests(unittest.TestCase):
    def test_installs_only_named_addon_and_verifies_hashes(self):
        mod = installer()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root=Path(folder)
            source=root/'source'/'ForeverContext'
            source.mkdir(parents=True)
            (source/'ForeverContext.toc').write_text('## Interface: 16001\nCore.lua\n')
            (source/'Core.lua').write_text('-- Synthetic installer fixture; no game data\n')
            addons=root/'AddOns'
            (addons/'OtherAddon').mkdir(parents=True)
            (addons/'OtherAddon'/'keep.txt').write_text('do not modify')
            result=mod.install_addon(source,addons)
            self.assertEqual(result['verifiedFiles'],2)
            self.assertEqual((addons/'OtherAddon'/'keep.txt').read_text(),'do not modify')
            self.assertEqual((addons/'ForeverContext'/'Core.lua').read_bytes(),(source/'Core.lua').read_bytes())
            self.assertEqual(mod.install_addon(source,addons)['status'],'already-current')

    def test_refuses_to_overwrite_an_existing_different_addon(self):
        mod=installer()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            root=Path(folder)
            source=root/'source'/'ForeverContext'
            source.mkdir(parents=True)
            (source/'ForeverContext.toc').write_text('## Interface: 16001\nCore.lua\n')
            (source/'Core.lua').write_text('-- new\n')
            target=root/'AddOns'/'ForeverContext'
            target.mkdir(parents=True)
            (target/'Core.lua').write_text('-- old\n')
            with self.assertRaises(mod.InstallError):
                mod.install_addon(source,root/'AddOns')
            self.assertEqual((target/'Core.lua').read_text(),'-- old\n')


if __name__=='__main__':
    unittest.main()
