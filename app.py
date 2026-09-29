import os
import ast
import operator
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DB_PATH = BASE_DIR / "lumen.db"
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-development-secret")
CORS(app)

FALLBACKS = {
    "Math": "Start by identifying what the problem is asking for. Write down the known values, choose the relationship that connects them, then solve one transformation at a time. Check the result by substituting it back into the original statement.",
    "Physics": "Separate the situation into knowns, unknowns, and a governing principle. Sketch the forces or motion first, keep units consistent, and only substitute numbers after the symbolic relationship is clear.",
    "Biology": "Build the explanation from structure to function: name the system, describe its key parts, then connect each part to the outcome. Use one concrete example to test whether the idea holds.",
    "Chemistry": "Balance the underlying relationship before calculating. Track what changes at the particle level, keep units visible, and use the final magnitude as a quick sanity check.",
    "History": "Place the event in its wider context, then connect cause, turning point, and consequence. A strong answer distinguishes what happened from why it mattered.",
    "English": "Look for the claim or feeling first, then anchor your interpretation in a specific word, image, or structural choice. Explain the effect before naming the technique.",
    "General": "Break the question into a smaller first step. Explain the idea in your own words, test it with a simple example, and then return to the original problem with the new pattern in mind.",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT NOT NULL,
                subject TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                label TEXT NOT NULL,
                detail TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        question_columns = {row[1] for row in db.execute("PRAGMA table_info(questions)")}
        activity_columns = {row[1] for row in db.execute("PRAGMA table_info(activity)")}
        if "user_id" not in question_columns:
            db.execute("ALTER TABLE questions ADD COLUMN user_id INTEGER")
        if "user_id" not in activity_columns:
            db.execute("ALTER TABLE activity ADD COLUMN user_id INTEGER")
        db.execute(
            "UPDATE questions SET answer = ? WHERE lower(question) LIKE ? AND lower(question) LIKE ?",
            (
                "The **lotus** (*Nelumbo nucifera*) is the national flower of India. It symbolizes purity, beauty, and spiritual growth.",
                "%national flower%",
                "%india%",
            ),
        )


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_db() as db:
        user = db.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(user) if user else None


def require_user():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Please log in first."}), 401)
    return user, None


def fallback_answer(question, subject):
    normalized_question = " ".join(question.lower().split())
    if "national flower" in normalized_question and "india" in normalized_question:
        return "The **lotus** (*Nelumbo nucifera*) is the national flower of India. It symbolizes purity, beauty, and spiritual growth."
    common_answers = {
        "capital of india": "The capital of India is **New Delhi**.",
        "national animal of india": "The national animal of India is the **Bengal tiger**.",
        "national bird of india": "The national bird of India is the **Indian peafowl**, commonly called the peacock.",
        "largest planet": "**Jupiter** is the largest planet in our solar system.",
        "red planet": "**Mars** is known as the red planet because iron minerals on its surface oxidize and look reddish.",
        "water chemical formula": "The chemical formula for water is **H2O**: two hydrogen atoms bonded to one oxygen atom.",
    }
    for phrase, answer in common_answers.items():
        if phrase in normalized_question:
            return answer
    arithmetic_answer = solve_arithmetic(normalized_question)
    if arithmetic_answer is not None:
        return f"The answer is **{arithmetic_answer}**."
    return (
        "I can answer this directly when the AI service is connected. Set `OPENAI_API_KEY` "
        "and restart the app for unrestricted questions. For now, tell me a simple "
        "fact or calculation and I’ll answer it using the built-in tutor."
    )


def solve_arithmetic(question):
    expression = question.replace("what is", "").replace("calculate", "").replace("=?", "")
    expression = expression.replace("?", "").strip()
    if not expression or any(character not in "0123456789+-*/%.() ^" for character in expression):
        return None
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
        operators = {
            ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
            ast.USub: operator.neg,
        }

        def evaluate(node):
            if isinstance(node, ast.Expression):
                return evaluate(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
                return operators[type(node.op)](evaluate(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in operators:
                left, right = evaluate(node.left), evaluate(node.right)
                if abs(right) > 1000000 or abs(left) > 1000000:
                    raise ValueError
                return operators[type(node.op)](left, right)
            raise ValueError

        result = evaluate(tree)
        return int(result) if result == int(result) else round(result, 6)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def generate_answer(question, subject):
    groq_api_key = os.getenv("GROQ_API_KEY")
    api_key = groq_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return fallback_answer(question, subject)

    client_options = {"api_key": api_key}
    if groq_api_key:
        client_options["base_url"] = "https://api.groq.com/openai/v1"
    client = OpenAI(**client_options)
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[
            {
                "role": "system",
                "content": "You are Lumen, a patient Socratic learning assistant. Answer in concise markdown. Explain the idea, show a useful first step, and end with one check-for-understanding question. Do not overdo it.",
            },
            {"role": "user", "content": f"Subject: {subject}\nQuestion: {question}"},
        ],
    )
    return response.choices[0].message.content or fallback_answer(question, subject)


@app.get("/")
def home():
    if not current_user():
        return redirect(url_for("login"))
    return render_template("index.html")


@app.get("/register")
def register():
    if current_user():
        return redirect(url_for("home"))
    return render_template("auth.html", mode="register")


@app.get("/login")
def login():
    if current_user():
        return redirect(url_for("home"))
    return render_template("auth.html", mode="login")


@app.post("/api/register")
def create_account():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not name or not email or len(password) < 6:
        return jsonify({"error": "Name, email, and a password of at least 6 characters are required."}), 400
    try:
        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), now()),
            )
        session["user_id"] = cursor.lastrowid
        return jsonify({"ok": True}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "An account with that email already exists."}), 409


@app.post("/api/login")
def authenticate():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Email or password is incorrect."}), 401
    session["user_id"] = user["id"]
    return jsonify({"ok": True})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    user, error = require_user()
    if error:
        return error
    return jsonify(user)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "ai_enabled": bool(os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))})


@app.get("/api/questions")
def list_questions():
    user, error = require_user()
    if error:
        return error
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM questions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/activity")
def list_activity():
    user, error = require_user()
    if error:
        return error
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM activity WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 10",
            (user["id"],),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/questions")
def create_question():
    user, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    subject = str(payload.get("subject", "General")).strip() or "General"
    if not question:
        return jsonify({"error": "Question is required."}), 400

    try:
        answer = generate_answer(question, subject)
        created_at = now()
        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO questions (user_id, question, subject, answer, created_at) VALUES (?, ?, ?, ?, ?)",
                (user["id"], question, subject, answer, created_at),
            )
            db.execute(
                "INSERT INTO activity (user_id, label, detail, kind, created_at) VALUES (?, ?, ?, ?, ?)",
                (user["id"], "Doubt resolved", f"{subject} · {question[:58]}", "spark", created_at),
            )
        return jsonify({"id": cursor.lastrowid, "question": question, "subject": subject, "answer": answer}), 201
    except Exception as error:
        app.logger.exception(error)
        return jsonify({"error": "The assistant could not answer right now."}), 500


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5000")))
