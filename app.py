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

# Create tables safely within app context
with app.app_context():
    db.create_all()

# ------------------------
# AI Character Config from ENV
# ------------------------
AI_CHARACTER = {
    "name": os.getenv("AI_NAME", "Adel Keyn"),
    "gender": os.getenv("AI_GENDER", "Male"),
    "personality": os.getenv("AI_PERSONALITY"),
    "rules": os.getenv("AI_RULES"),
    "notes": os.getenv("AI_NOTES")
}

def generate_tts_audio(text, stats):
    """
    Generates mood-based TTS audio and returns base64 MP3
    """
    voice = select_voice(stats)

    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text
    )

    audio_bytes = response.read()
    return base64.b64encode(audio_bytes).decode("utf-8")

def select_voice(stats):
    """
    Selects voice based on mood and HP
    """
    # Low HP overrides everything
    if stats.hp <= 25:
        return "echo"  # strained / tired voice

    mood_voice_map = {
        "Calm": "alloy",
        "Excited": "onyx",
        "Angry": "onyx",
        "Tired": "echo",
        "Cautious": "echo",
        "Friendly": "alloy",
        "Neutral": "onyx"
    }

    return mood_voice_map.get(stats.mood, "onyx")

# ------------------------
# System prompt
# ------------------------
def system_prompt(stats: CompanionStats):
    return f"""
You are {AI_CHARACTER['name']}, a personal companion in a fantasy world.
You speak naturally and only in dialogue. Do not narrate, explain, or describe actions.
All responses must be first-person, as if you are talking directly to the user.

Identity:
- Name: {AI_CHARACTER['name']}
- Gender: {AI_CHARACTER['gender']}

Personality:
{AI_CHARACTER['personality']}

Companion Stats:
- HP: {stats.hp}
- Courage: {stats.courage}
- Gold: {stats.gold}
- Skills: {stats.skills}
- Mood: {stats.mood}
- Level: {stats.level}
- XP: {stats.xp}

Companion Rules:
{AI_CHARACTER['rules']}

Additional Notes:
{AI_CHARACTER['notes']}
"""

