from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import THRESHOLDS


def _columns(payload, names):
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    return {time: {name: hourly.get(name, [None] * len(times))[i]
                   if i < len(hourly.get(name, [])) else None for name in names}
            for i, time in enumerate(times)}


def merge_forecasts(weather, air):
    weather_names = ("temperature_2m", "precipitation_probability", "wind_speed_10m")
    air_names = ("pm2_5", "european_aqi")
    w = _columns(weather, weather_names)
    a = _columns(air, air_names)
    return [{"time": time, **w.get(time, {}), **a.get(time, {}),
             "complete": time in w and time in a and
             all(value is not None for value in [*w.get(time, {}).values(), *a.get(time, {}).values()])}
            for time in sorted(set(w) | set(a))]


def evaluate(row, activity):
    if not row["complete"]:
        return {"level": "数据不完整", "reasons": ["该小时缺少天气或空气质量预测"]}
    t = THRESHOLDS
    reasons = []
    level = 0
    for key, label, caution, avoid, unit in (
        ("precipitation_probability", "降水概率", t["rain_caution"], t["rain_avoid"], "%"),
        ("wind_speed_10m", "风速", t["wind_caution"], t["wind_avoid"], "km/h"),
        ("european_aqi", "European AQI", t["aqi_caution"], t["aqi_avoid"], ""),
        ("pm2_5", "PM2.5", t["pm25_caution"], t["pm25_avoid"], "µg/m³"),
    ):
        value = row[key]
        if value >= avoid:
            level = max(level, 2)
            reasons.append(f"{label} {value}{unit}（达到项目暂不推荐阈值 {avoid}{unit}）")
        elif value >= caution:
            level = max(level, 1)
            reasons.append(f"{label} {value}{unit}（达到项目留意阈值 {caution}{unit}）")
    if activity == "跑步" and row["temperature_2m"] >= 32:
        level = max(level, 1)
        reasons.append(f"气温 {row['temperature_2m']}°C（跑步时留意高温）")
    return {"level": ["较适合", "需留意", "暂不推荐"][level],
            "reasons": reasons or ["所选指标未达到项目风险阈值"]}


def select_hours(rows, day, period, timezone):
    today = datetime.now(ZoneInfo(timezone)).date()
    target = datetime.fromisoformat(day).date()
    if not today <= target <= today + timedelta(days=4):
        raise ValueError("请选择当地日期起未来 5 天内的日期")
    hours = {"全天": range(24), "上午": range(6, 12), "下午": range(12, 18),
             "晚上": range(18, 24)}[period]
    return [row for row in rows if row["time"][:10] == day and int(row["time"][11:13]) in hours]
