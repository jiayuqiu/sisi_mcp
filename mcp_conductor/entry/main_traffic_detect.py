"""
This script is to 1. combine the changepoints detector with deepseek and sisi-ai.
Once we find the changepoints from pipe data, ask deepseek with web search to get weather and news around the pipe.
Finally, feed the text of weather and news into sisi-ai to rephase, summay and tranlate the text into chinese.
"""

import json
from mcp_conductor.ai_platforms.deepseek.rest_api import DeepSeekClient
from mcp_conductor.ai_platforms.sisi.rest_api import SISIClient
from mcp_conductor.detector.pipe_detect_engine import pipe_detect_engine
from mcp_conductor.ai_platforms.tools import remove_think_tag
from mcp_conductor.templates.questions import WEB_SEARCH_WEATHER_NEWS


def run_app():
    run_date = "2023-04-30"
    changepoints_df = pipe_detect_engine(run_date)

    # deepseek client
    ds_client = DeepSeekClient()
    sisi_client = SISIClient()

    # for each changepoints, request deepseek web search to find out the reason.
    detection_records = []
    for _, row in changepoints_df.iterrows():
        # weather, news
        changepoint_date_id = row['日期']
        pipe_name = row['通道名称']
        weather_news_question = WEB_SEARCH_WEATHER_NEWS.format(
            date_id = changepoint_date_id,
            pipe_name = pipe_name
        )

        weather_news_response = ds_client.search_and_ask(
            question=weather_news_question
        )
        weather_news_text = weather_news_response["choices"][0]["message"]["content"]

        # rephase and summay by sisi-ai
        summary_resp = sisi_client.search_and_ask(question=weather_news_text)
        summary_text = remove_think_tag(summary_resp["choices"][0]["message"]["content"])
        # remove think tag
        detection_records.append(
            {
                "date_id": changepoint_date_id,
                "pipe_name": pipe_name,
                "detection": summary_text
            }
        )
    
    # Save detection_records as JSON file
    output_file = f"/home/jerry/codebase/sisimcp/data/detection_results_{run_date.replace('-', '')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detection_records, f, ensure_ascii=False, indent=2)
    
    print(f"\nDetection results saved to: {output_file}")
    print(f"Total records: {len(detection_records)}")


if __name__ == "__main__":
    run_app()
