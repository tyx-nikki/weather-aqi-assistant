from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

from config import THRESHOLDS


def _columns(payload, names):
    hourly = payload.get("hourly", {})
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("预测响应缺少有效的逐小时时间序列")
    times = hourly.get("time", [])
    if any(not isinstance(t, str) or len(t) != 16 for t in times) or len(set(times)) != len(times):
        raise ValueError("预测时间序列格式异常或包含重复小时")
    columns = {key: hourly.get(key) for key in names}
    return {
        time: {
            name: values[i] if isinstance(values, list) and i < len(values) else None
            for name, values in columns.items()
        }
        for i, time in enumerate(times)
    }


def merge_forecasts(weather, air):
    if weather.get("timezone") and air.get("timezone") and weather["timezone"] != air["timezone"]:
        raise ValueError("天气与空气质量时区不一致，不能直接按当地小时融合")
    weather_names = ("temperature_2m", "precipitation_probability", "wind_speed_10m")
    air_names = ("pm2_5", "european_aqi")
    w = _columns(weather, (*weather_names, "apparent_temperature"))
    a = _columns(air, air_names)
    rows = []
    for time in sorted(set(w) | set(a)):
        row = {"time": time, **{k: None for k in (*weather_names, *air_names)}, **w.get(time, {}), **a.get(time, {})}
        row.setdefault("apparent_temperature", None)
        for key in (*weather_names, *air_names, "apparent_temperature"):
            value = row[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or (key not in ("temperature_2m", "apparent_temperature") and value < 0)
                or (key == "precipitation_probability" and value > 100)):
                row[key] = None
        row["complete"] = all(row[k] is not None for k in (*weather_names, *air_names))
        rows.append(row)
    return rows


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


def best_hour(rows):
    usable = [row for row in rows if row.get("complete")]
    if not usable:
        return None
    chosen = min(usable, key=hour_rank)
    return {"time": chosen["time"], "level": chosen["advice"]["level"],
            "reasons": chosen["advice"]["reasons"], "method": "先比较提示等级，再比较四项指标相对阈值之和"}


def hour_rank(row):
    level = {"较适合": 0, "需留意": 1, "暂不推荐": 2}[row["advice"]["level"]]
    score = row["precipitation_probability"]/70 + row["wind_speed_10m"]/40 + row["pm2_5"]/50 + row["european_aqi"]/80
    return level, score, row["time"]


def activity_window(rows, duration, earliest):
    """Rank complete consecutive local hours within the selected period."""
    candidates = []
    blocked = set()
    for index in range(len(rows) - duration + 1):
        window = rows[index:index + duration]
        start = datetime.fromisoformat(window[0]["time"])
        if start < earliest or not all(row["complete"] for row in window):
            continue
        if any(datetime.fromisoformat(row["time"]) != start + timedelta(hours=i)
               for i, row in enumerate(window)):
            continue
        worst = max(window, key=hour_rank)
        if worst["advice"]["level"] == "暂不推荐":
            blocked.update(worst["advice"]["reasons"])
            continue
        ranks = [hour_rank(row) for row in window]
        priority = (max(rank[0] for rank in ranks), sum(rank[1] for rank in ranks), start)
        result = dict(start=window[0]["time"], end=(start + timedelta(hours=duration)).isoformat(timespec="minutes"),
                      level=worst["advice"]["level"], reasons=worst["advice"]["reasons"],
                      max_rain=max(row["precipitation_probability"] for row in window),
                      max_aqi=max(row["european_aqi"] for row in window))
        candidates.append((priority, result))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    if blocked:
        return {"message": "所有数据完整的候选时段均含暂不推荐的小时。", "reasons": sorted(blocked)}
    return {"message": "可出发的时间内没有足够的连续完整预测小时，请缩短活动或更换时段。", "reasons": []}
