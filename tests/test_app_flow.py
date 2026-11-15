import io,json,tempfile,unittest
from datetime import date,datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import app as server
import parser
from api_client import DataError
from core import best_hour
CITY=dict(id=1796236,name='上海',admin1='上海市',country='中国',latitude=31.22222,longitude=121.45806,timezone='Asia/Shanghai')

class AppFlowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(server,'DATABASE',str(Path(self.tmp.name)/'app.sqlite3'));self.dbpatch.start();self.c=server.app.test_client()
  self.day=(datetime.now(ZoneInfo('Asia/Shanghai')).date()+timedelta(days=1)).isoformat();self.query=dict(city='上海',date=self.day,period='下午',activity='跑步',selected_city=CITY['id'])
  self.w=dict(timezone='Asia/Shanghai',hourly=dict(time=[self.day+'T12:00',self.day+'T13:00'],temperature_2m=[20,21],precipitation_probability=[10,75],wind_speed_10m=[5,20]))
  self.a=dict(timezone='Asia/Shanghai',hourly=dict(time=[self.day+'T12:00',self.day+'T13:00'],pm2_5=[10,55],european_aqi=[20,70]))
 def tearDown(self):self.dbpatch.stop();self.tmp.cleanup()
 def query(self,body=None):return self.c.post('/api/forecast',json=body or self.query)
 def test_collection_cache_export_and_replay(self):
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts',return_value=(self.w,self.a)) as fetch:
   first=self.c.post('/api/forecast',json=self.query);second=self.c.post('/api/forecast',json=self.query)
   self.assertEqual(first.status_code,200);self.assertEqual(second.status_code,200);self.assertEqual(fetch.call_count,1)
  a,b=first.get_json(),second.get_json();self.assertEqual(a['source_mode'],'live');self.assertEqual(b['source_mode'],'cache');self.assertEqual(a['fetched_at'],b['fetched_at']);self.assertEqual(a['best_hour']['time'],self.day+'T12:00')
  export=self.c.get(f"/api/history/{a['query_id']}/export.csv");self.assertEqual(export.status_code,200);self.assertTrue(export.data.startswith(b'\xef\xbb\xbf'));self.assertIn('上海',export.data.decode('utf-8-sig'))
  exported=self.c.get(f"/api/history/{a['query_id']}/export.json").get_json();self.assertEqual(exported['rows'],a['rows'])
  replay=self.c.get(f"/api/history/{a['query_id']}").get_json();self.assertEqual(replay['source_mode'],'snapshot');self.assertEqual(replay['fetched_at'],a['fetched_at'])
 def test_force_refresh_fetches_again(self):
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts',return_value=(self.w,self.a)) as fetch:
   self.c.post('/api/forecast',json=self.query);r=self.c.post('/api/forecast',json={**self.query,'refresh':True});self.assertEqual(fetch.call_count,2);self.assertEqual(r.get_json()['source_mode'],'live')
 def test_upstream_failure_can_show_dated_cache(self):
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts',return_value=(self.w,self.a)):
   first=self.c.post('/api/forecast',json=self.query).get_json()
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts',side_effect=DataError('offline')):
   r=self.c.post('/api/forecast',json={**self.query,'refresh':True}).get_json()
  self.assertEqual(r['source_mode'],'stale');self.assertEqual(r['fetched_at'],first['fetched_at'])
 def test_no_cache_reports_upstream_error(self):
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts',side_effect=DataError('offline')):
   self.assertEqual(self.c.post('/api/forecast',json=self.query).status_code,502)
 def test_city_selection_before_fetch(self):
  with patch.object(server,'find_cities',return_value=[CITY]),patch.object(server,'fetch_forecasts') as fetch:
   r=self.c.post('/api/forecast',json={**self.query,'selected_city':None});self.assertEqual(r.status_code,409);self.assertTrue(r.get_json()['needs_selection']);fetch.assert_not_called()
 def test_health_and_unknown_export(self):
  self.assertEqual(self.c.get('/api/health').get_json()['status'],'ok');self.assertEqual(self.c.get('/api/history/999/export.csv').status_code,404);self.assertEqual(self.c.get('/api/history/1/export.exe').status_code,400)
 def test_non_text_and_empty_arrays(self):
  for value in [[],None,0]:self.assertEqual(self.c.post('/api/parse',json=value).status_code,400)
  self.assertEqual(self.c.post('/api/parse',json={'text':123}).status_code,400)

class ParserFlowTests(unittest.TestCase):
 def test_explicit_date_is_calculated_after_model_extracts(self):
  data={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(dict(city='杭州',date='',period='晚上',activity='骑行'),ensure_ascii=False)}}],'model':'test','usage':{}}
  with patch.object(parser,'model_available',return_value=True),patch.object(parser,'MODEL_BASE_URL','https://example.com'),patch.object(parser.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
   detail=parser.model_parse_detailed('今天晚上在杭州骑行',date(2026,11,15))
  self.assertEqual(detail['parsed']['date'],'');self.assertEqual(detail['result']['date'],'2026-11-15')
 def test_ambiguous_dates_are_not_normalized(self):
  with self.assertRaises(ValueError):parser.explicit_date('明天或者后天',date(2026,11,15))
 def test_auto_uses_rule_before_model(self):
  with patch.object(parser,'model_parse') as model:
   result,method=parser.auto_parse('明天下午在上海跑步');self.assertEqual(method,'rule');model.assert_not_called()
 def test_auto_uses_model_for_colloquial_input(self):
  expected=dict(city='上海',date='2026-11-16',period='下午',activity='跑步')
  with patch.object(parser,'model_available',return_value=True),patch.object(parser,'model_parse',return_value=expected) as model:
   result,method=parser.auto_parse('明天下午想去上海跑个步');self.assertEqual(method,'model');self.assertEqual(result,expected);model.assert_called_once()
 def test_city_with_he_character(self):
  self.assertEqual(parser.rule_parse('明天下午在呼和浩特跑步')['city'],'呼和浩特')
 def test_best_hour_excludes_incomplete_rows(self):
  self.assertIsNone(best_hour([{'complete':False}]))

if __name__=='__main__':unittest.main()
