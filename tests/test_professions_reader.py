"""Synthetic additive profession-schema tests; no live character data."""
import copy
import json
import unittest
from typing import Any
from tools.read_snapshot import validate_snapshot,render_summary,SnapshotError


def profession_snapshot() -> dict[str,Any]:
    from test_live_capture import snapshot
    data=snapshot(100)
    data.update(professionsKnown=True,professionsCapturedAt=100,
        professions=[{'name':'Mining','category':'primary','skillLineId':186,
                      'skillLevel':140,'maxSkillLevel':225,'skillModifier':5,'known':True}])
    return data


class ProfessionReaderTests(unittest.TestCase):
    def test_malformed_profession_bundle_is_rejected(self):
        cases=[]
        for field,value in [('professions',{}),('professionsKnown','yes'),('professionsCapturedAt',101),('professionsCapturedAt',99),('professionsCapturedAt',True)]:
            data=profession_snapshot();data[field]=value;cases.append(data)
        for field,value in [('skillLevel',True),('skillLevel',-1),('skillLevel',226),('skillLevel',None),('maxSkillLevel',0),('skillLineId',False),('category','weapon'),('known','yes'),('name','')]:
            data=profession_snapshot();data['professions'][0][field]=value;cases.append(data)
        data=profession_snapshot();data['professions'].append(copy.deepcopy(data['professions'][0]));cases.append(data)
        data=profession_snapshot();data['professions'][0]['known']=False;cases.append(data)
        for n,data in enumerate(cases):
            with self.subTest(case=n):
                with self.assertRaises(SnapshotError):
                    validate_snapshot(json.dumps(data))


    def test_summary_shows_profession_rank_cap_and_separate_bonus(self):
        data=validate_snapshot(json.dumps(profession_snapshot()))
        summary=render_summary(data,now=100)
        self.assertIn('## Professions',summary)
        self.assertIn('Mining: 140/225',summary)
        self.assertIn('bonus +5',summary)
        self.assertNotIn('Mining: 145/225',summary)

    def test_summary_distinguishes_old_unknown_partial_and_known_empty(self):
        from test_live_capture import snapshot
        old=validate_snapshot(json.dumps(snapshot(100)))
        self.assertIn('Professions unknown',render_summary(old,now=100))
        empty=profession_snapshot();empty['professions']=[]
        self.assertIn('No learned professions reported',render_summary(validate_snapshot(json.dumps(empty)),now=100))
        partial=profession_snapshot();partial['professionsKnown']=False
        partial['professions'][0]['known']=False
        del partial['professions'][0]['skillLevel']
        summary=render_summary(validate_snapshot(json.dumps(partial)),now=100)
        self.assertIn('Mining: unknown/225',summary)
        self.assertIn('incomplete',summary)


if __name__=='__main__':
    unittest.main()
