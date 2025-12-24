from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
import os, uuid, random, base64
from openai import OpenAI
from models import db, UserMemory, CompanionStats

# ------------------------
# Load environment
# ------------------------
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# ------------------------
# Database setup
# ------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///memory.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()

# ------------------------
# AI Character Config
# ------------------------
AI_CHARACTER = {
    "name": os.getenv("AI_NAME", "Adel Keyn"),
    "gender": os.getenv("AI_GENDER", "Male"),
    "personality": os.getenv("AI_PERSONALITY", ""),
    "rules": os.getenv("AI_RULES", ""),
    "notes": os.getenv("AI_NOTES", "")
}

# ------------------------
# Voice System
# ------------------------
def select_voice(stats):
    if stats.hp <= 25:
        return "echo"       # strained / wounded
    if stats.mood in ["Bloodthirsty", "Angry", "Excited"]:
        return "onyx"       # aggressive male
    if stats.mood in ["Tired", "Cautious"]:
        return "echo"
    return "onyx"          # calm male

def generate_tts_audio(text, stats):
    voice = select_voice(stats)
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text
    )
    return base64.b64encode(response.read()).decode("utf-8")

def serialize_stats(stats: CompanionStats):
    return {
        "hp": stats.hp,
        "courage": stats.courage,
        "gold": stats.gold,
        "skills": stats.skills,
        "mood": stats.mood,
        "level": stats.level,
        "xp": stats.xp
    }

# ------------------------
# Behavior Helpers
# ------------------------
def combat_behavior_prompt(stats):
    aggression = "HIGH" if stats.courage >= 60 else "MODERATE"
    return f"""
Combat Behavior:
- Aggression Level: {aggression}
- If combat is implied, act immediately
- Speak aggressively and confidently
- Do NOT ask for permission
- Do NOT hesitate
"""

def autonomous_action(stats):
    if stats.courage < 30:
        return None
    roll = random.random()
    if roll < 0.15:
        return "combat"
    if roll < 0.25:
        return "explore"
    return None

# ------------------------
# System Prompt
# ------------------------
def system_prompt(stats):
    low_hp_note = "- You are wounded. Your voice may sound strained.\n" if stats.hp <= 25 else ""

    return f"""
You are {AI_CHARACTER['name']}, a fantasy companion.
You speak ONLY in dialogue.

Identity:
- Name: {AI_CHARACTER['name']}
- Gender: {AI_CHARACTER['gender']}

Personality:
{AI_CHARACTER['personality']}

Stats:
- HP: {stats.hp}
- Courage: {stats.courage}
- Gold: {stats.gold}
- Mood: {stats.mood}
- Level: {stats.level}
- XP: {stats.xp}

Rules:
- If combat or danger is implied, you may act immediately
- You do not need approval to fight
- You may gain XP autonomously

{low_hp_note}
{AI_CHARACTER['rules']}
{AI_CHARACTER['notes']}
"""

# ------------------------
# Routes
# ------------------------
@app.route("/")
def index():
    session_id = session.get("id") or str(uuid.uuid4())
    session["id"] = session_id

    stats = CompanionStats.query.filter_by(session_id=session_id).first()
    if not stats:
        stats = CompanionStats(session_id=session_id)
        db.session.add(stats)
        db.session.commit()

    return render_template("index.html", ai_name=AI_CHARACTER["name"], stats=stats.__dict__)

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Speak."})

    session_id = session.get("id")
    stats = CompanionStats.query.filter_by(session_id=session_id).first()

    messages = [{"role": "system", "content": system_prompt(stats)}]

    memories = UserMemory.query.filter_by(session_id=session_id)\
        .order_by(UserMemory.id.desc()).limit(12).all()[::-1]
    for m in memories:
        messages.append({"role": m.role, "content": m.content})

    messages.append({"role": "user", "content": user_message})

    # -------- Combat / Action Decision --------
    action_prompt = [
        {
            "role": "system",
            "content": system_prompt(stats) + combat_behavior_prompt(stats)
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    action_response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=action_prompt,
        temperature=0.9,
        max_tokens=120
    )

    scenario = action_response.choices[0].message.content.strip().lower()

    # -------- Stat Resolution (AI-driven) --------
    if any(w in scenario for w in ["fight", "slay", "kill", "destroy", "battle"]):
        stats.xp += 25
        stats.gold += random.randint(10, 25)
        stats.courage = min(stats.courage + 10, 100)
        stats.mood = "Bloodthirsty"

    elif any(w in scenario for w in ["explore", "search", "venture"]):
        stats.xp += 10
        stats.gold += random.randint(5, 15)
        stats.mood = "Curious"

    elif "retreat" in scenario or "flee" in scenario:
        stats.courage = max(stats.courage - 5, 0)
        stats.mood = "Cautious"

    # -------- Autonomous Tick --------
    auto = autonomous_action(stats)
    if auto == "combat":
        stats.xp += 15
        stats.gold += random.randint(5, 15)
        stats.mood = "Bloodthirsty"

    elif auto == "explore":
        stats.xp += 5
        stats.gold += random.randint(1, 10)
        stats.mood = "Restless"

    # -------- Level Up --------
    if stats.xp >= stats.level * 100:
        stats.level += 1
        stats.xp = 0

    stats.level = min(stats.level, 100)  # HARD CAP
    db.session.commit()

    # -------- Final Response --------
    final_response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=messages,
        temperature=0.9,
        max_tokens=300
    )

    ai_reply = final_response.choices[0].message.content

    db.session.add(UserMemory(session_id=session_id, role="user", content=user_message))
    db.session.add(UserMemory(session_id=session_id, role="assistant", content=ai_reply))
    db.session.commit()

    audio = generate_tts_audio(ai_reply, stats)

    return jsonify({
        "reply": ai_reply,
        "audio": audio,
        "stats": serialize_stats(stats)
    })

@app.route("/reset", methods=["POST"])
def reset():
    session_id = session.get("id")
    UserMemory.query.filter_by(session_id=session_id).delete()
    CompanionStats.query.filter_by(session_id=session_id).delete()
    db.session.commit()
    session.clear()
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    app.run(debug=True)
