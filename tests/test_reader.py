"""Synthetic fixtures for the file reader; never character inventory data."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import contextlib
import io

ROOT = Path(__file__).resolve().parents[1]
TEST_SCRATCH = Path.home() / 'AppData' / 'Local' / 'hermes' / 'cache' / 'scratch'
TEST_SCRATCH.mkdir(parents=True, exist_ok=True)


def run_cli(reader, args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return reader.main(args)


def module():
    path = ROOT / 'tools' / 'read_snapshot.py'
    if not path.exists():
        raise AssertionError('Missing read_snapshot.py implementation')
    spec = importlib.util.spec_from_file_location('forever_reader', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class SavedVariableTests(unittest.TestCase):
    def test_reads_json_export_without_executing_cache(self):
        reader = module()
        value = '{"schemaVersion":1,"name":"Test"}'
        raw = 'ForeverContextDB = { ["cache"] = { 1, 2, true, }, }\nForeverContextExport = ' + json.dumps(value)
        self.assertEqual(reader.extract_export(raw), value)


    def test_rejects_executable_lua_and_duplicate_assignment(self):
        reader = module()
        for raw in [
            'ForeverContextExport = "{}"; os.execute("bad")',
            'ForeverContextExport = (function() return "{}" end)()',
            'ForeverContextExport = "{}"\nForeverContextExport = "{}"',
            'ForeverContextDB = { x = function() end }',
            'ForeverContextExport = "unterminated',
        ]:
            with self.subTest(raw=raw), self.assertRaises(reader.SnapshotError):
                reader.extract_export(raw)

    def test_preserves_unicode_and_literal_item_suffix(self):
        reader = module()
        text = r'ForeverContextExport = "{\"name\":\"\195\137lune\",\"link\":\"item:123:0:0:0:0:0:-27:789\"}"'
        result = json.loads(reader.extract_export(text))
        self.assertEqual(result['name'], 'Élune')
        self.assertEqual(result['link'], 'item:123:0:0:0:0:0:-27:789')

    def test_comments_cannot_spoof_export_and_long_strings_work(self):
        reader = module()
        raw = '-- ForeverContextExport = "bad"\n--[=[\nForeverContextExport = "bad"\n]=]\nForeverContextExport = [==[\n{"ok":true}]==]'
        self.assertEqual(reader.extract_export(raw), '{"ok":true}')

    def test_item_links_reject_controls_and_preserve_full_literal(self):
        reader = module()
        link = '|cffa335ee|Hitem:123:7:0:0:0:0:-27:789|h[Élune`s Helm]|h|r'
        data = sample()
        data['equipment'][0]['link'] = link
        validated = reader.validate_snapshot(json.dumps(data))
        self.assertEqual(validated['equipment'][0]['link'], link)
        with self.subTest(literal_preservation=True):
            self.assertIn(link, reader.render_summary(validated, now=2000))
        for bad in ['item:123\n# Spoof', 'item:123\rSpoof', 'item:123\tSpoof',
                    'item:123\x00', 'item:123\x1b[31m', 'item:123\x7f',
                    'item:123\x85', 'item:123\u2028# Spoof', 'item:123\u2029Spoof', 42, []]:
            with self.subTest(link=bad):
                data['equipment'][0]['link'] = bad
                with self.assertRaises(reader.SnapshotError):
                    reader.validate_snapshot(json.dumps(data))

    def test_optional_item_string_is_validated_and_preserved_in_summary(self):
        reader = module()
        data = sample()
        raw = 'item:123:456:0:0:0:0:-27:789'
        data['equipment'][0]['itemString'] = raw
        validated = reader.validate_snapshot(json.dumps(data))
        self.assertEqual(validated['equipment'][0]['itemString'], raw)
        self.assertIn('Raw item string: `' + raw + '`', reader.render_summary(validated, now=2000))
        for bad in (42, [], 'item:123\nspoof', '[Name]', 'item:abc', 'item:123|h'):
            with self.subTest(itemString=bad), self.assertRaises(reader.SnapshotError):
                data['equipment'][0]['itemString'] = bad
                reader.validate_snapshot(json.dumps(data))

    def test_empty_realm_accepts_guid_identity_without_inventing_realm(self):
        reader = module()
        data = sample()
        data['character'].update(realm='', guid='Player-1234-00000001')
        validated = reader.validate_snapshot(json.dumps(data))
        self.assertEqual(validated['character']['realm'], '')
        self.assertIn('realm unknown', reader.render_summary(validated, now=2000).lower())
        for guid in [None, '', ' ', 42, [], {}, 'Player-', 'GUID-A', 'Player-x-ABC', 'Player-1-ZZZ', 'Player-1-ABC\n']:
            with self.subTest(guid=guid), self.assertRaises(reader.SnapshotError):
                data['character']['guid'] = guid
                reader.validate_snapshot(json.dumps(data))

    def test_validates_schema_and_creates_honest_summary(self):
        reader = module()
        data = sample()
        result = reader.validate_snapshot(json.dumps(data))
        text = reader.render_summary(result, now=2000)
        self.assertIn('FixtureHero', text)
        self.assertIn('unknown', text.lower())
        self.assertIn('not live', text.lower())
        self.assertIn('item:123:0:0:0:0:0:-27:789', text)
        for bad in [dict(data, schemaVersion=99), dict(data, capturedAt='yesterday'), dict(data, equipment={})]:
            with self.subTest(bad=bad), self.assertRaises(reader.SnapshotError):
                reader.validate_snapshot(json.dumps(bad))


def sample(name='FixtureHero', timestamp=1000):
    return {'schemaVersion':1, 'addonVersion':'test', 'capturedAt':timestamp,
            'character':{'name':name,'realm':'FixtureRealm','guid':'TEST-NOT-REAL','level':38},
            'equipment':[{'slot':1,'slotName':'Head','name':'Synthetic fixture helm',
                          'link':'item:123:0:0:0:0:0:-27:789','tooltip':[{'left':'+4 Spell Power'}]}],
            'bags':[], 'bank':{'known':False, 'accessible':False, 'items':[]},
            'talents':[], 'stats':{}, 'warnings':[]}


class ImportTests(unittest.TestCase):
    def test_pasted_txt_json_accepts_unknown_realm_and_preserves_name_only_links(self):
        reader = module()
        data = sample()
        data['character'].update(realm='', guid='Player-1234-00000001')
        data['equipment'][0]['link'] = '[Original Name]'
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            path = Path(folder)/'pasted.txt'
            path.write_text(json.dumps(data), encoding='utf-8')
            loaded = reader.load_snapshot(path)
            self.assertEqual(loaded, data)
            self.assertNotIn('itemString', loaded['equipment'][0])
            summary = reader.render_summary(loaded, now=2000)
            self.assertIn('full hyperlink unavailable', summary.lower())
            self.assertNotIn('Full original item link:', summary)
            console = io.StringIO()
            with contextlib.redirect_stdout(console):
                self.assertEqual(reader.main(['--input', str(path), '--output-dir', str(Path(folder)/'out')]), 0)
            self.assertIn('realm unknown', console.getvalue().lower())

    def test_publication_failure_restores_previous_output_generation(self):
        reader = module()
        for old_json, old_md in [(b'old json\r\n', b'old markdown\x00\r\n'),
                                 (None, None), (b'old json', None), (None, b'old markdown')]:
            with self.subTest(old_json=old_json, old_md=old_md):
                with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
                    out = Path(folder)
                    originals = {'latest.json':old_json, 'latest.md':old_md}
                    for name, content in originals.items():
                        if content is not None:
                            (out/name).write_bytes(content)
                    real_replace = reader.os.replace
                    calls = 0

                    def fail_second_replace(source, destination):
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise PermissionError('simulated second publication failure')
                        return real_replace(source, destination)

                    with mock.patch.object(reader.os, 'replace', side_effect=fail_second_replace):
                        with self.assertRaises(PermissionError):
                            reader.write_outputs(sample(timestamp=2000), out)
                    for name, content in originals.items():
                        if content is None:
                            self.assertFalse((out/name).exists())
                        else:
                            self.assertEqual((out/name).read_bytes(), content)
                    self.assertFalse(list(out.glob('.fctx-*')))

    def write_saved(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('ForeverContextDB = {}\nForeverContextExport = ' + json.dumps(json.dumps(data,ensure_ascii=False),ensure_ascii=False), encoding='utf-8')

    def test_import_writes_json_and_summary_and_refuses_invalid_overwrite(self):
        reader = module()
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            root = Path(folder)
            src = root / 'ForeverContext.lua'
            out = root / 'out'
            self.write_saved(src, sample())
            self.assertEqual(run_cli(reader,['--input',str(src),'--output-dir',str(out)]), 0)
            before = (out/'latest.json').read_bytes()
            self.assertEqual(json.loads(before)['character']['name'], 'FixtureHero')
            self.assertTrue((out/'latest.md').exists())
            src.write_text('ForeverContextExport = os.execute("bad")',encoding='utf-8')
            self.assertEqual(run_cli(reader,['--input',str(src),'--output-dir',str(out)]), 2)
            self.assertEqual((out/'latest.json').read_bytes(),before)

    def test_invalid_guid_and_out_of_range_timestamps_are_validation_errors(self):
        reader = module()
        for guid in [[], {}, 42, True]:
            with self.subTest(guid=guid):
                data = sample()
                data['character']['guid'] = guid
                with self.assertRaises(reader.SnapshotError):
                    reader.validate_snapshot(json.dumps(data))
        for field in ['snapshot', 'bank']:
            for timestamp in [10**400, 1e100, 253402300799, -1, True]:
                with self.subTest(field=field, timestamp=timestamp):
                    data = sample()
                    if field == 'snapshot':
                        data['capturedAt'] = timestamp
                    else:
                        data['bank'].update(known=True, capturedAt=timestamp)
                    with self.assertRaises(reader.SnapshotError):
                        reader.validate_snapshot(json.dumps(data))

    def test_rejects_nonfinite_exponents_recursively_but_preserves_giant_ints(self):
        reader = module()
        for branch in ['stats', 'equipment', 'bank', 'extra']:
            for number in ['1e309', '-1e309']:
                with self.subTest(branch=branch, number=number):
                    data = sample()
                    nested = {'nested':[{'value':'EXPONENT_SENTINEL'}]}
                    if branch == 'equipment':
                        data[branch][0]['extra'] = nested
                    elif branch == 'bank':
                        data[branch]['extra'] = nested
                    else:
                        data[branch] = nested
                    raw = json.dumps(data).replace('"EXPONENT_SENTINEL"', number)
                    with self.assertRaises(reader.SnapshotError):
                        reader.validate_snapshot(raw)
        data = sample()
        data['stats'] = {'giant':10**400}
        validated = reader.validate_snapshot(json.dumps(data))
        self.assertEqual(validated['stats']['giant'], 10**400)
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            reader.write_outputs(validated, folder)
            self.assertEqual(json.loads((Path(folder)/'latest.json').read_text())['stats']['giant'], 10**400)
            self.assertIn(str(10**400), (Path(folder)/'latest.md').read_text(encoding='utf-8'))

    def test_bank_accessibility_is_boolean_and_bank_cannot_postdate_snapshot(self):
        reader = module()
        for accessible in ['false', 0, 1, [], None]:
            with self.subTest(accessible=accessible):
                data = sample()
                data['bank']['accessible'] = accessible
                with self.assertRaises(reader.SnapshotError):
                    reader.validate_snapshot(json.dumps(data))
        with self.subTest(missing_accessible=True):
            data = sample()
            del data['bank']['accessible']
            with self.assertRaises(reader.SnapshotError):
                reader.validate_snapshot(json.dumps(data))
        with self.subTest(future_bank=True):
            data = sample()
            data['bank'].update(known=True, capturedAt=1001)
            with self.assertRaises(reader.SnapshotError):
                reader.validate_snapshot(json.dumps(data))
        data['bank']['capturedAt'] = data['capturedAt']
        self.assertEqual(reader.validate_snapshot(json.dumps(data))['bank']['capturedAt'], 1000)

    def test_missing_input_does_not_make_fake_data(self):
        reader = module()
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            root = Path(folder)
            self.assertEqual(run_cli(reader,['--wow-root',str(root),'--output-dir',str(root/'out')]), 2)
            self.assertFalse((root/'out'/'latest.json').exists())

    def test_same_name_realm_with_different_guids_requires_explicit_input(self):
        reader = module()
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            root = Path(folder)
            paths = []
            for account, guid in [('ACCOUNT-A','GUID-A'), ('ACCOUNT-B','GUID-B')]:
                data = sample()
                data['character']['guid'] = guid
                path = root/'WTF'/'Account'/account/'SavedVariables'/'ForeverContext.lua'
                self.write_saved(path, data)
                paths.append(path)
            args = ['--wow-root',str(root),'--output-dir',str(root/'out')]
            for selection in [[], ['--character','FixtureHero-FixtureRealm']]:
                with self.subTest(selection=selection):
                    error = io.StringIO()
                    with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(reader.main(args + selection), 2)
                    self.assertIn('--input', error.getvalue())
                    self.assertFalse((root/'out'/'latest.json').exists())
            self.assertEqual(run_cli(reader, args + ['--input',str(paths[0])]), 0)
            self.assertEqual(json.loads((root/'out'/'latest.json').read_text())['character']['guid'], 'GUID-A')

    def test_multiple_characters_require_selection(self):
        reader = module()
        with tempfile.TemporaryDirectory(dir=TEST_SCRATCH) as folder:
            root = Path(folder)
            for account, name in [('ACCOUNT-A','FixtureHero'),('ACCOUNT-B','OtherFixture')]:
                self.write_saved(root/'WTF'/'Account'/account/'SavedVariables'/'ForeverContext.lua',sample(name))
            args = ['--wow-root',str(root),'--output-dir',str(root/'out')]
            self.assertEqual(run_cli(reader,args), 2)
            self.assertFalse((root/'out'/'latest.json').exists())
            self.assertEqual(run_cli(reader,args+['--character','FixtureHero-FixtureRealm']), 0)
            self.assertNotIn('ACCOUNT-A',(root/'out'/'latest.md').read_text(encoding='utf-8'))

    def test_rejects_invalid_nested_data_before_writing(self):
        reader = module()
        for key, value in [('talents',[42]),('warnings',[{}]),('equipment',[{'tooltip':[{'left':{'bad':'value'}}]}]),('character',{'name':42,'realm':'x'})]:
            with self.subTest(key=key), self.assertRaises(reader.SnapshotError):
                reader.validate_snapshot(json.dumps(dict(sample(), **{key:value})))

    def test_known_empty_bank_and_stale_capture_remain_explicit(self):
        reader = module()
        data = sample()
        data['bank'] = {'known':True,'capturedAt':900,'accessible':False,'items':[]}
        rendered = reader.render_summary(reader.validate_snapshot(json.dumps(data)),now=10000)
        self.assertIn('STALE',rendered)
        self.assertIn('Last observed',rendered)
        self.assertNotIn('**Unknown:**',rendered)

    def test_duplicate_json_nonfinite_and_corrupt_bank_rejected(self):
        reader = module()
        for raw in ['{"schemaVersion":1,"schemaVersion":2}', '{"schemaVersion":NaN}', json.dumps(dict(sample(),bank={'known':True,'items':[]}))]:
            with self.subTest(raw=raw), self.assertRaises(reader.SnapshotError):
                reader.validate_snapshot(raw)


if __name__ == '__main__':
    unittest.main()
