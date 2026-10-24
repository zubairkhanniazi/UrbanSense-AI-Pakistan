from pathlib import Path
import json
import re

import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

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
    / "pilot_lahore_2024"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CITY = "Lahore"
YEAR = 2024
ASSETS = ("red", "nir", "scl")

if not PLAN_FILE.exists():
    raise FileNotFoundError(f"Missing master plan: {PLAN_FILE}")

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(f"Missing boundaries: {BOUNDARY_FILE}")

with PLAN_FILE.open("r", encoding="utf-8") as f:
    plan = json.load(f)

groups = [
    group for group in plan
    if group.get("study_area") == CITY
    and int(group.get("year", 0)) == YEAR
]

if len(groups) != 1:
    raise RuntimeError(
        f"Expected exactly one Lahore {YEAR} group; found {len(groups)}."
    )

group = groups[0]

if group.get("strategy") != "single_date_tiles":
    raise RuntimeError(
        "This pilot expects a same-date tile group. "
        "The selected strategy requires review."
    )

if not str(group.get("status", "")).startswith("PLANNED"):
    raise RuntimeError(
        f"Selection group is not ready for testing: {group.get('status')}"
    )

scenes = group.get("scenes", [])

if not scenes:
    raise RuntimeError("No scenes are present in the selected group.")

dates = {
    scene.get("acquisition_date")
    for scene in scenes
}

if len(dates) != 1 or not next(iter(dates)):
    raise RuntimeError(
        f"Expected one acquisition date, found: {sorted(str(d) for d in dates)}"
    )

date = next(iter(dates))

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

boundary = boundaries[
    boundaries["shapeName"] == CITY
].copy()

if boundary.empty:
    raise ValueError(f"Boundary not found for {CITY}.")

print("=" * 65)
print("LAHORE SENTINEL-2 PILOT DOWNLOAD")
print("=" * 65)
print("City:", CITY)
print("Year:", YEAR)
print("Acquisition date:", date)
print("Selected tiles:", len(scenes))
print("Assets per tile:", ", ".join(ASSETS))
print("Existing valid files will be reused.")

saved = 0
skipped = 0
errors = []

for scene in scenes:
    item_id = scene.get("item_id", "")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
    asset_urls = scene.get("assets") or {}

    if not item_id:
        errors.append("A scene has no item ID.")
        continue

    print(f"\nProcessing tile: {item_id}")

    for asset_name in ASSETS:
        url = asset_urls.get(asset_name)

        if not url:
            errors.append(f"{item_id}: missing {asset_name} URL")
            print(f"  MISSING URL: {asset_name}")
            continue

        output_path = OUTPUT_DIR / f"{safe_id}_{asset_name}.tif"

        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                with rasterio.open(output_path) as existing:
                    if existing.count == 1 and existing.crs is not None:
                        print(f"  Already saved: {output_path.name}")
                        skipped += 1
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

                    projected_boundary = boundary.to_crs(src.crs)
                    geometries = [
                        mapping(geom)
                        for geom in projected_boundary.geometry
                        if geom is not None and not geom.is_empty
                    ]

                    if not geometries:
                        raise ValueError("No usable boundary geometry.")

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
                f"{item_id} | {asset_name}: {type(exc).__name__}: {exc}"
            )
            print(f"  ERROR: {exc}")

expected = len(scenes) * len(ASSETS)

print("\n" + "=" * 65)
print("LAHORE PILOT FINISHED")
print("=" * 65)
print("Selected tiles:", len(scenes))
print("Expected raster files:", expected)
print("Newly saved raster files:", saved)
print("Existing files reused:", skipped)
print("Output folder:", OUTPUT_DIR)

if errors:
    print("\nErrors:", len(errors))
    for error in errors:
        print("-", error)

print(
    "\nNote: These are cropped source rasters. "
    "They still require mosaicking, pixel-level quality checks "
    "and consistent alignment before NDVI analysis."
)
