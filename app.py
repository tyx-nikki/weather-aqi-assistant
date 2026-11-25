import json
import os
import sqlite3
import csv
import io
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template, request

from api_client import DataError, fetch_forecasts, find_cities
from config import CACHE_SECONDS, DATABASE
from outfit import trip_hours, outfit_advice
from core import activity_window, best_hour, evaluate, merge_forecasts, select_hours
from parser import ModelServiceError, auto_parse, model_available, model_parse, rule_parse, validate

app = Flask(__name__)


@contextmanager
def db():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=10)
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, city TEXT NOT NULL,
                latitude REAL NOT NULL, longitude REAL NOT NULL, timezone TEXT NOT NULL,
                weather_json TEXT NOT NULL, air_json TEXT NOT NULL, merged_json TEXT NOT NULL,
                response_json TEXT)""")
            if "response_json" not in {row[1] for row in connection.execute("PRAGMA table_info(queries)")}:
                connection.execute("BEGIN IMMEDIATE")
                if "response_json" not in {row[1] for row in connection.execute("PRAGMA table_info(queries)")}:
                    connection.execute("ALTER TABLE queries ADD COLUMN response_json TEXT")
                connection.commit()
            connection.execute("""CREATE TABLE IF NOT EXISTS forecast_cache (
                cache_key TEXT PRIMARY KEY, fetched_at TEXT NOT NULL,
                weather_json TEXT NOT NULL, air_json TEXT NOT NULL)""")
            yield connection
    finally:
        connection.close()


@app.get("/")
def index():
    return render_template("index.html", model_available=model_available())


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/api/cities")
def cities():
    name = request.args.get("q", "").strip()
    if len(name) < 2 or len(name) > 50:
        return jsonify(error="请输入至少两个字符的城市名称"), 400
    try:
        return jsonify(cities=find_cities(name))
    except DataError as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/parse")
def parse():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="请求正文须为 JSON 对象"), 400
    if not isinstance(payload.get("text"), str):
        return jsonify(error="出行需求须为文本"), 400
    text = payload["text"].strip()
    if not 2 <= len(text) <= 300:
        return jsonify(error="请输入 2～300 字的出行需求"), 400
    method = payload.get("method", "rule")
    if method not in ("rule", "model", "auto"):
        return jsonify(error="请选择规则、AI或自动解析"), 400
    try:
        if method == "auto":
            result, used = auto_parse(text)
        else:
            result = model_parse(text) if method == "model" else rule_parse(text)
            used = method
        return jsonify(**result, method=used, requested_method=method)
    except ModelServiceError as exc:
        return jsonify(error=str(exc)), 502
    except ValueError as exc:
        return jsonify(error=str(exc)), 422


@app.post("/api/forecast")
def forecast():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="请求正文须为 JSON 对象"), 400
    if "refresh" in payload and not isinstance(payload["refresh"], bool):
        return jsonify(error="重新获取选项须为布尔值"), 400
    try:
        value = validate(payload)
        duration = payload.get("duration_hours", 1)
        if type(duration) is not int or not 1 <= duration <= 4:
            raise ValueError("活动时长须为 1 至 4 个整小时")
        value["duration_hours"] = duration
        stops = trip_hours(payload)
        if stops:
            value.update(stops)
        city = payload.get("selected_city")
        candidates = find_cities(value["city"])
        if not candidates:
            return jsonify(error="未找到该城市，请检查名称"), 404
        if city is None:
            return jsonify(candidates=candidates, needs_selection=True), 409
        city = next((x for x in candidates if x["id"] == city), None)
        if city is None:
            return jsonify(error="城市候选已失效，请重新选择"), 409
        # Reject out-of-range dates before making either forecast request.
        select_hours([], value["date"], value["period"], city["timezone"])
        today = datetime.now(ZoneInfo(city["timezone"])).date().isoformat()
        cache_key = f"{city['id']}:{city['latitude']}:{city['longitude']}:{city['timezone']}:{today}"
        with db() as connection:
            cached = connection.execute("SELECT fetched_at,weather_json,air_json FROM forecast_cache WHERE cache_key=?", (cache_key,)).fetchone()
        now = datetime.now(ZoneInfo("UTC"))
        fresh = bool(cached and 0 <= (now-datetime.fromisoformat(cached[0])).total_seconds() < CACHE_SECONDS)
        source_mode = "cache" if fresh and not payload.get("refresh") else "live"
        if source_mode == "cache":
            fetched_at, weather, air = cached[0], json.loads(cached[1]), json.loads(cached[2])
        else:
            try:
                weather, air = fetch_forecasts(city)
                merged = merge_forecasts(weather, air)
                fetched_at = datetime.now(ZoneInfo("UTC")).isoformat()
                with db() as connection:
                    connection.execute("INSERT OR REPLACE INTO forecast_cache VALUES (?,?,?,?)", (cache_key,fetched_at,json.dumps(weather,ensure_ascii=False),json.dumps(air,ensure_ascii=False)))
            except DataError:
                if not cached:
                    raise
                fetched_at, weather, air = cached[0], json.loads(cached[1]), json.loads(cached[2])
                source_mode = "stale"
        if source_mode != "live":
            merged = merge_forecasts(weather, air)
        selected = select_hours(merged, value["date"], value["period"], city["timezone"])
        if stops:
            by_time = {row["time"]: row for row in merged}
            selected = []
            for hour in stops.values():
                stamp = f"{value['date']}T{hour:02}:00"
                selected.append(by_time.get(stamp, {"time": stamp, "complete": False}))
        if not selected:
            return jsonify(error="该时段没有可用预测数据"), 404
        for row in selected:
            row["advice"] = evaluate(row, value["activity"])
        earliest = datetime.now(ZoneInfo(city["timezone"])).replace(tzinfo=None)
        result = dict(activity_window=None if stops else activity_window(selected, duration, earliest), city=city, fetched_at=fetched_at, rows=selected, query=value,
            snapshot=False, source_mode=source_mode, best_hour=best_hour(selected),
            units={"temperature_2m": "°C", "precipitation_probability": "%",
                   "wind_speed_10m": "km/h", "pm2_5": "µg/m³", "european_aqi": "European AQI"},
            sources={"weather": "Open-Meteo Weather Forecast API", "air": "Open-Meteo Air Quality API"})
        result["units"]["apparent_temperature"] = "°C"
        if stops:
            result["outfit"] = outfit_advice(selected, value["activity"])
        with db() as connection:
            cursor = connection.execute("INSERT INTO queries (fetched_at,city,latitude,longitude,timezone,weather_json,air_json,merged_json,response_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (fetched_at, city["name"], city["latitude"], city["longitude"], city["timezone"],
                 json.dumps(weather, ensure_ascii=False), json.dumps(air, ensure_ascii=False),
                 json.dumps(merged, ensure_ascii=False), json.dumps(result, ensure_ascii=False)))
            result["query_id"] = cursor.lastrowid
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except DataError as exc:
        return jsonify(error=str(exc)), 502


@app.get("/api/history")
def history():
    with db() as connection:
        rows = connection.execute("SELECT id,city,fetched_at,response_json FROM queries WHERE response_json IS NOT NULL ORDER BY id DESC LIMIT 100").fetchall()
    items, seen = [], set()
    for row in rows:
        result = json.loads(row[3])
        query = result.get("query", {})
        city_key = result.get("city", {}).get("id", row[1])
        key = (city_key, row[2], query.get("date"), query.get("period"), query.get("activity"), query.get("duration_hours", 1), query.get("departure_hour"), query.get("return_hour"))
        if key in seen:
            continue
        seen.add(key)
        items.append({"id": row[0], "city": row[1], "fetched_at": row[2], "query": query})
        if len(items) == 10:
            break
    return jsonify(items=items)


@app.get("/api/history/<int:query_id>")
def replay(query_id):
    with db() as connection:
        row = connection.execute("SELECT response_json FROM queries WHERE id=?", (query_id,)).fetchone()
    if row is None or row[0] is None:
        return jsonify(error="未找到可回放的采集快照"), 404
    result = json.loads(row[0])
    result.update(snapshot=True, query_id=query_id, source_mode="snapshot")
    result.setdefault("best_hour", best_hour(result.get("rows", [])))
    return jsonify(result)


@app.get("/api/history/<int:query_id>/export.<kind>")
def export_query(query_id, kind):
    if kind not in ("csv", "json"):
        return jsonify(error="支持CSV或JSON导出"), 400
    with db() as connection:
        row = connection.execute("SELECT response_json FROM queries WHERE id=?", (query_id,)).fetchone()
    if row is None or row[0] is None:
        return jsonify(error="未找到该记录"), 404
    if kind == "json":
        return Response(row[0], mimetype="application/json", headers={"Content-Disposition": f'attachment; filename="forecast-{query_id}.json"'})
    data = json.loads(row[0]); stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["城市", "当地时间", "气温°C", "降水概率%", "风速km/h", "PM2.5µg/m³", "European AQI", "提示", "依据", "采集时间UTC"])
    for item in data["rows"]:
        writer.writerow([data["city"]["name"], *[item.get(k, "") for k in ("time", "temperature_2m", "precipitation_probability", "wind_speed_10m", "pm2_5", "european_aqi")], item["advice"]["level"], "；".join(item["advice"]["reasons"]), data["fetched_at"]])
    return Response("\ufeff"+stream.getvalue(), content_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="forecast-{query_id}.csv"'})


@app.get("/api/health")
def health():
    with db() as connection:
        total = connection.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    return jsonify(status="ok", model_available=model_available(), stored_queries=total, cache_seconds=CACHE_SECONDS)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
