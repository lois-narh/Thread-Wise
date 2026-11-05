import hashlib, hmac, os, sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "threadwise.db"


def _conn():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY, name TEXT, business TEXT, pw_hash TEXT)""")
    return conn


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def signup(name, business, email, password):
    """Returns (user, error). Exactly one of them is None."""
    email = email.strip().lower()
    if not (name.strip() and business.strip() and "@" in email and len(password) >= 8):
        return None, "Fill in every field. Password needs 8+ characters."
    salt = os.urandom(16)
    try:
        with _conn() as c:
            c.execute("INSERT INTO users VALUES (?,?,?,?)",
                      (email, name.strip(), business.strip(),
                       salt.hex() + ":" + _hash(password, salt)))
    except sqlite3.IntegrityError:
        return None, "That email already has an account."
    return {"email": email, "name": name.strip(), "business": business.strip()}, None


def login(email, password):
    email = email.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT name, business, pw_hash FROM users WHERE email=?",
                        (email,)).fetchone()
    if row:
        salt, digest = row[2].split(":")
        if hmac.compare_digest(_hash(password, bytes.fromhex(salt)), digest):
            return {"email": email, "name": row[0], "business": row[1]}, None
    return None, "Email or password is incorrect."