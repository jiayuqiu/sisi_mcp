import requests
import hashlib
import time
import random
import json
from typing import Optional, Dict, Any

# --- 配置信息 (请替换为您的真实凭证) ---

# API 基础 URL [cite: 6]
BASE_URL = "http://101.132.25.38:8891/bci/openapi/zbcsdb/getZbcsdb"

# 平台发放的 appId (基于文档示例) [cite: 29, 48]
APP_ID = "qiu"

# 平台发放的 secret key (基于文档示例) [cite: 39]
SECRET_KEY = "kevqkjn6bi1ximve3ukc8gp3kkr9ez9y"


# --- 签名函数 ---

def generate_signature(params_to_sign: Dict[str, str], secret_key: str) -> str:
    """
    根据文档生成 API 签名。
    """
    # 第一步：将集合 M 内参数的键名按照 ASCII 码从小到大排序 [cite: 20, 22]
    sorted_params = sorted(params_to_sign.items())

    # 拼接成 key1=value1&key2=value2... 格式的字符串 stringA [cite: 20]
    # 文档示例 [cite: 37] 包含: appId, client, endDay, nonce, startDay, timestamp
    string_a_parts = []
    for key, value in sorted_params:
        string_a_parts.append(f"{key}={value}")

    string_a = "&".join(string_a_parts)

    # 第二步：在 stringA 最后拼接上 key 得到 stringSignTemp [cite: 25]
    # 根据示例 [cite: 44]，拼接格式为 stringA + "&key=" + secret_key
    string_sign_temp = f"{string_a}&key={secret_key}"

    # 对 stringSignTemp 进行 MD5，并转换为小写 [cite: 25, 45]
    sign = hashlib.md5(string_sign_temp.encode('utf-8')).hexdigest().lower()

    return sign


# --- API 调用函数 ---

def get_bci_metrics(
        client: str,
        start_day: str,
        end_day: str,
        zbxxs: Optional[str] = None,
        csdbs: Optional[str] = None
) -> Dict[str, Any]:
    """
    调用获取指标接口 (getZbcsdb)。

    参数:
    client (str): 第三方标识 [cite: 9]
    start_day (str): 查询开始日期 (YYYY-MM-DD) [cite: 9]
    end_day (str): 查询结束日期 (YYYY-MM-DD) [cite: 9]
    zbxxs (Optional[str]): 指标信息, 多个用逗号分隔 [cite: 9]
    csdbs (Optional[str]): CSDB信息, 多个用逗号分隔 [cite: 9]
    """

    # --- 1. 准备参数 ---

    # 准备 URL 查询参数 (Query Parameters)
    # 这些参数会附加到 URL 上
    query_params = {
        "client": client,
        "startDay": start_day,
        "endDay": end_day,
    }

    # zbxxs 和 csdbs 不参与签名 [cite: 9]
    # 但它们需要作为 URL 参数传递
    if zbxxs:
        query_params["zbxxs"] = zbxxs  #
    if csdbs:
        query_params["csdbs"] = csdbs  #

    # 准备头部参数 (Header Parameters)
    # timestamp (有效期15分钟) [cite: 30]
    timestamp = str(int(time.time()))

    # nonce (随机数) [cite: 31]
    nonce = str(random.randint(1000000000, 9999999999))  # 示例 [cite: 31] 是10位

    # --- 2. 准备签名 ---

    # 根据文档 [cite: 37]，参与签名的参数包括:
    # appId, client, endDay, nonce, startDay, timestamp
    # 注意：zbxxs 和 csdbs 不参与签名 [cite: 9]
    params_to_sign = {
        "appId": APP_ID,
        "client": client,
        "endDay": end_day,
        "nonce": nonce,
        "startDay": start_day,
        "timestamp": timestamp,
    }

    # 生成签名
    sign = generate_signature(params_to_sign, SECRET_KEY)

    # --- 3. 准备请求头 ---

    # 最终发送的数据包含 HTTP 请求头参数 [cite: 47]
    headers = {
        "appId": APP_ID,  # [cite: 48]
        "timestamp": timestamp,  # [cite: 49]
        "nonce": nonce,  # [cite: 50]
        "sign": sign,  # [cite: 51]
        "Content-Type": "application/json;charset=UTF-8"  # 推荐做法
    }

    # --- 4. 发送 GET 请求 ---

    # print(f"--- 正在调用 API ---")
    # print(f"URL: {BASE_URL}")
    # print(f"Headers: {headers}")
    # print(f"Query Params: {query_params}")

    try:
        # 提交方式: GET [cite: 7]
        # requests 会自动将 params 字典附加到 URL ?key=value&...
        response = requests.get(
            BASE_URL,
            headers=headers,
            params=query_params,
            timeout=10  # 10秒超时
        )

        # 检查 HTTP 状态码
        response.raise_for_status()

        # 返回 JSON 响应
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP 错误: {http_err}")
        print(f"响应内容: {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"请求 错误: {req_err}")

    return {"success": False, "message": "请求失败"}


if __name__ == "__main__":
    # 示例 1：查询第三方配置的所有指标信息
    # 使用文档中的示例参数 [cite: 6]
    print("\n=== 示例 1: 查询所有指标 ===")
    client_val = APP_ID
    start_val = "2026-01-01"
    end_val = "2026-01-05"

    response_1 = get_bci_metrics(
        client=client_val,
        start_day=start_val,
        end_day=end_val
    )

    print("\n--- 响应结果 1 ---")
    # 使用 json.dumps 美化输出
    print(json.dumps(response_1, indent=2, ensure_ascii=False))

    # 示例 2：仅查询第三方配置的 zbxxs 指标信息
    print("\n=== 示例 2: 按 zbxxs 查询 ===")
    # 假设我们要查询 zbxx [cite: 67] 和 zbxx [cite: 83]
    zbxxs_val = "101-0003,101-0004"

    response_2 = get_bci_metrics(
        client=client_val,
        start_day=start_val,
        end_day=end_val,
        zbxxs=zbxxs_val
    )

    print("\n--- 响应结果 2 ---")
    print(json.dumps(response_2, indent=2, ensure_ascii=False))

    # 示例 3：仅查询第三方配置的 csdbs 指标信息
    print("\n=== 示例 3: 按 csdbs 查询 ===")
    # 假设我们要查询 csdb [cite: 69]
    csdbs_val = "055477ABB03B456E8B4B135E8193B25A"

    response_3 = get_bci_metrics(
        client=client_val,
        start_day=start_val,
        end_day=end_val,
        csdbs=csdbs_val
    )

    print("\n--- 响应结果 3 ---")
    print(json.dumps(response_3, indent=2, ensure_ascii=False))