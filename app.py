"""
Educational Stock Idea Scanner - Advanced Version
FOR LEARNING PURPOSES ONLY – NOT FINANCIAL ADVICE
"""

import streamlit as st
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import yfinance as yf
from datetime import datetime
import re
from collections import defaultdict
import pandas as pd

st.set_page_config(
    page_title="Educational Stock Scanner",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=120 * 1000, key="refresh")
except:
    pass

# -------------------- Config --------------------
BLACKLIST = {
    "CEO", "CFO", "CTO", "COO", "IPO", "GDP", "FED", "SEC", "USA", "USD",
    "THE", "AND", "FOR", "NEW", "TOP", "ALL", "BIG", "NOW", "OUT", "YOU",
    "BUY", "SELL", "HOLD", "NEWS", "STOCK", "MARKET", "SHARES", "PRICE",
    "HOME", "PLAN", "WORLD", "LARGE", "BUILD", "AFTER", "MOVING",
    "NYC", "LA", "SF", "DC", "UK", "EU", "AI", "EV", "TECH", "DATA",
    "FUND", "BANK", "CITY", "STATE", "YEAR", "TIME", "RATE", "RISE"
}

TOP_N = 7

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.marketwatch.com/rss/topstories",
    "https://www.investing.com/rss/news.rss",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=stocks+OR+%22stock+market%22+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://moxie.foxbusiness.com/google-publisher/latest.xml",
    "https://moxie.foxbusiness.com/google-publisher/markets.xml",
    "https://seekingalpha.com/market_currents.xml",
    "https://www.businessinsider.com/rss",
]

NAME_TO_TICKER = {
    "tesla": "TSLA", "elon musk": "TSLA", "waymo": "GOOGL",
    "apple": "AAPL", "nvidia": "NVDA", "jensen huang": "NVDA",
    "microsoft": "MSFT", "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL",
    "meta": "META", "facebook": "META", "netflix": "NFLX",
    "amd": "AMD", "intel": "INTC", "broadcom": "AVGO",
    "boeing": "BA", "disney": "DIS", "palantir": "PLTR",
    "costco": "COST", "walmart": "WMT", "jpmorgan": "JPM", "jp morgan": "JPM",
    "goldman sachs": "GS", "berkshire": "BRK-B", "warren buffett": "BRK-B",
    "salesforce": "CRM", "adobe": "ADBE", "shopify": "SHOP",
    "coinbase": "COIN", "sofi": "SOFI", "robinhood": "HOOD",
    "technology select sector": "XLK", "xlk": "XLK",
}

# Catalyst keywords that increase score
BULLISH_CATALYSTS = [
    "upgrade", "upgrades", "raises", "raised guidance", "beats", "beat estimates",
    "strong earnings", "record revenue", "acquires", "acquisition", "partnership",
    "fda approval", "contract win", "major deal", "buyback", "dividend increase"
]

BEARISH_CATALYSTS = [
    "downgrade", "downgrades", "cuts guidance", "misses", "missed estimates",
    "weak earnings", "investigation", "lawsuit", "sec probe", "fraud", "recall"
]

# -------------------- Helpers --------------------
@st.cache_resource
def load_sentiment():
    try:
        from transformers import pipeline
        return pipeline("sentiment-analysis", model="ProsusAI/finbert"), True
    except:
        return SentimentIntensityAnalyzer(), False

sentiment_model, use_finbert = load_sentiment()

def get_sentiment(text):
    text = (text or "")[:512]
    if use_finbert:
        try:
            result = sentiment_model(text)[0]
            label = result["label"].lower()
            score = result["score"]
            return score if label == "positive" else -score if label == "negative" else 0.0
        except:
            pass
    return sentiment_model.polarity_scores(text)["compound"]

def extract_tickers(text):
    text_lower = text.lower()
    found = set()
    for name, ticker in NAME_TO_TICKER.items():
        if name in text_lower:
            found.add(ticker)

    matches = re.findall(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])', text)
    for m in matches:
        t = (m[0] or m[1]).upper()
        if t and t.isalpha() and 2 <= len(t) <= 5 and t not in BLACKLIST:
            found.add(t)
    return list(found)

