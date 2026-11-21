"""Profession queries use the same strict live/stale policy as other sections."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.live_capture import atomic_json
from tools.live_mcp import LiveReader
from tests.test_live_capture import SCRATCH


def prepare(folder, professions=True):
    from test_live_mcp import fixture
    from test_professions_reader import profession_snapshot
    fixture(folder)
    if professions:
        path=Path(folder)/'current.json'
        envelope=json.loads(path.read_text())
        envelope['snapshot']=profession_snapshot()
        atomic_json(path,envelope)


class ProfessionMCPTests(unittest.TestCase):
    def test_fresh_profession_levels_include_known_and_observation_metadata(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            prepare(folder)
            value=LiveReader(folder).read('professions',now=101)
            self.assertTrue(value['metadata']['live'])
            self.assertTrue(value['metadata'].get('professionsKnown'))
            self.assertEqual(value['metadata']['professionsCapturedAt'],100)
            self.assertEqual(value['data'][0]['skillLevel'],140)
            self.assertEqual(value['data'][0]['skillModifier'],5)


    def test_old_snapshot_reports_unknown_not_empty_professions(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            prepare(folder,professions=False)
            value=LiveReader(folder).read('professions',now=101)
            self.assertEqual(value['availability'],'unavailable')
            self.assertFalse(value['metadata']['professionsKnown'])
            self.assertNotIn('data',value)


    def test_incomplete_read_is_partial_or_unavailable_never_known_empty(self):
        for empty in (False,True):
            with self.subTest(empty=empty),tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
                prepare(folder)
                path=Path(folder)/'current.json'
                envelope=json.loads(path.read_text())
                data=envelope['snapshot'];data['professionsKnown']=False
                if empty:
                    data['professions']=[]
                else:
                    data['professions'][0]['known']=False
                    del data['professions'][0]['skillLevel']
                atomic_json(path,envelope)
                value=LiveReader(folder).read('professions',now=101)
                self.assertEqual(value['availability'],'unavailable' if empty else 'partial')
                self.assertFalse(value['metadata']['professionsKnown'])
                if empty:
                    self.assertNotIn('data',value)
                else:
                    self.assertNotIn('skillLevel',value['data'][0])


    def test_successful_empty_list_is_known_empty(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            prepare(folder)
            path=Path(folder)/'current.json'
            envelope=json.loads(path.read_text());envelope['snapshot']['professions']=[]
            atomic_json(path,envelope)
            value=LiveReader(folder).read('professions',now=101)
            self.assertEqual(value['availability'],'live')
            self.assertTrue(value['metadata']['professionsKnown'])
            self.assertEqual(value['data'],[])

    def test_stale_professions_are_denied_unless_explicitly_allowed(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            prepare(folder)
            denied=LiveReader(folder).read('professions',now=120)
            self.assertNotIn('data',denied)
            allowed=LiveReader(folder).read('professions',allow_stale=True,now=120)
            self.assertFalse(allowed['metadata']['live'])
            self.assertEqual(allowed['availability'],'stale')
            self.assertEqual(allowed['data'][0]['skillLevel'],140)


if __name__=='__main__':
    unittest.main()
