"""
Educational Stock Idea Scanner - Mobile Version
FOR LEARNING PURPOSES ONLY – NOT FINANCIAL ADVICE
"""

import streamlit as st
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import yfinance as yf
from datetime import datetime
import re
from collections import defaultdict

# Page settings
st.set_page_config(
    page_title="Educational Stock Scanner",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Auto refresh every 2 minutes
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=120 * 1000, key="refresh")
except:
    pass

# Blacklist of common non-tickers
BLACKLIST = {
    "CEO", "CFO", "CTO", "COO", "IPO", "GDP", "FED", "SEC", "USA", "USD",
    "THE", "AND", "FOR", "NEW", "TOP", "ALL", "BIG", "NOW", "OUT", "YOU",
    "BUY", "SELL", "HOLD", "NEWS", "STOCK", "MARKET", "SHARES", "PRICE"
}

TOP_N = 8   # Show more candidates

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
    "salesforce": "CRM", "adobe": "ADBE", "shopify": "SHOP",
    "coinbase": "COIN", "sofi": "SOFI", "robinhood": "HOOD",
}

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
            result = sentiment_model(text)[0]
            label = result["label"].lower()
            score = result["score"]
            if label == "positive":
                return score
            elif label == "negative":
                return -score
            return 0.0
        except:
            pass
    scores = sentiment_model.polarity_scores(text)
    return scores["compound"]

def extract_tickers(text):
    text_lower = text.lower()
    found = set()

    # Name matching
    for name, ticker in NAME_TO_TICKER.items():
        if name in text_lower:
            found.add(ticker)

    # $TICKER or uppercase words
    matches = re.findall(r'\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])', text)
    for m in matches:
        t = m[0] or m[1]
        if t and t.isalpha() and 2 <= len(t) <= 5 and t not in BLACKLIST:
            found.add(t)

    return list(found)

def get_price_info(ticker):
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

@st.cache_data(ttl=90)
def run_scan():
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                text = f"{title}. {summary}"
                if len(text) > 30:
                    articles.append({"title": title, "text": text})
        except:
            continue

    ticker_data = defaultdict(list)
    for art in articles:
        sent = get_sentiment(art["text"])
        for t in extract_tickers(art["text"]):
            ticker_data[t].append({
                "title": art["title"],
                "sentiment": sent
            })

    ideas = []
    for ticker, items in ticker_data.items():
        compounds = [i["sentiment"] for i in items]
        avg_sent = sum(compounds) / len(compounds)
        score = avg_sent * (1 + 0.15 * min(len(items), 5))

        price_info = get_price_info(ticker)

        # Simple confirmation boost
        if price_info:
            if score > 0.15 and price_info.get("chg_5d", 0) > 1.5:
                score *= 1.12
            elif score < -0.15 and price_info.get("chg_5d", 0) < -1.5:
                score *= 1.12

        if score >= 0.18:
            signal = "BUY"
        elif score <= -0.18:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        ideas.append({
            "ticker": ticker,
            "score": score,
            "signal": signal,
            "mentions": len(items),
            "headlines": [i["title"] for i in items[:2]],
            "price_info": price_info
        })

    ideas.sort(key=lambda x: abs(x["score"]), reverse=True)
    return ideas

# ====================== UI ======================
st.title("📊 Educational Stock Scanner")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Auto-refreshes every 2 min")

st.warning("**Educational only – Not financial advice.** These are idea candidates based on news sentiment, not real recommendations.")

with st.spinner("Scanning latest news..."):
    ideas = run_scan()

buys = [i for i in ideas if i["signal"] == "BUY"][:TOP_N]
sells = [i for i in ideas if i["signal"] == "SELL"][:TOP_N]
neutrals = [i for i in ideas if i["signal"] == "NEUTRAL"][:5]

def render_section(title, items, emoji):
    st.subheader(f"{emoji} {title}")
    if not items:
        st.write("None this scan")
        return

    for idea in items:
        price = idea["price_info"]
        price_text = ""
        if price:
            price_text = f"${price.get('price')}  |  1d: {price.get('chg_1d', 0):+.1f}%  |  5d: {price.get('chg_5d', 0):+.1f}%"

        st.markdown(f"**{idea['ticker']}**  •  Score: `{idea['score']:+.3f}`  •  Mentions: {idea['mentions']}")
        if price_text:
            st.caption(price_text)
        for h in idea["headlines"]:
            st.write(f"• {h[:110]}...")
        st.divider()

render_section("CLEAR BUY CANDIDATES", buys, "🟢")
render_section("CLEAR SELL CANDIDATES", sells, "🔴")
render_section("NEUTRAL / WEAK SIGNALS", neutrals, "⚪")

st.caption("This tool is for learning how news + sentiment systems work. Always do your own research.")
