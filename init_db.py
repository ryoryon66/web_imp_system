import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "imp.db"
DEFAULT_USER = "user1"
DEFAULT_PASS = "imp_user1"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()



    # Create users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    # Create history table
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

    # Insert or update default admin user
    password_hash = generate_password_hash(DEFAULT_PASS)
    c.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USER,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, DEFAULT_USER))
    else:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (DEFAULT_USER, password_hash))

    conn.commit()
    conn.close()
    print(f"Initialized database and set admin user ({DEFAULT_USER}/{DEFAULT_PASS})")


if __name__ == "__main__":
    init_db()
