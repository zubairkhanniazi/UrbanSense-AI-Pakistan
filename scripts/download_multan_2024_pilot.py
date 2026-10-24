from pathlib import Path
import json
import re

import geopandas as gpd
import rasterio
from rasterio.mask import mask

ROOT = Path(__file__).resolve().parents[1]

PLAN_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_master_acquisition_plan.json"
)
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = (
    ROOT / "data" / "interim"
    / "pilot_multan_2024"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CITY = "Multan"
YEAR = 2024
ASSETS = ("red", "nir", "scl")

for path in (PLAN_FILE, BOUNDARY_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

with PLAN_FILE.open("r", encoding="utf-8") as f:
    plan = json.load(f)

groups = [
    g for g in plan
    if g.get("study_area") == CITY
    and int(g.get("year", 0)) == YEAR
]

if len(groups) != 1:
    raise RuntimeError(
        f"Expected one Multan {YEAR} group; found {len(groups)}."
    )

group = groups[0]

if group.get("strategy") != "single_date_tiles":
    raise RuntimeError(
        f"Unexpected acquisition strategy: {group.get('strategy')}"
    )

if not str(group.get("status", "")).startswith("PLANNED"):
    raise RuntimeError(
        f"Selection requires review: {group.get('status')}"
    )

scenes = group.get("scenes", [])

if not scenes:
    raise RuntimeError("No scenes found in the master plan.")

dates = {
    scene.get("acquisition_date")
    for scene in scenes
}

if len(dates) != 1 or not next(iter(dates)):
    raise RuntimeError(
        f"Expected one common acquisition date; found {dates}"
    )

acquisition_date = next(iter(dates))

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

boundary = boundaries[
    boundaries["shapeName"] == CITY
].copy()

if boundary.empty:
    raise ValueError("Multan administrative boundary not found.")

print("=" * 65)
print("MULTAN SENTINEL-2 PILOT DOWNLOAD")
print("=" * 65)
print("City:", CITY)
print("Year:", YEAR)
print("Acquisition date:", acquisition_date)
print("Selected tiles:", len(scenes))
print("Assets per tile:", ", ".join(ASSETS))
print("Output folder:", OUTPUT_DIR)

saved = 0
reused = 0
errors = []

for scene in scenes:
    item_id = scene.get("item_id", "")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
    assets = scene.get("assets") or {}

    if not item_id:
        errors.append("Scene has no item ID.")
        continue

    print(f"\nProcessing tile: {item_id}")

    for asset_name in ASSETS:
        url = assets.get(asset_name)

        if not url:
            errors.append(f"{item_id}: missing {asset_name} URL.")
            print(f"  MISSING URL: {asset_name}")
            continue

        output_path = OUTPUT_DIR / f"{safe_id}_{asset_name}.tif"

        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                with rasterio.open(output_path) as existing:
                    if existing.count == 1 and existing.crs is not None:
                        print(f"  Reusing: {output_path.name}")
                        reused += 1
                        continue
            except Exception:
                pass

        try:
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_RETRY_DELAY="2",
            ):
                with rasterio.open(url) as src:
                    if src.crs is None:
                        raise ValueError("Source raster has no CRS.")

                    projected = boundary.to_crs(src.crs)
                    geometries = [
                        geom.__geo_interface__
                        for geom in projected.geometry
                        if geom is not None and not geom.is_empty
                    ]

                    if not geometries:
                        raise ValueError("No valid boundary geometry.")

                    nodata = src.nodata if src.nodata is not None else 0

                    image, out_transform = mask(
                        src,
                        geometries,
                        crop=True,
                        filled=True,
                        nodata=nodata,
                    )

                    profile = src.profile.copy()
                    profile.update(
                        driver="GTiff",
                        height=image.shape[1],
                        width=image.shape[2],
                        transform=out_transform,
                        compress="deflate",
                        nodata=nodata,
                        tiled=False,
                    )
                    profile.pop("blockxsize", None)
                    profile.pop("blockysize", None)

                    with rasterio.open(output_path, "w", **profile) as dst:
                        dst.write(image)

                    saved += 1
                    print(
                        f"  SAVED {asset_name}: "
                        f"{image.shape[2]} x {image.shape[1]} pixels"
                    )
                    print(f"  CRS: {src.crs}")
                    print(f"  File: {output_path.name}")

        except Exception as exc:
            errors.append(
                f"{item_id} | {asset_name}: "
                f"{type(exc).__name__}: {exc}"
            )
            print(f"  ERROR: {exc}")

expected = len(scenes) * len(ASSETS)

print("\n" + "=" * 65)
print("MULTAN PILOT DOWNLOAD FINISHED")
print("=" * 65)
print("Selected tiles:", len(scenes))
print("Expected raster assets:", expected)
print("Newly saved assets:", saved)
print("Existing assets reused:", reused)
print("Output folder:", OUTPUT_DIR)
print("Errors:", len(errors))

for error in errors:
    print("-", error)

if not errors and saved + reused == expected:
    print("\nSUCCESS: All expected raster assets are available.")
else:
    print("\nINCOMPLETE: Review errors before continuing.")

print(
    "\nThese are clipped source rasters. They still require "
    "mosaicking, SCL quality checks and grid alignment before "
    "calculating NDVI."
)
