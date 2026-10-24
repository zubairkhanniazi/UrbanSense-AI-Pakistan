from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
import json
import time

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE = OUTPUT_DIR / "sentinel2_scene_search_results.csv"
JSON_FILE = OUTPUT_DIR / "sentinel2_scene_search_results.json"

STAC_API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"

START_YEAR = 2020
END_YEAR = 2025
MAX_CLOUD_PERCENT = 30
MAX_SCENES_PER_CITY_YEAR = 5

# Retrieve a larger, cloud-cover-sorted result page.
SEARCH_LIMIT = 100

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(
        f"Study boundaries not found: {BOUNDARY_FILE}"
    )

areas = gpd.read_file(BOUNDARY_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

if areas.crs.to_epsg() != 4326:
    areas = areas.to_crs("EPSG:4326")

areas = areas.sort_values("shapeName")

def post_search(payload):
    request = Request(
        STAC_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/geo+json, application/json",
            "User-Agent": "UrbanSense-AI-Pakistan/0.1",
        },
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))

records = []
errors = []
total = len(areas) * (END_YEAR - START_YEAR + 1)
counter = 0

print("Corrected Sentinel-2 metadata search")
print("Sorting: cloud cover ascending, then acquisition date")
print("Results per city/year requested:", SEARCH_LIMIT)

for _, area in areas.iterrows():
    city = area["shapeName"]
    geometry = area.geometry.__geo_interface__

    for year in range(START_YEAR, END_YEAR + 1):
        counter += 1
        print(f"\n[{counter}/{total}] {city} | {year}")

        payload = {
            "collections": [COLLECTION],
            "intersects": geometry,
            "datetime": (
                f"{year}-01-01T00:00:00Z/"
                f"{year}-12-31T23:59:59Z"
            ),
            "limit": SEARCH_LIMIT,
            "query": {
                "eo:cloud_cover": {
                    "lte": MAX_CLOUD_PERCENT
                }
            },
            "sortby": [
                {
                    "field": "properties.eo:cloud_cover",
                    "direction": "asc",
                },
                {
                    "field": "properties.datetime",
                    "direction": "desc",
                },
            ],
        }

        try:
            result = post_search(payload)
        except (HTTPError, URLError, TimeoutError, OSError,
                json.JSONDecodeError) as exc:
            message = f"{city} {year}: {exc}"
            errors.append(message)
            print("SEARCH ERROR:", exc)
            continue

        candidates = []

        for feature in result.get("features", []):
            props = feature.get("properties") or {}
            cloud = props.get("eo:cloud_cover")

            if cloud is None:
                continue

            cloud = float(cloud)

            if not 0 <= cloud <= MAX_CLOUD_PERCENT:
                continue

            acquired = props.get(
                "datetime",
                props.get("start_datetime", ""),
            )

            links = feature.get("links") or []
            item_url = next(
                (
                    urljoin(STAC_API, link["href"])
                    for link in links
                    if link.get("rel") in ("self", "canonical")
                    and link.get("href")
                ),
                "",
            )

            tile_parts = [
                props.get("mgrs:utm_zone"),
                props.get("mgrs:latitude_band"),
                props.get("mgrs:grid_square"),
            ]
            tile = "".join(
                str(value) for value in tile_parts
                if value not in (None, "")
            )

            assets = {
                name: asset.get("href")
                for name, asset in (
                    feature.get("assets") or {}
                ).items()
                if asset.get("href")
            }

            candidates.append({
                "study_area": city,
                "year": year,
                "item_id": feature.get("id", ""),
                "datetime_utc": acquired,
                "cloud_cover_percent": cloud,
                "platform": props.get("platform", ""),
                "mgrs_tile": tile,
                "item_url": item_url,
                "assets": assets,
            })

        # Rank returned scenes locally as an additional check.
        candidates.sort(
            key=lambda item: (
                item["cloud_cover_percent"],
                item["datetime_utc"],
            ),
        )

        selected = candidates[:MAX_SCENES_PER_CITY_YEAR]
        records.extend(selected)

        print(
            f"Returned: {len(result.get('features', []))}; "
            f"retained: {len(selected)}"
        )

        time.sleep(0.2)

columns = [
    "study_area",
    "year",
    "item_id",
    "datetime_utc",
    "cloud_cover_percent",
    "platform",
    "mgrs_tile",
    "item_url",
    "assets",
]

pd.DataFrame(
    [
        {
            **record,
            "assets": json.dumps(record["assets"]),
        }
        for record in records
    ],
    columns=columns,
).to_csv(CSV_FILE, index=False, encoding="utf-8")

with JSON_FILE.open("w", encoding="utf-8") as file:
    json.dump(records, file, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print("CORRECTED SEARCH FINISHED")
print("=" * 60)
print("Selected candidate scenes:", len(records))

if errors:
    print("\nSearch errors:", len(errors))
    for error in errors:
        print("-", error)

if records:
    df = pd.DataFrame(records)
    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], errors="coerce", utc=True
    )
    df["month"] = df["datetime_utc"].dt.month

    print("\nCandidate counts by city and year:")
    print(
        df.groupby(["study_area", "year"])
        .size()
        .unstack(fill_value=0)
        .to_string()
    )

    print("\nAcquisition-month distribution:")
    print(df["month"].value_counts().sort_index().to_string())

    print("\nMean cloud cover by city:")
    print(
        df.groupby("study_area")["cloud_cover_percent"]
        .mean().round(2).to_string()
    )

print("\nCSV:", CSV_FILE)
print("JSON:", JSON_FILE)
print(
    "\nNote: Sorting applies to catalog results, not necessarily "
    "every item in the complete archive. Full scene coverage "
    "and seasonal consistency still require validation."
)
