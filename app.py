"""
Educational Stock Idea Scanner - Improved Version
FOR LEARNING PURPOSES ONLY – NOT FINANCIAL ADVICE
"""

import streamlit as st
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import yfinance as yf
from datetime import datetime
import re
from collections import defaultdict

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
    "FUND", "BANK", "CITY", "STATE", "YEAR", "TIME", "RATE", "RISE",
    "FUTURES", "STOCKS", "GAINS", "HIGHER", "LOWER"
}

TOP_N = 6

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.marketwatch.com/rss/topstories",
    "https://www.investing.com/rss/news.rss",
    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
    "https://moxie.foxbusiness.com/google-publisher/markets.xml",
    "https://seekingalpha.com/market_currents.xml",
    "https://www.businessinsider.com/rss",
]

NAME_TO_TICKER = {
    "tesla": "TSLA", "elon musk": "TSLA",
    "apple": "AAPL", "nvidia": "NVDA", "jensen huang": "NVDA",
    "microsoft": "MSFT", "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL",
    "meta": "META", "facebook": "META", "netflix": "NFLX",
    "amd": "AMD", "intel": "INTC", "broadcom": "AVGO",
    "boeing": "BA", "disney": "DIS", "palantir": "PLTR",
    "costco": "COST", "walmart": "WMT", "jpmorgan": "JPM", "jp morgan": "JPM",
    "goldman sachs": "GS", "berkshire": "BRK-B",
    "salesforce": "CRM", "adobe": "ADBE", "shopify": "SHOP",
    "coinbase": "COIN", "sofi": "SOFI", "robinhood": "HOOD",
    "uber": "UBER", "lyft": "LYFT", "airbnb": "ABNB",
    "spotify": "SPOT", "block": "SQ", "square": "SQ",
    "crowdstrike": "CRWD", "snowflake": "SNOW", "datadog": "DDOG",
    "paypal": "PYPL", "visa": "V", "mastercard": "MA",
}

BULLISH_CATALYSTS = [
    "upgrade", "upgrades", "raises guidance", "raised guidance", "beats estimates",
    "beat estimates", "strong earnings", "record revenue", "acquires", "acquisition",
    "partnership", "fda approval", "contract win", "major deal", "buyback"
]

BEARISH_CATALYSTS = [
    "downgrade", "downgrades", "cuts guidance", "misses estimates", "missed estimates",
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
    text = (text or "")[:450]
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

    # Prefer company name matches
    for name, ticker in NAME_TO_TICKER.items():
        if name in text_lower:
            found.add(ticker)

    # Only add raw tickers if they look clean
    matches = re.findall(r'\$([A-Z]{1,5})\b', text)
    for t in matches:
        if t not in BLACKLIST and 2 <= len(t) <= 5:
            found.add(t)

    return list(found)

def get_market_context(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1mo")
        if len(hist) < 20:
            return None

        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        week_ago = hist["Close"].iloc[-5]

        sma20 = hist["Close"].rolling(20).mean().iloc[-1]
        sma50 = hist["Close"].rolling(20).mean().iloc[-1]  # using 20 for speed on free tier

        avg_vol = hist["Volume"].tail(8).mean()
        vol_ratio = hist["Volume"].iloc[-1] / avg_vol if avg_vol > 0 else 1.0

        # Relative strength vs SPY
        spy = yf.Ticker("SPY").history(period="1mo")
        rs = None
        if len(spy) >= 5:
            spy_chg = (spy["Close"].iloc[-1] / spy["Close"].iloc[-5] - 1) * 100
            stock_chg = (last / week_ago - 1) * 100
            rs = stock_chg - spy_chg

        trend = "Above 20 SMA" if last > sma20 else "Below 20 SMA"

        return {
            "price": round(last, 2),
            "chg_1d": round((last / prev - 1) * 100, 2),
            "chg_5d": round((last / week_ago - 1) * 100, 2),
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
            boost += 0.22
    for word in BEARISH_CATALYSTS:
        if word in text_lower:
            boost -= 0.22
    return boost

# -------------------- Main Scan --------------------
@st.cache_data(ttl=110)
def run_scan():
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                text = f"{title}. {summary}"
                if len(text) > 40:
                    articles.append({"title": title, "text": text})
        except:
            continue

    ticker_map = defaultdict(list)
    for art in articles:
        sent = get_sentiment(art["text"]) + catalyst_boost(art["text"])
        for t in extract_tickers(art["text"]):
            ticker_map[t].append({
                "title": art["title"],
                "sentiment": sent
            })

    ideas = []
    for ticker, items in ticker_map.items():
        ctx = get_market_context(ticker)
        if ctx is None:
            continue

        compounds = [i["sentiment"] for i in items]
        avg_sent = sum(compounds) / len(compounds)
        mentions = len(items)

        score = avg_sent * (1 + 0.12 * min(mentions, 4))

        # Technical confirmation
        if score > 0.15 and ctx["chg_5d"] > 1.2 and (ctx.get("rs_vs_spy") or 0) > 0.8:
            score *= 1.12

        # High Conviction rules (much stricter)
        high_conviction = False
        if score >= 0.32 and mentions >= 2:
            high_conviction = True
        if score >= 0.38:
            high_conviction = True
        # Must have some positive price action for high conviction buys
        if high_conviction and score > 0 and ctx["chg_5d"] < 0:
            high_conviction = False

        if score >= 0.18:
            signal = "BUY"
        elif score <= -0.20:
            signal = "SELL"
        elif score >= 0.08:
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
            "context": ctx
        })

    ideas.sort(key=lambda x: abs(x["score"]), reverse=True)
    return ideas

# -------------------- UI --------------------
st.title("📊 Educational Stock Scanner")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} • Auto-refreshes every 2 min")

st.warning("**Educational only – Not financial advice.** These are idea candidates, not recommendations.")

with st.spinner("Scanning news + price action..."):
    ideas = run_scan()

high_conv = [i for i in ideas if i["signal"] == "BUY" and i["high_conviction"]][:4]
buys = [i for i in ideas if i["signal"] == "BUY" and not i["high_conviction"]][:TOP_N]
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
        
        # Cleaner mobile technical line
        tech_line = f"${ctx['price']}   |   1d: {ctx['chg_1d']:+.1f}%   |   5d: {ctx['chg_5d']:+.1f}%"
        st.caption(tech_line)
        
        extra = f"{ctx['trend']}   •   Vol: {ctx['vol_ratio']:.1f}x"
        if ctx.get("rs_vs_spy") is not None:
            extra += f"   •   RS: {ctx['rs_vs_spy']:+.1f}"
        st.caption(extra)

        for h in idea["headlines"]:
            st.write(f"• {h[:100]}...")
        st.divider()

render_section("HIGH CONVICTION BUYS", high_conv, "🟢🟢")
render_section("BUY CANDIDATES", buys, "🟢")
render_section("WATCHLIST", watches, "🟡")
render_section("SELL CANDIDATES", sells, "🔴")

st.caption("Combines news sentiment + price/volume context for educational use only.")
