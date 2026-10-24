from pathlib import Path
from urllib.request import Request, urlopen
import json
import time

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]

SCENES_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_scene_search_results.json"
)
BOUNDARIES_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "sentinel2_coverage_audit.csv"

if not SCENES_FILE.exists():
    raise FileNotFoundError(f"Missing scene records: {SCENES_FILE}")

if not BOUNDARIES_FILE.exists():
    raise FileNotFoundError(f"Missing boundaries: {BOUNDARIES_FILE}")

with SCENES_FILE.open("r", encoding="utf-8") as f:
    records = json.load(f)

areas = gpd.read_file(BOUNDARIES_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

if areas.crs.to_epsg() != 4326:
    areas = areas.to_crs("EPSG:4326")

areas = areas.set_index("shapeName")

# Use an equal-area projection for meaningful area comparisons.
project = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:6933",
    always_xy=True,
).transform

# Keep one lowest-cloud candidate per city and year.
df = pd.DataFrame(records)

df["cloud_cover_percent"] = pd.to_numeric(
    df["cloud_cover_percent"], errors="coerce"
)
df["datetime_utc"] = pd.to_datetime(
    df["datetime_utc"], errors="coerce", utc=True
)

df = df.dropna(
    subset=["study_area", "year", "item_id", "item_url"]
)

df = df.sort_values(
    ["study_area", "year", "cloud_cover_percent", "datetime_utc"]
)

best = df.drop_duplicates(
    subset=["study_area", "year"],
    keep="first",
)

results = []

print("Auditing selected Sentinel-2 scene footprints...")
print("No satellite imagery will be downloaded.")

for _, row in best.iterrows():
    city = row["study_area"]
    year = int(row["year"])
    item_url = row["item_url"]

    print(f"\nChecking {city} | {year}")

    if city not in areas.index:
        print("  ERROR: Study boundary not found.")
        continue

    try:
        request = Request(
            item_url,
            headers={
                "User-Agent": "UrbanSense-AI-Pakistan/0.1"
            },
        )

        with urlopen(request, timeout=45) as response:
            item = json.loads(response.read().decode("utf-8"))

        item_geometry = item.get("geometry")

        if not item_geometry:
            raise ValueError("STAC item has no geometry.")

        scene_geom = shape(item_geometry)
        city_geom = areas.loc[city].geometry

        scene_projected = transform(project, scene_geom)
        city_projected = transform(project, city_geom)

        city_area = city_projected.area

        if city_area <= 0:
            raise ValueError("Study-area geometry has zero area.")

        intersection_area = (
            city_projected.intersection(scene_projected).area
        )

        coverage_pct = min(
            100.0,
            max(0.0, 100.0 * intersection_area / city_area),
        )

        result = {
            "study_area": city,
            "year": year,
            "item_id": item.get("id", row["item_id"]),
            "datetime_utc": row["datetime_utc"].isoformat(),
            "cloud_cover_percent": float(
                row["cloud_cover_percent"]
            ),
            "mgrs_tile": row.get("mgrs_tile", ""),
            "administrative_area_km2": city_area / 1_000_000,
            "scene_intersection_km2": (
                intersection_area / 1_000_000
            ),
            "boundary_coverage_percent": coverage_pct,
            "coverage_status": (
                "Full coverage"
                if coverage_pct >= 99.0
                else "Partial coverage"
            ),
            "item_url": item_url,
        }

        results.append(result)

        print(f"  Acquisition: {result['datetime_utc']}")
        print(f"  Scene coverage: {coverage_pct:.2f}%")
        print(f"  Status: {result['coverage_status']}")

    except Exception as exc:
        print("  ERROR:", exc)

    time.sleep(0.15)

if results:
    audit = pd.DataFrame(results)

    audit.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("COVERAGE AUDIT FINISHED")
    print("=" * 60)

    print("Scenes checked:", len(audit))
    print(
        "Full-coverage scenes:",
        int((audit["boundary_coverage_percent"] >= 99).sum()),
    )
    print(
        "Partial-coverage scenes:",
        int((audit["boundary_coverage_percent"] < 99).sum()),
    )

    print("\nCoverage by city and year:")
    print(
        audit.pivot(
            index="study_area",
            columns="year",
            values="boundary_coverage_percent",
        ).round(2).to_string()
    )

    print("\nAudit CSV:", OUTPUT_FILE)

else:
    print("\nNo coverage results were produced.")

print(
    "\nNote: Footprint coverage is not the same as cloud-free "
    "coverage. SCL quality validation is still required."
)
