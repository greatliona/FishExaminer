import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import re
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import datetime

# --- FinMind API 配置 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0wNyAyMzozMTozMCIsInVzZXJfaWQiOiJWaXNpb24iLCJlbWFpbCI6ImRlbGlnaHRpbnRoZWtva0BnbWFpbC5jb20iLCJpcCI6IjM2LjIyNS45Ni42NiJ9.cwrtCVs1OVnqY2vaZpFB7Yr3Y0NNgU_GSgj2f_TUkcg"

def get_finmind_data(dataset, stock_id, start_date):
    url = "https://api.finmindtrade.com/api/v4/data"
    headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"}
    parameter = {"dataset": dataset, "data_id": stock_id, "start_date": start_date}
    try:
        resp = requests.get(url, params=parameter, headers=headers, timeout=10)
        res_json = resp.json()
        if res_json.get("msg") == "success":
            return pd.DataFrame(res_json["data"])
    except: pass
    return pd.DataFrame()

# --- SuperTrend 計算 (V1.2.2 原始邏輯) ---
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
        else: direction[i] = direction[i-1]
        if direction[i] == 1 and lb[i] < lb[i-1]: lb[i] = lb[i-1]
        if direction[i] == -1 and ub[i] > ub[i-1]: ub[i] = ub[i-1]
    return direction, ub, lb

# --- UI 配置 ---
st.set_page_config(page_title="Fish Diagnoser E1.4.2", layout="wide")
st.title("盛夏風情・魚兒診斷器 (E1.4.2 - 樣式與功能終極對位版)")

# --- Sidebar (100% 找回 V1.2.2 參數) ---
st.sidebar.header("🔍 診斷參數設定")
lookback = st.sidebar.selectbox("追溯參考天數", [3, 5, 10, 20, 60], index=2)
st.sidebar.header("🥢 SuperTrend 參數")
long_p, long_m = st.sidebar.number_input("長期 ATR 週期", value=120), st.sidebar.number_input("長期系數", value=4.0)
short_p, short_m = st.sidebar.number_input("短期 ATR 週期", value=3), st.sidebar.number_input("短期系數", value=2.0)

query = st.text_area("🐟 輸入代碼 (例如: 1609, 2330, btc)", height=100)

