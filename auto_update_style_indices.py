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
    url = f"https://www.cnindex.com.cn/api/index/get_index_detail?indexCode={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.cnindex.com.cn/module/index-detail.html?indexCode={code}",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20).json()
        if resp.get("code") == "200" and resp.get("data"):
            data = resp["data"]
            # 提取最新点位和日期
            current_val = float(data.get("indexCurrent"))
            trade_date = data.get("tradeDate") # 格式通常为 YYYY-MM-DD
            return trade_date, current_val
    except Exception as e:
        print(f"抓取国证指数 {code} 失败: {e}")
    return None, None

def update_html(file_path):
    print(f"正在处理文件: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 匹配 allData 数据结构
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
            print(f"警告：HTML 数据中未找到指数名称【{name}】")
            continue
            
        target_date, latest_val = fetch_cni_detail(code)
        
        if latest_val and target_date:
            dates = all_data[name]["dates"]
            values = all_data[name]["values"]
            
            # 检查日期是否已存在
            if target_date in dates:
                idx = dates.index(target_date)
                # 如果点位有显著变化则更新
                if abs(values[idx] - latest_val) > 0.001:
                    values[idx] = latest_val
                    updated_any = True
                    print(f"更新 {name} [{target_date}]: {latest_val}")
            else:
                dates.append(target_date)
                values.append(latest_val)
                # 按日期排序，确保图表连续
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
        print("✅ HTML 文件数据已成功更新并保存。")
    else:
        print("ℹ️ 未检测到新数据变化，文件未修改。")

if __name__ == "__main__":
    import os
    # 目标文件名
    target_file = "价值成长风格轮动策略.html"
    if os.path.exists(target_file):
        update_html(target_file)
    else:
        print(f"错误：当前目录下未找到文件 {target_file}")
