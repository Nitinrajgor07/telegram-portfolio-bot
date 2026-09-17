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
import logging
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
import yfinance as yf
import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_portfolio_bot")

app = FastAPI()

IST = pytz.timezone("Asia/Kolkata")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HOLDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings.json")


def ist_now():
    return datetime.now(IST)


def load_holdings():
    """holdings.json se holdings padho — format: { ticker: {shares, avg_price, first_buy_date} }

    File missing hona ek valid "abhi tak sync nahi hua" state hai, isliye {} return
    hota hai. Lekin corrupt/invalid JSON ek real error hai — usse silently {} return
    karna "koi holdings nahi mili" jaisा galat message dikha deta hai, isliye woh
    propagate hota hai taaki caller usse surface kar sake.
    """
    try:
        with open(HOLDINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("holdings file not found at %s; treating as empty", HOLDINGS_FILE)
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("failed to read holdings file %s: %s", HOLDINGS_FILE, e)
        raise RuntimeError(f"holdings.json padhne mein dikkat: {e}") from e


def get_live_price(ticker):
    """yfinance se current price + previous close fetch karo, fail hone par None.

    Dono attempts fail hone par (None, None) return hota hai, lekin ab exceptions
    silently swallow nahi hoti — log hoti hain taaki price-fetch failures debug ho sakें.
    """
    try:
        info = yf.Ticker(ticker).fast_info
        cur = float(info.last_price)
        prev = float(info.previous_close)
        return cur, prev
    except Exception as e:
        logger.warning("fast_info price fetch failed for %s: %s; trying history fallback", ticker, e)
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d").dropna(subset=["Close"])
            if len(hist) >= 2:
                return float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2])
            logger.warning("history fallback for %s returned insufficient data (%d rows)", ticker, len(hist))
        except Exception as e2:
            logger.warning("history fallback price fetch failed for %s: %s", ticker, e2)
    return None, None


def build_portfolio_message():
    """
    Naya compact format — pehle har holding 3 lines leta tha (10 holdings = 40+
    lines, phone pe wall-of-text). Ab: (1) bada clear summary sabse upar (sabse
    zyada important number turant dikhe), (2) ek compact monospace table — ek
    holding = ek line, taaki phone screen pe bina zyada scroll kiye sab dikh jaaye.
    """
    holdings = load_holdings()
    if not holdings:
        return "📭 Koi holdings nahi mili. Pehle Streamlit app se sync karo (sync_holdings.py chalao)."

    today = ist_now().date()
    rows = []
    stale_tickers = []
    total_cur = 0.0
    total_inv = 0.0
    total_day_pnl = 0.0
    total_pnl = 0.0
    prev_total_val = 0.0

    for ticker, h in holdings.items():
        shares = h.get("shares", 0)
        avg_price = h.get("avg_price", 0.0)
        if shares <= 0:
            continue

        cur_p, prev_p = get_live_price(ticker)
        if cur_p is None:
            # Live price nahi mila — avg_price pe fall back karte hain taaki row
            # dikhe, par isse P&L 0 dikhta hai jo galat/stale hai, isliye ticker ko
            # track karke user ko neeche note dikhate hain (silently hide nahi karte).
            stale_tickers.append(ticker.replace(".NS", ""))
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
            except ValueError as e:
                logger.warning("invalid first_buy_date %r for %s: %s", fb_date_str, ticker, e)

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
        prev_total_val += (prev_p or cur_p) * shares

    # Sort by total P&L descending — sabse zyada profit upar
    rows.sort(key=lambda r: r["pnl"], reverse=True)

    total_pnl_pct = (total_pnl / total_inv * 100) if total_inv else 0
    total_day_pct = (total_day_pnl / prev_total_val * 100) if prev_total_val else 0
    day_emoji = "🟢" if total_day_pnl >= 0 else "🔴"
    tot_emoji = "📈" if total_pnl >= 0 else "📉"

    lines = []
    # ── Header ──────────────────────────────────────────────────────────────
    lines.append(f"📊 <b>PORTFOLIO</b>  •  {ist_now().strftime('%d %b, %I:%M %p')}")
    lines.append("")

    # ── BIG summary — sabse zyada important number sabse pehle ───────────────
    lines.append(f"💰 <b>₹{total_cur:,.0f}</b>  <i>(invested ₹{total_inv:,.0f})</i>")
    lines.append(f"{day_emoji} Day:   <b>₹{total_day_pnl:+,.0f}</b>  ({total_day_pct:+.2f}%)")
    lines.append(f"{tot_emoji} Total: <b>₹{total_pnl:+,.0f}</b>  ({total_pnl_pct:+.2f}%)")
    lines.append("")

    # ── Compact monospace table — 1 holding = 1 line ─────────────────────────
    # Telegram <pre> block monospace font use karta hai, isliye columns align
    # honge — fixed-width padding se. Emoji ko pre ke bahar/start mein rakha
    # hai consistency ke liye, lekin yahan text-symbol use kiya emoji ki jagah
    # taaki monospace alignment kabhi na bigde (kuch fonts mein emoji-width
    # vary karti hai).
    table_lines = []
    table_lines.append(f"{'STOCK':<10}{'DAY%':>8}{'TOTAL%':>9}{'VALUE':>10}")
    table_lines.append("─" * 37)
    for r in rows:
        day_sign = "+" if r["day_pct"] >= 0 else ""
        tot_sign = "+" if r["pnl_pct"] >= 0 else ""
        day_mark = "▲" if r["day_pct"] >= 0 else "▼"
        tot_mark = "▲" if r["pnl_pct"] >= 0 else "▼"
        name_short = r["name"][:9]
        val_str = f"{r['cur_v']/100000:,.1f}L" if r["cur_v"] >= 100000 else f"{r['cur_v']:,.0f}"
        table_lines.append(
            f"{name_short:<10}" +
            (f"{day_mark}{day_sign}{r['day_pct']:.1f}%").rjust(8) +
            (f"{tot_mark}{tot_sign}{r['pnl_pct']:.1f}%").rjust(9) +
            f"{val_str}".rjust(10)
        )
    lines.append("<pre>" + "\n".join(table_lines) + "</pre>")

    # ── Top mover callout — quick highlight ───────────────────────────────────
    if rows:
        best = max(rows, key=lambda r: r["day_pct"])
        worst = min(rows, key=lambda r: r["day_pct"])
        if best["day_pct"] > 0:
            lines.append(f"🚀 Best today: <b>{best['name']}</b> ({best['day_pct']:+.2f}%)")
        if worst["day_pct"] < 0:
            lines.append(f"⚠️ Worst today: <b>{worst['name']}</b> ({worst['day_pct']:+.2f}%)")

    # ── Stale-price warning — live price fetch fail hui in tickers ke liye ─────
    if stale_tickers:
        lines.append("")
        lines.append(
            "⚠️ <i>Live price nahi mila (avg cost pe dikha rahe hain): "
            + ", ".join(stale_tickers)
            + "</i>"
        )

    return "\n".join(lines)


