"""Run the same labeled inputs through the rule parser and optional model parser."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from parser import model_available, model_parse, rule_parse


def cases():
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    return [
        ("明天下午在上海跑步", {"city": "上海", "date": tomorrow, "period": "下午", "activity": "跑步"}),
        ("明天上午去北京步行", {"city": "北京", "date": tomorrow, "period": "上午", "activity": "步行"}),
        ("明天晚上在杭州骑行", {"city": "杭州", "date": tomorrow, "period": "晚上", "activity": "骑行"}),
        ("明天下午在广州通勤", {"city": "广州", "date": tomorrow, "period": "下午", "activity": "通勤"}),
        ("明天下午想去上海跑个步", {"city": "上海", "date": tomorrow, "period": "下午", "activity": "跑步"}),
        ("明天下午上海适合跑步吗", {"city": "上海", "date": tomorrow, "period": "下午", "activity": "跑步"}),
        ("明天下午跑步", None),
        ("在上海跑步", None),
        ("明天在上海跑步", None),
        ("明天下午在上海活动", None),
    ]


def run(method, function, labeled):
    results = []
    for text, expected in labeled:
        start = time.perf_counter()
        try:
            result = function(text)
            error = None
        except ValueError as exc:
            result, error = None, str(exc)
        results.append({"input": text, "expected": expected, "actual": result,
                        "correct": result == expected, "error": error,
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)})
    print(f"{method}: {sum(x['correct'] for x in results)}/{len(results)} 条完全正确，平均耗时 {sum(x['elapsed_ms'] for x in results)/len(results):.2f} ms")
    return results


if __name__ == "__main__":
    labeled = cases()
    report = {"generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
              "rule": run("规则", rule_parse, labeled)}
    if model_available():
        report["model"] = run("模型", model_parse, labeled)
    else:
        print("模型接口未配置，跳过模型实测。")
    path = Path(__file__).parent / "data" / "parser_evaluation.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详细结果：{path}")
