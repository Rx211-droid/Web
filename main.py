import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from flask import Flask, render_template_string, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# -----------------------
# CONFIG / ENV
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "TelegramAnalytics")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "demo")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# -----------------------
# GOOGLE SHEETS SETUP
# -----------------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_JSON, scope)
gc = gspread.authorize(creds)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# -----------------------
# PROFANITY / LITE AI
# -----------------------
BAD_WORDS = ["madarchod","bhosdike","chutiya","gaand","bc"]

def is_profane(text):
    return any(word in text.lower() for word in BAD_WORDS)

def run_gemini_analysis(text):
    """
    Free Gemini API call example (Lite version)
    Returns: keywords, sentiment
    """
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    data = {"input": text, "model": "gemini-2.5-flash-lite"}
    try:
        res = requests.post("https://api.openai.com/v1/responses", headers=headers, json=data, timeout=5)
        r = res.json()
        keywords = r.get("keywords", [])
        sentiment = r.get("sentiment", "neutral")
        return keywords, sentiment
    except:
        return [], "neutral"

# -----------------------
# BOT HANDLERS
# -----------------------
premium_users = set()  # example, can sync with sheet

@dp.message(CommandStart())
async def start_cmd(msg: types.Message):
    await msg.reply("👋 Bot Active! Use /dashboard to view analytics.")

@dp.message(Command("dashboard"))
async def dashboard_cmd(msg: types.Message):
    user_id = msg.from_user.id
    if user_id in premium_users:
        await msg.reply("🔥 Premium user: AI analysis enabled. Visit https://yourwebapp.url/dashboard")
    else:
        await msg.reply("📊 Free user: Basic analytics only. Visit https://yourwebapp.url/dashboard")

@dp.message()
async def log_message(msg: types.Message):
    if not msg.text:
        return
    profane = is_profane(msg.text)
    row = [str(datetime.utcnow()), msg.chat.id, msg.from_user.id, msg.from_user.username, "message", msg.text, str(profane)]
    sheet.append_row(row)

# -----------------------
# FLASK WEB INTERFACE
# -----------------------
@app.route("/dashboard")
def dashboard():
    records = sheet.get_all_records()
    total_messages = len([r for r in records if r["EventType"]=="message"])
    joins = len([r for r in records if r["EventType"]=="join"])
    leaves = len([r for r in records if r["EventType"]=="leave"])
    # simple Chart.js embed
    html = f"""
    <html>
    <head>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
      <h2>Telegram Analytics Dashboard</h2>
      <p>Total messages: {total_messages}</p>
      <p>Joins: {joins}, Leaves: {leaves}</p>
      <canvas id="myChart"></canvas>
      <script>
      var ctx = document.getElementById('myChart').getContext('2d');
      var chart = new Chart(ctx, {{
          type: 'bar',
          data: {{
              labels: ['Messages','Joins','Leaves'],
              datasets: [{{
                  label: 'Counts',
                  data: [{total_messages},{joins},{leaves}],
                  backgroundColor: ['blue','green','red']
              }}]
          }},
          options: {{}}
      }});
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

# -----------------------
# RUN BOTH BOT + WEB
# -----------------------
async def main():
    from threading import Thread
    # Flask in separate thread
    def run_flask():
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
    Thread(target=run_flask).start()
    # Bot polling (can switch to webhook in Render)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
