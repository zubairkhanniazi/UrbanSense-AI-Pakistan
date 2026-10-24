from pathlib import Path

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

PILOT = ROOT / "data" / "interim" / "pilot_lahore_2024"
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)
OUT = ROOT / "data" / "processed" / "lahore_2024_10_13"
FIGURES = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"

for folder in (OUT, FIGURES, TABLES):
    folder.mkdir(parents=True, exist_ok=True)

CITY = "Lahore"
DATE = "2024-10-13"
NODATA_NDVI = -9999.0

VALID_SCL_CLASSES = [4, 5, 6]
CLOUD_SHADOW_CLASSES = [3, 8, 9, 10, 11]

def create_mosaic(pattern, output_path):
    files = sorted(PILOT.glob(pattern))

    if len(files) != 3:
        raise RuntimeError(
            f"Expected 3 files matching {pattern}; found {len(files)}."
        )

    datasets = []

    try:
        for file in files:
            datasets.append(rasterio.open(file))

        first = datasets[0]

        for ds in datasets:
            if ds.crs != first.crs:
                raise ValueError(
                    f"CRS mismatch: {ds.name} has {ds.crs}, "
                    f"expected {first.crs}."
                )

            if not np.allclose(ds.res, first.res):
                raise ValueError(
                    f"Resolution mismatch in {ds.name}."
                )

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
            compress="deflate",
            nodata=0,
            tiled=False,
        )
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mosaic)

        print(f"\nMosaic created: {output_path.name}")
        print(f"  Input tiles: {len(files)}")
        print(f"  Dimensions: {mosaic.shape[2]} x {mosaic.shape[1]}")
        print(f"  CRS: {first.crs}")
        print(f"  Resolution: {first.res}")

        return mosaic[0], transform, first.crs, profile

    finally:
        for ds in datasets:
            ds.close()


print("=" * 65)
print("LAHORE SENTINEL-2 NDVI PROCESSING")
print("=" * 65)

if not PILOT.exists():
    raise FileNotFoundError(f"Pilot folder missing: {PILOT}")

red_path = OUT / "red_mosaic_10m.tif"
nir_path = OUT / "nir_mosaic_10m.tif"
scl_path = OUT / "scl_mosaic_20m.tif"
scl_aligned_path = OUT / "scl_aligned_10m.tif"
ndvi_path = OUT / "ndvi_2024_10_13.tif"
mask_path = OUT / "ndvi_valid_mask.tif"
figure_path = FIGURES / "lahore_ndvi_2024-10-13.png"
summary_path = TABLES / "lahore_ndvi_pilot_summary.csv"

# 1. Create the Red, NIR and SCL mosaics.
red, red_transform, red_crs, red_profile = create_mosaic(
    "*_red.tif", red_path
)
nir, nir_transform, nir_crs, nir_profile = create_mosaic(
    "*_nir.tif", nir_path
)
scl, scl_transform, scl_crs, scl_profile = create_mosaic(
    "*_scl.tif", scl_path
)

# 2. Ensure Red and NIR share the same grid.
if nir_crs != red_crs:
    raise ValueError("Red and NIR CRS differ.")

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

# 3. Align categorical SCL to the Red-band grid.
scl_aligned = np.zeros(red.shape, dtype=np.uint8)

reproject(
    source=scl.astype(np.uint8),
    destination=scl_aligned,
    src_transform=scl_transform,
    src_crs=scl_crs,
    src_nodata=0,
    dst_transform=red_transform,
    dst_crs=red_crs,
    dst_nodata=0,
    resampling=Resampling.nearest,
)

scl_profile_out = red_profile.copy()
scl_profile_out.update(
    dtype="uint8",
    count=1,
    nodata=0,
    height=scl_aligned.shape[0],
    width=scl_aligned.shape[1],
    transform=red_transform,
    compress="deflate",
    tiled=False,
)
scl_profile_out.pop("blockxsize", None)
scl_profile_out.pop("blockysize", None)

with rasterio.open(scl_aligned_path, "w", **scl_profile_out) as dst:
    dst.write(scl_aligned, 1)

# 4. Calculate NDVI after excluding unsuitable SCL classes.
red_float = red.astype(np.float32)
nir_float = nir.astype(np.float32)
denominator = nir_float + red_float

valid = (
    (red > 0)
    & (nir > 0)
    & (denominator > 0)
    & np.isin(scl_aligned, VALID_SCL_CLASSES)
)

ndvi = np.full(red.shape, NODATA_NDVI, dtype=np.float32)
ndvi[valid] = (
    (nir_float[valid] - red_float[valid])
    / denominator[valid]
)

# 5. Save the NDVI raster and validity mask.
ndvi_profile = red_profile.copy()
ndvi_profile.update(
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

# 6. Summarize pixel quality and NDVI.
classified = scl_aligned > 0
classified_count = int(classified.sum())
valid_count = int(valid.sum())

cloud_shadow = (
    np.isin(scl_aligned, CLOUD_SHADOW_CLASSES)
    & classified
)

cloud_shadow_pct = (
    100 * cloud_shadow.sum() / classified_count
    if classified_count else float("nan")
)

valid_pct = (
    100 * valid_count / classified_count
    if classified_count else float("nan")
)

values = ndvi[valid]

if values.size == 0:
    raise RuntimeError(
        "No valid NDVI pixels. Inspect the mosaics and SCL data."
    )

pixel_area_m2 = abs(red_transform.a * red_transform.e)

summary = pd.DataFrame([{
    "study_area": CITY,
    "acquisition_date": DATE,
    "crs": str(red_crs),
    "pixel_area_m2": pixel_area_m2,
    "classified_scl_pixels": classified_count,
    "valid_ndvi_pixels": valid_count,
    "valid_pixel_percent": valid_pct,
    "cloud_shadow_cirrus_snow_class_percent": cloud_shadow_pct,
    "mean_ndvi": float(values.mean()),
    "median_ndvi": float(np.median(values)),
    "minimum_ndvi": float(values.min()),
    "maximum_ndvi": float(values.max()),
}])

summary.to_csv(summary_path, index=False, encoding="utf-8")

print("\nQUALITY AND NDVI SUMMARY")
print(summary.to_string(index=False))

# 7. Draw the map and overlay the administrative boundary.
boundaries = gpd.read_file(BOUNDARY_FILE)
boundary = boundaries[boundaries["shapeName"] == CITY].copy()

if boundary.crs is None:
    raise ValueError("Boundary file has no CRS.")

boundary = boundary.to_crs(red_crs)

height, width = ndvi.shape
west, south, east, north = array_bounds(
    height, width, red_transform
)

plot_data = np.ma.masked_where(
    ndvi == NODATA_NDVI, ndvi
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

boundary.boundary.plot(
    ax=ax,
    color="black",
    linewidth=0.7,
)

colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
colorbar.set_label("NDVI")

ax.set_title(
    "Lahore NDVI — 13 October 2024\n"
    "Sentinel-2 L2A | SCL-filtered pilot"
)
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig(figure_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nOUTPUTS CREATED")
print("Red mosaic:", red_path)
print("NIR mosaic:", nir_path)
print("SCL mosaic:", scl_path)
print("Aligned SCL:", scl_aligned_path)
print("NDVI raster:", ndvi_path)
print("Valid mask:", mask_path)
print("NDVI map:", figure_path)
print("Summary CSV:", summary_path)

print(
    "\nResearch caution: SCL masking is preliminary. "
    "The reported quality percentages are not independent "
    "validation of cloud-free pixels or full-city coverage."
)
