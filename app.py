import streamlit as st
from playwright.sync_api import sync_playwright
import pytesseract
from PIL import Image, ImageEnhance
import io
import os
import re
import time
import pytz
import json
import requests
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 環境與檔案路徑初始化 ---
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

PIZZA_FILE = "intelligence_data.json"
MARKET_FILE = "market_data.json"
tz_tw = pytz.timezone('Asia/Taipei')
tz_us = pytz.timezone('America/New_York')

# --- 2. 資料持久化函數 ---
def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

# --- 3. UI 樣式 ---
st.set_page_config(page_title="Global Intel Center", page_icon="🛡️", layout="centered")

st.markdown("""
    <style>
    .time-container {
        background-color: #1e1e1e; border-radius: 8px; padding: 10px;
        margin-bottom: 15px; display: flex; justify-content: space-around;
        align-items: center; border-left: 4px solid #444;
    }
    .dashboard-card {
        background-color: #000; border-radius: 12px; padding: 20px;
        margin-bottom: 15px; border: 1px solid #333;
    }
    .db-value { font-family: 'Courier New', monospace; font-weight: bold; color: #FF4B4B; line-height: 1; }
    .market-label { font-size: 12px; color: #999; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 數據抓取邏輯 ---

# 披薩指數 OCR
def get_pizza_intel(progress_bar):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto("https://worldmonitor.app/", timeout=60000)
            for i in range(100):
                time.sleep(0.05)
                progress_bar.progress(i + 1)
            screenshot = page.screenshot(clip={'x': 0, 'y': 0, 'width': 1920, 'height': 120})
            browser.close()
            img = Image.open(io.BytesIO(screenshot)).convert('L')
            img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
            raw_text = pytesseract.image_to_string(img, config='--psm 6').lower()
            lvl = re.search(r'defcon\s*[^\d]?\s*(\d)', raw_text)
            pct = re.search(r'(\d+)\s*%', raw_text)
            return (int(lvl.group(1)) if lvl else 1), (float(pct.group(1)) if pct else 0.0)
    except: return None, None

# 市場恐慌指數
def fetch_market_data():
    try:
        # 1. 美股 VIX
        vix_us_df = yf.download("^VIX", period="1d", progress=False)
        v_us = round(vix_us_df['Close'].iloc[-1], 2)
        # 2. 台指 VIXTWN
        dl = DataLoader()
        start_dt = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        df_tw = dl.taiwan_stock_index_vix(index_id='VIXTWN', start_date=start_dt)
        v_tw = df_tw['vix'].iloc[-1] if not df_tw.empty else "N/A"
        # 3. 加密貨幣 F&G
        res = requests.get("https://api.alternative.me/fng/").json()
        v_crypto = res['data'][0]['value']
        return v_us, v_tw, v_crypto
    except: return None, None, None

# --- 5. 頁面呈現 ---
st.title("🛡️ 戰情監控中心")

# 時間顯示
now_tw, now_us = datetime.now(tz_tw), datetime.now(tz_us)
st.markdown(f'<div class="time-container">'
            f'<div><small>🇹🇼 台北</small><br><b>{now_tw.strftime("%H:%M:%S")}</b></div>'
            f'<div><small>🇺🇸 華盛頓</small><br><b>{now_us.strftime("%H:%M:%S")}</b></div>'
            f'</div>', unsafe_allow_html=True)

# --- 第一部分：披薩指數 ---
st.subheader("🍕 五角大廈披薩情報")
saved_pizza = load_json(PIZZA_FILE, {"lvl": 1, "pct": 0, "update_time": "尚未更新"})

if st.button("🛰️ 更新披薩指數 (OCR 掃描)"):
    bar = st.progress(0)
    lvl, pct = get_pizza_intel(bar)
    if lvl is not None:
        save_json(PIZZA_FILE, {"lvl": lvl, "pct": pct, "update_time": datetime.now(tz_tw).strftime("%H:%M:%S")})
        st.rerun()
    else: st.error("掃描失敗")

# 顯示披薩卡片
st.markdown(f"""
    <div class="dashboard-card">
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div><p class="market-label">DEFCON</p><p class="db-value" style="font-size:50px;">{saved_pizza['lvl']}</p></div>
            <div style="border-left:1px solid #333; height:50px; align-self:center;"></div>
            <div><p class="market-label">PIZZA INDEX</p><p class="db-value" style="font-size:50px;">{int(saved_pizza['pct'])}%</p></div>
        </div>
        <p style="text-align:center; font-size:10px; color:#555;">最後更新：{saved_pizza['update_time']}</p>
    </div>
    """, unsafe_allow_html=True)

# --- 第二部分：市場恐慌指數 ---
st.divider()
st.subheader("📉 全球市場恐慌監控")
saved_market = load_json(MARKET_FILE, {"v_us": "N/A", "v_tw": "N/A", "v_crypto": "N/A", "update_time": "尚未更新"})

if st.button("📊 更新市場恐慌情報 (API 抓取)"):
    with st.spinner("正在串接金融數據..."):
        v_us, v_tw, v_crypto = fetch_market_data()
        if v_us:
            save_json(MARKET_FILE, {"v_us": v_us, "v_tw": v_tw, "v_crypto": v_crypto, "update_time": datetime.now(tz_tw).strftime("%H:%M:%S")})
            st.rerun()
        else: st.error("數據獲取失敗")

# 顯示三個市場卡片
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">美股 VIX</p><p class="db-value" style="font-size:35px;">{saved_market["v_us"]}</p></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">台指 VIXTWN</p><p class="db-value" style="font-size:35px;">{saved_market["v_tw"]}</p></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">加密 F&G</p><p class="db-value" style="font-size:35px;">{saved_market["v_crypto"]}</p></div>', unsafe_allow_html=True)

st.caption(f"市場數據最後更新：{saved_market['update_time']}")
