"""Run directly with Python. The tests use no network access or external packages."""
import importlib.util
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("followthrough", Path(__file__).with_name("build-fed-yield-followthrough.py"))
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class FollowThroughTests(unittest.TestCase):
    def test_next_fix_skips_weekend_and_preserves_opposite_subsequent_move(self):
        source = {"date":"2020-01-17", "time":"14:00", "values":{"yield2y":3}, "documentUrl":"official"}
        # Friday 17 January is followed by a long weekend and a Tuesday fixing.
        days = [16,17,21,22,23,24,27]
        levels = [100,108,105,103,106,108,107]
        rates = {date(2020,1,d):v for d,v in zip(days,levels)}
        row = study.event_rows([source], {"yield2y":rates})[0]
        self.assertEqual((row["nextDate"],row["fifthDate"]), ("2020-01-21","2020-01-27"))
        self.assertEqual((row["priorToEvent"],row["priorToNext"],row["priorToFifth"]), (8,5,7))
        self.assertEqual((row["eventToNext"],row["eventToFifth"]), (-3,-1))

    def test_missing_meeting_fix_does_not_roll_to_next_fix(self):
        meeting = {"date":"2020-01-17","time":"14:00","values":{"slope":4},"documentUrl":"source"}
        row = study.event_rows([meeting],{"slope":{date(2020,1,16):1,date(2020,1,20):5}})[0]
        self.assertTrue(all(row[k] is None for k in study.WINDOWS))

    def test_flat_daily_moves_included_in_denominator(self):
        rows = [dict(intradayBp=-4, change=v) for v in [-8,4,0,None]]
        s = study.summaries(rows,"change")
        self.assertEqual((s["n"],s["sameDirection"],s["oppositeDirection"],s["flat"]), (3,1,1,1))
        self.assertAlmostEqual(s["sameShare"],1/3,places=6)
        self.assertIsNone(s["correlation"])


if __name__ == "__main__":
    unittest.main()
