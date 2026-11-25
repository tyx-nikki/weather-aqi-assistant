import unittest

from outfit import outfit_advice, trip_hours


class TripTests(unittest.TestCase):
    def test_return_must_follow_departure(self):
        for hours in [(8, 8), (18, 8), (None, 18)]:
            with self.assertRaises(ValueError):
                trip_hours(dict(zip(("departure_hour", "return_hour"), hours)))

    def test_rain_gear_depends_on_return_forecast_and_activity(self):
        outbound = dict(time="08:00", apparent_temperature=13, precipitation_probability=10, wind_speed_10m=5)
        inbound = dict(outbound, time="18:00", apparent_temperature=7, precipitation_probability=70)
        for activity, gear in [("骑行", "雨衣"), ("步行", "雨伞")]:
            legs = outfit_advice([outbound, inbound], activity)
            self.assertNotIn(gear, str(legs[0]))
            self.assertIn(gear, str(legs[1]))
            self.assertIn("降温 6°C", str(legs[1]))
            self.assertEqual(outfit_advice([outbound], activity), legs[:1])

    def test_missing_temperature_keeps_rain_evidence(self):
        leg = outfit_advice([dict(time="08:00", precipitation_probability=75)], "骑行")[0]
        self.assertIn("缺少体感预测", leg["notes"])
        self.assertIn("75%", str(leg))
