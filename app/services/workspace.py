import hashlib, re, sqlite3
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
    """{table: rows} for every data table in the workspace."""
    with _conn(user) as c:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name != 'meta' AND name NOT LIKE 'sqlite_%'")]
        return {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in names}

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


def run_sql_file(user, filename):
    """Run every query in sql/<filename> against the workspace.

    Each query starts with `-- name: ...`, then optional `-- note: ...` (what the result means)
    and `-- chart: bar|line col,col` lines. Returns [{name, note, chart, sql, df}].
    """
    text = (ROOT / "sql" / filename).read_text()
    results = []
    with _conn(user) as c:
        for block in re.split(r"(?m)^-- name:", text)[1:]:
            lines = block.strip().splitlines()
            item = {"name": lines[0].strip(), "note": "", "chart": None}
            body = []
            for line in lines[1:]:
                if line.startswith("-- note:"):
                    item["note"] = line[8:].strip()
                elif line.startswith("-- chart:"):
                    kind, cols = line[9:].split()
                    item["chart"] = (kind, cols.split(","))
                else:
                    body.append(line)
            item["sql"] = "\n".join(body).strip()
            item["df"] = pd.read_sql_query(item["sql"], c)
            results.append(item)
    return results