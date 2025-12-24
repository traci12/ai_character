# AI Character (Python)

## Requirements
- Python 3.10+
- pip

## Installation

```bash
git@github.com:traci12/ai_character.git
cd ai_character

python -m venv venv
source venv/Scripts/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration
Create `.env` file and paste the following:
```bash
OPENAI_API_KEY=
FLASK_SECRET_KEY=

AI_NAME=
AI_GENDER=
AI_PERSONALITY=
AI_RULES=
AI_NOTES=
```

## Rund the Game

```bash
python app.py