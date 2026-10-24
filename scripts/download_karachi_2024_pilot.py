from pathlib import Path
import json
import re

import geopandas as gpd
import rasterio
from rasterio.mask import mask

ROOT = Path(__file__).resolve().parents[1]

PLAN_FILE = (
    ROOT / "data" / "interim"
    / "karachi_multidate_composite_plan.json"
)
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUTPUT_DIR = (
    ROOT / "data" / "interim"
    / "pilot_karachi_2024_multidate"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ASSET_NAMES = ("red", "nir", "scl")
EXPECTED_DATES = {
    "2024-10-09",
    "2024-11-06",
    "2024-11-26",
}

for path in (PLAN_FILE, BOUNDARY_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

with PLAN_FILE.open("r", encoding="utf-8-sig") as f:
    plan = json.load(f)

def collect_scenes(obj):
    found = []

    if isinstance(obj, dict):
        if (
            obj.get("item_id")
            and isinstance(obj.get("assets"), dict)
        ):
            found.append(obj)

        for value in obj.values():
            found.extend(collect_scenes(value))

    elif isinstance(obj, list):
        for value in obj:
            found.extend(collect_scenes(value))

    return found

def get_date(scene):
    value = scene.get("acquisition_date") or scene.get("datetime")

    if value:
        return str(value)[:10]

    match = re.search(
        r"_(20\d{6})_",
        str(scene.get("item_id", ""))
    )

    if match:
        raw = match.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    return None

all_scenes = collect_scenes(plan)
selected = {}

for scene in all_scenes:
    date = get_date(scene)

    if date in EXPECTED_DATES:
        selected[str(scene["item_id"])] = (date, scene)

scenes = list(selected.values())

if len(scenes) != 3:
    raise RuntimeError(
        f"Expected 3 unique Karachi 2024 scenes; found {len(scenes)}. "
        "Check the plan before downloading."
    )

found_dates = {date for date, scene in scenes}

if found_dates != EXPECTED_DATES:
    raise RuntimeError(
        f"Unexpected acquisition dates: {sorted(found_dates)}"
    )

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Administrative boundaries have no CRS.")

boundary = boundaries[
    boundaries["shapeName"] == "Karachi"
].copy()

if boundary.empty:
    raise ValueError("Karachi boundary not found.")

print("=" * 65)
print("KARACHI SENTINEL-2 PILOT DOWNLOAD")
print("=" * 65)
print("Scenes selected:", len(scenes))
print("Expected assets:", len(scenes) * len(ASSET_NAMES))
print("Output folder:", OUTPUT_DIR)

saved = 0
reused = 0
errors = []
manifest = []

for date, scene in sorted(scenes, key=lambda pair: pair[0]):
    item_id = str(scene["item_id"])
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
    assets = scene["assets"]

    print(f"\nScene: {item_id}")
    print("Acquisition date:", date)

    for asset_name in ASSET_NAMES:
        url = assets.get(asset_name)

        if not url or not str(url).startswith("https://"):
            errors.append(f"{item_id}: missing valid {asset_name} URL")
            print(f"  MISSING URL: {asset_name}")
            continue

        output_path = OUTPUT_DIR / f"{safe_id}_{asset_name}.tif"

        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                with rasterio.open(output_path) as existing:
                    if existing.count == 1 and existing.crs is not None:
                        print(f"  Reusing: {output_path.name}")
                        reused += 1
                        manifest.append({
                            "item_id": item_id,
                            "acquisition_date": date,
                            "asset": asset_name,
                            "file": output_path.name,
                            "source_url": url,
                            "source_crs": str(existing.crs),
                            "width": existing.width,
                            "height": existing.height,
                            "resolution": list(existing.res),
                        })
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
                        raise ValueError("No usable boundary geometry.")

                    nodata = src.nodata if src.nodata is not None else 0

                    image, transform = mask(
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
                        transform=transform,
                        nodata=nodata,
                        compress="deflate",
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
                    print("  CRS:", src.crs)
                    print("  File:", output_path.name)

                    manifest.append({
                        "item_id": item_id,
                        "acquisition_date": date,
                        "asset": asset_name,
                        "file": output_path.name,
                        "source_url": url,
                        "source_crs": str(src.crs),
                        "width": image.shape[2],
                        "height": image.shape[1],
                        "resolution": list(src.res),
                    })

        except Exception as exc:
            errors.append(
                f"{item_id} | {asset_name}: "
                f"{type(exc).__name__}: {exc}"
            )
            print(f"  ERROR: {exc}")

manifest_path = OUTPUT_DIR / "download_manifest.json"

with manifest_path.open("w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

expected = len(scenes) * len(ASSET_NAMES)

print("\n" + "=" * 65)
print("KARACHI PILOT DOWNLOAD FINISHED")
print("=" * 65)
print("Selected scenes:", len(scenes))
print("Expected assets:", expected)
print("Newly saved assets:", saved)
print("Existing assets reused:", reused)
print("Errors:", len(errors))
print("Manifest:", manifest_path)

for error in errors:
    print("-", error)

if not errors and saved + reused == expected:
    print("\nSUCCESS: All nine raster assets are available.")
else:
    print("\nINCOMPLETE: Review errors before proceeding.")

print(
    "\nResearch note: The three acquisition dates remain separate. "
    "A common-grid reprojection, pixel-level SCL masking, "
    "and a documented compositing method are required before "
    "producing a Karachi NDVI composite."
)
