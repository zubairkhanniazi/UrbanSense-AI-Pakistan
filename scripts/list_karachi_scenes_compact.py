import json
import re
from pathlib import Path

p = Path("data/interim/karachi_multidate_composite_plan.json")
data = json.loads(p.read_text(encoding="utf-8-sig"))

def walk(obj):
    if isinstance(obj, dict):
        if "item_id" in obj:
            yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)

seen = set()

for s in walk(data):
    item = str(s.get("item_id", ""))
    match = re.search(r"(20\d{6})", item)
    date = s.get("acquisition_date") or s.get("datetime")
    if date:
        date = str(date)[:10]
    elif match:
        raw = match.group(1)
        date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    if date and date.startswith("2024") and item not in seen:
        seen.add(item)
        assets = s.get("assets") or {}
        print(f"Scene: {item}")
        print(f"Date: {date}")
        print("Red/NIR/SCL:", *[
            "OK" if assets.get(a) else "MISSING"
            for a in ("red", "nir", "scl")
        ])
        print()

print("Total matching scenes:", len(seen))
