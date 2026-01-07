import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import datetime
import streamlit.components.v1 as components

# --- SuperTrend 計算 (核心邏輯不變) ---
def calculate_st_full(df, period, multiplier):
    df_st = df.copy().reset_index(drop=True)
    high, low, close = df_st['High'], df_st['Low'], df_st['Close']
    tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    hl2 = (high + low) / 2
    f_upper, f_lower = hl2 + (multiplier * atr), hl2 - (multiplier * atr)
    direction = np.ones(len(df_st))
    ub, lb, c = f_upper.values, f_lower.values, close.values
    for i in range(period, len(df_st)):
        if c[i-1] > lb[i-1]: lb[i] = max(lb[i], lb[i-1])
        if c[i-1] < ub[i-1]: ub[i] = min(ub[i], ub[i-1])
        if i < len(df_st) and c[i] > ub[i-1]: direction[i] = 1
        elif i < len(df_st) and c[i] < lb[i-1]: direction[i] = -1
        else:
            direction[i] = direction[i-1]
            if direction[i] == 1 and lb[i] < lb[i-1]: lb[i] = lb[i-1]
            if direction[i] == -1 and ub[i] > ub[i-1]: ub[i] = ub[i-1]
    return direction, ub, lb

# --- 資料下載快取 ---
@st.cache_data(ttl=3600)
def get_data(ticker):
    raw = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
    return raw

# --- TradingView 圖表轉換器 ---
def get_tv_symbol(symbol):
    if ".TW" in symbol: return f"TWSE:{symbol.replace('.TW', '')}"
    if ".TWO" in symbol: return f"TPEX:{symbol.replace('.TWO', '')}"
    if "-" in symbol: return symbol.replace("-", "")
    return symbol

# --- UI 配置 ---
st.set_page_config(page_title="Fish Diagnoser V1.2.4", layout="wide")
st.title("盛夏風情・魚兒診斷器 (V1.2.4 - 色彩美化版)")

# --- Sidebar ---
st.sidebar.header("🔍 診斷參數設定")
lookback = st.sidebar.selectbox("追溯參考天數", [3, 5, 10, 20, 60], index=2)
st.sidebar.header("🥢 SuperTrend 參數")
long_p, long_m = st.sidebar.number_input("長期 ATR 週期", value=120), st.sidebar.number_input("長期系數", value=4.0)
short_p, short_m = st.sidebar.number_input("短期 ATR 週期", value=3), st.sidebar.number_input("短期系數", value=2.0)

# --- 標的搜尋 ---
query = st.text_area("🐟 請輸入代碼", placeholder="例如: 1609, 2308, btc", height=100)

