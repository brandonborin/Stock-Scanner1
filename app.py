"""
Educational Stock Idea Scanner - Mobile Streamlit Version
FOR LEARNING PURPOSES ONLY - NOT FINANCIAL ADVICE
"""

import streamlit as st
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import yfinance as yf
import pandas as pd
from datetime import datetime
import re
import requests
from collections import defaultdict
import time

# --------------------------
# Page Config (Mobile Friendly)
# --------------------------
st.set_page_config(
    page_title="Educational Stock Scanner",
    page_icon="📊",
    layout="centered",          # Better for phones
    initial_sidebar_state="collapsed"
)

# Auto-refresh every 120 seconds
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=120 * 1000, key="auto_refresh")
except:
    st.info("Install streamlit-autorefresh for automatic updates")

# --------------------------
# Config
# --------------------------
TOP_N = 8

# Optional free API keys (leave empty if you don't have them)
ALPHA_VANTAGE_KEY = st.secrets.get("ALPHA_VANTAGE_KEY", "") if "ALPHA_VANTAGE_KEY" in st.secrets else ""
CURRENTS_API_KEY = st.secrets.get("CURRENTS_API_KEY", "") if "CURRENTS_API_KEY" in st.secrets else ""
FINNHUB_KEY = st.secrets.get("FINNHUB_KEY", "") if "FINNHUB_KEY" in st.secrets else ""
NEWSDATA_KEY = st.secrets.get("NEWSDATA_KEY", "") if "NEWSDATA_KEY" in st.secrets else ""

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.marketwatch.com/rss/topstories",
    "https://www.investing.com/rss/news.rss",
]

NAME_TO_TICKER = {
    "tesla": "TSLA", "elon musk": "TSLA",
    "apple": "AAPL", "nvidia": "NVDA", "jensen huang": "NVDA",
    "microsoft": "MSFT", "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL",
    "meta": "META", "facebook": "META", "netflix": "NFLX",
    "amd": "AMD", "intel": "INTC", "broadcom": "AVGO",
    "boeing": "BA", "disney": "DIS", "palantir": "PLTR",
    "costco": "COST", "walmart": "WMT", "jpmorgan": "JPM",
    "goldman sachs": "GS", "berkshire": "BRK-B",
}

# --------------------------
# Sentiment
# --------------------------
@st.cache_resource
def load_sentiment():
    try:
        from transformers import pipeline
        return pipeline("sentiment-analysis", model="ProsusAI/finbert"), True
    except:
        return SentimentIntensityAnalyzer(), False

sentiment_model, use_finbert = load_sentiment()

def get_sentiment(text):
    text = (text or "")[:500]
    if use_finbert:
        try:
            r = sentiment_model(text)[0]
            label = r["label"].lower()
            score = r["score"]
            compound = score if label == "positive" else -score if label == "negative" else 0.0
            return compound
        except:
            pass
    scores = sentiment_model.polarity_scores(text)
    return scores["compound"]

# --------------------------
# Data functions
# --------------------------
def extract_tickers(text):
    text_l = text.lower()
    found = set()
    for name, ticker in NAME_TO_TICKER.items():
        if name in text_l:
            found.add(ticker)
    for m in re.findall(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])', text):
        t = m[0] or m[1]
        if t and t.isalpha() and 1 < len(t) <= 5:
            found.add(t)
    return list(found)

def fetch_rss():
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:8]:
                title = e.get("title", "").strip()
                summary = e.get("summary", e.get("description", "")).strip()
                text = f"{title}. {summary}"
                if len(text) > 30:
                    articles.append({"title": title, "text": text, "source": "RSS"})
        except:
            pass
    return articles

def get_market_context(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="7d")
        if len(hist) < 3:
            return {}
        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        week = hist["Close"].iloc[0]
        return {
            "price": round(last, 2),
            "chg_1d": round(((last - prev) / prev) * 100, 2),
            "chg_5d": round(((last - week) / week) * 100, 2)
        }
    except:
        return {}

@st.cache_data(ttl=100)  # Cache for ~1.5 minutes
def run_scan():
    articles = fetch_rss()
    # You can add more free API fetches here later

    ticker_map = defaultdict(list)
    for art in articles:
        sent = get_sentiment(art["text"])
        for t in extract_tickers(art["text"]):
            ticker_map[t].append({"title": art["title"], "sentiment": sent, "source": art["source"]})

    ideas = []
    for ticker, items in ticker_map.items():
        compounds = [i["sentiment"] for i in items]
        avg = sum(compounds) / len(compounds)
        score = avg * (1 + 0.12 * min(len(items), 5))
        ctx = get_market_context(ticker)

        if ctx:
            if score > 0.15 and ctx.get("chg_5d", 0) > 1.5:
                score *= 1.1
            elif score < -0.15 and ctx.get("chg_5d", 0) < -1.5:
                score *= 1.1

        if score >= 0.20:
            signal = "BUY"
        elif score <= -0.20:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        ideas.append({
            "ticker": ticker,
            "score": score,
            "signal": signal,
            "mentions": len(items),
            "headlines": [i["title"] for i in items[:2]],
            "context": ctx
        })

    ideas.sort(key=lambda x: abs(x["score"]), reverse=True)
    return ideas

# --------------------------
# UI
# --------------------------
st.title("📊 Educational Stock Scanner")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Auto-refreshes every 2 min")

st.warning("**Educational only – Not financial advice.** These are not real buy/sell recommendations.")

with st.spinner("Scanning news sources..."):
    ideas = run_scan()

buys = [i for i in ideas if i["signal"] == "BUY"][:TOP_N]
sells = [i for i in ideas if i["signal"] == "SELL"][:TOP_N]
neutrals = [i for i in ideas if i["signal"] == "NEUTRAL"][:5]

def show_section(title, items, color):
    st.subheader(title)
    if not items:
        st.write("None this scan")
        return
    for idea in items:
        ctx = idea["context"]
        price_info = ""
        if ctx:
            price_info = f"${ctx.get('price')}  |  1d: {ctx.get('chg_1d', 0):+.1f}%  |  5d: {ctx.get('chg_5d', 0):+.1f}%"
        
        with st.container():
            st.markdown(f"**{idea['ticker']}**  •  Score: `{idea['score']:+.3f}`  •  Mentions: {idea['mentions']}")
            if price_info:
                st.caption(price_info)
            for h in idea["headlines"]:
                st.write(f"• {h[:110]}...")
            st.divider()

show_section("🟢 CLEAR BUY CANDIDATES", buys, "green")
show_section("🔴 CLEAR SELL CANDIDATES", sells, "red")
show_section("⚪ NEUTRAL / WEAK", neutrals, "gray")

st.caption("This tool is for learning how news + sentiment pipelines work. Always do your own research.")
