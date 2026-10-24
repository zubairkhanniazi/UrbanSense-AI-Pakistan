from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "interim"

SELECTION_FILE = (
    DATA / "sentinel2_autumn_full_coverage_candidates.csv"
)
MANIFEST_FILE = DATA / "sentinel2_autumn_scene_manifest.json"

PLAN_JSON = DATA / "sentinel2_selected_scene_plan.json"
PLAN_CSV = DATA / "sentinel2_selected_scene_tiles.csv"
GAPS_CSV = DATA / "sentinel2_scene_selection_gaps.csv"

CITIES = [
    "Islamabad Capital Territory",
    "Karachi",
    "Lahore",
    "Multan",
]
YEARS = range(2020, 2026)

for path in (SELECTION_FILE, MANIFEST_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

selected_df = pd.read_csv(SELECTION_FILE)
with MANIFEST_FILE.open("r", encoding="utf-8") as f:
    records = json.load(f)

groups = []
tile_rows = []
gaps = []

for _, selection in selected_df.iterrows():
    city = selection["study_area"]
    year = int(selection["year"])
    date = pd.to_datetime(
        selection["acquisition_date"]
    ).strftime("%Y-%m-%d")

    expected_tiles = int(selection["tile_count"])

    matches = [
        r for r in records
        if r.get("study_area") == city
        and int(r.get("year", 0)) == year
        and r.get("acquisition_date") == date
    ]

    # Remove duplicate item IDs.
    unique = {r["item_id"]: r for r in matches}
    matches = sorted(unique.values(), key=lambda r: r["item_id"])

    missing_assets = []
    for record in matches:
        assets = record.get("assets") or {}
        missing = [
            name for name in ("red", "nir", "scl")
            if not assets.get(name)
        ]
        if missing:
            missing_assets.append({
                "item_id": record.get("item_id"),
                "missing_assets": missing,
            })

    if not matches:
        status = "REVIEW: no matching manifest records"
    elif missing_assets:
        status = "REVIEW: missing required assets"
    elif len(matches) != expected_tiles:
        status = "REVIEW: tile count differs from coverage audit"
    else:
        status = "READY FOR FURTHER QUALITY CHECKS"

    group = {
        "study_area": city,
        "year": year,
        "acquisition_date": date,
        "expected_tile_count": expected_tiles,
        "matched_manifest_tiles": len(matches),
        "boundary_coverage_percent": float(
            selection["boundary_coverage_percent"]
        ),
        "mean_scene_cloud_percent": float(
            selection["mean_scene_cloud_percent"]
        ),
        "status": status,
        "tiles": [],
    }

    for record in matches:
        assets = record.get("assets") or {}

        tile = {
            "item_id": record["item_id"],
            "datetime_utc": record.get("datetime_utc"),
            "mgrs_tile": record.get("mgrs_tile", ""),
            "cloud_cover_percent": record.get(
                "cloud_cover_percent"
            ),
            "item_url": record.get("item_url", ""),
            "red_asset_url": assets.get("red", ""),
            "nir_asset_url": assets.get("nir", ""),
            "scl_asset_url": assets.get("scl", ""),
        }

        group["tiles"].append(tile)

        tile_rows.append({
            "study_area": city,
            "year": year,
            "acquisition_date": date,
            "item_id": tile["item_id"],
            "mgrs_tile": tile["mgrs_tile"],
            "cloud_cover_percent": tile["cloud_cover_percent"],
            "item_url": tile["item_url"],
            "red_asset_available": bool(tile["red_asset_url"]),
            "nir_asset_available": bool(tile["nir_asset_url"]),
            "scl_asset_available": bool(tile["scl_asset_url"]),
            "group_status": status,
        })

    groups.append(group)

# Identify all city/year combinations without a full-coverage
# October-November selection.
selected_keys = {
    (g["study_area"], g["year"]) for g in groups
}

for city in CITIES:
    for year in YEARS:
        if (city, year) not in selected_keys:
            gaps.append({
                "study_area": city,
                "year": year,
                "status": "Needs further scene search",
                "reason": (
                    "No qualifying same-date October-November "
                    "group with at least 99% boundary coverage "
                    "in the current selection results."
                ),
            })

with PLAN_JSON.open("w", encoding="utf-8") as f:
    json.dump(groups, f, indent=2, ensure_ascii=False)

pd.DataFrame(tile_rows).to_csv(
    PLAN_CSV, index=False, encoding="utf-8"
)

pd.DataFrame(gaps).to_csv(
    GAPS_CSV, index=False, encoding="utf-8"
)

print("=" * 65)
print("SATELLITE SCENE SELECTION PLAN")
print("=" * 65)
print("Selected city/year groups:", len(groups))
print("Tile records matched:", len(tile_rows))
print("City/year combinations needing further search:", len(gaps))

if groups:
    print("\nSelection status:")
    print(
        pd.DataFrame(groups)
        .groupby("status")
        .size()
        .to_string()
    )

    print("\nSelected scenes by city and year:")
    print(
        pd.DataFrame(groups)[
            [
                "study_area",
                "year",
                "acquisition_date",
                "expected_tile_count",
                "matched_manifest_tiles",
                "status",
            ]
        ].to_string(index=False)
    )

print("\nUnresolved city/year combinations:")
for gap in gaps:
    print(f"  {gap['study_area']} | {gap['year']}")

print("\nFiles created:")
print("Plan JSON:", PLAN_JSON)
print("Tile inventory CSV:", PLAN_CSV)
print("Coverage gaps CSV:", GAPS_CSV)

print(
    "\nNo satellite images were downloaded. "
    "READY means the scene records and required asset links "
    "matched the preliminary selection, not that the pixels "
    "have passed cloud or scientific quality validation."
)
