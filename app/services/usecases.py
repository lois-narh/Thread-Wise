import json
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "use_cases"


def all_usecases():
    """{key: config}. A new use case is just a new .json file in app/usecases/."""
    return {p.stem: json.loads(p.read_text()) for p in sorted(DIR.glob("*.json"))}