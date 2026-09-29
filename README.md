# Lumen

A small AI-based doubt solving and learning assistant built with a Python Flask backend, SQLite database, and a responsive vanilla HTML/CSS/JS frontend.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py app.py
```

Open http://127.0.0.1:5000.

Without an API key, Lumen uses built-in fallback guidance. For Groq-backed answers, set your key before starting the server:

```powershell
Copy-Item .env.example .env
# Put your real key in .env, then start the app:
py app.py
```

The `.env` file is local and ignored by Git. Set `GROQ_API_KEY` there for Groq, or `OPENAI_API_KEY` for OpenAI. The SQLite file `lumen.db` is created automatically.

If an API key was ever committed, revoke it with its provider and create a replacement. Removing it from the latest version does not remove it from Git history.
