import hashlib, sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TABLES = ["customers", "tailors", "orders"]


def db_path(user):
    """One database file per business."""
    return ROOT / "data" / "workspaces" / (hashlib.sha1(user["email"].encode()).hexdigest()[:10] + ".db")


def _conn(user):
    p = db_path(user)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def table_counts(user):
    """{table: rows}, or {} if no data has been loaded yet."""
    with _conn(user) as c:
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES if t in have}


def preview(user, table="orders", n=5):
    with _conn(user) as c:
        return pd.read_sql(f"SELECT * FROM {table} LIMIT {int(n)}", c)


def get_usecase(user):
    with _conn(user) as c:
        row = c.execute("SELECT value FROM meta WHERE key='usecase'").fetchone()
    return row[0] if row else None


def set_usecase(user, key):
    with _conn(user) as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES ('usecase', ?)", (key,))