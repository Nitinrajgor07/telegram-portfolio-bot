"""
Telegram Portfolio Bot — Webhook Receiver
==========================================
Yeh app Render.com (ya kisi bhi free webhook-friendly host) pe deploy hoti hai.
Jab aap Telegram pe /portfolio bhejte ho, Telegram seedha is app ke endpoint
ko call karta hai — koi continuous polling nahi chahiye.

Data source: holdings.json (isi repo mein) — jab bhi Streamlit app mein
BUY/SELL karo, isी file ko bhi update + GitHub pe push karna hai (sync_holdings.py
script se, jo Streamlit app ke folder mein milega).

Live prices: yfinance se directly fetch hote hain, har request pe fresh.
"""

import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
import yfinance as yf
import pytz

app = FastAPI()

IST = pytz.timezone("Asia/Kolkata")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HOLDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings.json")


def ist_now():
    return datetime.now(IST)


def load_holdings():
    """holdings.json se holdings padho — format: { ticker: {shares, avg_price, first_buy_date} }"""
    try:
        with open(HOLDINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def get_live_price(ticker):
    """yfinance se current price + previous close fetch karo, fail hone par None."""
    try:
        info = yf.Ticker(ticker).fast_info
        cur = float(info.last_price)
        prev = float(info.previous_close)
        return cur, prev
    except Exception:
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d").dropna(subset=["Close"])
            if len(hist) >= 2:
                return float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2])
        except Exception:
            pass
    return None, None


def build_portfolio_message():
    """
    Exact wahi format jaisa Streamlit HOLDINGS table mein hai:
    Stock | Qty | Held For | Avg Cost | LTP | Cur. Val | Day's P&L | Total P&L
    Telegram monospace table jaisa dikhega (HTML <pre> tag se).
    """
    holdings = load_holdings()
    if not holdings:
        return "📭 Koi holdings nahi mili. Pehle Streamlit app se sync karo (sync_holdings.py chalao)."

    today = ist_now().date()
    rows = []
    total_cur = 0.0
    total_inv = 0.0
    total_day_pnl = 0.0
    total_pnl = 0.0

    for ticker, h in holdings.items():
        shares = h.get("shares", 0)
        avg_price = h.get("avg_price", 0.0)
        if shares <= 0:
            continue

        cur_p, prev_p = get_live_price(ticker)
        if cur_p is None:
            cur_p = avg_price
            prev_p = avg_price

        inv = shares * avg_price
        cur_v = shares * cur_p
        pnl = cur_v - inv
        pnl_pct = (pnl / inv * 100) if inv else 0
        day_pnl = (cur_p - prev_p) * shares if prev_p else 0
        day_pct = ((cur_p - prev_p) / prev_p * 100) if prev_p else 0

        fb_date_str = h.get("first_buy_date")
        held_days = None
        term_label = ""
        if fb_date_str:
            try:
                fb_date = datetime.strptime(fb_date_str, "%Y-%m-%d").date()
                held_days = (today - fb_date).days
                term_label = "LT" if held_days > 365 else "ST"
            except Exception:
                pass

        name = ticker.replace(".NS", "")
        rows.append({
            "name": name, "shares": shares, "held_days": held_days, "term": term_label,
            "avg": avg_price, "ltp": cur_p, "cur_v": cur_v,
            "day_pnl": day_pnl, "day_pct": day_pct, "pnl": pnl, "pnl_pct": pnl_pct,
        })
        total_cur += cur_v
        total_inv += inv
        total_day_pnl += day_pnl
        total_pnl += pnl

    # Sort by total P&L descending — sabse zyada profit upar
    rows.sort(key=lambda r: r["pnl"], reverse=True)

    lines = []
    lines.append(f"📊 <b>HOLDINGS</b>  ({ist_now().strftime('%d %b %Y, %I:%M %p')})")
    lines.append("")

    for r in rows:
        day_arrow = "🟢" if r["day_pnl"] >= 0 else "🔴"
        tot_arrow = "▲" if r["pnl"] >= 0 else "▼"
        held_str = f"{r['held_days']}d ({r['term']})" if r["held_days"] is not None else "—"
        lines.append(f"<b>{r['name']}</b>  ·  {int(r['shares'])} shares  ·  Held {held_str}")
        lines.append(f"  Avg ₹{r['avg']:,.2f} → LTP ₹{r['ltp']:,.2f}  |  Val ₹{r['cur_v']:,.0f}")
        lines.append(f"  {day_arrow} Day: ₹{r['day_pnl']:+,.0f} ({r['day_pct']:+.2f}%)   "
                     f"{tot_arrow} Total: ₹{r['pnl']:+,.0f} ({r['pnl_pct']:+.2f}%)")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"<b>TOTAL</b>  Cur. Val: ₹{total_cur:,.0f}  (Invested ₹{total_inv:,.0f})")
    day_arrow_t = "🟢" if total_day_pnl >= 0 else "🔴"
    tot_arrow_t = "▲" if total_pnl >= 0 else "▼"
    total_day_pct = (total_day_pnl / (total_cur - total_day_pnl) * 100) if (total_cur - total_day_pnl) else 0
    total_pnl_pct = (total_pnl / total_inv * 100) if total_inv else 0
    lines.append(f"{day_arrow_t} Day's P&L: ₹{total_day_pnl:+,.0f} ({total_day_pct:+.2f}%)")
    lines.append(f"{tot_arrow_t} Total P&L: ₹{total_pnl:+,.0f} ({total_pnl_pct:+.2f}%)")

    return "\n".join(lines)


async def send_telegram_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram yahan POST karta hai jab koi message aata hai."""
    data = await request.json()
    message = data.get("message", {})
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    if not chat_id:
        return {"ok": True}

    if text in ("/portfolio", "/holdings", "/start"):
        try:
            reply = build_portfolio_message()
        except Exception as e:
            reply = f"⚠️ Error: {e}"
        await send_telegram_message(chat_id, reply)
    else:
        await send_telegram_message(
            chat_id,
            "Samajh nahi aaya. /portfolio bhejो current holdings dekhne ke liye."
        )

    return {"ok": True}


@app.get("/")
async def health_check():
    return {"status": "Bot is running"}
