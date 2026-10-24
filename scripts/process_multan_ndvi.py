from pathlib import Path
import json

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling
from rasterio.transform import array_bounds

ROOT = Path(__file__).resolve().parents[1]

PLAN_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_master_acquisition_plan.json"
)
PILOT_DIR = ROOT / "data" / "interim" / "pilot_multan_2024"
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

FIGURES = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"

for directory in (FIGURES, TABLES):
    directory.mkdir(parents=True, exist_ok=True)

CITY = "Multan"
YEAR = 2024
VALID_SCL_CLASSES = [4, 5, 6]
NODATA_NDVI = -9999.0

for path in (PLAN_FILE, BOUNDARY_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

with PLAN_FILE.open("r", encoding="utf-8") as f:
    plan = json.load(f)

groups = [
    group for group in plan
    if group.get("study_area") == CITY
    and int(group.get("year", 0)) == YEAR
]

if len(groups) != 1:
    raise RuntimeError(
        f"Expected one Multan {YEAR} acquisition group; found {len(groups)}."
    )

group = groups[0]
scenes = group.get("scenes", [])

dates = {scene.get("acquisition_date") for scene in scenes}

if len(dates) != 1 or not next(iter(dates)):
    raise RuntimeError(
        f"Expected one acquisition date for all tiles; found {dates}"
    )

date = next(iter(dates))
date_tag = date.replace("-", "_")

output_dir = ROOT / "data" / "processed" / f"multan_{date_tag}"
output_dir.mkdir(parents=True, exist_ok=True)

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Administrative boundary file has no CRS.")

boundary = boundaries[boundaries["shapeName"] == CITY].copy()

if boundary.empty:
    raise ValueError("Multan administrative boundary not found.")

print("=" * 65)
print("MULTAN SENTINEL-2 NDVI PROCESSING")
print("=" * 65)
print("Acquisition date:", date)
print("Selected tiles:", len(scenes))
print("Output folder:", output_dir)

def create_mosaic(pattern, output_path):
    files = sorted(PILOT_DIR.glob(pattern))

    if len(files) != len(scenes):
        raise RuntimeError(
            f"{pattern}: expected {len(scenes)} files, "
            f"found {len(files)}."
        )

    datasets = []

    try:
        for path in files:
            datasets.append(rasterio.open(path))

        first = datasets[0]

        for ds in datasets:
            if ds.crs != first.crs:
                raise ValueError(f"CRS mismatch in {ds.name}")

            if not np.allclose(ds.res, first.res):
                raise ValueError(f"Pixel resolution mismatch in {ds.name}")

        mosaic, transform = merge(
            datasets,
            nodata=0,
            method="first",
        )

        profile = first.profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            nodata=0,
            compress="deflate",
            tiled=False,
        )
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mosaic)

        print(f"\nCreated mosaic: {output_path.name}")
        print("  Input tiles:", len(files))
        print("  Dimensions:", mosaic.shape[2], "x", mosaic.shape[1])
        print("  CRS:", first.crs)
        print("  Resolution:", first.res)

        return mosaic[0], transform, first.crs, profile

    finally:
        for ds in datasets:
            ds.close()

red_path = output_dir / "red_mosaic_10m.tif"
nir_path = output_dir / "nir_mosaic_10m.tif"
scl_path = output_dir / "scl_mosaic_20m.tif"
aligned_scl_path = output_dir / "scl_aligned_10m.tif"
ndvi_path = output_dir / f"ndvi_{date}.tif"
mask_path = output_dir / "ndvi_valid_mask.tif"

red, red_transform, red_crs, red_profile = create_mosaic(
    "*_red.tif", red_path
)
nir, nir_transform, nir_crs, _ = create_mosaic(
    "*_nir.tif", nir_path
)
scl, scl_transform, scl_crs, _ = create_mosaic(
    "*_scl.tif", scl_path
)

if nir_crs != red_crs:
    raise ValueError("Red and NIR coordinate systems do not match.")

if nir.shape != red.shape or nir_transform != red_transform:
    aligned_nir = np.zeros(red.shape, dtype=np.float32)

    reproject(
        source=nir,
        destination=aligned_nir,
        src_transform=nir_transform,
        src_crs=nir_crs,
        src_nodata=0,
        dst_transform=red_transform,
        dst_crs=red_crs,
        dst_nodata=0,
        resampling=Resampling.bilinear,
    )

    nir = aligned_nir

aligned_scl = np.zeros(red.shape, dtype=np.uint8)

reproject(
    source=scl.astype(np.uint8),
    destination=aligned_scl,
    src_transform=scl_transform,
    src_crs=scl_crs,
    src_nodata=0,
    dst_transform=red_transform,
    dst_crs=red_crs,
    dst_nodata=0,
    resampling=Resampling.nearest,
)

