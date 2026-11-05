"""Prompts, grounding check and caching around the Snwolley client."""
import hashlib
import json
import re
from pathlib import Path

from ai import snwolley

RULES = (
    "You are the analytics assistant inside ThreadWise, a tool for tailoring businesses.\n"
    "Rules:\n"
    "1. Use ONLY the facts in the JSON below. Never invent numbers, orders, people or causes.\n"
    "2. Quote figures exactly as given. If the facts do not answer something, say so plainly.\n"
    "3. Describe patterns as associations in the data, not proven causes.\n"
    "4. Write for a busy shop owner: plain English, no jargon, no model internals.\n"
)
TASKS = {
    "executive_summary": "Write an executive summary of about 150 words: how the business is doing on late "
                         "orders, the main reasons orders run late, and the single biggest risk right now.",
    "action_plan": "Recommend exactly three actions for the shop owner this week. For each give the action, "
                   "which tailor or order IDs it applies to, and the figure that justifies it.",
    "explain_drivers": "Explain in plain English why orders in this business run late, ranked by how much each "
                       "factor matters, with the supporting numbers.",
}
NUM = re.compile(r"\d[\d,]*\.?\d*")


def build_message(task: str, facts: dict, question: str | None = None) -> str:
    ask = (question or "").strip()[:500] if task == "ask" else TASKS[task]
    return f"{RULES}\nFACTS:\n{json.dumps(facts, indent=1, default=str)}\n\nTASK: {ask}"


def _numbers(obj, acc):
    if isinstance(obj, dict):
        [_numbers(v, acc) for v in obj.values()]
    elif isinstance(obj, (list, tuple)):
        [_numbers(v, acc) for v in obj]
    elif isinstance(obj, (int, float)):
        acc.add(float(obj)); acc.add(float(obj) * 100)
    elif isinstance(obj, str):
        for m in NUM.findall(obj):
            try: acc.add(float(m.replace(",", "")))
            except ValueError: pass
    return acc


def unsupported_figures(text: str, facts: dict) -> list[str]:
    """Numbers in the AI's answer that don't appear in the facts we sent."""
    known, bad = _numbers(facts, set()), []
    for m in NUM.findall(text):
        try: v = float(m.replace(",", "").rstrip("."))
        except ValueError: continue
        if v <= 10 or 2020 <= v <= 2030:        # list numbers, "three actions", years
            continue
        if not any(abs(v - k) <= max(0.51, abs(k) * 0.005) for k in known):
            bad.append(m)
    return bad


def get_insight(task, facts, cache_dir, question=None, refresh=False) -> dict:
    msg = build_message(task, facts, question)
    key = hashlib.sha256(msg.encode()).hexdigest()[:16]
    f = Path(cache_dir) / f"{task}_{key}.json"
    if f.exists() and not refresh:
        return {**json.loads(f.read_text()), "cached": True}
    reply = snwolley.ask(msg)
    out = {"task": task, "text": reply["text"], "unverified_figures": unsupported_figures(reply["text"], facts)}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return {**out, "cached": False}