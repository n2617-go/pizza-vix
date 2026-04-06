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


def fetch_vixtwn():
    """
    台指 VIXTWN 專屬抓取函數（純 requests，不需額外套件）
    兩層備援：
      A. FinMind REST API - TaiwanFuturesDaily (data_id=VIX)
      B. FinMind REST API - TaiwanVariousIndicators5Seconds (data_id=VIXTWN)
    回傳: (數值 or None, 來源說明 or 錯誤訊息)
    """
    base_url = "https://api.finmindtrade.com/api/v4/data"
    start_dt = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # --- 方案 A：TaiwanFuturesDaily，data_id=VIX ---
    try:
        params = {
            "dataset": "TaiwanFuturesDaily",
            "data_id": "VIX",
            "start_date": start_dt,
        }
        res = requests.get(base_url, params=params, timeout=15)
        res.raise_for_status()
        records = res.json().get("data", [])
        if records:
            latest = sorted(records, key=lambda x: x.get("date", ""))[-1]
            val = float(latest.get("close", 0))
            if val > 0:
                return round(val, 2), f"FinMind TaiwanFuturesDaily（{latest.get('date','')}）"
    except Exception:
        pass

    # --- 方案 B：TaiwanVariousIndicators5Seconds，data_id=VIXTWN ---
    try:
        start_dt_short = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        params = {
            "dataset": "TaiwanVariousIndicators5Seconds",
            "data_id": "VIXTWN",
            "start_date": start_dt_short,
        }
        res = requests.get(base_url, params=params, timeout=15)
        res.raise_for_status()
        records = res.json().get("data", [])
        if records:
            latest = sorted(records, key=lambda x: x.get("date", ""))[-1]
            val = float(latest.get("price", latest.get("close", 0)))
            if val > 0:
                return round(val, 2), f"FinMind Indicators（{latest.get('date','')}）"
    except Exception:
        pass

    return None, "FinMind 兩個 dataset 均無回傳資料（可能為非交易日或 API 限流）"


def fetch_market_data():
    """三大市場恐慌指數抓取"""
    v_us, v_tw, v_crypto = "N/A", "N/A", "N/A"
    errors = []

    # 1. 美股 VIX（yfinance）
    try:
        hist_us = yf.Ticker("^VIX").history(period="5d")
        if not hist_us.empty:
            v_us = round(hist_us['Close'].iloc[-1], 2)
        else:
            errors.append("美股 VIX：yfinance 回傳空資料")
    except Exception as e:
        errors.append(f"美股 VIX 失敗: {e}")

    # 2. 台指 VIXTWN（FinMind REST API 兩層備援）
    val, source = fetch_vixtwn()
    if val is not None:
        v_tw = val
    else:
        errors.append(f"台指 VIXTWN 失敗：{source}")

    # 3. 加密貨幣 Fear & Greed Index
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=15).json()
        v_crypto = res['data'][0]['value']
    except Exception as e:
        errors.append(f"加密 F&G 失敗: {e}")

    return v_us, v_tw, v_crypto, errors


# --- 5. 頁面呈現 ---
st.markdown("<h1>🛡️ Global Intel Center</h1>", unsafe_allow_html=True)

# 時間顯示
now_tw = datetime.now(tz_tw)
now_us = datetime.now(tz_us)
st.markdown(f"""
    <div class="time-container">
        <div style="text-align:center;"><div style="font-size:10px;color:#aaa;">🇹🇼 台北</div><b>{now_tw.strftime("%H:%M:%S")}</b></div>
        <div style="text-align:center;"><div style="font-size:10px;color:#aaa;">🇺🇸 華盛頓</div><b>{now_us.strftime("%H:%M:%S")}</b></div>
    </div>
    """, unsafe_allow_html=True)

# 披薩區
st.subheader("🍕 五角大廈披薩情報")
saved_pizza = load_json(PIZZA_FILE, {"lvl": 1, "pct": 0.0, "update_time": "尚未更新"})
if st.button("🛰️ 更新披薩指數"):
    bar = st.progress(0)
    lvl, pct = get_pizza_intel(bar)
    if lvl is not None:
        save_json(PIZZA_FILE, {
            "lvl": lvl,
            "pct": pct,
            "update_time": datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
        })
        st.rerun()
    bar.empty()

st.markdown(f"""
    <div class="dashboard-card">
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div><p class="market-label">DEFCON</p><p class="db-value" style="font-size:50px;">{saved_pizza['lvl']}</p></div>
            <div><p class="market-label">PIZZA INDEX</p><p class="db-value" style="font-size:50px;">{int(saved_pizza['pct'])}%</p></div>
        </div>
        <p class="update-tag">最後更新：{saved_pizza['update_time']}</p>
    </div>""", unsafe_allow_html=True)

# 市場區
st.divider()
st.subheader("📉 全球市場恐慌監控")
saved_market = load_json(MARKET_FILE, {
    "v_us": "N/A", "v_tw": "N/A", "v_crypto": "N/A", "update_time": "尚未更新"
})

if st.button("📊 更新市場恐慌情報"):
    with st.spinner("抓取最新金融數據..."):
        v_us, v_tw, v_crypto, errors = fetch_market_data()

        any_success = any(v != "N/A" for v in [v_us, v_tw, v_crypto])
        if any_success:
            save_json(MARKET_FILE, {
                "v_us": v_us,
                "v_tw": v_tw,
                "v_crypto": v_crypto,
                "update_time": datetime.now(tz_tw).strftime("%H:%M:%S")
            })

        # 錯誤訊息直接顯示（不收進 expander，方便排查）
        for e in errors:
            st.warning(f"⚠️ {e}")

        if any_success:
            st.rerun()
        else:
            st.error("所有數據源均抓取失敗，請稍後再試。")

m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    st.markdown(
        f'<div class="dashboard-card" style="text-align:center;">'
        f'<p class="market-label">美股 VIX</p>'
        f'<p class="db-value" style="font-size:32px;">{saved_market["v_us"]}</p></div>',
        unsafe_allow_html=True)
with m_col2:
    st.markdown(
        f'<div class="dashboard-card" style="text-align:center;">'
        f'<p class="market-label">台指 VIXTWN</p>'
        f'<p class="db-value" style="font-size:32px;">{saved_market["v_tw"]}</p></div>',
        unsafe_allow_html=True)
with m_col3:
    st.markdown(
        f'<div class="dashboard-card" style="text-align:center;">'
        f'<p class="market-label">加密 F&G</p>'
        f'<p class="db-value" style="font-size:32px;">{saved_market["v_crypto"]}</p></div>',
        unsafe_allow_html=True)

st.caption(f"數據最後更新：{saved_market['update_time']}")
