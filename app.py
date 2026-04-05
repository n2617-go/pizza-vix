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
            try:
                return json.load(f)
            except:
                return default
    return default

# --- 3. UI 樣式設定 ---
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
    .update-tag { text-align: center; font-size: 10px; color: #666; margin-top: -10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 核心數據抓取邏輯 ---

def get_pizza_intel(progress_bar):
    """披薩指數 OCR 邏輯"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto("https://worldmonitor.app/", wait_until="commit", timeout=60000)
            for i in range(100):
                time.sleep(0.05)
                progress_bar.progress(i + 1)
            screenshot = page.screenshot(clip={'x': 0, 'y': 0, 'width': 1920, 'height': 120})
            browser.close()
            img = Image.open(io.BytesIO(screenshot)).convert('L')
            img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
            img = ImageEnhance.Contrast(img).enhance(3.5)
            raw_text = pytesseract.image_to_string(img, config='--psm 6').lower().strip()
            lvl = re.search(r'defcon\s*[is|l|\||!]?\s*(\d)', raw_text)
            pct = re.search(r'(\d+)\s*%', raw_text)
            return (int(lvl.group(1)) if lvl else 1), (float(pct.group(1)) if pct else 0.0)
    except Exception as e:
        st.error(f"OCR 掃描失敗: {e}")
        return None, None

def fetch_market_data():
    """三大市場恐慌指數抓取 - 強化版"""
    v_us, v_tw, v_crypto = "N/A", "N/A", "N/A"
    errors = []
    
    # 1. 美股 VIX (yfinance)
    try:
        vix_ticker = yf.Ticker("^VIX")
        hist_us = vix_ticker.history(period="7d")
        if not hist_us.empty:
            v_us = round(hist_us['Close'].iloc[-1], 2)
    except Exception as e:
        errors.append(f"美股 VIX 失敗: {e}")

    # 2. 臺指 VIXTWN (FinMind) - 擴大搜尋範圍至 30 天
    try:
        dl = DataLoader()
        start_dt = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        df_tw = dl.taiwan_stock_index_vix(index_id='VIXTWN', start_date=start_dt)
        if not df_tw.empty:
            v_tw = round(df_tw['vix'].iloc[-1], 2)
    except Exception as e:
        errors.append(f"台指 VIXTWN 失敗: {e}")

    # 3. 加密貨幣 F&G (Alternative.me)
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=15).json()
        v_crypto = res['data'][0]['value']
    except Exception as e:
        errors.append(f"加密 F&G 失敗: {e}")
        
    return v_us, v_tw, v_crypto, errors

# --- 5. 頁面呈現 ---
st.markdown("<h1>🛡️ Global Intel Center</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#888;'>全球軍事與金融風險監控中心</p>", unsafe_allow_html=True)

# 時間顯示
now_tw = datetime.now(tz_tw)
now_us = datetime.now(tz_us)
st.markdown(f"""
    <div class="time-container">
        <div style="text-align:center;"><div style="font-size:10px;color:#aaa;">🇹🇼 台北</div><b>{now_tw.strftime("%H:%M:%S")}</b></div>
        <div style="text-align:center;"><div style="font-size:10px;color:#aaa;">🇺🇸 華盛頓</div><b>{now_us.strftime("%H:%M:%S")}</b></div>
    </div>
    """, unsafe_allow_html=True)

# --- 披薩指標區塊 ---
st.subheader("🍕 五角大廈披薩情報")
saved_pizza = load_json(PIZZA_FILE, {"lvl": 1, "pct": 0.0, "update_time": "尚未更新"})

if st.button("🛰️ 更新披薩指數 (OCR 掃描)"):
    bar = st.progress(0)
    with st.spinner("衛星情報掃描中..."):
        lvl, pct = get_pizza_intel(bar)
        if lvl is not None:
            save_json(PIZZA_FILE, {
                "lvl": lvl, "pct": pct, 
                "update_time": datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
            })
            st.toast("披薩情報更新成功", icon="✅")
            st.rerun()
    bar.empty()

st.markdown(f'<div class="update-tag">最後情報更新時間：{saved_pizza["update_time"]}</div>', unsafe_allow_html=True)
st.markdown(f"""
    <div class="dashboard-card">
        <div style="display:flex; justify-content:space-around; align-items:center; text-align:center;">
            <div style="flex:1;"><p class="market-label">DEFCON</p><p class="db-value" style="font-size:50px;margin:0;">{saved_pizza['lvl']}</p></div>
            <div style="border-left:1px solid #333; height:40px;"></div>
            <div style="flex:1;"><p class="market-label">PIZZA INDEX</p><p class="db-value" style="font-size:50px;margin:0;">{int(saved_pizza['pct'])}%</p></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 市場指標區塊 ---
st.divider()
st.subheader("📉 全球市場恐慌監控")
saved_market = load_json(MARKET_FILE, {"v_us": "N/A", "v_tw": "N/A", "v_crypto": "N/A", "update_time": "尚未更新"})

if st.button("📊 更新市場恐慌情報 (API 抓取)"):
    with st.spinner("正在串接全球金融數據..."):
        v_us, v_tw, v_crypto, errors = fetch_market_data()
        # 只要有一項成功就儲存
        if v_us != "N/A" or v_tw != "N/A" or v_crypto != "N/A":
            save_json(MARKET_FILE, {
                "v_us": v_us, "v_tw": v_tw, "v_crypto": v_crypto,
                "update_time": datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
            })
            st.toast("市場數據更新成功", icon="📈")
            if errors:
                with st.expander("部分數據抓取有誤"):
                    for err in errors: st.write(err)
            time.sleep(1)
            st.rerun()
        else:
            st.error("市場數據抓取失敗")
            for err in errors: st.write(err)

st.markdown(f'<div class="update-tag">最後市場更新時間：{saved_market["update_time"]}</div>', unsafe_allow_html=True)

m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">美股 VIX</p><p class="db-value" style="font-size:32px;">{saved_market["v_us"]}</p></div>', unsafe_allow_html=True)
with m_col2:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">台指 VIXTWN</p><p class="db-value" style="font-size:32px;">{saved_market["v_tw"]}</p></div>', unsafe_allow_html=True)
with m_col3:
    st.markdown(f'<div class="dashboard-card" style="text-align:center;">'
                f'<p class="market-label">加密 F&G</p><p class="db-value" style="font-size:32px;">{saved_market["v_crypto"]}</p></div>', unsafe_allow_html=True)

st.caption("數據來源：Yahoo Finance, FinMind, Alternative.me")