if query:
    input_list = [t.strip().upper() for t in query.replace(',', ' ').split() if t.strip()]
    # E1.4.1 BTC 預設轉換
    input_list = ["BTC-USD" if x == "BTC" else x for x in input_list]

    if input_list:
        selected_tickers = []
        st.subheader("📌 請確認診斷對象")
        cols = st.columns(min(len(input_list), 3))
        for idx, q in enumerate(input_list):
            with cols[idx % 3]:
                search_res = yf.Search(q, max_results=3).quotes
                if search_res:
                    options = {f"{r['symbol']} ({r.get('longname', '未知')})": r['symbol'] for r in search_res}
                    chosen = st.selectbox(f"搜尋 '{q}'：", list(options.keys()), key=f"sel_{q}_{idx}")
                    selected_tickers.append((options[chosen], chosen))

        if st.button("🚀 開始完整診斷", use_container_width=True):
            results_for_excel = []
            for idx, (target_ticker, display_name) in enumerate(selected_tickers):
                try:
                    raw = yf.download(target_ticker, period="2y", progress=False)
                    if not raw.empty:
                        df = raw.copy()
                        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                        
                        # --- 指標判定全數復歸 ---
                        curr_p = float(df['Close'].iloc[-1])
                        base_p = float(df['Close'].iloc[-(lookback + 1)])
                        ma5, ma10, ma20 = df['Close'].rolling(5).mean().iloc[-1], df['Close'].rolling(10).mean().iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
                        ma60, ma120 = df['Close'].rolling(60).mean().iloc[-1], df['Close'].rolling(120).mean().iloc[-1]
                        ma20_prev = df['Close'].rolling(20).mean().iloc[-(lookback + 1)]
                        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
                        ema20_prev = df['Close'].ewm(span=20, adjust=False).mean().iloc[-(lookback + 1)]
                        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
                        curr_vol = df['Volume'].iloc[-1]
                        
                        l_dir, _, _ = calculate_st_full(df, long_p, long_m)
                        s_dir, _, _ = calculate_st_full(df, short_p, short_m)
                        status_map = {(1, 1): ("✨ 浮光躍金", "#FFD700"), (-1, 1): ("🚀 靈魚突圍", "#00FFFF"), (1, -1): ("🍂 迴游潛歇", "#FFA500")}
                        final_label, status_color = status_map.get((l_dir[-1], s_dir[-1]), ("🌑 影跡稀微", "#A9A9A9"))

                        results_for_excel.append([target_ticker, curr_p, ma5, ma10, ma20, ma60, ma120, ema20, curr_vol, vol_ma5, final_label])

                        with st.expander(f"🔍 {display_name} - {final_label}", expanded=True):
                            # --- 頂部看板 (V1.2.2 樣式復歸) ---
                            p_pct = ((curr_p - base_p) / base_p) * 100
                            st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; padding: 15px; background-color: #1e1e1e; border-radius: 10px; border: 1px solid #333; margin-bottom: 20px;">
                                <div style="flex: 1;"><div style="color: #aaa; font-size: 0.9rem;">目前現價</div><div style="font-size: 1.8rem; font-weight: bold; color: white;">{curr_p:,.2f}</div></div>
                                <div style="flex: 1;"><div style="color: #aaa; font-size: 0.9rem;">{lookback}日漲跌</div><div style="font-size: 1.8rem; font-weight: bold; color: white;">{p_pct:+.2f}%</div></div>
                                <div style="flex: 1;"><div style="color: #aaa; font-size: 0.9rem;">綜合判定</div><div style="font-size: 1.6rem; font-weight: bold; color: {status_color};">{final_label}</div></div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # --- 多空 5+5 判定區 ---
                            col_bull, col_bear = st.columns(2)
                            red_check = '<span style="color:#FF4B4B; font-weight:bold;">✔</span>'
                            
                            with col_bull:
                                st.markdown("### 🟠 多方動能")
                                if curr_p > ma60: st.markdown(f'<div style="padding:10px; border-radius:5px; background-color:rgba(255,140,0,0.1); border-left:5px solid #FF8C00; color:white; margin-bottom:10px;">{red_check} 生命線：守穩 60MA 之上</div>', unsafe_allow_html=True)
                                if ma20 > ma60: st.markdown(f'<div style="padding:10px; border-radius:5px; background-color:rgba(255,140,0,0.1); border-left:5px solid #FF8C00; color:white; margin-bottom:10px;">{red_check} 中長期趨勢：20MA/60MA 黃金交叉</div>', unsafe_allow_html=True)
                                if curr_p >= ma20: st.markdown(f'<div style="padding:10px; border-radius:5px; background-color:rgba(255,140,0,0.1); border-left:5px solid #FF8C00; color:white; margin-bottom:10px;">{red_check} 位階判定：目前站穩月線</div>', unsafe_allow_html=True)
                                if s_dir[-1] == 1: st.markdown(f'<div style="padding:10px; border-radius:5px; background-color:rgba(255,140,0,0.1); border-left:5px solid #FF8C00; color:white; margin-bottom:10px;">{red_check} SuperTrend：短線維持多頭</div>', unsafe_allow_html=True)
                                if l_dir[-1] == 1: st.markdown(f'<div style="padding:10px; border-radius:5px; background-color:rgba(255,140,0,0.1); border-left:5px solid #FF8C00; color:white; margin-bottom:10px;">{red_check} SuperTrend：長線背景偏多</div>', unsafe_allow_html=True)
                            
                            with col_bear:
                                st.markdown("### 🔵 空方警示")
                                if curr_p < ma60: st.markdown('<div style="padding:10px; border-radius:5px; background-color:rgba(30,144,255,0.1); border-left:5px solid #1E90FF; color:white; margin-bottom:10px;">❌ 跌破 60MA 生命線</div>', unsafe_allow_html=True)
                                if ma20 < ma60: st.markdown('<div style="padding:10px; border-radius:5px; background-color:rgba(30,144,255,0.1); border-left:5px solid #1E90FF; color:white; margin-bottom:10px;">❌ 20MA/60MA 中長期死叉</div>', unsafe_allow_html=True)
                                if curr_p < ma20: st.markdown('<div style="padding:10px; border-radius:5px; background-color:rgba(30,144,255,0.1); border-left:5px solid #1E90FF; color:white; margin-bottom:10px;">❌ 位階偏低：目前在月線下</div>', unsafe_allow_html=True)
                                if s_dir[-1] == -1: st.markdown('<div style="padding:10px; border-radius:5px; background-color:rgba(30,144,255,0.1); border-left:5px solid #1E90FF; color:white; margin-bottom:10px;">❌ SuperTrend：短線轉弱</div>', unsafe_allow_html=True)
                                if l_dir[-1] == -1: st.markdown('<div style="padding:10px; border-radius:5px; background-color:rgba(30,144,255,0.1); border-left:5px solid #1E90FF; color:white; margin-bottom:10px;">❌ SuperTrend：長線背景偏空</div>', unsafe_allow_html=True)

                            # --- 財務數據區 ---
                            st.markdown("---")
                            sid_only = re.sub(r'\D', '', target_ticker)
                            if "USD" not in target_ticker:
                                col_f1, col_f2 = st.columns(2)
                                with col_f1:
                                    st.write("📊 **營收精算 (月份偏移校正)**")
                                    rev_df = get_finmind_data("TaiwanStockMonthRevenue", sid_only, "2024-11-01")
                                    if not rev_df.empty:
                                        rev_df = rev_df[rev_df['revenue'] > 0].sort_values(by='date', ascending=True).reset_index(drop=True)
                                        rev_df['MoM'], rev_df['YoY'] = rev_df['revenue'].pct_change() * 100, rev_df['revenue'].pct_change(12) * 100
                                        for _, r in rev_df.tail(3).sort_values(by='date', ascending=False).iterrows():
                                            m = (pd.to_datetime(r['date']) - pd.DateOffset(months=1)).strftime('%m')
                                            st.write(f"**{m}月營收**：{r['revenue']/1e8:,.2f} 億 | MoM: `{r['MoM']:+.1f}%` | YoY: `{r['YoY']:+.1f}%`")
                                with col_f2:
                                    st.write("💰 **最新季報 EPS**")
                                    eps_df = get_finmind_data("TaiwanStockFinancialStatements", sid_only, "2025-01-01")
                                    if not eps_df.empty:
                                        for _, r in eps_df[eps_df['type'] == 'EPS'].tail(3).sort_values(by='date', ascending=False).iterrows():
                                            dt = pd.to_datetime(r['date'])
                                            st.write(f"**{dt.year} Q{((dt.month-1)//3)+1} EPS**：{r['value']:.2f} 元")
                            
                            tv_p = "BINANCE" if "USD" in target_ticker else ("TPEX" if ".TWO" in target_ticker else "TWSE")
                            tv_c = "BTCUSD" if "BTC" in target_ticker else sid_only
                            st.markdown(f"[🔗 開啟 TradingView 詳細圖表](https://www.tradingview.com/chart/?symbol={tv_p}:{tv_c})")

                except Exception as e: st.error(f"分析失敗: {e}")

            if results_for_excel:
                output = BytesIO()
                wb = Workbook()
                ws = wb.active
                headers = ["代碼", "現價", "5MA", "10MA", "20MA", "60MA", "120MA", "EMA20", "成交量", "5MA均量", "象限"]
                for i, h in enumerate(headers, 1):
                    cell = ws.cell(1, i, h)
                    cell.font, cell.fill, cell.border, cell.alignment = Font(bold=True), PatternFill("solid", fgColor="DDEBF7"), Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin')), Alignment(horizontal='center')
                for r_idx, row_data in enumerate(results_for_excel, 2):
                    for c_idx, val in enumerate(row_data, 1):
                        ws.cell(r_idx, c_idx, val).alignment = Alignment(horizontal='center')
                        if isinstance(val, (int, float)): ws.cell(r_idx, c_idx).number_format = '#,##0.00'
                wb.save(output)
                st.download_button(label="📥 下載 E1.4.2 完整報表", data=output.getvalue(), file_name=f"Fish_E1.4.2_{datetime.date.today()}.xlsx", use_container_width=True)
