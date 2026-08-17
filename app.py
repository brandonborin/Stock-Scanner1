"""
Educational Stock Idea Scanner - Quality Focused Version
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

# Low quality headline patterns (heavily penalized)
LOW_QUALITY_PHRASES = [
    "here are", "stocks to watch", "stocks primed", "stocks that could",
    "best stocks", "top stocks", "stocks for", "stocks set to",
    "20 stocks", "10 stocks", "15 stocks", "stocks to buy",
    "could benefit", "may benefit", "poised to", "ready to surge"
]

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
    "partnership", "fda approval", "contract win", "major deal", "buyback",
    "price target raised", "outperform"
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

def is_low_quality_headline(text):
    text_lower = text.lower()
    for phrase in LOW_QUALITY_PHRASES:
        if phrase in text_lower:
            return True
    return False

def extract_tickers(text):
    text_lower = text.lower()
    found = set()

    for name, ticker in NAME_TO_TICKER.items():
        if name in text_lower:
            found.add(ticker)

    matches = re.findall(r'\$([A-Z]{1,5})\b', text)
    for t in matches:
        if t not in BLACKLIST and 2 <= len(t) <= 5:
            found.add(t)

    return list(found)

def get_market_context(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1mo")
        if len(hist) < 15:
            return None

        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]
        week_ago = hist["Close"].iloc[-5]

        sma20 = hist["Close"].rolling(20).mean().iloc[-1]
        avg_vol = hist["Volume"].tail(8).mean()
        vol_ratio = hist["Volume"].iloc[-1] / avg_vol if avg_vol > 0 else 1.0

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
            boost += 0.25
    for word in BEARISH_CATALYSTS:
        if word in text_lower:
            boost -= 0.25
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
        base_sent = get_sentiment(art["text"])
        boost = catalyst_boost(art["text"])

        # Heavy penalty for low quality headlines
        if is_low_quality_headline(art["text"]):
            boost -= 0.35

        final_sent = base_sent + boost

        for t in extract_tickers(art["text"]):
            ticker_map[t].append({
                "title": art["title"],
                "sentiment": final_sent,
                "is_low_quality": is_low_quality_headline(art["text"])
            })

    ideas = []
    for ticker, items in ticker_map.items():
        ctx = get_market_context(ticker)
        if ctx is None:
            continue

        compounds = [i["sentiment"] for i in items]
        avg_sent = sum(compounds) / len(compounds)
        mentions = len(items)
        low_quality_count = sum(1 for i in items if i["is_low_quality"])

        score = avg_sent * (1 + 0.11 * min(mentions, 4))

        # Penalize if most headlines are low quality
        if low_quality_count >= mentions * 0.6:
            score *= 0.65

        # Technical confirmation
        if score > 0.15 and ctx["chg_5d"] > 1.0 and (ctx.get("rs_vs_spy") or 0) > 0.5:
            score *= 1.10

        # ========== STRICT High Conviction Rules ==========
        high_conviction = False

        # Must have strong score
        if score >= 0.36 and mentions >= 2:
            high_conviction = True
        if score >= 0.45:
            high_conviction = True

        # Must not be dominated by low quality headlines
        if low_quality_count > 0 and mentions == 1:
            high_conviction = False

        # Prefer positive price action for high conviction longs
        if high_conviction and score > 0 and ctx["chg_5d"] < -1.0:
            high_conviction = False

        # Signal classification
        if score >= 0.19:
            signal = "BUY"
        elif score <= -0.22:
            signal = "SELL"
        elif score >= 0.09:
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

with st.spinner("Scanning news + analyzing quality..."):
    ideas = run_scan()

high_conv = [i for i in ideas if i["signal"] == "BUY" and i["high_conviction"]][:3]
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
        
        st.caption(f"${ctx['price']}   •   1d: {ctx['chg_1d']:+.1f}%   •   5d: {ctx['chg_5d']:+.1f}%")
        
        extra = f"{ctx['trend']}   •   Vol {ctx['vol_ratio']:.1f}x"
        if ctx.get("rs_vs_spy") is not None:
            extra += f"   •   RS {ctx['rs_vs_spy']:+.1f}"
        st.caption(extra)

        for h in idea["headlines"]:
            st.write(f"• {h[:100]}...")
        st.divider()

render_section("HIGH CONVICTION BUYS", high_conv, "🟢🟢")
render_section("BUY CANDIDATES", buys, "🟢")
render_section("WATCHLIST", watches, "🟡")
render_section("SELL CANDIDATES", sells, "🔴")

st.caption("Focuses on higher-quality news + price context. Educational use only.")