async def send_telegram_message(chat_id, text):
    """Telegram sendMessage API call karo.

    Pehle yeh response ko poori tarah ignore karta tha — HTTP timeout, network
    error, ya Telegram ka non-2xx (jaisे invalid HTML parse) sab silently chale
    jaate the. Ab timeout set hai, response status check hota hai, aur error par
    exception raise hoti hai taaki caller usse handle/log kar sake.
    """
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN set nahi hai — message send nahi ho sakta.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
    if resp.status_code >= 400:
        logger.error(
            "telegram sendMessage failed for chat %s: HTTP %s %s",
            chat_id, resp.status_code, resp.text,
        )
        resp.raise_for_status()
    return resp


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram yahan POST karta hai jab koi message aata hai."""
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError) as e:
        # Malformed body — Telegram retry na kare isliye 200 return karte hain,
        # par error swallow nahi karte: log hota hai.
        logger.warning("received webhook with non-JSON body: %s", e)
        return {"ok": False, "error": "invalid JSON body"}

    if not isinstance(data, dict):
        logger.warning("received webhook payload that is not an object: %r", type(data).__name__)
        return {"ok": False, "error": "unexpected payload"}

    message = data.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")

    if not chat_id:
        return {"ok": True}

    if text in ("/portfolio", "/holdings", "/start"):
        try:
            reply = build_portfolio_message()
        except Exception:
            # Poora traceback log karte hain, par user ko raw internal error leak
            # nahi karte — ek generic message dikhate hain.
            logger.exception("failed to build portfolio message for chat %s", chat_id)
            reply = "⚠️ Portfolio banate waqt error aa gaya. Thodi der baad phir try karo."
    else:
        reply = "Samajh nahi aaya. /portfolio bhejो current holdings dekhne ke liye."

    try:
        await send_telegram_message(chat_id, reply)
    except Exception:
        logger.exception("failed to send telegram message to chat %s", chat_id)
        return {"ok": False, "error": "send failed"}

    return {"ok": True}


@app.get("/")
async def health_check():
    return {"status": "Bot is running"}
