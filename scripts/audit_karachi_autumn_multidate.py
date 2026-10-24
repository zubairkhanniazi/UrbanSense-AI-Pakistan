from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from pyproj import Transformer
import geopandas as gpd
import pandas as pd
import json
import time

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "karachi_autumn_multidate_coverage.csv"

API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
YEARS = range(2020, 2026)
MAX_CLOUD = 30
PAGE_LIMIT = 100
MAX_PAGES = 30

areas = gpd.read_file(BOUNDARY_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

areas = areas.to_crs("EPSG:4326")
karachi = areas[areas["shapeName"] == "Karachi"]

if karachi.empty:
    raise ValueError("Karachi boundary not found.")

city_geometry = karachi.geometry.iloc[0]

project = Transformer.from_crs(
    "EPSG:4326", "EPSG:6933", always_xy=True
).transform

city_projected = transform(project, city_geometry)
city_area = city_projected.area


def request_json(url, payload=None):
    headers = {
        "User-Agent": "UrbanSense-AI-Pakistan/0.1",
        "Accept": "application/geo+json, application/json",
    }

    if payload is not None:
        headers["Content-Type"] = "application/json"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    else:
        request = Request(url, headers=headers)

    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def search_all(payload):
    result = request_json(API, payload)
    features = list(result.get("features", []))
    seen = {f.get("id") for f in features}
    pages = 1

    while pages < MAX_PAGES:
        next_links = [
            link for link in result.get("links", [])
            if link.get("rel") == "next"
        ]

        if not next_links:
            break

        link = next_links[0]

        if link.get("method", "GET").upper() == "POST":
            result = request_json(
                link["href"],
                link.get("body", {}),
            )
        else:
            result = request_json(link["href"])

        for feature in result.get("features", []):
            item_id = feature.get("id")
            if item_id not in seen:
                features.append(feature)
                seen.add(item_id)

        pages += 1

    return features, pages


def measure_coverage(features):
    geometries = []
    clouds = []
    dates = []
    seen = set()

    for feature in features:
        item_id = feature.get("id")

        if item_id in seen:
            continue
        seen.add(item_id)

        geometry = feature.get("geometry")
        props = feature.get("properties") or {}

        if not geometry:
            continue

        try:
            projected_geometry = transform(
                project, shape(geometry)
            )
        except Exception:
            continue

        if not projected_geometry.is_valid:
            projected_geometry = projected_geometry.buffer(0)

        if projected_geometry.is_empty:
            continue

        geometries.append(projected_geometry)

        cloud = props.get("eo:cloud_cover")
        if cloud is not None:
            clouds.append(float(cloud))

        if props.get("datetime"):
            dates.append(props["datetime"][:10])

    if not geometries:
        return {
            "unique_scenes": 0,
            "coverage_percent": 0.0,
            "mean_scene_cloud_percent": None,
            "first_acquisition": "",
            "last_acquisition": "",
        }

    combined = unary_union(geometries)
    covered_area = city_projected.intersection(combined).area
    coverage = 100 * covered_area / city_area

    return {
        "unique_scenes": len(geometries),
        "coverage_percent": min(100.0, max(0.0, coverage)),
        "mean_scene_cloud_percent": (
            sum(clouds) / len(clouds) if clouds else None
        ),
        "first_acquisition": min(dates) if dates else "",
        "last_acquisition": max(dates) if dates else "",
    }


results = []
errors = []

print("KARACHI AUTUMN MULTI-DATE COVERAGE TEST")
print("Season: October-November")
print("Years: 2020-2025")
print("Maximum scene-level cloud cover:", MAX_CLOUD, "%")
print("No satellite imagery will be downloaded.")

for year in YEARS:
    print(f"\nSearching Karachi | {year}")

    payload = {
        "collections": [COLLECTION],
        "intersects": city_geometry.__geo_interface__,
        "datetime": (
            f"{year}-10-01T00:00:00Z/"
            f"{year}-12-01T00:00:00Z"
        ),
        "limit": PAGE_LIMIT,
        "query": {
            "eo:cloud_cover": {"lte": MAX_CLOUD}
        },
    }

    try:
        features, pages = search_all(payload)
    except Exception as exc:
        errors.append(f"{year}: {exc}")
        print("SEARCH ERROR:", exc)
        continue

    print("Scenes retrieved:", len(features))
    print("Pages retrieved:", pages)

    for label, month_numbers in [
        ("October", {10}),
        ("November", {11}),
        ("October-November", {10, 11}),
    ]:
        subset = []

        for feature in features:
            props = feature.get("properties") or {}
            acquired = props.get("datetime", "")

            if len(acquired) < 7:
                continue

            try:
                month = int(acquired[5:7])
            except ValueError:
                continue

            if month in month_numbers:
                subset.append(feature)

        metrics = measure_coverage(subset)

        record = {
            "year": year,
            "period": label,
            **metrics,
        }
        results.append(record)

        print(
            f"  {label}: {metrics['coverage_percent']:.2f}% "
            f"coverage | {metrics['unique_scenes']} scenes"
        )

    time.sleep(0.5)

if results:
    result_df = pd.DataFrame(results)
    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("AUTUMN MULTI-DATE COVERAGE TEST FINISHED")
    print("=" * 60)
    print(result_df.to_string(index=False))
    print("\nCSV:", OUTPUT_FILE)

if errors:
    print("\nSearch errors:", len(errors))
    for error in errors:
        print("-", error)

print(
    "\nImportant: Union of scene footprints measures geographic "
    "coverage, not clear pixels. A seasonal composite still "
    "requires pixel-level cloud masking and consistent processing."
)
