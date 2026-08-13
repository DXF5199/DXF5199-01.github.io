import requests
import json
import re
from datetime import datetime, timedelta
import os

INDEX_CONFIG = [
    {"code": "480081", "name": "价值100R"},
    {"code": "480080", "name": "成长100R"}
]

def fetch_cni_history(code):
    """从国证指数官方内部 API 获取最近的历史行情数据"""
    url = "http://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat"
    end_str = datetime.now().strftime("%Y-%m-%d")
    start_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    params = {
        "indexCode": code,
        "startDate": start_str,
        "endDate": end_str,
        "frequency": "day",
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("data") and data["data"].get("data"):
            rows = data["data"]["data"]
            result = {}
            for row in rows:
                date_str = row[0]
                close_price = float(row[5])
                result[date_str] = close_price
            return result
    except Exception as e:
        print(f"获取指数 {code} 历史行情失败: {e}")
    return {}

def update_html(file_path):
    print(f"正在处理文件: {file_path}")
    if not os.path.exists(file_path):
        print(f"错误：找不到文件 {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(r'let allData = (\{.*?\});', content, re.DOTALL)
    if not match:
        print("错误：在 HTML 中未找到 allData 数据标识")
        return
    
    try:
        all_data = json.loads(match.group(1))
    except Exception as e:
        print(f"解析 allData JSON 失败: {e}")
        return

    updated_any = False

    # 1. 更新基础指数数据
    for item in INDEX_CONFIG:
        code = item["code"]
        name = item["name"]
        
        if name not in all_data:
            print(f"警告：HTML 数据中未找到 {name}")
            continue
            
        recent_data = fetch_cni_history(code)
        if not recent_data:
            print(f"未获取到 {name} ({code}) 的最新数据")
            continue
            
        dates = all_data[name]["dates"]
        values = all_data[name]["values"]
        
        for date_str, price in sorted(recent_data.items(), key=lambda x: x[0]):
            if date_str in dates:
                idx = dates.index(date_str)
                if abs(values[idx] - price) > 0.001:
                    values[idx] = price
                    updated_any = True
                    print(f"更新已有数据 -> {name} [{date_str}]: {price}")
            else:
                dates.append(date_str)
                values.append(price)
                updated_any = True
                print(f"新增最新数据 -> {name} [{date_str}]: {price}")
        
        combined = sorted(zip(dates, values), key=lambda x: x[0])
        all_data[name]["dates"] = [x[0] for x in combined]
        all_data[name]["values"] = [x[1] for x in combined]

    # 2. 同步更新 DASHBOARD 比值数据
    if updated_any and "DASHBOARD" in all_data:
        print("正在同步更新 DASHBOARD 比值仪表盘数据...")
        dash = all_data["DASHBOARD"]
        g_data = all_data["成长100R"]
        v_data = all_data["价值100R"]
        
        # 获取所有日期的并集
        date_set = set(g_data["dates"]) | set(v_data["dates"])
        sorted_dates = sorted(list(date_set))
        
        g_map = dict(zip(g_data["dates"], g_data["values"]))
        v_map = dict(zip(v_data["dates"], v_data["values"]))
        
        dash["dates"] = sorted_dates
        dash["growth_values"] = [g_map.get(d) for d in sorted_dates]
        dash["value_values"] = [v_map.get(d) for d in sorted_dates]
        
        # 计算比值 (价值 / 成长)
        ratios = []
        for d in sorted_dates:
            gv = g_map.get(d)
            vv = v_map.get(d)
            if gv and vv:
                ratios.append(round(vv / gv, 4))
            else:
                ratios.append(None)
        
        dash["ratio"] = ratios
        
        # 重新计算比值均值 (基准线)
        valid_ratios = [r for r in ratios if r is not None]
        if valid_ratios:
            dash["ratio_mean"] = round(sum(valid_ratios) / len(valid_ratios), 4)
            print(f"DASHBOARD 已更新，当前比值均值: {dash['ratio_mean']}")

    if updated_any:
        # 使用 ensure_ascii=False 保持中文不转义，indent=None 压缩体积
        new_json = json.dumps(all_data, ensure_ascii=False)
        new_content = content.replace(match.group(1), new_json)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✅ HTML 文件及仪表盘数据已成功更新并保存。")
    else:
        print("ℹ️ 数据已是最新，未检测到需要更新的内容。")

if __name__ == "__main__":
    target_file = "价值成长风格轮动策略.html"
    update_html(target_file)
