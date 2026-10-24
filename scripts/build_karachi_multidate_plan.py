from pathlib import Path
import json
import re

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "interim"

MANIFEST = DATA / "sentinel2_autumn_scene_manifest.json"
BOUNDARIES = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

JSON_OUT = DATA / "karachi_multidate_composite_plan.json"
CSV_OUT = DATA / "karachi_multidate_composite_plan.csv"

YEARS = range(2020, 2025)
TARGET_COVERAGE = 99.0
MAX_SCENES_PER_YEAR = 40

for path in (MANIFEST, BOUNDARIES):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")

with MANIFEST.open("r", encoding="utf-8") as f:
    records = json.load(f)

boundaries = gpd.read_file(BOUNDARIES)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

boundaries = boundaries.to_crs("EPSG:4326")
karachi = boundaries[boundaries["shapeName"] == "Karachi"]

if karachi.empty:
    raise ValueError("Karachi boundary not found.")

city_geometry = karachi.geometry.iloc[0]

project = Transformer.from_crs(
    "EPSG:4326", "EPSG:6933", always_xy=True
).transform

city_projected = transform(project, city_geometry)
city_area = city_projected.area

if city_area <= 0:
    raise ValueError("Invalid Karachi boundary area.")

# Build unique candidates for Karachi, October-November only.
candidates_by_year = {year: {} for year in YEARS}

for record in records:
    if record.get("study_area") != "Karachi":
        continue

    date = record.get("acquisition_date", "")

    if len(date) < 10:
        continue

    try:
        year = int(date[:4])
        month = int(date[5:7])
    except ValueError:
        continue

    if year not in candidates_by_year or month not in (10, 11):
        continue

    item_id = record.get("item_id")
    geometry_json = record.get("geometry")
    assets = record.get("assets") or {}

    if not item_id or not geometry_json:
        continue

    if not all(assets.get(name) for name in ("red", "nir", "scl")):
        continue

    try:
        geom = transform(project, shape(geometry_json))

        if not geom.is_valid:
            geom = geom.buffer(0)

        geom = geom.intersection(city_projected)

        if geom.is_empty or geom.area <= 0:
            continue

        cloud = record.get("cloud_cover_percent")

        if cloud is None:
            continue

        cloud = float(cloud)

        if not 0 <= cloud <= 30:
            continue

    except Exception:
        continue

    # Deduplicate by satellite item ID.
    candidates_by_year[year][item_id] = {
        "item_id": item_id,
        "date": date,
        "cloud": cloud,
        "mgrs_tile": record.get("mgrs_tile", ""),
        "item_url": record.get("item_url", ""),
        "assets": {
            name: assets[name]
            for name in ("red", "nir", "scl")
        },
        "geometry": geom,
    }

plans = []
csv_rows = []

print("=" * 65)
print("KARACHI MULTI-DATE SCENE PLANNING")
print("=" * 65)
print("Season: October-November")
print("Years: 2020-2024")
print(f"Target geometric coverage: {TARGET_COVERAGE:.1f}%")
print("Maximum selected scenes per year:", MAX_SCENES_PER_YEAR)
print("No imagery will be downloaded.")

for year in YEARS:
    candidates = list(candidates_by_year[year].values())

    print(f"\nYear: {year}")
    print("Unique eligible candidate scenes:", len(candidates))

    selected = []
    remaining = candidates[:]
    covered_geometry = None
    coverage = 0.0

    while remaining and len(selected) < MAX_SCENES_PER_YEAR:
        if covered_geometry is None:
            uncovered = city_projected
        else:
            uncovered = city_projected.difference(covered_geometry)

        best_candidate = None
        best_gain = 0.0
        best_key = None

        for candidate in remaining:
            gain = candidate["geometry"].intersection(
                uncovered
            ).area

            # Prefer the largest new geographic contribution;
            # prefer lower cloud cover when gains are tied.
            key = (gain, -candidate["cloud"])

            if best_key is None or key > best_key:
                best_key = key
                best_candidate = candidate
                best_gain = gain

        if best_candidate is None or best_gain <= 1.0:
            break

        selected.append(best_candidate)
        remaining.remove(best_candidate)

        if covered_geometry is None:
            covered_geometry = best_candidate["geometry"]
        else:
            covered_geometry = unary_union([
                covered_geometry,
                best_candidate["geometry"],
            ])

        coverage = (
            100 * city_projected.intersection(
                covered_geometry
            ).area / city_area
        )

        if coverage >= TARGET_COVERAGE:
            break

    status = (
        "GEOMETRIC TARGET REACHED"
        if coverage >= TARGET_COVERAGE
        else "MORE SCENES OR DIFFERENT DATA NEEDED"
    )

    mean_cloud = (
        sum(item["cloud"] for item in selected) / len(selected)
        if selected else None
    )

    plan = {
        "study_area": "Karachi",
        "year": year,
        "season": "October-November",
        "target_coverage_percent": TARGET_COVERAGE,
        "achieved_geometric_coverage_percent": round(
            coverage, 4
        ),
        "candidate_scene_count": len(candidates),
        "selected_scene_count": len(selected),
        "mean_selected_scene_cloud_percent": (
            round(mean_cloud, 4) if mean_cloud is not None else None
        ),
        "status": status,
        "selected_scenes": [],
    }

    for index, item in enumerate(selected, start=1):
        scene = {
            "selection_order": index,
            "item_id": item["item_id"],
            "acquisition_date": item["date"],
            "cloud_cover_percent": item["cloud"],
            "mgrs_tile": item["mgrs_tile"],
            "item_url": item["item_url"],
            "assets": item["assets"],
        }

        plan["selected_scenes"].append(scene)

        csv_rows.append({
            "study_area": "Karachi",
            "year": year,
            "selection_order": index,
            "item_id": item["item_id"],
            "acquisition_date": item["date"],
            "cloud_cover_percent": item["cloud"],
            "mgrs_tile": item["mgrs_tile"],
            "item_url": item["item_url"],
            "red_asset_available": bool(item["assets"].get("red")),
            "nir_asset_available": bool(item["assets"].get("nir")),
            "scl_asset_available": bool(item["assets"].get("scl")),
            "achieved_coverage_percent": round(coverage, 4),
            "status": status,
        })

    plans.append(plan)

    print("Selected scenes:", len(selected))
    print(f"Achieved geometric coverage: {coverage:.2f}%")
    print("Mean selected scene cloud cover:",
          f"{mean_cloud:.2f}%" if mean_cloud is not None else "N/A")
    print("Status:", status)

with JSON_OUT.open("w", encoding="utf-8") as f:
    json.dump(plans, f, indent=2, ensure_ascii=False)

pd.DataFrame(csv_rows).to_csv(
    CSV_OUT, index=False, encoding="utf-8"
)

print("\n" + "=" * 65)
print("KARACHI MULTI-DATE PLAN FINISHED")
print("=" * 65)

print("\nCoverage summary:")
for plan in plans:
    print(
        f"{plan['year']}: "
        f"{plan['achieved_geometric_coverage_percent']:.2f}% | "
        f"{plan['selected_scene_count']} scenes | "
        f"{plan['status']}"
    )

print("\nJSON plan:", JSON_OUT)
print("CSV scene list:", CSV_OUT)

print(
    "\nResearch caution: This is a greedy geometric coverage plan. "
    "It does not establish cloud-free pixel coverage, radiometric "
    "consistency, or scientific suitability. Multiple dates will "
    "need pixel-level masking and a documented compositing method."
)