scl_profile = red_profile.copy()
scl_profile.update(
    driver="GTiff",
    dtype="uint8",
    count=1,
    nodata=0,
    height=aligned_scl.shape[0],
    width=aligned_scl.shape[1],
    transform=red_transform,
    compress="deflate",
    tiled=False,
)
scl_profile.pop("blockxsize", None)
scl_profile.pop("blockysize", None)

with rasterio.open(aligned_scl_path, "w", **scl_profile) as dst:
    dst.write(aligned_scl, 1)

red_float = red.astype(np.float32)
nir_float = nir.astype(np.float32)
denominator = red_float + nir_float

valid = (
    (red > 0)
    & (nir > 0)
    & (denominator > 0)
    & np.isin(aligned_scl, VALID_SCL_CLASSES)
)

ndvi = np.full(red.shape, NODATA_NDVI, dtype=np.float32)

ndvi[valid] = (
    (nir_float[valid] - red_float[valid])
    / denominator[valid]
)

ndvi_profile = red_profile.copy()
ndvi_profile.update(
    driver="GTiff",
    dtype="float32",
    count=1,
    nodata=NODATA_NDVI,
    height=ndvi.shape[0],
    width=ndvi.shape[1],
    transform=red_transform,
    compress="deflate",
    tiled=False,
)
ndvi_profile.pop("blockxsize", None)
ndvi_profile.pop("blockysize", None)

with rasterio.open(ndvi_path, "w", **ndvi_profile) as dst:
    dst.write(ndvi, 1)

mask_profile = ndvi_profile.copy()
mask_profile.update(dtype="uint8", nodata=0)

with rasterio.open(mask_path, "w", **mask_profile) as dst:
    dst.write(valid.astype(np.uint8), 1)

classified = aligned_scl > 0
classified_count = int(classified.sum())
valid_count = int(valid.sum())

if valid_count == 0:
    raise RuntimeError("No valid NDVI pixels were produced.")

values = ndvi[valid]
pixel_area = abs(red_transform.a * red_transform.e)

summary = pd.DataFrame([{
    "study_area": CITY,
    "acquisition_date": date,
    "crs": str(red_crs),
    "pixel_area_m2": pixel_area,
    "classified_scl_pixels": classified_count,
    "valid_ndvi_pixels": valid_count,
    "valid_ndvi_percent_of_classified": (
        100 * valid_count / classified_count
        if classified_count else np.nan
    ),
    "scl_vegetation_percent_of_valid_ndvi": (
        100 * np.count_nonzero(valid & (aligned_scl == 4))
        / valid_count
    ),
    "mean_ndvi": float(values.mean()),
    "median_ndvi": float(np.median(values)),
    "minimum_ndvi": float(values.min()),
    "maximum_ndvi": float(values.max()),
}])

summary_path = TABLES / f"multan_ndvi_{date}.csv"
summary.to_csv(summary_path, index=False, encoding="utf-8")

boundary_projected = boundary.to_crs(red_crs)

height, width = ndvi.shape
west, south, east, north = array_bounds(
    height, width, red_transform
)

plot_data = np.ma.masked_where(
    ndvi == NODATA_NDVI,
    ndvi,
)

fig, ax = plt.subplots(figsize=(10, 9))

image = ax.imshow(
    plot_data,
    extent=(west, east, south, north),
    origin="upper",
    cmap="RdYlGn",
    vmin=-1,
    vmax=1,
)

boundary_projected.boundary.plot(
    ax=ax,
    color="black",
    linewidth=0.7,
)

colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
colorbar.set_label("NDVI")

ax.set_title(f"Multan NDVI — {date}\nSentinel-2 L2A pilot")
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_aspect("equal")
fig.tight_layout()

map_path = FIGURES / f"multan_ndvi_{date}.png"
fig.savefig(map_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nMULTAN NDVI SUMMARY")
print(summary.to_string(index=False))

print("\nOUTPUTS CREATED")
print("Red mosaic:", red_path)
print("NIR mosaic:", nir_path)
print("SCL mosaic:", scl_path)
print("Aligned SCL:", aligned_scl_path)
print("NDVI raster:", ndvi_path)
print("Valid mask:", mask_path)
print("NDVI map:", map_path)
print("Summary CSV:", summary_path)

print(
    "\nResearch caution: This is a preliminary pilot. "
    "NDVI statistics do not establish full-boundary coverage, "
    "independent cloud-free pixel quality or scientific validity. "
    "The reflectance scaling and SCL class distribution must "
    "be checked before final research conclusions."
)
