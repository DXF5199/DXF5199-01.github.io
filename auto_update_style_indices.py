import requests
import json
import re
import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime, timedelta
import os

# 配置指数代码映射
INDEX_CONFIG = [
    {"code": "480081", "name": "价值100R"},
    {"code": "480080", "name": "成长100R"}
]

def fetch_cni_history(code):
    """从国证指数官方内部 API 获取最近的历史行情数据"""
    url = "http://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat"
    end_str = datetime.now().strftime("%Y-%m-%d")
    start_str = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    
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

def find_points(prices, is_high=True, window=120):
    points = []
    n = len(prices)
    for i in range(0, n, window):
        segment = prices[i:i+window]
        if not segment: continue
        val = max(segment) if is_high else min(segment)
        idx = i + segment.index(val)
        points.append((idx, np.log(val)))
    return points

def calculate_regression_channels(data_obj):
    """为指数计算近10年的对数回归通道"""
    values = data_obj["values"]
    prices = np.array(values)
    n_total = len(prices)
    
    # 对数回归通道：严格使用最新交易日向前滚动10个日历年的样本。
    date_index = pd.to_datetime(data_obj["dates"])
    cutoff_date = date_index[-1] - pd.DateOffset(years=10)
    valid_indices = np.flatnonzero(date_index >= cutoff_date)
    start_idx = int(valid_indices[0]) if len(valid_indices) else 0
    prices_10y = values[start_idx:]
    n_10y = len(prices_10y)

    high_pts_local = find_points(prices_10y, is_high=True)
    low_pts_local = find_points(prices_10y, is_high=False)

    def get_line(pts):
        x = np.array([p[0] for p in pts])
        y = np.array([p[1] for p in pts])
        slope, intercept, _, _, _ = stats.linregress(x, y)
        line = slope * np.arange(n_10y) + intercept
        annual_ret = (np.exp(slope * 252) - 1) * 100
        return line, round(float(annual_ret), 2)

    reg_high_10y, high_ret = get_line(high_pts_local)
    reg_low_10y, low_ret = get_line(low_pts_local)

    # 10年窗口外用None占位，避免绘制不属于当前拟合样本的通道线。
    prefix = [None] * start_idx
    data_obj["reg_high"] = prefix + [round(float(v), 4) for v in reg_high_10y]
    data_obj["reg_low"] = prefix + [round(float(v), 4) for v in reg_low_10y]
    data_obj["high_points"] = [[int(p[0] + start_idx), round(float(p[1]), 4)] for p in high_pts_local]
    data_obj["low_points"] = [[int(p[0] + start_idx), round(float(p[1]), 4)] for p in low_pts_local]
    data_obj["annual_return_high"] = high_ret
    data_obj["annual_return_low"] = low_ret
    data_obj["regression_start_index"] = start_idx
    data_obj["regression_start_date"] = data_obj["dates"][start_idx]
    data_obj["regression_window_years"] = 10

def update_html(file_path):
    print(f"正在处理文件: {file_path}")
    if not os.path.exists(file_path):
        print(f"跳过：找不到文件 {file_path}")
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

    # 1. 更新基础指数数据并重算回归
    for item in INDEX_CONFIG:
        code = item["code"]
        name = item["name"]
        
        if name not in all_data:
            print(f"警告：HTML 数据中未找到 {name}")
            continue
            
        recent_data = fetch_cni_history(code)
        
        dates = all_data[name]["dates"]
        values = all_data[name]["values"]
        index_updated = False
        
        if recent_data:
            for date_str, price in sorted(recent_data.items(), key=lambda x: x[0]):
                if date_str in dates:
                    idx = dates.index(date_str)
                    if abs(values[idx] - price) > 0.001:
                        values[idx] = price
                        index_updated = True
                else:
                    dates.append(date_str)
                    values.append(price)
                    index_updated = True
        
        # 检查是否需要重算回归 (数据更新或字段缺失/长度不匹配)
        has_reg = (
            "reg_high" in all_data[name]
            and len(all_data[name]["reg_high"]) == len(dates)
            and "regression_start_index" in all_data[name]
            and all_data[name].get("regression_window_years") == 10
        )
        if index_updated or not has_reg:
            combined = sorted(zip(dates, values), key=lambda x: x[0])
            all_data[name]["dates"] = [x[0] for x in combined]
            all_data[name]["values"] = [x[1] for x in combined]
            
            print(f"正在为 {name} 重新计算回归通道指标...")
            calculate_regression_channels(all_data[name])
            updated_any = True

    # 2. 同步 DASHBOARD 数据
    g_data = all_data.get("成长100R", {"dates": [], "values": []})
    v_data = all_data.get("价值100R", {"dates": [], "values": []})
    
    date_set = set(g_data["dates"]) | set(v_data["dates"])
    sorted_dates = sorted(list(date_set))
    
    g_map = dict(zip(g_data["dates"], g_data["values"]))
    v_map = dict(zip(v_data["dates"], v_data["values"]))
    
    new_dash = {
        "dates": sorted_dates,
        "growth_values": [g_map.get(d) for d in sorted_dates],
        "value_values": [v_map.get(d) for d in sorted_dates],
        "ratio": []
    }
    
    for d in sorted_dates:
        gv = g_map.get(d)
        vv = v_map.get(d)
        if gv and vv:
            new_dash["ratio"].append(round(vv / gv, 4))
        else:
            new_dash["ratio"].append(None)
    
    valid_ratios = [r for r in new_dash["ratio"] if r is not None]
    if valid_ratios:
        new_dash["ratio_mean"] = round(sum(valid_ratios) / len(valid_ratios), 4)

    if "DASHBOARD" not in all_data or all_data["DASHBOARD"].get("dates") != new_dash["dates"]:
        all_data["DASHBOARD"] = new_dash
        updated_any = True
        print("DASHBOARD 数据已同步更新。")

    if updated_any:
        new_json = json.dumps(all_data, ensure_ascii=False)
        new_content = content.replace(match.group(1), new_json)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ {file_path} 及图表指标已成功更新。")
    else:
        print(f"ℹ️ {file_path} 已是最新。")

if __name__ == "__main__":
    # 尝试更新指定的 HTML 文件
    target_file = "价值成长风格轮动策略.html"
    update_html(target_file)
