from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import io
import contextlib
import queue
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from processing_system.interpreter import run_code
import argparse

app = Flask(__name__)
app.secret_key = "super_secret_key"
DB_PATH = "imp.db"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# --- User Model ---
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get_by_username(username):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        return User(*row) if row else None

    @staticmethod
    def get_by_id(user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return User(*row) if row else None

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))

# --- DB Setup ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            status TEXT CHECK(status IN ('success', 'timeout', 'error')) NOT NULL,
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Create default admin user if not exists
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (
            'admin', generate_password_hash('imp_admin')
        ))

    conn.commit()
    conn.close()

# --- Log history ---
def log_history(code, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    c.execute("INSERT INTO history (code, status, date, user_id) VALUES (?, ?, ?, ?)", (
        code, status, now, current_user.id
    ))
    conn.commit()
    conn.close()

# --- Routes ---
@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("index"))
        return render_template("login.html", error="ログイン失敗")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/run_interpreter", methods=["POST"])
@login_required
def run_interpreter():
    program = request.json.get("code", "")
    q = queue.Queue()

    def target():
        try:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                tree = run_code(program)
            q.put({"dot": tree.out_to_dot(), "stdout": f.getvalue()})
        except Exception as e:
            q.put({"error": str(e)})

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=2.0)

    if thread.is_alive():
        log_history(program, "timeout")
        return jsonify({"error": "処理が2秒でタイムアウトしました。"}), 408

    if q.empty():
        log_history(program, "error")
        return jsonify({"error": "スレッドが終了しましたが結果が得られませんでした。"}), 500

    result = q.get()
    if "error" in result:
        log_history(program, "error")
        return jsonify({"error": result["error"]}), 400

    log_history(program, "success")
    return jsonify(result)

@app.route("/sample_codes")
def sample_codes():
    return render_template("sample_codes.html")

@app.route("/history")
@login_required
def history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT A.code, A.status, A.date, B.username
        FROM history A
        JOIN users B ON A.user_id = B.id
        ORDER BY A.date DESC
        LIMIT 100
    """)
    records = c.fetchall()
    conn.close()
    return render_template("history.html", records=records)

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500

if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="IMP Web System Flask App")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the Flask app on")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask app on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    app.run(host=args.host,port=args.port,debug=args.debug)


