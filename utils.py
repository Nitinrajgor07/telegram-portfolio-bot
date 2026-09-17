"""
Shared formatting/utility helpers
==================================
telegram_bot_main.py mein kuch chhote patterns baar-baar repeat ho rahe the
(sign nikalna, ▲/▼ mark, emoji chunna, ₹ value ko short karna). Un sabko yahan
ek jagah rakh diya taaki ek hi behaviour har jagah consistent rahe aur future
mein change karna ho to sirf yahi file chhedni pade.
"""

from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")


def ist_now():
    """Abhi ka time IST mein."""
    return datetime.now(IST)


def sign_emoji(value, up="🟢", down="🔴"):
    """value >= 0 par `up` emoji, warna `down` emoji."""
    return up if value >= 0 else down


def format_pct_cell(pct, width):
    """
    Monospace table ke liye ek percent cell: `▲+1.2%` / `▼-3.4%`, right-aligned.
    Pehle day% aur total% dono ke liye yeh exact same 3 lines alag-alag likhi
    thi — ab ek hi jagah.
    """
    mark = "▲" if pct >= 0 else "▼"
    sign = "+" if pct >= 0 else ""
    return f"{mark}{sign}{pct:.1f}%".rjust(width)


def format_short_value(value):
    """Badi value ko lakh (L) notation mein short karo, chhoti ko as-is."""
    if value >= 100000:
        return f"{value / 100000:,.1f}L"
    return f"{value:,.0f}"
