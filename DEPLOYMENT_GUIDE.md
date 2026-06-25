# 📱 Telegram Portfolio Bot — Deployment Guide

Yeh guide aapko step-by-step batayegi ki Telegram bot ko **free** mein **24/7 cloud pe** kaise deploy karna hai, taaki laptop band hone par bhi `/portfolio` command kaam kare.

## Kya milega isse
Telegram pe `/portfolio` bhejने par, aapकी holdings ka live snapshot reply mein aayega — Stock, Qty, Held For, Avg Cost, LTP, Day's P&L, Total P&L — bilkul Streamlit HOLDINGS table jaisa, sabse zyada profit wala stock sabse upar.

---

## Step 1 — Telegram Bot Banao (5 minute)

1. Telegram app khोlो, search karo **"BotFather"** (yeh official Telegram bot hai bots banाne ke liye)
2. BotFather ko message karo: `/newbot`
3. Apने bot ka naam pucha jayega (jaisे "My Portfolio Bot") — koi bhi naam do
4. Username pucha jayega (jaisे "myportfolio_bot") — yeh unique hona chahiye, end mein "bot" hona zaroori hai
5. BotFather aapको ek **Bot Token** dega, jaisा:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
   **Yeh token safe rakhो — kisi ko share na karo.**

## Step 2 — GitHub Repository Banao

1. [github.com](https://github.com) pe account banao (free) agar nahi hai
2. Naya repository banao — naam jaisे `telegram-portfolio-bot`
3. Is folder ki saari files (`main.py`, `requirements.txt`, `holdings.json`, `sync_holdings.py`) us repository mein upload karo:
   - GitHub website pe "Add file" → "Upload files" se directly upload kar sakते ho (no command line zaroori nahi)

## Step 3 — Apni Actual Holdings `holdings.json` mein Daalो

1. Apne Streamlit app ke folder mein `sync_holdings.py` ko copy karo (jahaan `portfolio_data.json` hai)
2. Terminal mein chalao:
   ```
   python sync_holdings.py
   ```
3. Yeh `holdings.json` banayegа aapकी **real holdings** ke saath
4. Is naye `holdings.json` ko GitHub repo mein upload kar dो (purani placeholder file ko replace karke)

## Step 4 — Render.com pe Deploy Karo (free hosting)

1. [render.com](https://render.com) pe account banao (free, GitHub se sign-in kar sakते ho)
2. Dashboard mein **"New +"** → **"Web Service"** click karo
3. Apनी GitHub repository connect karo (jo Step 2 mein banाई)
4. Settings:
   - **Name**: kuch bhi (jaisे `portfolio-bot`)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. **Environment Variables** section mein add karo:
   - Key: `TELEGRAM_BOT_TOKEN`
   - Value: woह token jo Step 1 mein mila (jaisे `123456789:ABCdef...`)
6. **"Create Web Service"** click karो — Render automatically build aur deploy kar dega (2-3 minute lagенge)
7. Deploy hone ke baad, aapको ek URL milegа jaisा:
   ```
   https://portfolio-bot-xxxx.onrender.com
   ```
   **Yeh URL note kar lो — agle step mein chahiye.**

## Step 5 — Telegram ko Webhook URL Batao

Apने browser mein yeh URL kholो (apना bot token aur Render URL daal ke):

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_RENDER_URL>/webhook
```

Example:
```
https://api.telegram.org/bot123456789:ABCdefGHI/setWebhook?url=https://portfolio-bot-xxxx.onrender.com/webhook
```

Agar successful hua, browser mein dikhegа:
```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

## Step 6 — Test Karo!

1. Telegram pe apne bot ko search karo (woही username jo Step 1 mein banाया)
2. **"Start"** dabाओ ya `/portfolio` bhejो
3. 2-3 second mein aapकी holdings ka summary reply mein aa jayega 🎉

---

## ⚠️ Free Tier Limitation — important

Render.com ka **free tier** kuch der inactive rehne par "sleep" mode mein chala jaता hai. Iसका matlab:
- Agar koi 15 minute tak `/portfolio` nahi bhejता, bot "so jata hai"
- Agle message pe **bot ko wake up hone mein 20-30 second lag sakte hain** (pehla reply thoda slow aayega)
- Iसके baad jab tak active ho, fast rahegа

Yeh free tier ka trade-off hai — paid plan ($7/month) se yeh issue nahi hoga, lekin free mein bhi kaam kar jaता hai, sirf pehला message thoda slow aata hai.

## Holdings Update Karne Ka Tareeka (jab BUY/SELL karो)

Har baar jab aapकी holdings badle (naya BUY/SELL), Telegram bot ko update karne ke liye:

1. `python sync_holdings.py` chalao apने Streamlit app folder mein
2. Naya `holdings.json` GitHub repo mein upload/replace karो
3. Render.com automatically naya code detect karega aur redeploy kar dega (1-2 minute)
4. Ab Telegram pe naye holdings dikhенगे

Yeh manual step hai — agar chahो to fully automate karne ka tareeka (GitHub API se direct push, Streamlit app se hi button click pe) bhi ban sakta hai, alag se bata sakta hoon agar zaroorat ho.

---

## Files in this folder

- `main.py` — FastAPI webhook receiver (Render pe deploy hoga)
- `requirements.txt` — Python dependencies
- `holdings.json` — aapकी holdings (placeholder hai, Step 3 se update karna hai)
- `sync_holdings.py` — Streamlit app se holdings export karne ka helper script
