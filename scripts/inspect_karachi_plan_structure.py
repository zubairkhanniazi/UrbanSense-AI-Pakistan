from pathlib import Path
import json

path = (
    Path.cwd() / "data" / "interim"
    / "karachi_multidate_composite_plan.json"
)

if not path.exists():
    raise FileNotFoundError(f"Plan not found: {path}")

with path.open("r", encoding="utf-8-sig") as f:
    data = json.load(f)

print("=" * 60)
print("KARACHI PLAN STRUCTURE")
print("=" * 60)
print("JSON type:", type(data).__name__)

def show_structure(obj, depth=0, max_depth=4):
    indent = "  " * depth

    if isinstance(obj, dict):
        print(f"{indent}Object keys: {list(obj.keys())[:40]}")

        if depth >= max_depth:
            return

        for key, value in list(obj.items())[:12]:
            print(f"{indent}[{key}]")
            show_structure(value, depth + 1, max_depth)

    elif isinstance(obj, list):
        print(f"{indent}List length: {len(obj)}")

        if depth >= max_depth or not obj:
            return

        for i, value in enumerate(obj[:2]):
            print(f"{indent}[item {i}]")
            show_structure(value, depth + 1, max_depth)

    else:
        value = repr(obj)
        print(f"{indent}{value[:180]}")

show_structure(data)

print("\nInspection complete. No files modified.")
