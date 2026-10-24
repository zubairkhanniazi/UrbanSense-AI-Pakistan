from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
path = (
    ROOT / "data" / "interim"
    / "karachi_multidate_composite_plan.json"
)

if not path.exists():
    raise FileNotFoundError(f"Karachi acquisition plan not found: {path}")

with path.open("r", encoding="utf-8") as f:
    data = json.load(f)

print("=" * 65)
print("KARACHI MULTI-DATE ACQUISITION PLAN")
print("=" * 65)

print("Plan type:", type(data).__name__)

if isinstance(data, dict):
    print("Top-level keys:", list(data.keys()))

def inspect(obj, depth=0):
    if isinstance(obj, dict):
        if any(k in obj for k in ("item_id", "scene_id")):
            print("\nScene record:")
            for key in (
                "study_area",
                "year",
                "acquisition_date",
                "item_id",
                "scene_id",
                "strategy",
                "status",
            ):
                if key in obj:
                    print(f"  {key}: {obj[key]}")

            assets = obj.get("assets", {})
            if isinstance(assets, dict):
                print("  Available asset keys:", list(assets.keys()))

        for value in obj.values():
            inspect(value, depth + 1)

    elif isinstance(obj, list):
        for value in obj:
            inspect(value, depth + 1)

inspect(data)

print("\nInspection finished. No files were modified.")
