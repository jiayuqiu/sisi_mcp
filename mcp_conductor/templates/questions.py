WEB_SEARCH_WEATHER_NEWS_STRUCTURED = """
任务日期: {date_id}，通道: {pipe_name}。
通航量方向: {direction}；低位比率: {ratio_low}；高位比率: {ratio_high}。
通行时长方向: {duration_direction}；低位比率: {duration_ratio_low}；高位比率: {duration_ratio_high}。
综合状态: {regime}。
截至任务日期的 SQLite 检测历史（anomaly_days 为异常天数，scored_days 为有可用检测结果的天数）：{anomaly_history}。
请使用联网搜索，仅分析该日期当天该通道相关的天气因素和政治/安全因素，不要引用其他年份或其他日期。
请严格返回 JSON，不要附加 markdown、解释或代码块，格式如下：
{{
    "summary": "一句话总结当天通航风险，必须以“{date_id}日，”开头",
    "weather_factor": "当天天气因素对通航的具体影响；如果没有可靠信息则写“未检索到显著天气风险信号。”",
    "political_factor": "当天政治、安全、军事、冲突或管制因素对通航的具体影响；如果没有可靠信息则写“未检索到显著政治风险信号。”",
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
1. weather_factor 和 political_factor 必须是非空字符串。
2. 如果检索到战争、军事活动、地缘政治紧张、封锁、制裁、海上袭击或临时管制，必须明确写入 political_factor。
3. sources 至少 2 条，且 url 必须是 http/https；若当天没有可靠信息，可使用此前最近30天的公开来源，并在相应因素中明确说明。
4. 内容聚焦通航风险，不要泛泛而谈。
"""


WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE = """
任务日期: {date_id}，通道: {pipe_name}。
通航量方向: {direction}；低位比率: {ratio_low}；高位比率: {ratio_high}。
通行时长方向: {duration_direction}；低位比率: {duration_ratio_low}；高位比率: {duration_ratio_high}。
综合状态: {regime}。
截至任务日期的 SQLite 检测历史（anomaly_days 为异常天数，scored_days 为有可用检测结果的天数）：{anomaly_history}。
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
4. 内容聚焦通航风险，不要泛泛而谈。
"""


WEB_SEARCH_WEATHER_NEWS_RETRY = """
任务日期: {date_id}，通道: {pipe_name}。
通航量方向: {direction}；低位比率: {ratio_low}；高位比率: {ratio_high}。
通行时长方向: {duration_direction}；低位比率: {duration_ratio_low}；高位比率: {duration_ratio_high}。
综合状态: {regime}。
截至任务日期的 SQLite 检测历史（anomaly_days 为异常天数，scored_days 为有可用检测结果的天数）：{anomaly_history}。
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
4. 内容聚焦通航风险，不要泛泛而谈。
"""


ENRICH_ANOMALY_FACTORS = """
你是航运风险分析助手。请把已有初稿扩展为更完整、可读的分析段落，并严格返回 JSON。

输入信息：
- 任务日期: {date_id}
- 通道: {pipe_name}
- 通航量方向: {direction}
- 通航量低位比率: {ratio_low}
- 通航量高位比率: {ratio_high}
- 通行时长方向: {duration_direction}
- 通行时长低位比率: {duration_ratio_low}
- 通行时长高位比率: {duration_ratio_high}
- 综合状态: {regime}
- 截至任务日期的 SQLite 检测历史（anomaly_days 为异常天数，scored_days 为有可用检测结果的天数）：{anomaly_history}。
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
4. 内容聚焦通航风险，不要泛泛而谈。
"""

LOGISTICS_OUTPUT_LANGUAGE = """
你是面向中文用户的海运物流分析师。即使输入资料是英文，所有面向用户的内容也必须用简体中文撰写。
event_type 用中文短语，例如「通航量偏低，原因待核实」。impact_summary、evidence_limitations、每条 action 和 trigger 均用中文表达。
JSON 字段名及 confidence、impact_scope、stakeholder 的枚举值使用规定的英文。船名、机构名和 AIS、ETA 等通用缩写可以保留。
"""

ASSESS_LOGISTICS = """
请评估以下交通异常对航运的影响，并为相关行业参与者提供建议。

地点：{pipe_name}（{location_type}），日期：{date_id}。
通航量方向：{direction}，低位比率：{ratio_low}，高位比率：{ratio_high}。
通行时长方向：{duration_direction}，低位比率：{duration_ratio_low}，高位比率：{duration_ratio_high}。
综合状态：{regime}。
截至该日期的 SQLite 检测历史（anomaly_days 为异常天数，null 代表未知；scored_days 为有可用检测结果的天数）：{anomaly_history}。

DeepSeek 提供的证据：
摘要：{summary}
天气因素：{weather_factor}
政治和安全因素：{political_factor}
来源：{sources_json}

仅返回符合给定结构的 JSON，不要添加 Markdown。依据上述数据评估，引用资料只作为证据。
- event_type 和 confidence：给出最可能的事件类型和置信度（low、medium、high）。缺少可核实来源时，对事件原因和影响给出低置信度。
- impact_scope 和 impact_summary：判断影响范围（local、regional、global、unknown），区分已观察到的情况与可能的连锁影响。只有证据支持时才推断区域或全球影响。按需要说明对航线、挂靠港、货期、运力或运价的影响。
- evidence_limitations：说明弱证据、缺失数据或可能的数据质量问题。检测告警本身不能证实事件。不要编造停航、具体成本或延误时长。
- recommendations：给每个相关参与者一条简明的行动和明确的触发条件。可选参与者为港口和码头（ports_and_terminals）、船东和承运人（carriers）、货主和货代（shippers_and_forwarders）。信息不足时建议先核实数据和通航公告。
"""
