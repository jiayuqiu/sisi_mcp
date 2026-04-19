WEB_SEARCH_WEATHER_NEWS = """
    任务日期: {date_id}，通道: {pipe_name}。
    请仅分析该日期当天的天气与相关新闻风险，不要引用其他年份或其他日期。
    输出要求：第一句必须以“{date_id}日，”开头；总字数控制在150字内，聚焦通航风险。
"""


WEB_SEARCH_WEATHER_NEWS_STRUCTURED = """
任务日期: {date_id}，通道: {pipe_name}。
请使用联网搜索，仅分析该日期当天该通道相关的天气因素和政治/安全因素，不要引用其他年份或其他日期。
请严格返回 JSON，不要附加 markdown、解释或代码块，格式如下：
{{
    "summary": "一句话总结当天通航风险，必须以“{date_id}日，”开头",
    "weather_factor": "当天天气因素对通航的具体影响；如果没有可靠信息则写“未检索到显著天气风险信号。”",
    "political_factor": "当天政治、安全、军事、冲突或管制因素对通航的具体影响；如果没有可靠信息则写“未检索到显著政治风险信号。”"
}}
要求：
1. weather_factor 和 political_factor 必须是非空字符串。
2. 如果检索到战争、军事活动、地缘政治紧张、封锁、制裁、海上袭击或临时管制，必须明确写入 political_factor。
3. 内容聚焦通航风险，不要泛泛而谈。
"""


WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE = """
任务日期: {date_id}，通道: {pipe_name}。
请先联网搜索，再输出结论。必须提供可核验来源。
请严格返回 JSON，不要附加 markdown、解释或代码块，格式如下：
{{
    "summary": "一句话总结当天通航风险，必须以“{date_id}日，”开头",
    "weather_factor": "当天天气因素对通航的具体影响；如果没有可靠信息则写“未检索到显著天气风险信号。”",
    "political_factor": "当天政治/安全/军事因素对通航的具体影响；如果没有可靠信息则写“未检索到显著政治风险信号。”",
    "sources": [
        {{
            "title": "来源标题",
            "url": "https://...",
            "published_date": "YYYY-MM-DD",
            "snippet": "与通航风险相关的简短证据"
        }}
    ]
}}
要求：
1. sources 至少 2 条，且 url 必须是 http/https。
2. 若任务日期是未来日期，允许使用“最近30天可得信息”进行风险代理判断，并在 summary 中说明“基于最近可得信息”。
3. 如果 sources 无有效条目，禁止输出“通航风险较低”这类确定性判断。
"""


WEB_SEARCH_WEATHER_NEWS_RETRY = """
任务日期: {date_id}，通道: {pipe_name}。
上一次回答缺乏有效证据。请重新联网搜索并只输出 JSON：
{{
    "summary": "一句话总结，必须以“{date_id}日，”开头",
    "weather_factor": "天气因素",
    "political_factor": "政治/安全因素",
    "sources": [
        {{"title": "", "url": "https://...", "published_date": "YYYY-MM-DD", "snippet": ""}}
    ]
}}
要求：
1. sources 至少 2 条。
2. 若无法获得当天信息，使用最近30天公开报道并明确写入 political_factor。
3. 不要输出“未检索到显著政治风险信号。”，除非 sources 明确显示无相关事件。
"""


ENRICH_ANOMALY_FACTORS = """
你是航运风险分析助手。请把已有初稿扩展为更完整、可读的分析段落，并严格返回 JSON。

输入信息：
- 任务日期: {date_id}
- 通道: {pipe_name}
- summary: {summary}
- weather_factor: {weather_factor}
- political_factor: {political_factor}
- sources_json: {sources_json}

输出格式（仅 JSON，不要 markdown）：
{{
    "weather_factor": "80-180字，说明天气/海况对能见度、航速或航线的影响；若证据不足可用‘根据历史同期与近期预报’表述，但不要只给一句空话。",
    "political_factor": "100-220字，说明地缘政治/军事/安全活动对通航不确定性的影响；如果是未来日期且缺少当天证据，明确写‘基于最近30天公开信息’并给出可能机制。"
}}
要求：
1. 中文输出，保持专业简洁。
2. 不要输出“我是AI无法联网”等元话术。
3. 不要编造具体伤亡/战果等无法核验细节。
"""