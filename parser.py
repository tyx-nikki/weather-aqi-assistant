import json
import re
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import MODEL_API_KEY, MODEL_BASE_URL, MODEL_NAME, REQUEST_TIMEOUT


ACTIVITIES = ("跑步", "步行", "通勤", "骑行")
PERIODS = ("上午", "下午", "晚上", "全天")


def validate(value):
    if not isinstance(value, dict):
        raise ValueError("解析结果不是对象")
    city = str(value.get("city", "")).strip()
    day = str(value.get("date", "")).strip()
    period = value.get("period")
    activity = value.get("activity")
    if not 1 <= len(city) <= 50 or not re.fullmatch(r"[\w\u4e00-\u9fff ·-]+", city):
        raise ValueError("请明确填写城市")
    try:
        datetime.fromisoformat(day).date()
    except ValueError as exc:
        raise ValueError("日期须为 YYYY-MM-DD") from exc
    if period not in PERIODS or activity not in ACTIVITIES:
        raise ValueError("请明确出行时段和活动类型")
    return {"city": city, "date": day, "period": period, "activity": activity}


def rule_parse(text):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    day = today + timedelta(days=1 if "明天" in text else 0)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if date_match:
        day = datetime.fromisoformat(date_match.group(1)).date()
    elif "今天" not in text and "明天" not in text:
        raise ValueError("请说明今天、明天或具体日期")
    period = next((x for x in PERIODS[:-1] if x in text), None)
    if period is None:
        raise ValueError("请说明上午、下午或晚上")
    activity = next((x for x in ACTIVITIES if x in text), None)
    if activity is None:
        raise ValueError("请说明跑步、步行、通勤或骑行")
    match = re.search(r"(?:在|去)([\u4e00-\u9fffA-Za-z· ]{2,30}?)(?:跑步|步行|通勤|骑行|，|。|$)", text)
    if not match:
        raise ValueError("请用“在上海跑步”这样的表达明确城市")
    city = match.group(1).strip()
    return validate({"city": city, "date": day.isoformat(), "period": period, "activity": activity})


def model_available():
    return bool(MODEL_BASE_URL and MODEL_API_KEY and MODEL_NAME)


def model_parse(text):
    if not model_available():
        raise ValueError("尚未配置模型接口")
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    body = {"model": MODEL_NAME, "temperature": 0,
            "messages": [
                {"role": "system", "content": f"今天是北京时间 {today}。仅从用户句子抽取 city、date(YYYY-MM-DD)、period(上午/下午/晚上/全天)、activity(跑步/步行/通勤/骑行)。缺失或歧义字段填空字符串。只返回 JSON 对象，不推测天气数据。"},
                {"role": "user", "content": text}]}
    request = urllib.request.Request(MODEL_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + MODEL_API_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.load(response)
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        return validate(json.loads(content))
    except Exception as exc:
        raise ValueError(f"模型解析失败：{exc}") from exc
