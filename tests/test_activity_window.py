from datetime import datetime
import unittest

from core import activity_window, evaluate


def hour(n, rain=5, complete=True):
    row = dict(time=f"2026-11-20T{n:02}:00", temperature_2m=20, complete=complete,
               precipitation_probability=rain, wind_speed_10m=5, pm2_5=5, european_aqi=10)
    row["advice"] = evaluate(row, "骑行")
    return row


class ActivityWindowTests(unittest.TestCase):
    earliest = datetime(2026, 11, 20, 11, 30)

    def test_ranks_whole_window_and_reports_exclusive_end(self):
        rows = [hour(12, 50), hour(13, 20), hour(14, 10)]
        result = activity_window(rows, 2, self.earliest)
        self.assertEqual((result["start"], result["end"]), (rows[1]["time"], "2026-11-20T15:00"))
        self.assertEqual(result["max_rain"], 20)

    def test_cannot_bridge_gap_or_missing_metrics(self):
        for rows in ([hour(12), hour(14)], [hour(12), hour(13, complete=False), hour(14)]):
            self.assertNotIn("start", activity_window(rows, 2, self.earliest))

    def test_rejects_every_window_containing_severe_hour(self):
        result = activity_window([hour(12), hour(13, 90), hour(14)], 2, self.earliest)
        self.assertNotIn("start", result)
        self.assertIn("90%", result["reasons"][0])

    def test_excludes_departures_in_the_past(self):
        self.assertNotIn("start", activity_window([hour(11), hour(12)], 2, self.earliest))
