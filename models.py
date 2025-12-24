from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ------------------------
# User Memory Model
# ------------------------
class UserMemory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = db.Column(db.Text, nullable=False)

# ------------------------
# Companion Stats Model
# ------------------------
class CompanionStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    hp = db.Column(db.Integer, default=100)
    courage = db.Column(db.Integer, default=50)
    gold = db.Column(db.Integer, default=0)
    skills = db.Column(db.Text, default="Swordsmanship, Archery")
    mood = db.Column(db.String(50), default="Neutral")
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)

# ------------------------
# Companion Quest Model
# ------------------------
class CompanionQuest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100))
    description = db.Column(db.Text)
    step = db.Column(db.Integer, default=1)
    completed = db.Column(db.Boolean, default=False)
