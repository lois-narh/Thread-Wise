"""Synthetic data for a Ghanaian tailoring shop. Same seed = same data.

Run it directly:  python -m scripts.generate_data --db data/demo.db --orders 2500 --seed 42
The app's "Generate data" button calls generate() with the workspace database.
"""
import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
START, END = date(2024, 1, 1), date(2026, 11, 1)  # Monday .. Sunday, so weeks are complete
EASTER = [date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5)]
EID = [date(2024, 4, 10), date(2024, 6, 16), date(2025, 3, 30), date(2025, 6, 6),
       date(2026, 3, 20), date(2026, 5, 27)]

# garment: (price low, price high, base days to sew, usual complexity, spellings seen in the ledger)
GARMENTS = {
    "Kaba & Slit": (250, 600, 7, 3, ["Kaba & Slit", "kaba and slit", "KABA & SLIT", "Kaba n Slit"]),
    "Agbada": (600, 1800, 10, 4, ["Agbada", "agbada ", "AGBADA"]),
    "Suit": (800, 2000, 14, 4, ["Suit", "suit", "SUIT"]),
    "Bridal Gown": (1500, 5000, 28, 5, ["Bridal Gown", "bridal gown", "Bridal gown"]),
    "School Uniform": (120, 250, 4, 1, ["School Uniform", "school uniform", "School uniform"]),
    "Ankara Two-piece": (250, 600, 7, 3, ["Ankara Two-piece", "ankara 2 piece", "Ankara two piece"]),
    "Shirt": (120, 300, 4, 2, ["Men's Shirt", "mens shirt", "Shirt"]),
    "Dress": (200, 700, 7, 3, ["Dress", "dress", "DRESS"]),
}
BY_OCCASION = {  # which garments each occasion asks for (weights follow the GARMENTS order)
    "School": [0, 0, 0, 0, 8, 0, 1, 0],
    "Wedding": [3, 2, 2, 2, 0, 1, 0, 2],
    "Funeral": [4, 1, 0, 0, 0, 3, 1, 2],
    "Eid": [1, 4, 1, 0, 0, 1, 2, 1],
    "Christmas": [3, 1, 1, 0, 0, 3, 1, 3],
    "Easter": [3, 1, 1, 0, 0, 3, 1, 3],
}
DEFAULT_GARMENT = [3, 2, 1, 0, 0, 2, 2, 2]
TAILORS = [("Kofi Mensah", 18), ("Ama Serwaa", 12), ("Yaw Boateng", 7), ("Efua Appiah", 20),
           ("Kwame Osei", 9), ("Abena Owusu", 5), ("Nana Yaa Darko", 15), ("Ibrahim Musah", 10)]
FIRST = ["Kwesi", "Akosua", "Kojo", "Adwoa", "Kwabena", "Esi", "Yaa", "Kofi", "Ama", "Nii", "Naa", "Selorm",
         "Mawuli", "Afia", "Fatima", "Abdul", "Grace", "Daniel", "Comfort", "Emmanuel"]
LAST = ["Asante", "Owusu", "Tetteh", "Quaye", "Boadu", "Addo", "Agyeman", "Lamptey", "Amoah", "Ofori",
        "Sarpong", "Ansah", "Nkrumah", "Adjei", "Danso", "Mahama", "Acheampong", "Annan"]
CITIES = ["Accra", "Tema", "Madina", "Kasoa", "Dansoman", "Adenta", "Osu", "Kumasi"]


def _near(d, dates, days_before):
    return any(0 <= (x - d).days <= days_before for x in dates)


def _season(d):
    """How busy a day is, relative to a normal day."""
    if (d.month == 11 and d.day >= 15) or (d.month == 12 and d.day <= 23):
        return 1.9
    if _near(d, EASTER, 21):
        return 1.5
    if _near(d, EID, 14):
        return 1.35
    if d.month == 9 and d.day <= 20:
        return 1.4
    return 0.8 if d.month == 1 else 1.0


