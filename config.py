import os


DATABASE = os.getenv("APP_DATABASE", os.path.join(os.path.dirname(__file__), "data", "travel.sqlite3"))
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "").rstrip("/")
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")
REQUEST_TIMEOUT = 12

# Project demonstration thresholds, not medical or official travel guidance.
THRESHOLDS = {
    "rain_caution": 40,
    "rain_avoid": 70,
    "wind_caution": 25,
    "wind_avoid": 40,
    "aqi_caution": 40,
    "aqi_avoid": 80,
    "pm25_caution": 15,
    "pm25_avoid": 50,
}
