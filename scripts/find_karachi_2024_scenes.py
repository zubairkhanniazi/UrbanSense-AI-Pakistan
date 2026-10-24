from pathlib import Path
import json
import re

path = (
    Path.cwd() / "data" / "interim"
    / "karachi_multidate_composite_plan.json"
)

if not path.exists():
    raise FileNotFoundError(f"Plan not found: {path}")

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
print("KARACHI 2024 SENTINEL-2 SCENES")
print("=" * 65)
print("Scene records found:", len(records))

matches = []

for scene in records:
    item_id = str(scene.get("item_id", ""))
    date = str(scene.get("acquisition_date", ""))

    if not date:
        found = re.search(r"_(20\d{6})_", item_id)
        if found:
            raw = found.group(1)
            date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    if date.startswith("2024"):
        assets = scene["assets"]
        matches.append(scene)

        print("\nScene ID:", item_id)
        print("Acquisition date:", date)
        print("Selection order:", scene.get("selection_order"))
        print("Red URL available:", bool(assets.get("red")))
        print("NIR URL available:", bool(assets.get("nir")))
        print("SCL URL available:", bool(assets.get("scl")))

print("\n2024 scene records found:", len(matches))

if not matches:
    print(
        "No 2024 scenes found in this plan. "
        "We will inspect the master acquisition plan next."
    )
