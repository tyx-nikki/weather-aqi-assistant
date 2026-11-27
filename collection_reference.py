"""Replay two reference tool sequences. These are scripted, not model decisions."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from api_client import AIR_FIELDS, WEATHER_FIELDS, fetch_air, fetch_weather, find_cities


def run():
    day = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    cases = [
        ("上海明早骑车上课会下雨吗", [("上海", 1796236)], range(6, 12),
         [(fetch_weather, ("precipitation_probability",))]),
        ("比较上海与杭州明天下午的跑步条件", [("上海", 1796236), ("杭州", 1808926)], range(12, 18),
         [(fetch_weather, WEATHER_FIELDS), (fetch_air, AIR_FIELDS)]),
    ]
    report = {"mode": "scripted_reference", "date": day, "cases": []}
    for question, locations, hours, calls in cases:
        trace = []
        report["cases"].append({"question": question, "trace": trace})
        for name, city_id in locations:
            start = perf_counter()
            choices = find_cities(name)
            city = next((x for x in choices if x["id"] == city_id), None)
            if city is None:
                raise ValueError(f"未找到预设演示地点 {name}")
            trace.append(dict(tool="find_cities", city=name, selected_id=city_id,
                              elapsed_ms=round((perf_counter()-start)*1000)))
            for tool, fields in calls:
                start = perf_counter()
                data = tool(city, fields, day)["hourly"]
                rows = [{field: data[field][i] for field in ("time", *fields)}
                        for i, stamp in enumerate(data["time"])
                        if datetime.fromisoformat(stamp).hour in hours]
                trace.append(dict(tool=tool.__name__, city=name, fields=fields, rows=rows,
                                  elapsed_ms=round((perf_counter()-start)*1000)))
    path = Path(__file__).parent / "data" / "collection_reference.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    run()
