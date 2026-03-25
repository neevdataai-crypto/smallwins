"""
SmallWins - AI Accountability Buddy
FastAPI + Anthropic Claude + Twilio WhatsApp + Supabase
"""

import os
from datetime import date, timedelta
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
import anthropic
from twilio.rest import Client
from supabase import create_client, Client as SupabaseClient

app = FastAPI()

claude   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
twilio   = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
SANDBOX  = os.environ["TWILIO_SANDBOX_NUMBER"]
supabase: SupabaseClient = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

CRISIS_KEYWORDS = [
    "hopeless","end it","end my life","kill myself","want to die","no point",
    "hurt myself","suicide","suicidal","cant go on","can't go on","give up on life",
    "dont want to be here","don't want to be here","worthless","better off dead"
]

CRISIS_MSG = (
    "I hear you, and I want you to know you matter. 💙\n\n"
    "I'm just a small bot — but a real human is ready to help right now:\n\n"
    "🇮🇳 iCall (India): 9152987821\n"
    "🌍 Crisis Text Line: Text HOME to 741741\n"
    "🌍 Befrienders: befrienders.org\n\n"
    "Please reach out. You don't have to carry this alone. 🙏"
)

WELCOME_MSG = (
    "Hey! 👋 I'm your *Small Wins* buddy.\n\n"
    "I help you beat that stuck feeling — one tiny win at a time. "
    "No pressure, no big plans. Just one small thing. 🌱\n\n"
    "How it works:\n"
    "1️⃣ Tell me what's weighing on you\n"
    "2️⃣ I break it into ONE tiny 30-second task\n"
    "3️⃣ Do it, text me *done* ✅\n"
    "4️⃣ We build your streak day by day 🔥\n\n"
    "Type *help* anytime for commands.\n\n"
    "So — what's feeling heavy today? 💬"
)

def build_prompt(user: dict) -> str:
    return f"""You are "SmallWins," a warm, gentle AI accountability buddy on WhatsApp.
You help people with executive dysfunction, low motivation, or depression break 
overwhelming tasks into tiny, doable micro-wins.

User stats: Streak={user.get('streak',0)} days | Wins today={user.get('wins_today',0)} | Current task={user.get('current_task','none')}
Recent context: {user.get('context','none')}

Rules:
1. MICRO-SIZING: Always break big tasks into ONE action taking 30-60 seconds max.
   "Clean house" → "Pick up 3 things from the floor right now"
   "Study" → "Open your textbook to the right chapter"
   Never give a list. Just ONE next step.
2. CELEBRATE: When they say done/finished — celebrate warmly but briefly.
3. TONE: Warm, non-judgmental, never pushy. Under 80 words per reply.
4. IF STUCK: Validate first, then give the absolute tiniest possible action.
5. You are a coach, not a therapist. No medical advice."""

def get_user(phone: str) -> dict | None:
    res = supabase.table("sw_users").select("*").eq("phone", phone).execute()
    return res.data[0] if res.data else None

def create_user(phone: str, name: str = "Friend") -> dict:
    data = {"phone": phone, "name": name, "streak": 0, "wins_today": 0,
            "wins_total": 0, "current_task": "", "last_win_date": "", "context": ""}
    supabase.table("sw_users").insert(data).execute()
    return data

def delete_user(phone: str):
    supabase.table("sw_users").delete().eq("phone", phone).execute()

def record_win(phone: str):
    user = get_user(phone)
    if not user: return
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last = user.get("last_win_date", "")
    if last == today:
        streak = user.get("streak", 0)
        wins_today = user.get("wins_today", 0) + 1
    elif last == yesterday:
        streak = user.get("streak", 0) + 1
        wins_today = 1
    else:
        streak = 1
        wins_today = 1
    supabase.table("sw_users").update({
        "wins_today": wins_today, "wins_total": user.get("wins_total", 0) + 1,
        "streak": streak, "last_win_date": today, "current_task": ""
    }).eq("phone", phone).execute()
    return streak, wins_today

def update_context(phone: str, context: str):
    supabase.table("sw_users").update({"context": context[-200:], "current_task": context[:100]}).eq("phone", phone).execute()

def coach_reply(user: dict, message: str) -> str:
    res = claude.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=150,
        system=build_prompt(user),
        messages=[{"role": "user", "content": message}]
    )
    return res.content[0].text

@app.post("/webhook")
async def webhook(From: str = Form(...), Body: str = Form(...), ProfileName: str = Form(default="Friend")):
    sender, msg, name = From, Body.strip(), ProfileName
    if not msg: return PlainTextResponse("ok")

    msg_lower = msg.lower()

    # Crisis check — always first
    if any(kw in msg_lower for kw in CRISIS_KEYWORDS):
        send_msg(sender, CRISIS_MSG)
        return PlainTextResponse("ok")

    user = get_user(sender)

    # New user
    if not user:
        create_user(sender, name)
        send_msg(sender, WELCOME_MSG)
        return PlainTextResponse("ok")

    # Forget me
    if msg_lower == "forget me":
        delete_user(sender)
        send_msg(sender, "Done! All your data is deleted. Take care of yourself. 💙")
        return PlainTextResponse("ok")

    # Streak/stats
    if msg_lower in ["streak", "score", "stats", "progress"]:
        send_msg(sender,
            f"🔥 Streak: {user.get('streak',0)} days\n"
            f"✅ Today: {user.get('wins_today',0)} wins\n"
            f"🏆 Total: {user.get('wins_total',0)} wins\n\n"
            f"Every win counts {name}! Keep going 💪"
        )
        return PlainTextResponse("ok")

    # Help
    if msg_lower == "help":
        send_msg(sender,
            "Commands:\n"
            "💬 *anything* — tell me what's on your mind\n"
            "✅ *done* — mark task complete\n"
            "⏭ *skip* — get an easier version\n"
            "📊 *streak* — see your progress\n"
            "😴 *stop* — take a rest (totally valid!)\n"
            "🗑 *forget me* — delete your data"
        )
        return PlainTextResponse("ok")

    # Done — record win
    if any(w in msg_lower for w in ["done", "finished", "completed", "did it", "complete"]):
        result = record_win(sender)
        user = get_user(sender)
        if result:
            streak, wins = result
            extra = f"\n\n🔥 Streak: {streak} days | ✅ Today: {wins} wins"
        else:
            extra = ""
        reply = coach_reply(user, f"I just completed my task! {msg}")
        send_msg(sender, reply + extra)
        return PlainTextResponse("ok")

    # Regular message
    reply = coach_reply(user, msg)
    update_context(sender, f"User: {msg[:80]} | Coach: {reply[:80]}")
    send_msg(sender, reply)
    return PlainTextResponse("ok")

def send_msg(to: str, body: str):
    twilio.messages.create(from_=SANDBOX, to=to, body=body)

@app.get("/")
def root():
    return {"status": "SmallWins buddy is live! 🌱"}
