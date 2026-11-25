"""Clothing suggestions for individual legs using project forecast thresholds."""
from config import THRESHOLDS

CLOTHING_BANDS = [(8, "厚外套"), (16, "长袖加外套"), (24, "轻薄长袖")]
COOLING_DROP = 5


def trip_hours(payload):
    hours = {}
    for key in ("departure_hour", "return_hour"):
        hour = payload.get(key)
        if hour is None:
            continue
        if type(hour) is not int or not 0 <= hour <= 23:
            raise ValueError("请选择 0 至 23 的当地整点")
        hours[key] = hour
    if "return_hour" in hours and ("departure_hour" not in hours or hours["return_hour"] <= hours["departure_hour"]):
        raise ValueError("当日返程须晚于出门整点")
    return hours


def outfit_advice(rows, activity):
    result = []
    departure_temp = rows[0].get("apparent_temperature")
    for i, row in enumerate(rows):
        notes = []
        temp = row.get("apparent_temperature")
        if temp is None:
            notes.append("缺少体感预测")
        else:
            clothing = next((wear for upper, wear in CLOTHING_BANDS if temp < upper), "轻薄短袖")
            notes.append(f"体感 {temp}°C，建议穿{clothing}")
            if i and departure_temp is not None and departure_temp - temp >= COOLING_DROP:
                notes.append(f"较出门降温 {departure_temp-temp:g}°C，出门时多带一件外层")
        rain, wind = row.get("precipitation_probability"), row.get("wind_speed_10m")
        if rain is None:
            notes.append("缺少降水预测")
        elif rain >= THRESHOLDS["rain_caution"]:
            gear = "雨衣" if activity == "骑行" else "雨伞"
            notes.append(f"降水概率 {rain}%，出门时带{gear}")
        if wind is None:
            notes.append("缺少风速预测")
        elif wind >= THRESHOLDS["wind_caution"]:
            notes.append(f"风速 {wind} km/h，带防风外层")
        result.append(dict(time=row["time"], label="返程" if i else "去程", notes=notes))
    return result
