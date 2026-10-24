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

OUTPUT_FILE = OUTPUT_DIR / "karachi_full_year_coverage_candidates.csv"

API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
YEARS = range(2020, 2025)
MAX_CLOUD = 30
PAGE_LIMIT = 100
MAX_PAGES = 15

areas = gpd.read_file(BOUNDARY_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

if areas.crs.to_epsg() != 4326:
    areas = areas.to_crs("EPSG:4326")

karachi = areas.loc[areas["shapeName"] == "Karachi"]

if karachi.empty:
    raise ValueError("Karachi boundary was not found.")

city_geometry = karachi.geometry.iloc[0]

project = Transformer.from_crs(
    "EPSG:4326", "EPSG:6933", always_xy=True
).transform

city_projected = transform(project, city_geometry)
city_area = city_projected.area


def request_json(url, payload=None, attempts=3):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            headers = {
                "User-Agent": "UrbanSense-AI-Pakistan/0.1",
                "Accept": "application/geo+json, application/json",
            }

            if payload is not None:
                headers["Content-Type"] = "application/json"
                req = Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
            else:
                req = Request(url, headers=headers)

            with urlopen(req, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))

        except (HTTPError, URLError, TimeoutError, OSError,
                json.JSONDecodeError) as exc:
            last_error = exc
            print(f"  Request attempt {attempt}/{attempts} failed: {exc}")

            if attempt < attempts:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Request failed after retries: {last_error}")


def get_all_features(payload):
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


all_results = []
errors = []

print("KARACHI SENTINEL-2 FULL-YEAR SEARCH")
print("Years: 2020–2024")
print("Maximum scene-level cloud cover:", MAX_CLOUD, "%")
print("Retrying failed requests where possible.")
print("No satellite images will be downloaded.")

for year in YEARS:
    print(f"\nSearching Karachi | {year}")

    payload = {
        "collections": [COLLECTION],
        "intersects": city_geometry.__geo_interface__,
        "datetime": (
            f"{year}-01-01T00:00:00Z/"
            f"{year}-12-31T23:59:59Z"
        ),
        "limit": PAGE_LIMIT,
        "query": {
            "eo:cloud_cover": {"lte": MAX_CLOUD}
        },
        "sortby": [
            {
                "field": "properties.eo:cloud_cover",
                "direction": "asc",
            }
        ],
    }

    try:
        features, pages = get_all_features(payload)
        print("Catalog items retrieved:", len(features))
        print("Pages retrieved:", pages)

    except Exception as exc:
        message = f"Karachi {year}: {exc}"
        errors.append(message)
        print("YEAR SEARCH FAILED:", exc)
        continue

    grouped = {}

    for feature in features:
        props = feature.get("properties") or {}
        cloud = props.get("eo:cloud_cover")
        acquired = props.get("datetime")
        geometry = feature.get("geometry")

        if cloud is None or not acquired or not geometry:
            continue

        cloud = float(cloud)

        if not 0 <= cloud <= MAX_CLOUD:
            continue

        try:
            projected_geometry = transform(
                project, shape(geometry)
            )
        except Exception:
            continue

        date = acquired[:10]

        grouped.setdefault(date, []).append({
            "item_id": feature.get("id", ""),
            "cloud": cloud,
            "geometry": projected_geometry,
        })

    for date, tiles in grouped.items():
        combined = unary_union([
            tile["geometry"] for tile in tiles
        ])

        intersection = city_projected.intersection(combined).area
        coverage = 100 * intersection / city_area

        all_results.append({
            "study_area": "Karachi",
            "year": year,
            "acquisition_date": date,
            "month": int(date[5:7]),
            "tile_count": len(tiles),
            "boundary_coverage_percent": min(
                100.0, max(0.0, coverage)
            ),
            "mean_scene_cloud_percent": sum(
                tile["cloud"] for tile in tiles
            ) / len(tiles),
            "item_ids": ";".join(
                tile["item_id"] for tile in tiles
            ),
        })

    time.sleep(0.5)

if not all_results:
    print("\nNo date groups were generated.")
    print("Review the search errors and catalog availability.")

else:
    df = pd.DataFrame(all_results)

    df = df.sort_values([
        "year",
        "acquisition_date",
        "mean_scene_cloud_percent",
    ])

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("KARACHI SEARCH RESULTS")
    print("=" * 60)

    full = df[df["boundary_coverage_percent"] >= 99.0].copy()

    print("Date groups found:", len(df))
    print("Full-coverage date groups:", len(full))

    print("\nFull-coverage groups by year and month:")
    if full.empty:
        print("None found in the retrieved catalog results.")
    else:
        print(
            full.groupby(["year", "month"])
            .size()
            .unstack(fill_value=0)
            .reindex(index=list(YEARS), fill_value=0)
            .to_string()
        )

        print("\nBest full-coverage candidate per year:")
        best = full.sort_values(
            [
                "year",
                "mean_scene_cloud_percent",
                "acquisition_date",
            ]
        ).drop_duplicates("year")

        print(
            best[
                [
                    "year",
                    "acquisition_date",
                    "tile_count",
                    "boundary_coverage_percent",
                    "mean_scene_cloud_percent",
                ]
            ].to_string(index=False)
        )

    print("\nCSV:", OUTPUT_FILE)

if errors:
    print("\nSearch errors:", len(errors))
    for error in errors:
        print("-", error)

print(
    "\nNote: Catalog search results are not guaranteed to be exhaustive. "
    "Full geometric coverage does not guarantee cloud-free pixels."
)
