from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import time

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
START_YEAR = 2020
END_YEAR = 2025
MAX_CLOUD = 30
PAGE_LIMIT = 100
MAX_PAGES = 20

CSV_OUT = OUTPUT_DIR / "sentinel2_same_day_tile_coverage.csv"
JSON_OUT = OUTPUT_DIR / "sentinel2_same_day_tile_coverage.json"

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(f"Missing boundaries: {BOUNDARY_FILE}")

areas = gpd.read_file(BOUNDARY_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

areas = areas.to_crs("EPSG:4326")
areas = areas.set_index("shapeName")

project = Transformer.from_crs(
    "EPSG:4326", "EPSG:6933", always_xy=True
).transform


def request_json(url, payload=None):
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
        req = Request(url, headers=headers, method="GET")

    with urlopen(req, timeout=120) as response:
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
        method = link.get("method", "GET").upper()

        if method == "POST":
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


rows = []
selected_groups = []
errors = []

total = len(areas) * (END_YEAR - START_YEAR + 1)
counter = 0

print("Searching for same-date Sentinel-2 tile groups.")
print("Cloud filter:", MAX_CLOUD, "% maximum per scene")
print("No imagery will be downloaded.")

for city in areas.index:
    city_geometry = areas.loc[city].geometry
    city_projected = transform(project, city_geometry)
    city_area = city_projected.area

    if city_area <= 0:
        raise ValueError(f"Invalid study area: {city}")

    for year in range(START_YEAR, END_YEAR + 1):
        counter += 1
        print(f"\n[{counter}/{total}] {city} | {year}")

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
            features, pages = search_all(payload)
        except Exception as exc:
            message = f"{city} {year}: {exc}"
            errors.append(message)
            print("SEARCH ERROR:", exc)
            continue

        # Group intersecting tile footprints by acquisition date.
        date_groups = {}

        for feature in features:
            props = feature.get("properties") or {}
            cloud = props.get("eo:cloud_cover")
            acquired = props.get("datetime")

            if cloud is None or not acquired or not feature.get("geometry"):
                continue

            cloud = float(cloud)
            if not 0 <= cloud <= MAX_CLOUD:
                continue

            date = acquired[:10]

            try:
                scene_geometry = shape(feature["geometry"])
                scene_projected = transform(project, scene_geometry)
            except Exception:
                continue

            if not scene_projected.is_valid:
                scene_projected = scene_projected.buffer(0)

            date_groups.setdefault(date, []).append({
                "item_id": feature.get("id", ""),
                "datetime_utc": acquired,
                "cloud_cover_percent": cloud,
                "platform": props.get("platform", ""),
                "mgrs_tile": (
                    str(props.get("mgrs:utm_zone", ""))
                    + str(props.get("mgrs:latitude_band", ""))
                    + str(props.get("mgrs:grid_square", ""))
                ),
                "item_url": next(
                    (
                        link["href"]
                        for link in feature.get("links", [])
                        if link.get("rel") in ("self", "canonical")
                        and link.get("href")
                    ),
                    "",
                ),
                "_geometry": scene_projected,
            })

        city_year_groups = []

        for date, tiles in date_groups.items():
            combined = unary_union([
                tile["_geometry"] for tile in tiles
            ])

            covered_area = city_projected.intersection(combined).area
            coverage = 100 * covered_area / city_area

            group = {
                "study_area": city,
                "year": year,
                "acquisition_date": date,
                "tile_count": len(tiles),
                "boundary_coverage_percent": min(100.0, coverage),
                "mean_scene_cloud_percent": sum(
                    t["cloud_cover_percent"] for t in tiles
                ) / len(tiles),
                "item_ids": [t["item_id"] for t in tiles],
                "tiles": [
                    {k: v for k, v in tile.items() if k != "_geometry"}
                    for tile in tiles
                ],
            }

            city_year_groups.append(group)

        # Prefer boundary coverage first, then lower mean cloud.
        city_year_groups.sort(
            key=lambda g: (
                -g["boundary_coverage_percent"],
                g["mean_scene_cloud_percent"],
                g["acquisition_date"],
            )
        )

        for rank, group in enumerate(city_year_groups, start=1):
            rows.append({
                "study_area": city,
                "year": year,
                "rank": rank,
                "acquisition_date": group["acquisition_date"],
                "tile_count": group["tile_count"],
                "boundary_coverage_percent": round(
                    group["boundary_coverage_percent"], 3
                ),
                "mean_scene_cloud_percent": round(
                    group["mean_scene_cloud_percent"], 6
                ),
                "item_ids": ";".join(group["item_ids"]),
            })

        # Preserve the top five date groups for later review.
        selected_groups.extend(city_year_groups[:5])

        if city_year_groups:
            best = city_year_groups[0]
            print("Catalog items inspected:", len(features))
            print("Pages retrieved:", pages)
            print("Acquisition dates grouped:", len(city_year_groups))
            print("Best date:", best["acquisition_date"])
            print("Tiles on that date:", best["tile_count"])
            print(
                "Combined boundary coverage:",
                f'{best["boundary_coverage_percent"]:.2f}%'
            )
        else:
            print("No usable scene groups found.")

        time.sleep(0.15)

pd.DataFrame(rows).to_csv(
    CSV_OUT, index=False, encoding="utf-8"
)

with JSON_OUT.open("w", encoding="utf-8") as f:
    json.dump(selected_groups, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print("SAME-DATE TILE COVERAGE SEARCH FINISHED")
print("=" * 60)
print("City-year searches:", total)
print("Date-group records:", len(rows))
print("Saved top groups:", len(selected_groups))
print("Coverage CSV:", CSV_OUT)
print("Tile-group JSON:", JSON_OUT)

if errors:
    print("\nSearch errors:", len(errors))
    for error in errors:
        print("-", error)

print(
    "\nResearch note: Full boundary coverage is a geometric "
    "test only. Cloud masking and pixel-level quality checks "
    "are still required."
)