def get_market_context(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        if len(hist) < 50:
            return None

        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        week_ago = hist["Close"].iloc[-6] if len(hist) > 6 else prev

        # Moving averages
        sma20 = hist["Close"].rolling(20).mean().iloc[-1]
        sma50 = hist["Close"].rolling(50).mean().iloc[-1]

        # Volume
        avg_vol = hist["Volume"].tail(10).mean()
        last_vol = hist["Volume"].iloc[-1]
        vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

        # Relative strength vs SPY
        spy = yf.Ticker("SPY").history(period="1mo")
        rs = None
        if len(spy) > 6:
            spy_chg = (spy["Close"].iloc[-1] / spy["Close"].iloc[-6] - 1) * 100
            stock_chg = (last / week_ago - 1) * 100
            rs = stock_chg - spy_chg

        trend = "Above 20 & 50 SMA" if last > sma20 and last > sma50 else \
                "Below both SMAs" if last < sma20 and last < sma50 else "Mixed"

        return {
            "price": round(last, 2),
            "chg_1d": round((last / prev - 1) * 100, 2),
            "chg_5d": round((last / week_ago - 1) * 100, 2),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "vol_ratio": round(vol_ratio, 2),
            "rs_vs_spy": round(rs, 2) if rs is not None else None,
            "trend": trend
        }
    except:
        return None

def catalyst_boost(text):
    text_lower = text.lower()
    boost = 0.0
    for word in BULLISH_CATALYSTS:
        if word in text_lower:
            boost += 0.18
    for word in BEARISH_CATALYSTS:
        if word in text_lower:
            boost -= 0.18
    return boost

# -------------------- Main Scan --------------------
@st.cache_data(ttl=100)
def run_scan():
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:7]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                text = f"{title}. {summary}"
                if len(text) > 35:
                    articles.append({"title": title, "text": text})
        except:
            continue

    ticker_map = defaultdict(list)
    for art in articles:
        sent = get_sentiment(art["text"])
        boost = catalyst_boost(art["text"])
        for t in extract_tickers(art["text"]):
            ticker_map[t].append({
                "title": art["title"],
                "sentiment": sent + boost
            })

    # Market regime
    spy_context = get_market_context("SPY")
    market_weak = False
    if spy_context and spy_context["trend"] == "Below both SMAs":
        market_weak = True

    ideas = []
    for ticker, items in ticker_map.items():
        ctx = get_market_context(ticker)
        if ctx is None:
            continue

        compounds = [i["sentiment"] for i in items]
        avg_sent = sum(compounds) / len(compounds)
        mentions = len(items)

        score = avg_sent * (1 + 0.15 * min(mentions, 4))

        # Technical confirmation
        if score > 0.12 and ctx["chg_5d"] > 1.5 and ctx.get("rs_vs_spy", 0) > 1:
            score *= 1.15
        elif score < -0.12 and ctx["chg_5d"] < -1.5:
            score *= 1.15

        # Volume confirmation
        if ctx["vol_ratio"] > 1.4 and abs(score) > 0.15:
            score *= 1.08

        # High conviction rules
        high_conviction = False
        if abs(score) >= 0.28 and mentions >= 2:
            high_conviction = True
        if abs(score) >= 0.35:
            high_conviction = True

        if score >= 0.16:
            signal = "BUY"
        elif score <= -0.18:
            signal = "SELL"
        elif score >= 0.07:
            signal = "WATCH"
        else:
            signal = "NEUTRAL"

        ideas.append({
            "ticker": ticker,
            "score": score,
            "signal": signal,
            "high_conviction": high_conviction,
            "mentions": mentions,
            "headlines": [i["title"] for i in items[:2]],
            "context": ctx,
            "market_weak": market_weak
        })

    ideas.sort(key=lambda x: abs(x["score"]), reverse=True)
    return ideas, market_weak

# -------------------- UI --------------------
st.title("📊 Educational Stock Scanner")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} • Auto-refreshes every 2 min")

st.warning("**Educational only – Not financial advice.** These are idea candidates, not recommendations.")

with st.spinner("Scanning news + analyzing price action..."):
    ideas, market_weak = run_scan()

if market_weak:
    st.info("Market regime note: SPY is below both 20 & 50-day SMAs → overall environment is weaker.")

high_conv_buys = [i for i in ideas if i["signal"] == "BUY" and i["high_conviction"]][:5]
regular_buys = [i for i in ideas if i["signal"] == "BUY" and not i["high_conviction"]][:TOP_N]
watches = [i for i in ideas if i["signal"] == "WATCH"][:TOP_N]
sells = [i for i in ideas if i["signal"] == "SELL"][:TOP_N]

def render_section(title, items, emoji):
    st.subheader(f"{emoji} {title}")
    if not items:
        st.write("None this scan")
        return

    for idea in items:
        ctx = idea["context"]
        st.markdown(f"**{idea['ticker']}**  •  Score: `{idea['score']:+.3f}`  •  Mentions: {idea['mentions']}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"${ctx['price']}  |  1d: {ctx['chg_1d']:+.1f}%  |  5d: {ctx['chg_5d']:+.1f}%")
        with col2:
            rs_text = f"RS vs SPY: {ctx['rs_vs_spy']:+.1f}" if ctx.get("rs_vs_spy") is not None else ""
            st.caption(f"{ctx['trend']}  |  Vol: {ctx['vol_ratio']:.1f}x  {rs_text}")

        for h in idea["headlines"]:
            st.write(f"• {h[:105]}...")
        st.divider()

render_section("HIGH CONVICTION BUYS", high_conv_buys, "🟢🟢")
render_section("BUY CANDIDATES", regular_buys, "🟢")
render_section("WATCHLIST", watches, "🟡")
render_section("SELL CANDIDATES", sells, "🔴")

st.caption("This tool combines news sentiment + basic price/volume context for educational purposes only.")
