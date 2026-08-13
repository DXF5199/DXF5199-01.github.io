import json
import re
import requests
from datetime import datetime

# 配置指数代码映射 (国证官网全收益点位)
INDEX_CONFIG = [
    {"code": "480081", "name": "价值100R"},
    {"code": "480080", "name": "成长100R"}
]

def fetch_cni_detail(code):
    """从国证指数官网获取最新详情数据"""
    # 经过分析，详情页展示的数据是通过 get_index_detail 接口获取的
    # 但直接请求可能会被拦截，我们需要模拟完整的浏览器头信息
    url = f"https://www.cnindex.com.cn/api/index/get_index_detail?indexCode={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.cnindex.com.cn/module/index-detail.html?indexCode={code}",
        "Accept": "application/json, text/plain, */*",
        "Host": "www.cnindex.com.cn"
    }
    try:
        # 国证官网 API 比较敏感，我们增加重试机制
        for _ in range(3):
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                data_json = resp.json()
                if data_json.get("code") == "200" and data_json.get("data"):
                    info = data_json["data"]
                    current_val = float(info.get("indexCurrent"))
                    trade_date = info.get("tradeDate")
                    return trade_date, current_val
            elif resp.status_code == 404:
                # 尝试备用接口（列表接口）
                list_url = "https://www.cnindex.com.cn/api/index/get_index_list"
                list_resp = requests.post(list_url, data={"indexCode": code}, headers=headers, timeout=20)
                if list_resp.status_code == 200:
                    list_data = list_resp.json()
                    if list_data.get("data") and list_data["data"].get("rows"):
                        row = list_data["data"]["rows"][0]
                        return row.get("tradeDate"), float(row.get("indexCurrent"))
    except Exception as e:
        print(f"抓取国证指数 {code} 失败: {e}")
    return None, None

def update_html(file_path):
    print(f"正在处理文件: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(r'let allData = (\{.*?\});', content, re.DOTALL)
    if not match:
        print("错误：在 HTML 中未找到 allData 数据标识")
        return
    
    all_data = json.loads(match.group(1))
    updated_any = False

    for item in INDEX_CONFIG:
        code = item["code"]
        name = item["name"]
        
        if name not in all_data:
            continue
            
        target_date, latest_val = fetch_cni_detail(code)
        
        if latest_val and target_date:
            dates = all_data[name]["dates"]
            values = all_data[name]["values"]
            
            if target_date in dates:
                idx = dates.index(target_date)
                if abs(values[idx] - latest_val) > 0.001:
                    values[idx] = latest_val
                    updated_any = True
                    print(f"更新 {name} [{target_date}]: {latest_val}")
            else:
                dates.append(target_date)
                values.append(latest_val)
                combined = sorted(zip(dates, values), key=lambda x: x[0])
                all_data[name]["dates"] = [x[0] for x in combined]
                all_data[name]["values"] = [x[1] for x in combined]
                updated_any = True
                print(f"新增 {name} [{target_date}]: {latest_val}")

    if updated_any:
        new_json = json.dumps(all_data, ensure_ascii=False)
        new_content = content.replace(match.group(1), new_json)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✅ HTML 文件数据已成功更新。")
    else:
        print("ℹ️ 未检测到新数据变化。")

if __name__ == "__main__":
    import os
    target_file = "价值成长风格轮动策略.html"
    if os.path.exists(target_file):
        update_html(target_file)
