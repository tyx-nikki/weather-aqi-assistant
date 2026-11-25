import json
import urllib.error
import urllib.parse
import urllib.request
import time
from threading import Lock

from config import REQUEST_TIMEOUT


class DataError(Exception):
    pass


_city_cache = {}
_cache_lock = Lock()


def get_json(base_url, params):
    url = base_url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "course-travel-assistant/1.0"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = json.load(response)
            if not isinstance(data, dict) or data.get("error"):
                raise DataError("数据接口返回了无效响应")
            return data
        except urllib.error.HTTPError as exc:
            if attempt == 0 and (exc.code == 429 or exc.code >= 500):
                time.sleep(.3)
                continue
            raise DataError(f"数据接口请求失败（HTTP {exc.code}），请稍后重试") from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt == 0:
                time.sleep(.3)
                continue
            raise DataError("数据接口连接超时或响应异常，请重试或查看历史记录") from None


def find_cities(name):
    with _cache_lock:
        cached = _city_cache.get(name)
        if cached and time.monotonic() - cached[0] < 86400:
            return [dict(item) for item in cached[1]]
    data = get_json("https://geocoding-api.open-meteo.com/v1/search", {
        "name": name, "count": 10, "language": "zh", "format": "json"
    })
    cities = [
        {"id": item["id"], "name": item["name"], "admin1": item.get("admin1", ""),
         "country": item.get("country", ""), "latitude": item["latitude"],
         "longitude": item["longitude"], "timezone": item.get("timezone", "auto")}
        for item in data.get("results", [])
    ]
    with _cache_lock:
        _city_cache[name] = (time.monotonic(), cities)
    return cities


def fetch_forecasts(city):
    common = {"latitude": city["latitude"], "longitude": city["longitude"],
              "timezone": city["timezone"], "forecast_days": 5}
    weather = get_json("https://api.open-meteo.com/v1/forecast", {
        **common, "hourly": "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m"
    })
    air = get_json("https://air-quality-api.open-meteo.com/v1/air-quality", {
        **common, "hourly": "pm2_5,european_aqi"
    })
    return weather, air
