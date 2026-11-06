"""Generic binary-classification pipeline driven by one SQL query.

The query must return: an id column, a date column, a split column
('train' | 'score' | 'exclude'), a 0/1 target, and feature columns.
Swap the SQL (and the arguments) to change the use case; this code stays the same.
"""
import argparse
import json
import logging
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

log = logging.getLogger("threadwise.ml")
HIGH, MEDIUM = 0.55, 0.30  # risk bands on predicted probability


def load_dataset(db_path, sql_path) -> pd.DataFrame:
    sql = Path(sql_path).read_text()
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(sql, con)
    log.info("Loaded %d rows from %s", len(df), sql_path)
    return df


def make_pipeline(model, num_cols, cat_cols) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num_cols),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), cat_cols),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def evaluate(y, p) -> dict:
    y = np.asarray(y)
    k = max(1, int(len(y) * 0.20))
    top = np.argsort(-p)[:k]
    pred = (p >= 0.5).astype(int)
    return {"roc_auc": round(roc_auc_score(y, p), 3),
            "pr_auc": round(average_precision_score(y, p), 3),
            "precision_at_0.5": round(precision_score(y, pred, zero_division=0), 3),
            "recall_at_0.5": round(recall_score(y, pred, zero_division=0), 3),
            "top20pct_capture": round(float(y[top].sum() / max(1, y.sum())), 3),
            "base_rate": round(float(y.mean()), 3), "n_test": int(len(y))}


def explain_rows(pipe, X, ref, top_n=3):
    """Local explanation: how much does each feature push this row's risk up?
    Replace one feature at a time with its typical value and measure the drop."""
    base = pipe.predict_proba(X)[:, 1]
    deltas = {}
    for col in X.columns:
        Xm = X.copy()
        Xm[col] = ref[col]
        deltas[col] = base - pipe.predict_proba(Xm)[:, 1]
    out = []
    for i in range(len(X)):
        ranked = sorted(((deltas[c][i], c) for c in X.columns), reverse=True)[:top_n]
        out.append([{"feature": c, "value": _clean(X.iloc[i][c]), "risk_points": round(float(d) * 100, 1)}
                    for d, c in ranked if d > 0.02])
    return out


def _clean(v):
    if pd.isna(v):
        return None
    return round(float(v), 2) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (np.integer,)) else v)


def run(db_path, sql_path, out_dir, target="is_late", id_col="order_id", date_col="order_date",
        split_col="split", passthrough=("promised_date", "tailor_id"), test_frac=0.20, seed=42) -> dict:
    df = load_dataset(db_path, sql_path)
    reserved = {id_col, target, split_col, date_col, *passthrough}
    feats = [c for c in df.columns if c not in reserved]
    num = [c for c in feats if pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in feats if c not in num]

    labeled = df[df[split_col] == "train"].sort_values([date_col, id_col]).reset_index(drop=True)
    if len(labeled) < 200 or labeled[target].nunique() < 2:
        raise ValueError("Need at least 200 labelled orders with both outcomes.")
    cut = int(len(labeled) * (1 - test_frac))           # time-based split: test = most recent orders
    tr, te = labeled.iloc[:cut], labeled.iloc[cut:]
    log.info("Train %d (to %s) | test %d (from %s)", len(tr), tr[date_col].max(), len(te), te[date_col].min())

    candidates = {
        "baseline_base_rate": DummyClassifier(strategy="prior"),
        "logistic_regression": LogisticRegression(max_iter=1000),
        "gradient_boosting": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08,
                                                            max_iter=200, random_state=seed),
    }
    metrics, fitted = {}, {}
    for name, model in candidates.items():
        pipe = make_pipeline(model, num, cat).fit(tr[feats], tr[target])
        metrics[name] = evaluate(te[target], pipe.predict_proba(te[feats])[:, 1])
        fitted[name] = pipe
    best = max((n for n in metrics if not n.startswith("baseline")), key=lambda n: metrics[n]["roc_auc"])
    log.info("Best model: %s %s", best, metrics[best])

    # Do the risk bands mean anything? Check the real late rate inside each band on the test set.
    p_test = fitted[best].predict_proba(te[feats])[:, 1]
    bands = pd.cut(p_test, [0, MEDIUM, HIGH, 1.0], labels=["low", "medium", "high"], include_lowest=True)
    band_check = {str(b): {"orders": int(r["count"]), "late_rate": round(float(r["mean"]), 3)}
                  for b, r in te[target].groupby(bands, observed=True).agg(["count", "mean"]).iterrows()}

    imp = permutation_importance(fitted[best], te[feats], te[target], scoring="roc_auc",
                                 n_repeats=5, random_state=seed)
    importance = sorted(({"feature": f, "importance": round(float(m), 4)}
                         for f, m in zip(feats, imp.importances_mean)), key=lambda r: -r["importance"])

    # refit the winner on all labelled data, then score open orders
    final = make_pipeline(clone(candidates[best]), num, cat)
    final.fit(labeled[feats], labeled[target])
    ref = {c: (labeled[c].median() if c in num else labeled[c].mode().iloc[0]) for c in feats}
    pending = df[df[split_col] == "score"].reset_index(drop=True)
    preds = []
    if len(pending):
        prob = final.predict_proba(pending[feats])[:, 1]
        drivers = explain_rows(final, pending[feats], ref)
        for i, row in pending.iterrows():
            p = float(prob[i])
            preds.append({id_col: int(row[id_col]), **{c: _clean(row[c]) for c in passthrough},
                          "probability": round(p, 3),
                          "risk": "high" if p >= HIGH else "medium" if p >= MEDIUM else "low",
                          "drivers": drivers[i]})
        preds.sort(key=lambda r: -r["probability"])

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    result = {"best_model": best, "band_check": band_check, "metrics": metrics, "importance": importance,
              "features": feats, "n_train": len(tr), "n_test": len(te), "predictions": preds}
    joblib.dump(final, out / "model.joblib")
    (out / "results.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame([{**{k: v for k, v in p.items() if k != "drivers"},
                   "drivers": "; ".join(f"{d['feature']}={d['value']} (+{d['risk_points']})" for d in p["drivers"])}
                  for p in preds]).to_csv(out / "predictions.csv", index=False)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to a workspace database, e.g. data/workspaces/abc123.db")
    ap.add_argument("--sql", default="sql/features_late.sql")
    ap.add_argument("--out", default="ml/artifacts/demo")
    a = ap.parse_args()
    r = run(a.db, a.sql, a.out)
    print(json.dumps({k: r[k] for k in ("best_model", "metrics", "band_check")}, indent=2))
    print("Top drivers:", r["importance"][:5])
    print("Open orders scored:", len(r["predictions"]))