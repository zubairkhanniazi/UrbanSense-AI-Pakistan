from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
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

JSON_OUT = OUTPUT_DIR / "sentinel2_autumn_scene_manifest.json"
CSV_OUT = OUTPUT_DIR / "sentinel2_autumn_scene_manifest.csv"

API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"

YEARS = range(2020, 2026)
MAX_CLOUD = 30
PAGE_LIMIT = 100
MAX_PAGES = 30

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(f"Missing boundaries: {BOUNDARY_FILE}")

areas = gpd.read_file(BOUNDARY_FILE)

if areas.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

if areas.crs.to_epsg() != 4326:
    areas = areas.to_crs("EPSG:4326")

areas = areas.sort_values("shapeName")


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

        except (
            HTTPError, URLError, TimeoutError, OSError,
            json.JSONDecodeError
        ) as exc:
            last_error = exc
            print(f"  Attempt {attempt}/{attempts} failed: {exc}")

            if attempt < attempts:
                time.sleep(attempt * 2)

    raise RuntimeError(f"Request failed after retries: {last_error}")


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


records = []
errors = []
search_count = len(areas) * len(YEARS)
counter = 0

print("SENTINEL-2 AUTUMN IMAGERY INVENTORY")
print("Period: October-November, 2020-2025")
print("Maximum scene-level cloud cover:", MAX_CLOUD, "%")
print("Searching metadata only; no imagery downloads.")

for _, area in areas.iterrows():
    city = area["shapeName"]
    geometry = area.geometry.__geo_interface__

    for year in YEARS:
        counter += 1
        print(f"\n[{counter}/{search_count}] {city} | {year}")

        payload = {
            "collections": [COLLECTION],
            "intersects": geometry,
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
            errors.append(f"{city} {year}: {exc}")
            print("SEARCH FAILED:", exc)
            continue

        added = 0

        for feature in features:
            props = feature.get("properties") or {}
            cloud = props.get("eo:cloud_cover")
            acquired = props.get("datetime")
            item_id = feature.get("id")

            if not item_id or not acquired or cloud is None:
                continue

            cloud = float(cloud)

            if not 0 <= cloud <= MAX_CLOUD:
                continue

            if not acquired.startswith(str(year)):
                continue

            month = int(acquired[5:7])
            if month not in (10, 11):
                continue

            assets = {
                name: asset.get("href")
                for name, asset in (
                    feature.get("assets") or {}
                ).items()
                if asset.get("href")
            }

            tile_parts = [
                props.get("mgrs:utm_zone"),
                props.get("mgrs:latitude_band"),
                props.get("mgrs:grid_square"),
            ]
            tile = "".join(
                str(part) for part in tile_parts
                if part not in (None, "")
            )

            item_links = feature.get("links") or []
            item_url = next(
                (
                    link["href"]
                    for link in item_links
                    if link.get("rel") in ("self", "canonical")
                    and link.get("href")
                ),
                "",
            )

            records.append({
                "study_area": city,
                "year": year,
                "acquisition_date": acquired[:10],
                "datetime_utc": acquired,
                "month": month,
                "item_id": item_id,
                "cloud_cover_percent": cloud,
                "platform": props.get("platform", ""),
                "mgrs_tile": tile,
                "item_url": item_url,
                "asset_names": sorted(assets.keys()),
                "assets": assets,
                "geometry": feature.get("geometry"),
            })

            added += 1

        print(
            f"Catalog items retrieved: {len(features)} | "
            f"Valid autumn records added: {added} | "
            f"Pages: {pages}"
        )

        time.sleep(0.3)

# Deduplicate records by city and satellite item.
unique = {}
for record in records:
    unique[(record["study_area"], record["item_id"])] = record

records = list(unique.values())

with JSON_OUT.open("w", encoding="utf-8") as file:
    json.dump(records, file, indent=2, ensure_ascii=False)

csv_records = []
for record in records:
    csv_records.append({
        key: value
        for key, value in record.items()
        if key not in ("assets", "geometry", "asset_names")
    } | {
        "asset_names": ", ".join(record["asset_names"]),
        "red_asset_available": bool(record["assets"].get("red")),
        "nir_asset_available": bool(record["assets"].get("nir")),
        "scl_asset_available": bool(record["assets"].get("scl")),
    })

pd.DataFrame(csv_records).to_csv(
    CSV_OUT, index=False, encoding="utf-8"
)

print("\n" + "=" * 65)
print("AUTUMN INVENTORY FINISHED")
print("=" * 65)
print("Unique city-scene records:", len(records))

if records:
    df = pd.DataFrame(csv_records)

    print("\nRecords by city and year:")
    print(
        df.groupby(["study_area", "year"])
        .size()
        .unstack(fill_value=0)
        .to_string()
    )

    print("\nRequired asset availability:")
    for asset in (
        "red_asset_available",
        "nir_asset_available",
        "scl_asset_available",
    ):
        print(f"{asset}: {int(df[asset].sum())}/{len(df)}")

print("\nJSON manifest:", JSON_OUT)
print("CSV manifest:", CSV_OUT)

if errors:
    print("\nSearch errors:", len(errors))
    for error in errors:
        print("-", error)

print(
    "\nNote: Scene metadata cloud cover is not pixel-level "
    "cloud validation. Asset URLs may require network access "
    "when we process the imagery."
)
