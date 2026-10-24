from pathlib import Path
import json
import re

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]

MANIFEST = (
    ROOT / "data" / "interim"
    / "sentinel2_autumn_scene_manifest.json"
)
BOUNDARIES = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = (
    ROOT / "data" / "interim"
    / "pilot_islamabad_2024"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CITY = "Islamabad Capital Territory"
TARGET_DATE = "2024-10-16"
REQUIRED_ASSETS = ("red", "nir", "scl")

if not MANIFEST.exists():
    raise FileNotFoundError(f"Missing scene manifest: {MANIFEST}")

if not BOUNDARIES.exists():
    raise FileNotFoundError(f"Missing boundaries: {BOUNDARIES}")

with MANIFEST.open("r", encoding="utf-8") as f:
    records = json.load(f)

# Select the two or more satellite tiles for the chosen date.
matches = [
    record for record in records
    if record.get("study_area") == CITY
    and int(record.get("year", 0)) == 2024
    and record.get("acquisition_date") == TARGET_DATE
]

# Remove duplicate records for the same satellite item.
unique = {record["item_id"]: record for record in matches}
matches = sorted(unique.values(), key=lambda record: record["item_id"])

if not matches:
    raise RuntimeError(
        f"No manifest records found for {CITY} on {TARGET_DATE}. "
        "Check the inventory before continuing."
    )

boundary_data = gpd.read_file(BOUNDARIES)

if boundary_data.crs is None:
    raise ValueError("Study-area boundaries have no CRS.")

boundary_data = boundary_data[
    boundary_data["shapeName"] == CITY
].copy()

if boundary_data.empty:
    raise ValueError(f"Boundary not found for {CITY}.")

print("=" * 65)
print("ISLAMABAD SENTINEL-2 PILOT")
print("=" * 65)
print("Acquisition date:", TARGET_DATE)
print("Satellite tiles found:", len(matches))
print("Assets per tile:", ", ".join(REQUIRED_ASSETS))
print("Using cropped raster reads; full tiles are not downloaded.")

results = []
errors = []

for record in matches:
    item_id = record["item_id"]
    assets = record.get("assets") or {}

    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)

    print(f"\nProcessing tile: {item_id}")

    for asset_name in REQUIRED_ASSETS:
        asset_url = assets.get(asset_name)

        if not asset_url:
            errors.append(f"{item_id}: missing {asset_name} asset")
            print(f"  MISSING ASSET: {asset_name}")
            continue

        output_path = (
            OUTPUT_DIR / f"{safe_id}_{asset_name}.tif"
        )

        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"  Already exists: {output_path.name}")
            continue

        try:
            # Remote COG reads normally retrieve only the needed
            # image windows when the server supports byte ranges.
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_RETRY_DELAY="2",
            ):
                with rasterio.open(asset_url) as src:
                    if src.crs is None:
                        raise ValueError(
                            "Source raster has no CRS."
                        )

                    projected_boundary = boundary_data.to_crs(
                        src.crs
                    )

                    geometries = [
                        mapping(geometry)
                        for geometry in projected_boundary.geometry
                        if geometry is not None
                        and not geometry.is_empty
                    ]

                    if not geometries:
                        raise ValueError(
                            "No usable study-area geometry."
                        )

                    nodata_value = (
                        src.nodata if src.nodata is not None else 0
                    )

                    image, out_transform = mask(
                        src,
                        geometries,
                        crop=True,
                        filled=True,
                        nodata=nodata_value,
                    )

                    profile = src.profile.copy()
                    profile.update(
                        driver="GTiff",
                        height=image.shape[1],
                        width=image.shape[2],
                        transform=out_transform,
                        compress="deflate",
                        nodata=nodata_value,
                        tiled=False,
                    )

                    profile.pop("blockxsize", None)
                    profile.pop("blockysize", None)

                    with rasterio.open(
                        output_path, "w", **profile
                    ) as dst:
                        dst.write(image)

                    result = {
                        "item_id": item_id,
                        "asset": asset_name,
                        "date": TARGET_DATE,
                        "crs": str(src.crs),
                        "width": image.shape[2],
                        "height": image.shape[1],
                        "bands": image.shape[0],
                        "pixel_size": str(src.res),
                        "output_file": str(output_path),
                        "file_size_mb": round(
                            output_path.stat().st_size / 1_000_000,
                            3,
                        ),
                    }

                    results.append(result)

                    print(
                        f"  SAVED {asset_name}: "
                        f"{image.shape[2]} x {image.shape[1]} pixels"
                    )
                    print(f"  CRS: {src.crs}")
                    print(f"  File: {output_path.name}")

        except Exception as exc:
            errors.append(
                f"{item_id} | {asset_name}: {type(exc).__name__}: {exc}"
            )
            print(f"  ERROR downloading {asset_name}: {exc}")

summary_path = OUTPUT_DIR / "pilot_download_summary.csv"

if results:
    pd.DataFrame(results).to_csv(
        summary_path,
        index=False,
        encoding="utf-8",
    )

print("\n" + "=" * 65)
print("PILOT DOWNLOAD FINISHED")
print("=" * 65)
print("Tiles selected:", len(matches))
print("Raster assets saved:", len(results))
print("Expected raster assets:", len(matches) * len(REQUIRED_ASSETS))
print("Summary CSV:", summary_path)

if errors:
    print("\nErrors:", len(errors))
    for error in errors:
        print("-", error)

if len(results) == len(matches) * len(REQUIRED_ASSETS):
    print("\nSUCCESS: All pilot raster assets were saved.")
else:
    print("\nWARNING: The pilot is incomplete; review errors above.")

print(
    "\nNote: These are clipped source rasters. "
    "We still need to mosaic tiles, validate SCL cloud classes, "
    "and align bands before calculating NDVI."
)
