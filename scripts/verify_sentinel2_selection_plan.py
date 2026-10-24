from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "interim"

plan_file = DATA / "sentinel2_selected_scene_plan.json"
gaps_file = DATA / "sentinel2_scene_selection_gaps.csv"

with plan_file.open("r", encoding="utf-8") as f:
    groups = json.load(f)

gaps = pd.read_csv(gaps_file) if gaps_file.exists() else pd.DataFrame()

print("=" * 65)
print("SENTINEL-2 SELECTION PLAN VALIDATION")
print("=" * 65)

print("Selected city-year groups:", len(groups))

status_counts = {}
missing_assets_total = 0
tile_count_mismatches = 0
empty_urls = 0

for group in groups:
    status = group.get("status", "UNKNOWN")
    status_counts[status] = status_counts.get(status, 0) + 1

    expected = group.get("expected_tile_count", 0)
    matched = group.get("matched_manifest_tiles", 0)

    if expected != matched:
        tile_count_mismatches += 1

    for tile in group.get("tiles", []):
        for asset in ("red_asset_url", "nir_asset_url", "scl_asset_url"):
            if not tile.get(asset):
                missing_assets_total += 1

        if not tile.get("item_url"):
            empty_urls += 1

print("\nGroup status counts:")
for status, count in sorted(status_counts.items()):
    print(f"  {status}: {count}")

print("\nTile-count mismatches:", tile_count_mismatches)
print("Missing required asset links:", missing_assets_total)
print("Missing STAC item links:", empty_urls)
print("Unresolved city-year combinations:", len(gaps))

print("\nSelected city-year groups:")
for group in groups:
    print(
        f"{group['study_area']} | {group['year']} | "
        f"{group['acquisition_date']} | "
        f"tiles: {group['matched_manifest_tiles']}/"
        f"{group['expected_tile_count']} | "
        f"{group['status']}"
    )

if not gaps.empty:
    print("\nUnresolved combinations:")
    print(gaps[["study_area", "year", "status"]].to_string(index=False))

print(
    "\nImportant: This checks the saved metadata and links, "
    "not whether remote assets can be downloaded or whether "
    "their pixels pass scientific quality checks."
)
