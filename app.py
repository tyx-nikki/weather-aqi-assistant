import json
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request

from api_client import DataError, fetch_forecasts, find_cities
from config import DATABASE
from core import evaluate, merge_forecasts, select_hours
from parser import model_available, model_parse, rule_parse, validate

app = Flask(__name__)


def db():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute("""CREATE TABLE IF NOT EXISTS queries (
        id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, city TEXT NOT NULL,
        latitude REAL NOT NULL, longitude REAL NOT NULL, timezone TEXT NOT NULL,
        weather_json TEXT NOT NULL, air_json TEXT NOT NULL, merged_json TEXT NOT NULL)""")
    return connection


@app.get("/")
def index():
    return render_template("index.html", model_available=model_available())


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
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not 2 <= len(text) <= 300:
        return jsonify(error="请输入 2～300 字的出行需求"), 400
    method = payload.get("method", "rule")
    if method not in ("rule", "model"):
        return jsonify(error="解析方式只能是 rule 或 model"), 400
    try:
        result = model_parse(text) if method == "model" else rule_parse(text)
        return jsonify(**result, method=method)
    except ValueError as exc:
        return jsonify(error=str(exc)), 422


@app.post("/api/forecast")
def forecast():
    payload = request.get_json(silent=True) or {}
    try:
        value = validate(payload)
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
        weather, air = fetch_forecasts(city)
        merged = merge_forecasts(weather, air)
        selected = select_hours(merged, value["date"], value["period"], city["timezone"])
        if not selected:
            return jsonify(error="该时段没有可用预测数据"), 404
        for row in selected:
            row["advice"] = evaluate(row, value["activity"])
        fetched_at = datetime.now(ZoneInfo("UTC")).isoformat()
        with db() as connection:
            connection.execute("INSERT INTO queries (fetched_at,city,latitude,longitude,timezone,weather_json,air_json,merged_json) VALUES (?,?,?,?,?,?,?,?)",
                (fetched_at, city["name"], city["latitude"], city["longitude"], city["timezone"],
                 json.dumps(weather, ensure_ascii=False), json.dumps(air, ensure_ascii=False),
                 json.dumps(merged, ensure_ascii=False)))
        return jsonify(city=city, fetched_at=fetched_at, rows=selected,
            units={"temperature_2m": "°C", "precipitation_probability": "%",
                   "wind_speed_10m": "km/h", "pm2_5": "µg/m³", "european_aqi": "European AQI"},
            sources={"weather": "Open-Meteo Weather Forecast API",
                     "air": "Open-Meteo Air Quality API"})
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except DataError as exc:
        return jsonify(error=str(exc)), 502


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
