from pathlib import Path
import json
import re

path = (
    Path.cwd() / "data" / "interim"
    / "karachi_multidate_composite_plan.json"
)

with path.open("r", encoding="utf-8-sig") as f:
    data = json.load(f)

records = []

def walk(obj):
    if isinstance(obj, dict):
        if "item_id" in obj and isinstance(obj.get("assets"), dict):
            records.append(obj)
        for value in obj.values():
            walk(value)
    elif isinstance(obj, list):
        for value in obj:
            walk(value)

walk(data)

print("=" * 65)
print("KARACHI 2024 — SELECTED SCENES")
print("=" * 65)

count = 0

for scene in records:
    item_id = str(scene.get("item_id", ""))
    date = str(scene.get("acquisition_date", ""))

    if not date:
        match = re.search(r"_(20\d{6})_", item_id)
        if match:
            raw = match.group(1)
            date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    if date.startswith("2024"):
        count += 1
        assets = scene["assets"]

        print(f"\nScene {count}: {item_id}")
        print("Date:", date)
        print("Selection order:", scene.get("selection_order"))

        for name in ("red", "nir", "scl"):
            url = assets.get(name)
            print(f"{name.upper()} asset available:", bool(url))
            if url:
                print(" ", url)

print("\nTotal 2024 scenes:", count)
print("Inspection only: no imagery downloaded.")
