import json
import urllib.error
import urllib.parse
import urllib.request

from config import REQUEST_TIMEOUT


class DataError(Exception):
    pass


def get_json(base_url, params):
    url = base_url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "course-travel-assistant/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise DataError(f"数据接口暂时不可用：{exc}") from exc


def find_cities(name):
    data = get_json("https://geocoding-api.open-meteo.com/v1/search", {
        "name": name, "count": 10, "language": "zh", "format": "json"
    })
    return [
        {"id": item["id"], "name": item["name"], "admin1": item.get("admin1", ""),
         "country": item.get("country", ""), "latitude": item["latitude"],
         "longitude": item["longitude"], "timezone": item.get("timezone", "auto")}
        for item in data.get("results", [])
    ]


def fetch_forecasts(city):
    common = {"latitude": city["latitude"], "longitude": city["longitude"],
              "timezone": city["timezone"], "forecast_days": 5}
    weather = get_json("https://api.open-meteo.com/v1/forecast", {
        **common, "hourly": "temperature_2m,precipitation_probability,wind_speed_10m"
    })
    air = get_json("https://air-quality-api.open-meteo.com/v1/air-quality", {
        **common, "hourly": "pm2_5,european_aqi"
    })
    return weather, air
