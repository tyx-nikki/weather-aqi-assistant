# 城市天气与空气质量出行助手

将同一城市的逐小时天气与空气质量预测合并显示，便于比较出行时段。支持手动填写、规则解析、AI 解析和自动解析，也可查看历史查询或下载 CSV、JSON。

## 启动

需要 Python 3.11 或更新版本。在 Windows PowerShell 中进入源码目录后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

也可以运行 `run.ps1`。浏览器打开 `http://127.0.0.1:5000`，填写城市、日期、时段和活动后查询。输入“明天下午在上海跑步”可试用规则解析。AI 配置完成后，可输入“明天下午想去上海跑个步”试用自动解析。

## 配置 AI 解析

在启动服务的同一 PowerShell 窗口中设置三个环境变量。以 DeepSeek 为例：

```powershell
$env:MODEL_BASE_URL = 'https://api.deepseek.com'
$env:MODEL_NAME = 'deepseek-flash'
$taskKey = Read-Host 'DeepSeek API Key' -AsSecureString
$env:MODEL_API_KEY = [System.Net.NetworkCredential]::new('', $taskKey).Password
.\.venv\Scripts\python.exe app.py
```

自动解析先尝试规则，未匹配时交给模型。手动表单、规则解析和历史查询可直接使用。模型配置从环境变量读取。

## 查询与数据

- 项目按城市当地日期提供包含当天在内的 5 天查询。天气字段为气温、降水概率和 10 米风速，空气质量字段为 PM2.5 和 European AQI。
- 选定城市后，以同一坐标和时区请求 Open-Meteo 的两类预测接口。按小时对齐数据，缺失字段显示为空。
- 相对优选小时先按项目提示等级排序，再比较降水、风速、PM2.5 和 European AQI 的相对阈值评分。
- 预测缓存有效期为 15 分钟。勾选“重新获取最新预测”可直接请求接口。若接口暂不可用而有同一发起日的缓存，页面显示已有预测并标明获取时间。
- `data/travel.sqlite3` 保存采集时间、原始响应与查询结果。包含示例数据库的版本可直接查看上海和北京的历史查询。CSV、JSON 导出链接位于逐小时结果上方。

数据来源：[Open-Meteo 天气](https://open-meteo.com/en/docs)、[Open-Meteo 空气质量](https://open-meteo.com/en/docs/air-quality-api)和[CAMS](https://atmosphere.copernicus.eu/)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluate_parser.py --date 2026-11-15
```

评测脚本用同一批 48 条标注语句运行规则与模型解析流程，结果写入 `data/parser_evaluation.json` 和 `data/parser_evaluation.csv`。参数 `--rule-only` 用于单独运行规则基线。模型评测使用 API 额度。

## 连续出行时段

在表单选择 1 至 4 小时的活动时长。查询会在所选日期和时段内比较仍可出发的整点，要求每个小时预测完整、时间连续。包含“暂不推荐”小时的组合会被排除。候选时段先比较最差小时的提示等级，再比较各小时的四项指标评分总和，同分时优先较早出发。结束时间表示活动结束的当地整点。新查询的推荐随历史快照和 JSON 导出保存。
