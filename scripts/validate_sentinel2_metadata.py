from pathlib import Path
from urllib.request import Request, urlopen
import json

root = Path(__file__).resolve().parents[1]
path = root / "data" / "interim" / "sentinel2_scene_search_results.json"

with path.open(encoding="utf-8") as f:
    records = json.load(f)

print("Total scenes:", len(records))
print("Saved cloud values:", sorted(set(
    r.get("cloud_cover_percent") for r in records
)))

seen = set()
checked = 0

for r in records:
    key = (r.get("study_area"), r.get("year"))
    url = r.get("item_url")

    if not url or key in seen:
        continue

    seen.add(key)
    print("\nCity:", key[0], "| Year:", key[1])
    print("Saved scene ID:", r.get("item_id"))
    print("Saved cloud cover:", r.get("cloud_cover_percent"))

    try:
        req = Request(
            url,
            headers={"User-Agent": "UrbanSense-AI-Pakistan/0.1"}
        )
        with urlopen(req, timeout=30) as response:
            item = json.loads(response.read().decode("utf-8"))

        props = item.get("properties", {})
        print("Verified scene ID:", item.get("id"))
        print("Original acquisition date:", props.get("datetime"))
        print("Original cloud cover:", props.get("eo:cloud_cover"))
        print("Original collection:", item.get("collection"))

    except Exception as exc:
        print("Verification error:", str(exc))

    checked += 1
    if checked == 3:
        break

if checked == 0:
    print("\nNo scene URLs available for verification.")

print("\nMetadata verification finished.")
