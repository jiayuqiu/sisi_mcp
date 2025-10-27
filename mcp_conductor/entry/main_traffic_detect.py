"""
This script is to 1. combine the changepoints detector with deepseek and sisi-ai.
Once we find the changepoints from pipe data, ask deepseek with web search to get weather and news around the pipe.
Finally, feed the text of weather and news into sisi-ai to rephase, summay and tranlate the text into chinese.
"""
from pprint import pprint
import argparse
import json

import pandas as pd

from mcp_conductor.ai_platforms.deepseek.rest_api import DeepSeekClient
from mcp_conductor.ai_platforms.sisi.rest_api import SISIClient
from mcp_conductor.detector.pipe_detect_engine import pipe_detect_engine
from mcp_conductor.ai_platforms.tools import remove_think_tag
from mcp_conductor.templates.questions import WEB_SEARCH_WEATHER_NEWS


def analyze_congestion(pipe_name: str, changepoints: pd.DataFrame) -> str:
    if changepoints.shape[0] == 0:
        pprint(f"🟢 {pipe_name} 通航正常")
    # get the last changepoint
    changepoints_result = changepoints.iloc[[-1], :]

    # deepseek client
    ds_client = DeepSeekClient()
    sisi_client = SISIClient()

    # for each changepoints, request deepseek web search to find out the reason.
    detection_records = []
    for _, row in changepoints_result.iterrows():
        # weather, news
        changepoint_date_id = row['date_id']
        pipe_name = row['pipe_name']
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
    
    # print the latest detection records dict
    pprint(f"🔴 {pipe_name} 通航拥堵 ")
    pprint(detection_records[-1]["detection"])
    return detection_records[-1]["detection"]
    
    # Save detection_records as JSON file
    # output_file = f"/home/jerry/codebase/sisimcp/data/detection/detection_results_{run_date.replace('-', '')}.json"
    # with open(output_file, 'w', encoding='utf-8') as f:
    #     json.dump(detection_records, f, ensure_ascii=False, indent=2)
    
    # print(f"\nDetection results saved to: {output_file}")
    # print(f"Total records: {len(detection_records)}")


def trigger_traffic_detect(run_date: str, pipe_name: str) -> str:
    changepoints_result: dict[str, pd.DataFrame] = pipe_detect_engine(run_date, pipe_name)
    changepoints = changepoints_result[pipe_name]
    detection_text: str = analyze_congestion(pipe_name=pipe_name, changepoints=changepoints)
    return detection_text


def run_app():
    parser = argparse.ArgumentParser(description='process match polygon for events')
    parser.add_argument(f"--run_date", type=str, required=True, help='Process model run date')
    parser.add_argument(f"--pipe", type=str, required=True, help='Process model on specific pipe')
    args = parser.parse_args()

    run_date = args.__getattribute__("run_date")
    pipe_name = args.__getattribute__("pipe")
    changepoints_result: dict[str, pd.DataFrame] = pipe_detect_engine(run_date, pipe_name)
    changepoints = changepoints_result[pipe_name]
    analyze_congestion(pipe_name=pipe_name, changepoints=changepoints)


if __name__ == "__main__":
    run_app()
