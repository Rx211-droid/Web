import os
import asyncio
from datetime import datetime
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from flask import Flask, render_template_string
import requests
from collections import Counter
import re

# Optional Database
USE_DATABASE = os.getenv("USE_DATABASE","False").lower() == "true"
DB_URL = os.getenv("DB_URL","sqlite:///data.db")

# Telegram & AI
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","demo")

# Initialize Bot + Dispatcher
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# -------------------------------
# Data Storage
# -------------------------------
if USE_DATABASE:
    from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(DB_URL, echo=False)
    Base = declarative_base()
    Session = sessionmaker(bind=engine)
    session = Session()

    class Message(Base):
        __tablename__ = 'messages'
        id = Column(Integer, primary_key=True)
        timestamp = Column(DateTime, default=datetime.utcnow)
        chat_id = Column(String)
        user_id = Column(String)
        username = Column(String)
        text = Column(Text)
        profane = Column(Boolean)

    class MemberEvent(Base):
        __tablename__ = 'member_events'
        id = Column(Integer, primary_key=True)
        timestamp = Column(DateTime, default=datetime.utcnow)
        chat_id = Column(String)
        user_id = Column(String)
        username = Column(String)
        event_type = Column(String)

    Base.metadata.create_all(engine)
else:
    # In-memory storage
    messages = []
    member_events = []

# -------------------------------
# Profanity / AI Functions
# -------------------------------
BAD_WORDS = ["madarchod","bhosdike","chutiya","gaand","bc"]
premium_users = set()  # manually add premium user IDs

def is_profane(text):
    return any(word in text.lower() for word in BAD_WORDS)

def extract_hashtags(text):
    return re.findall(r"#\w+", text.lower())

def run_gemini_analysis(text):
    """Lite AI Analysis for Premium Users"""
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

# -------------------------------
# Telegram Bot Handlers
# -------------------------------
@dp.message(CommandStart())
async def start_cmd(msg: types.Message):
    await msg.reply("👋 Bot Active! Use /dashboard to view analytics.")

@dp.message(Command("dashboard"))
async def dashboard_cmd(msg: types.Message):
    user_id = msg.from_user.id
    if user_id in premium_users:
        await msg.reply("🔥 Premium: AI & leaderboard enabled. Visit /dashboard")
    else:
        await msg.reply("📊 Free: Basic analytics only. Visit /dashboard")

@dp.message()
async def log_message(msg: types.Message):
    if not msg.text:
        return
    profane = is_profane(msg.text)
    hashtags = extract_hashtags(msg.text)

    # Save message
    if USE_DATABASE:
        m = Message(
            chat_id=str(msg.chat.id),
            user_id=str(msg.from_user.id),
            username=msg.from_user.username,
            text=msg.text,
            profane=profane
        )
        session.add(m)
        session.commit()
    else:
        messages.append({
            "timestamp": datetime.utcnow(),
            "chat_id": str(msg.chat.id),
            "user_id": str(msg.from_user.id),
            "username": msg.from_user.username,
            "text": msg.text,
            "profane": profane,
            "hashtags": hashtags
        })

    # Profanity alert
    if profane and msg.from_user.id in premium_users:
        await msg.reply("⚠️ Abusive language detected!")

    # Optional AI for premium
    if msg.from_user.id in premium_users:
        keywords, sentiment = run_gemini_analysis(msg.text)
        print(f"Premium AI Analysis: {keywords}, {sentiment}")

@dp.chat_member()
async def member_update(event: types.ChatMemberUpdated):
    user = event.new_chat_member.user
    event_type = None
    if event.old_chat_member.status in ["left", "kicked"] and event.new_chat_member.status == "member":
        event_type = "join"
    elif event.old_chat_member.status == "member" and event.new_chat_member.status in ["left", "kicked"]:
        event_type = "leave"

    if event_type:
        if USE_DATABASE:
            e = MemberEvent(
                chat_id=str(event.chat.id),
                user_id=str(user.id),
                username=user.username,
                event_type=event_type
            )
            session.add(e)
            session.commit()
        else:
            member_events.append({
                "timestamp": datetime.utcnow(),
                "chat_id": str(event.chat.id),
                "user_id": str(user.id),
                "username": user.username,
                "event_type": event_type
            })

# -------------------------------
# Flask Web Dashboard
# -------------------------------
@app.route("/dashboard")
def dashboard():
    # Fetch data
    if USE_DATABASE:
        msgs = session.query(Message).all()
        evts = session.query(MemberEvent).all()
    else:
        msgs = messages
        evts = member_events

    total_messages = len(msgs)
    joins = len([e for e in evts if e["event_type"]=="join"])
    leaves = len([e for e in evts if e["event_type"]=="leave"])

    # Profanity leaderboard
    profane_msgs = [m for m in msgs if m["profane"] if not USE_DATABASE else getattr(m, "profane")]
    prof_users = Counter([m["username"] if not USE_DATABASE else m.username for m in profane_msgs])
    
    # Top hashtags
    all_hashtags = []
    for m in msgs:
        tags = m["hashtags"] if not USE_DATABASE else extract_hashtags(m.text)
        all_hashtags.extend(tags)
    top_hashtags = Counter(all_hashtags)

    # Top 5 each
    leaderboard = prof_users.most_common(5)
    top5_hashtags = top_hashtags.most_common(5)

    html = f"""
    <html>
    <head>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@3.3.3/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 p-6">
      <div class="max-w-4xl mx-auto bg-white p-6 rounded-xl shadow-lg">
        <h2 class="text-2xl font-bold mb-4">Telegram Analytics Dashboard</h2>
        <p class="mb-2">Total Messages: {total_messages}</p>
        <p class="mb-2">Joins: {joins} | Leaves: {leaves}</p>

        <canvas id="myChart" class="mb-6"></canvas>

        <h3 class="text-xl font-semibold mt-4 mb-2">Top Hashtags</h3>
        <ul class="list-disc list-inside">
          {''.join(f"<li>{tag}: {count}</li>" for tag, count in top5_hashtags)}
        </ul>

        <h3 class="text-xl font-semibold mt-4 mb-2">Profanity Leaderboard</h3>
        <ul class="list-disc list-inside">
          {''.join(f"<li>{user}: {count}</li>" for user, count in leaderboard)}
        </ul>

      </div>
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

# -------------------------------
# Run Flask + Bot Together
# -------------------------------
async def main():
    def run_flask():
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
    Thread(target=run_flask).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
