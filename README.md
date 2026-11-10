# 城市天气与空气质量出行助手

课程项目第一版：用 Open-Meteo 的地理编码、天气和空气质量接口取得逐小时预测，按城市坐标、时区与小时融合，显示趋势和有依据的出行提示。自然语言输入支持规则解析；配置模型接口后可使用 AI 解析。模型仅提取采集参数，不生成天气数据。

## 运行

克隆仓库后，在仓库目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

浏览器打开 `http://127.0.0.1:5000`。先选城市、日期、时段、活动，再点击查询。地理编码返回多个结果时须选择候选城市。可输入“明天下午在上海跑步”试用规则解析。

协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交前运行 `python -m unittest discover -s tests -v`；GitHub Actions 会对推送和 Pull Request 运行相同检查。

如需启用 AI 解析，在启动前设置 `MODEL_BASE_URL`（兼容 OpenAI Chat Completions 的服务根地址，通常以 `/v1` 结尾）、`MODEL_API_KEY`、`MODEL_NAME`。例如在 PowerShell 中用 `$env:MODEL_BASE_URL=...` 设置。密钥仅放环境变量，不提交到项目。

## 数据与口径

- 天气：`temperature_2m`、`precipitation_probability`、`wind_speed_10m`。
- 空气质量：`pm2_5`、`european_aqi`。European AQI 与中国 AQI 不是同一指标。
- 查询限未来 5 天。页面内容为预测，不是现场观测；空气质量模型约 11 km 分辨率，不提供街道级判断。
- SQLite 文件在 `data/travel.sqlite3`，保存 UTC 获取时间、坐标、时区、原始接口响应和融合记录。用于复核和准备演示材料。
- 建议阈值见 `config.py`，属于项目演示规则，不是官方健康指引。缺失值不插补。

## 项目结构

`api_client.py` 调用接口；`core.py` 负责时间融合和建议；`parser.py` 负责规则／模型解析；`app.py` 提供页面与 API；`templates/` 和 `static/` 为界面。

## 汇报前验证

1. 用上海、北京等城市完成真实请求，记录页面截图和 SQLite 中的原始响应。
2. 测试同名地点选择、超出 5 天、缺少时段和接口异常。
3. 建立人工标注语句集，在同一批句子上对比规则与 AI 的字段正确率、失败率、耗时和调用成本。未配置模型时不要宣称已经完成 AI 实测。
4. 保留一份实际运行截图或录屏供现场接口异常时演示。

运行 `python evaluate_parser.py` 可生成带逐条结果与耗时的 `data/parser_evaluation.json`。未配置模型接口时只运行规则基线，不会生成虚假的模型结果。