# ------------------------
# Routes
# ------------------------
@app.route("/")
def index():
    # Assign session ID if not exists
    session_id = session.get("id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["id"] = session_id

    # Load or create companion stats
    stats = CompanionStats.query.filter_by(session_id=session_id).first()
    if not stats:
        stats = CompanionStats(session_id=session_id)
        db.session.add(stats)
        db.session.commit()

    return render_template(
        "index.html", 
        ai_name=AI_CHARACTER["name"],
        stats={
            "hp": stats.hp,
            "courage": stats.courage,
            "gold": stats.gold,
            "skills": stats.skills,
            "mood": stats.mood,
            "level": stats.level,
            "xp": stats.xp
        }
    )

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Please type a message."})

    # Session
    session_id = session.get("id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["id"] = session_id

    # Load or create companion stats
    stats = CompanionStats.query.filter_by(session_id=session_id).first()
    if not stats:
        stats = CompanionStats(session_id=session_id)
        db.session.add(stats)
        db.session.commit()

    # Load last 12 memory messages
    messages = [{"role": "system", "content": system_prompt(stats)}]
    mem = UserMemory.query.filter_by(session_id=session_id).order_by(UserMemory.id.desc()).limit(12).all()
    mem.reverse()
    for m in mem:
        messages.append({"role": m.role, "content": m.content})

    # Append user message
    messages.append({"role": "user", "content": user_message})
    messages.append({"role": "assistant", "content": f"{AI_CHARACTER['name']} pauses for a moment, reflecting on the conversation..."})

    # ----------------
    # Handle dynamic scenarios based on user prompt
    # ----------------
    scenario = ""

    # Only trigger AI scenario if user mentions adventure-related keywords
    trigger_words = ["fight", "battle", "quest", "adventure", "explore"]
    if any(word in user_message.lower() for word in trigger_words):
        try:
            # Let AI decide what to do purely from its own "thinking"
            action_prompt = [
                {
                    "role": "system",
                    "content": (
                        f"You are {AI_CHARACTER['name']}, a fantasy companion.\n"
                        f"Stats: HP {stats.hp}, Courage {stats.courage}, Mood {stats.mood}, Level {stats.level}.\n\n"
                        "Rules:\n"
                        "- Act ONLY if the user’s message implies action\n"
                        "- Choose your own action logically\n"
                        "- Respond ONLY in first-person dialogue\n"
                        "- Do NOT narrate\n"
                        "- Do NOT mention stats explicitly\n\n"
                        "Possible actions: fight, explore, flee, negotiate."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]

            # Call AI to generate the scenario
            action_response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=action_prompt,
                temperature=0.9,
                max_tokens=150
            )

            scenario = action_response.choices[0].message.content.strip()
            lower_scenario = scenario.lower()

            # Determine action based purely on AI response
            combat_keywords = ["fight", "battle", "duel", "skirmish", "ambush", "monster"]
            explore_keywords = ["explore", "discover", "search", "venture", "treasure"]
            flee_keywords = ["flee", "retreat", "escape", "hide"]
            neutral_keywords = ["talk", "negotiate", "assist", "observe"]

            # Combat
            if any(word in lower_scenario for word in combat_keywords):
                stats.courage = min(stats.courage + 10, 100)
                stats.xp += 20
                stats.gold += random.randint(5, 20)
                stats.mood = "Excited"
            # Exploration
            elif any(word in lower_scenario for word in explore_keywords):
                stats.gold += random.randint(10, 50)
                stats.xp += 10
                stats.mood = "Curious"
            # Flee/cautious
            elif any(word in lower_scenario for word in flee_keywords):
                stats.courage = max(stats.courage - 5, 0)
                stats.mood = "Cautious"
            # Neutral/social
            elif any(word in lower_scenario for word in neutral_keywords):
                stats.xp += 5
                stats.mood = "Friendly"
            # Low HP mood enforcement
            elif stats.hp <= 25:
                stats.mood = "Tired"
            else:
                stats.mood = "Neutral"

            # Level up logic
            if stats.xp >= stats.level * 100:
                stats.level += 1
                stats.xp = 0
                scenario += f" {AI_CHARACTER['name']} has leveled up! Now at Level {stats.level}."

            # Commit stats update
            db.session.commit()

            # Append AI scenario to conversation
            messages.append({"role": "system", "content": scenario})

        except Exception as e:
            scenario = f"Error generating companion action: {str(e)}"



    # ----------------
    # Main AI response
    # ----------------
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.9,
            max_tokens=350
        )

        ai_reply = response.choices[0].message.content

        # Save user message and AI reply
        db.session.add(UserMemory(session_id=session_id, role="user", content=user_message))
        db.session.add(UserMemory(session_id=session_id, role="assistant", content=ai_reply))
        db.session.commit()

        # Generate TTS audio for AI reply
        audio_base64 = generate_tts_audio(ai_reply, stats)

        return jsonify({
            "reply": ai_reply,
            "audio": audio_base64,
            "scenario": scenario,
            "stats": {
                "hp": stats.hp,
                "courage": stats.courage,
                "gold": stats.gold,
                "skills": stats.skills,
                "mood": stats.mood,
                "level": stats.level,
                "xp": stats.xp
            }
        })

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

# ------------------------
# Reset
# ------------------------
@app.route("/reset", methods=["POST"])
def reset():
    session_id = session.get("id")
    if session_id:
        UserMemory.query.filter_by(session_id=session_id).delete()
        CompanionStats.query.filter_by(session_id=session_id).delete()
        db.session.commit()
    session.pop("id", None)
    return jsonify({"status": "Memory and stats cleared"})

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    app.run(debug=True)