import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import evaluate, merge_forecasts
from parser import rule_parse


class CoreTests(unittest.TestCase):
    def test_merges_by_hour_and_preserves_missing_data(self):
        weather = {"hourly": {"time": ["2026-11-12T12:00"], "temperature_2m": [20],
                              "precipitation_probability": [80], "wind_speed_10m": [10]}}
        air = {"hourly": {"time": ["2026-11-12T13:00"], "pm2_5": [10], "european_aqi": [20]}}
        rows = merge_forecasts(weather, air)
        self.assertEqual([row["time"] for row in rows], ["2026-11-12T12:00", "2026-11-12T13:00"])
        self.assertFalse(any(row["complete"] for row in rows))
        self.assertTrue(all(evaluate(row, "跑步")["level"] == "数据不完整" for row in rows))

    def test_recommendation_exposes_trigger(self):
        row = {"complete": True, "temperature_2m": 22, "precipitation_probability": 75,
               "wind_speed_10m": 5, "pm2_5": 8, "european_aqi": 20}
        result = evaluate(row, "跑步")
        self.assertEqual(result["level"], "暂不推荐")
        self.assertIn("75%", result["reasons"][0])

    def test_rule_parser_requires_missing_fields(self):
        with self.assertRaises(ValueError):
            rule_parse("明天下午跑步")


if __name__ == "__main__":
    unittest.main()
