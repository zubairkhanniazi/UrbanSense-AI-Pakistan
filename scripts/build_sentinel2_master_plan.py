from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "interim"

SINGLE_FILE = DATA / "sentinel2_selected_scene_plan.json"
KARACHI_FILE = DATA / "karachi_multidate_composite_plan.json"

MASTER_JSON = DATA / "sentinel2_master_acquisition_plan.json"
MASTER_CSV = DATA / "sentinel2_master_acquisition_plan.csv"
SUMMARY_CSV = DATA / "sentinel2_master_plan_summary.csv"

CITIES = [
    "Islamabad Capital Territory",
    "Karachi",
    "Lahore",
    "Multan",
]
YEARS = range(2020, 2026)

for path in (SINGLE_FILE, KARACHI_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Required plan not found: {path}")

with SINGLE_FILE.open("r", encoding="utf-8") as f:
    single_groups = json.load(f)

with KARACHI_FILE.open("r", encoding="utf-8") as f:
    karachi_groups = json.load(f)

# Index single-date groups by city and year.
single_index = {}
for group in single_groups:
    key = (group["study_area"], int(group["year"]))

    if key in single_index:
        raise ValueError(f"Duplicate single-date group: {key}")

    single_index[key] = group

# Index Karachi multi-date groups by year.
karachi_index = {}
for group in karachi_groups:
    year = int(group["year"])

    if year in karachi_index:
        raise ValueError(f"Duplicate Karachi multi-date year: {year}")

    karachi_index[year] = group

master = []
tile_rows = []

for city in CITIES:
    for year in YEARS:
        key = (city, year)

        # Karachi 2020-2024 uses the multi-date plan.
        if city == "Karachi" and year in range(2020, 2025):
            source = karachi_index.get(year)

            if source is None:
                master.append({
                    "study_area": city,
                    "year": year,
                    "strategy": "multi_date_autumn",
                    "status": "MISSING SOURCE PLAN",
                    "acquisition_dates": [],
                    "expected_coverage_percent": None,
                    "scene_count": 0,
                    "scenes": [],
                })
                continue

            scenes = []

            for item in source.get("selected_scenes", []):
                assets = item.get("assets") or {}

                scenes.append({
                    "item_id": item.get("item_id", ""),
                    "acquisition_date": item.get(
                        "acquisition_date", ""
                    ),
                    "cloud_cover_percent": item.get(
                        "cloud_cover_percent"
                    ),
                    "mgrs_tile": item.get("mgrs_tile", ""),
                    "item_url": item.get("item_url", ""),
                    "assets": {
                        "red": assets.get("red", ""),
                        "nir": assets.get("nir", ""),
                        "scl": assets.get("scl", ""),
                    },
                })

            coverage = source.get(
                "achieved_geometric_coverage_percent"
            )

            assets_complete = all(
                all(scene["assets"].get(a) for a in ("red", "nir", "scl"))
                for scene in scenes
            )

            if coverage is not None and coverage >= 99 and scenes and assets_complete:
                status = "PLANNED - REQUIRES PIXEL QUALITY VALIDATION"
            else:
                status = "REVIEW REQUIRED"

            group = {
                "study_area": city,
                "year": year,
                "strategy": "multi_date_autumn",
                "season": "October-November",
                "status": status,
                "acquisition_dates": sorted({
                    scene["acquisition_date"] for scene in scenes
                    if scene["acquisition_date"]
                }),
                "expected_coverage_percent": coverage,
                "scene_count": len(scenes),
                "mean_scene_cloud_percent": source.get(
                    "mean_selected_scene_cloud_percent"
                ),
                "scenes": scenes,
            }

        else:
            source = single_index.get(key)

            if source is None:
                group = {
                    "study_area": city,
                    "year": year,
                    "strategy": "single_date_tiles",
                    "status": "MISSING SOURCE PLAN",
                    "acquisition_dates": [],
                    "expected_coverage_percent": None,
                    "scene_count": 0,
                    "scenes": [],
                }
            else:
                scenes = []

                for tile in source.get("tiles", []):
                    scenes.append({
                        "item_id": tile.get("item_id", ""),
                        "acquisition_date": source.get(
                            "acquisition_date", ""
                        ),
                        "cloud_cover_percent": tile.get(
                            "cloud_cover_percent"
                        ),
                        "mgrs_tile": tile.get("mgrs_tile", ""),
                        "item_url": tile.get("item_url", ""),
                        "assets": {
                            "red": tile.get("red_asset_url", ""),
                            "nir": tile.get("nir_asset_url", ""),
                            "scl": tile.get("scl_asset_url", ""),
                        },
                    })

                assets_complete = all(
                    all(scene["assets"].get(a) for a in ("red", "nir", "scl"))
                    for scene in scenes
                )

                coverage = source.get("boundary_coverage_percent")

                if (
                    scenes
                    and assets_complete
                    and coverage is not None
                    and coverage >= 99
                    and len(scenes) == int(
                        source.get("expected_tile_count", 0)
                    )
                ):
                    status = "PLANNED - REQUIRES PIXEL QUALITY VALIDATION"
                else:
                    status = "REVIEW REQUIRED"

                group = {
                    "study_area": city,
                    "year": year,
                    "strategy": "single_date_tiles",
                    "season": "October-November",
                    "status": status,
                    "acquisition_dates": (
                        [source.get("acquisition_date", "")]
                        if source.get("acquisition_date") else []
                    ),
                    "expected_coverage_percent": coverage,
                    "scene_count": len(scenes),
                    "mean_scene_cloud_percent": source.get(
                        "mean_scene_cloud_percent"
                    ),
                    "scenes": scenes,
                }

        master.append(group)

        for scene in group["scenes"]:
            assets = scene["assets"]

            tile_rows.append({
                "study_area": group["study_area"],
                "year": group["year"],
                "strategy": group["strategy"],
                "acquisition_date": scene["acquisition_date"],
                "item_id": scene["item_id"],
                "mgrs_tile": scene["mgrs_tile"],
                "cloud_cover_percent": scene["cloud_cover_percent"],
                "item_url": scene["item_url"],
                "red_asset_available": bool(assets.get("red")),
                "nir_asset_available": bool(assets.get("nir")),
                "scl_asset_available": bool(assets.get("scl")),
                "expected_coverage_percent": group.get(
                    "expected_coverage_percent"
                ),
                "group_status": group["status"],
            })

# Ensure every intended city-year combination occurs exactly once.
expected_keys = {
    (city, year) for city in CITIES for year in YEARS
}
actual_keys = [
    (group["study_area"], int(group["year"]))
    for group in master
]

if len(actual_keys) != len(set(actual_keys)):
    raise ValueError("Duplicate city-year combinations in master plan.")

missing_keys = expected_keys - set(actual_keys)

if missing_keys:
    raise ValueError(f"Missing city-year combinations: {missing_keys}")

with MASTER_JSON.open("w", encoding="utf-8") as f:
    json.dump(master, f, indent=2, ensure_ascii=False)

pd.DataFrame(tile_rows).to_csv(
    MASTER_CSV, index=False, encoding="utf-8"
)

summary_rows = []
for group in master:
    summary_rows.append({
        "study_area": group["study_area"],
        "year": group["year"],
        "strategy": group["strategy"],
        "scene_count": group["scene_count"],
        "expected_coverage_percent": group.get(
            "expected_coverage_percent"
        ),
        "status": group["status"],
    })

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(
    SUMMARY_CSV, index=False, encoding="utf-8"
)

print("=" * 65)
print("MASTER SATELLITE ACQUISITION PLAN")
print("=" * 65)
print("Expected city-year combinations:", len(expected_keys))
print("Master groups created:", len(master))
print("Selected scene records:", len(tile_rows))

print("\nGroups by strategy:")
print(summary_df.groupby("strategy").size().to_string())

print("\nGroups by status:")
print(summary_df.groupby("status").size().to_string())

print("\nCity-year overview:")
print(
    summary_df.pivot(
        index="study_area",
        columns="year",
        values="scene_count",
    ).to_string()
)

missing_assets = sum(
    not (
        row["red_asset_available"]
        and row["nir_asset_available"]
        and row["scl_asset_available"]
    )
    for row in tile_rows
)

print("\nScene records with missing required asset links:", missing_assets)

print("\nFiles created:")
print("Master JSON:", MASTER_JSON)
print("Master scene CSV:", MASTER_CSV)
print("Master summary CSV:", SUMMARY_CSV)

print(
    "\nIMPORTANT: This master plan consolidates preliminary "
    "geometric selections. It is not a pixel-validated dataset. "
    "Cloud masking, same-grid alignment, radiometric consistency "
    "and seasonal compositing must be checked before scientific "
    "comparisons are reported."
)