if query:
    input_list = [t.strip().upper() for t in query.replace(',', ' ').split() if t.strip()]
    results_for_excel = [] 

    if input_list:
        selected_tickers = []
        st.subheader("📌 請確認診斷對象")
        cols = st.columns(min(len(input_list), 3))
        for idx, q in enumerate(input_list):
            with cols[idx % 3]:
                search_res = yf.Search(q, max_results=3).quotes
                if search_res:
                    options = {f"{r['symbol']} ({r.get('longname', '未知')})": r['symbol'] for r in search_res}
                    chosen = st.selectbox(f"搜尋詞 '{q}'：", list(options.keys()), key=f"sel_{q}_{idx}")
                    selected_tickers.append((options[chosen], chosen))

        if st.button("🚀 開始批次診斷", use_container_width=True):
            with st.spinner("魚群精算中..."):
                for target_ticker, display_name in selected_tickers:
                    try:
                        raw = get_data(target_ticker)
                        if not raw.empty:
                            df = raw.copy()
                            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                            df = df.loc[:, ~df.columns.duplicated()]

                            curr_p = float(df['Close'].iloc[-1])
                            base_p = float(df['Close'].iloc[-(lookback + 1)])
                            ma20 = df['Close'].rolling(20).mean().iloc[-1]
                            ma60 = df['Close'].rolling(60).mean().iloc[-1]
                            ma120 = df['Close'].rolling(120).mean().iloc[-1]
                            ma20_prev = df['Close'].rolling(20).mean().iloc[-(lookback + 1)]
                            
                            l_dir, _, _ = calculate_st_full(df, long_p, long_m)
                            s_dir, _, _ = calculate_st_full(df, short_p, short_m)
                            cur_l, cur_s = l_dir[-1], s_dir[-1]

                            if cur_l == 1 and cur_s == 1: final_label, status_color = "✨ 浮光躍金 (雙強)", "#FFD700"
                            elif cur_l == -1 and cur_s == 1: final_label, status_color = "🚀 靈魚突圍 (轉強)", "#00FFFF"
                            elif cur_l == 1 and cur_s == -1: final_label, status_color = "🍂 迴游潛歇 (轉弱)", "#FFA500"
                            else: final_label, status_color = "🌑 影跡稀微 (雙弱)", "#A9A9A9"

                            results_for_excel.append([target_ticker, curr_p, ma20, ma60, ma120, final_label])

                            with st.expander(f"🔍 {display_name} - {final_label}", expanded=False):
                                # 對外連結
                                tv_symbol = get_tv_symbol(target_ticker)
                                st.markdown(f"[🔗 開啟 TradingView 官網查看您的個人指標](https://www.tradingview.com/chart/?symbol={tv_symbol})")
                                
                                # --- TradingView 修正腳本 (漸層藍色系) ---
                                tv_html = f"""
                                <div style="height: 500px; width: 100%;">
                                    <div id="tv_{target_ticker}" style="height: 500px;"></div>
                                    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                                    <script type="text/javascript">
                                    new TradingView.widget({{
                                      "width": "100%", "height": 500, "symbol": "{tv_symbol}", 
                                      "interval": "D", "timezone": "Asia/Taipei", "theme": "dark", "style": "1", "locale": "zh_TW",
                                      "container_id": "tv_{target_ticker}",
                                      "no_referral_id": true,
                                      "studies": [
                                        {{ "id": "BB@tv-basicstudies", "inputs": {{ "length": 22 }} }},
                                        {{ "id": "MAExp@tv-basicstudies", "inputs": {{ "length": 20 }} }},
                                        {{ "id": "MASimple@tv-basicstudies", "inputs": {{ "length": 60 }} }},
                                        {{ "id": "MAWeighted@tv-basicstudies", "inputs": {{ "length": 120 }} }}
                                      ],
                                      "studies_overrides": {{
                                        "bollinger bands.median.color": "#9370DB",
                                        "bollinger bands.upper.color": "#9370DB",
                                        "bollinger bands.lower.color": "#9370DB",
                                        "moving average exponential.MA.color": "#C0DFFF",
                                        "moving average exponential.MA.linewidth": 3,
                                        "moving average.MA.color": "#6FB7FF",
                                        "moving average.MA.linewidth": 3,
                                        "moving average weighted.MA.color": "#0078FF",
                                        "moving average weighted.MA.linewidth": 3
                                      }}
                                    }});
                                    </script>
                                </div>
                                """
                                components.html(tv_html, height=520)
                    except Exception as e:
                        st.error(f"分析錯誤。")

            if results_for_excel:
                output = BytesIO()
                wb = Workbook()
                ws = wb.active
                headers = ["標的代碼", "現價", "20MA", "60MA", "120MA", "判定"]
                for i, h in enumerate(headers, 1): ws.cell(1, i, h).font = Font(bold=True)
                for r_idx, row in enumerate(results_for_excel, 2):
                    for c_idx, val in enumerate(row, 1): ws.cell(r_idx, c_idx, val).alignment = Alignment(horizontal='center')
                wb.save(output)
                st.download_button(label="📥 下載診斷報表", data=output.getvalue(), file_name=f"Fish_V1.2.4.xlsx", use_container_width=True)