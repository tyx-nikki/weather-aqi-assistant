import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from core import merge_forecasts
from parser import ModelServiceError, rule_parse, validate
import app as server

CITY=dict(id=1796236,name='上海',admin1='上海市',country='中国',latitude=31.22222,longitude=121.45806,timezone='Asia/Shanghai')

class StageOneTests(unittest.TestCase):
    def test_real_date_and_string_types_required(self):
        for value in [dict(city=None,date='2026-11-15',period='下午',activity='跑步'),dict(city='上海',date='2026-02-30',period='下午',activity='跑步'),dict(city='上海',date='2026-11-15T12:00',period='下午',activity='跑步')]:
            with self.subTest(value=value),self.assertRaises(ValueError):validate(value)

    def test_after_tomorrow_and_full_day(self):
        self.assertEqual(rule_parse('后天全天在上海跑步',date(2026,11,15))['date'],'2026-11-17')

    def test_rule_abstains_on_multiple_dates_cities_and_periods(self):
        for text in ['明天或后天下午在上海跑步','明天下午在上海或者北京跑步','明天上午或者下午在上海跑步']:
            with self.subTest(text=text),self.assertRaises(ValueError):rule_parse(text)

    def test_timezones_cannot_be_silently_merged(self):
        with self.assertRaises(ValueError):merge_forecasts({'timezone':'UTC'},{'timezone':'Asia/Shanghai'})

    def test_invalid_numbers_do_not_become_safe_advice(self):
        w={'hourly':{'time':['2026-11-15T12:00'],'temperature_2m':[20],'precipitation_probability':[101],'wind_speed_10m':[10]}}
        a={'hourly':{'time':['2026-11-15T12:00'],'pm2_5':[-1],'european_aqi':[float('nan')]}}
        row=merge_forecasts(w,a)[0]
        self.assertFalse(row['complete']);self.assertIsNone(row['pm2_5']);self.assertIsNone(row['european_aqi'])

    def test_service_error_is_not_a_clarification(self):
        with patch.object(server,'model_parse',side_effect=ModelServiceError('模型接口 HTTP 503')):
            result=server.app.test_client().post('/api/parse',json={'text':'明天下午在上海跑步','method':'model'})
            self.assertEqual(result.status_code,502)

    def test_non_object_json(self):
        for path in ['/api/parse','/api/forecast']:
            self.assertEqual(server.app.test_client().post(path,json=['wrong']).status_code,400)

    def test_snapshot_is_replayed_without_network_and_keeps_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(server,'DATABASE',str(Path(tmp)/'history.sqlite3')):
            c=server.app.test_client();old='2026-11-10T00:00:00+00:00'
            value=dict(city=CITY,fetched_at=old,rows=[],query={'date':'2026-11-11'},snapshot=False)
            with server.db() as con:
                con.execute('INSERT INTO queries(fetched_at,city,latitude,longitude,timezone,weather_json,air_json,merged_json,response_json) VALUES(?,?,?,?,?,?,?,?,?)',(old,'上海',31.,121.,'Asia/Shanghai','{}','{}','[]',json.dumps(value)))
            with patch.object(server,'fetch_forecasts',side_effect=AssertionError('network must not be called')),patch.object(server,'find_cities',side_effect=AssertionError('network must not be called')):
                result=c.get('/api/history/1').get_json()
            self.assertTrue(result['snapshot']);self.assertEqual(result['fetched_at'],old)
            self.assertEqual(len(c.get('/api/history').get_json()['items']),1)
            self.assertEqual(c.get('/api/history/999').status_code,404)

    def test_future_limit_rejects_before_forecast(self):
        c=server.app.test_client()
        with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts') as fetch:
            result=c.post('/api/forecast',json=dict(city='上海',date='2099-01-01',period='下午',activity='跑步',selected_city=CITY['id']))
            self.assertEqual(result.status_code,400);fetch.assert_not_called()

if __name__=='__main__':unittest.main()