def _occasion(d, rng):
    w = {"Funeral": 2.0, "Wedding": 1.5, "Church": 2.0, "Eid": 0.1, "Christmas": 0.05, "Easter": 0.05,
         "Graduation": 0.3, "School": 0.3, "Everyday": 2.5}
    if d.month in (11, 12):
        w.update(Christmas=4, Church=3, Funeral=3)
    if _near(d, EASTER, 21):
        w["Easter"] = 4
    if _near(d, EID, 14):
        w["Eid"] = 4
    if d.month in (8, 9):
        w["School"] = 4
    names = list(w)
    p = np.array([w[n] for n in names])
    return rng.choice(names, p=p / p.sum())


def make_tables(n_orders=2500, seed=42):
    rng = np.random.default_rng(seed)
    garments = list(GARMENTS)

    tailors = pd.DataFrame({
        "tailor_id": range(1, len(TAILORS) + 1),
        "name": [t[0] for t in TAILORS],
        "skill_level": ["Junior" if t[1] < 8 else "Mid" if t[1] < 14 else "Senior" for t in TAILORS],
        "years_experience": [t[1] for t in TAILORS],
    })
    years = tailors["years_experience"].to_numpy()
    speed = np.clip(1.25 - 0.015 * years + rng.normal(0, 0.05, len(years)), 0.9, 1.2)  # < 1 = faster
    capacity = np.maximum(2, (3 + years / 5) * n_orders / 2500)

    n_cust = max(100, n_orders // 4)
    cust_weight = rng.gamma(0.8, 1.0, n_cust)  # a few customers come back often
    cust_weight /= cust_weight.sum()
    cust_effect = rng.normal(0, 1.0, n_cust)   # some customers are always slow to confirm fittings

    days = [START + timedelta(i) for i in range((END - START).days + 1)]
    w = np.array([(0.15 if d.weekday() == 6 else 1.0) * _season(d) * (1 + 0.25 * i / len(days))
                  for i, d in enumerate(days)])
    order_days = sorted(days[i] for i in rng.choice(len(days), n_orders, p=w / w.sum()))

    deliveries = [[] for _ in TAILORS]  # delivery dates of each tailor's orders
    load, current_day, rows = np.zeros(len(TAILORS)), None, []
    for d in order_days:
        if d != current_day:  # open orders per tailor at the start of the day
            current_day = d
            deliveries = [[x for x in dl if x > d] for dl in deliveries]
            load = np.array([len(dl) for dl in deliveries], dtype=float)
        occasion = _occasion(d, rng)
        g = rng.choice(len(garments), p=np.array(BY_OCCASION.get(occasion, DEFAULT_GARMENT), float) /
                       sum(BY_OCCASION.get(occasion, DEFAULT_GARMENT)))
        lo, hi, base_days, usual, _ = GARMENTS[garments[g]]
        complexity = int(np.clip(round(rng.normal(usual, 0.7)), 1, 5))
        rush = int(rng.random() < (0.3 if occasion in ("Funeral", "Christmas", "Easter", "Eid") else 0.08))
        fabric = "Customer" if rng.random() < 0.55 else "Shop"
        t = int(rng.choice(len(TAILORS)))
        c = int(rng.choice(n_cust, p=cust_weight))
        price = round(rng.uniform(lo, hi) * (1 + 0.1 * (complexity - 3)) * (1.25 if rush else 1.0), -1)
        dep_pct = rng.choice([0, 20, 30, 50, 60, 100], p=[0.08, 0.12, 0.25, 0.3, 0.1, 0.15])

        tight = rush or occasion in ("Funeral", "Christmas", "Easter", "Eid")
        lead = max(2, round(base_days * rng.uniform(0.85, 1.2 if rush else 1.5) if tight
                            else base_days * rng.uniform(1.15, 2.2)))
        pressure = load[t] / capacity[t]
        work = base_days * (1 + 0.12 * (complexity - 3)) * speed[t]
        extra = (5 * max(0, pressure - 0.8) + 1.2 * pressure
                 + (rng.exponential(2.6) if fabric == "Customer" and rng.random() < 0.55 else 0)
                 + (rng.exponential(1.3) if d.month in (3, 4, 11, 12) else 0)
                 + (rng.exponential(1.2) if dep_pct < 30 else 0)
                 + cust_effect[c] + rng.normal(0, 1.5))
        delivered = d + timedelta(max(1, round(work + extra)))
        deliveries[t].append(delivered)
        rows.append({
            "customer_id": c + 1, "tailor_id": t + 1, "order_date": d.isoformat(),
            "promised_date": (d + timedelta(lead)).isoformat(),
            "delivered_date": delivered.isoformat() if delivered <= END else None,
            "garment_type": garments[g], "fabric_source": fabric, "complexity": complexity, "is_rush": rush,
            "occasion": occasion, "price_ghs": price, "deposit_ghs": round(price * dep_pct / 100, 0),
            "status": "Delivered" if delivered <= END else "In progress",
        })

    # Real-world imperfections
    out = []
    for r in rows:
        r["garment_type"] = rng.choice(GARMENTS[r["garment_type"]][4], p=None)
        if rng.random() < 0.08:
            r["occasion"] = r["occasion"].lower()
        if rng.random() < 0.05:
            r["fabric_source"] = r["fabric_source"].upper()
        for col, p in [("garment_type", 0.02), ("occasion", 0.03), ("fabric_source", 0.04), ("complexity", 0.03),
                       ("price_ghs", 0.02), ("deposit_ghs", 0.03)]:
            if rng.random() < p:
                r[col] = None
        if r["price_ghs"] is not None and rng.random() < 0.007:
            r["price_ghs"] *= 1000                       # extra zeros typed
        if r["delivered_date"] and rng.random() < 0.005:  # date typed wrongly
            r["delivered_date"] = (date.fromisoformat(r["order_date"]) - timedelta(int(rng.integers(1, 5)))).isoformat()
        out.append(r)
        if rng.random() < 0.015:                          # the same order entered twice
            out.append(dict(r))
    orders = pd.DataFrame(out)
    ids, seen = [], 0
    for i, r in enumerate(out):  # duplicates must share the order_id of the entry before them
        if i > 0 and out[i] is not out[i - 1] and r == out[i - 1]:
            ids.append(ids[-1])
        else:
            seen += 1
            ids.append(f"TW-{seen:05d}")
    orders.insert(0, "order_id", ids)

    first = orders.groupby("customer_id")["order_date"].min()
    customers = pd.DataFrame({
        "customer_id": range(1, n_cust + 1),
        "name": [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(n_cust)],
        "city": rng.choice(CITIES, n_cust, p=[0.35, 0.15, 0.12, 0.1, 0.08, 0.08, 0.07, 0.05]),
        "phone": ["0" + rng.choice(["24", "54", "20", "55", "27"]) + "".join(map(str, rng.integers(0, 10, 7)))
                  for _ in range(n_cust)],
    })
    customers["joined_date"] = [
        (date.fromisoformat(first.get(i, START.isoformat())) - timedelta(int(rng.integers(0, 200)))).isoformat()
        for i in customers["customer_id"]]
    return {"customers": customers, "tailors": tailors, "orders": orders}


def generate(db_path, n_orders=2500, seed=42):
    """(Re)build the schema, load the synthetic tables and create the orders_clean view."""
    tables = make_tables(n_orders, seed)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP VIEW IF EXISTS orders_clean")
        conn.executescript((ROOT / "sql" / "schema.sql").read_text())
        for name, df in tables.items():
            df.to_sql(name, conn, if_exists="append", index=False)
        conn.executescript((ROOT / "sql" / "clean.sql").read_text())
        conn.commit()
    finally:
        conn.close()
    return {name: len(df) for name, df in tables.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(ROOT / "data" / "demo.db"))
    ap.add_argument("--orders", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print(generate(a.db, a.orders, a.seed), "->", a.db)