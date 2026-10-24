from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling
from rasterio.transform import array_bounds

ROOT = Path(__file__).resolve().parents[1]

PILOT = ROOT / "data" / "interim" / "pilot_islamabad_2024"
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

OUT = ROOT / "data" / "processed" / "islamabad_2024_10_16"
FIGURES = ROOT / "reports" / "figures"

OUT.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

CITY = "Islamabad Capital Territory"
DATE = "2024-10-16"
NODATA_NDVI = -9999.0

# SCL classes retained for NDVI:
# 4 vegetation, 5 not vegetated, 6 water.
# Other classes are excluded conservatively, including clouds,
# cirrus, cloud shadows, unclassified pixels and no-data pixels.
VALID_SCL_CLASSES = [4, 5, 6]
CLOUD_SHADOW_CLASSES = [3, 8, 9, 10, 11]

def mosaic_band(pattern, output_path):
    files = sorted(PILOT.glob(pattern))

    if len(files) < 2:
        raise FileNotFoundError(
            f"Expected at least two files matching {pattern}; "
            f"found {len(files)} in {PILOT}"
        )

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"
    ):
        with rasterio.open(files[0]) as first:
            target_crs = first.crs
            target_res = first.res

        if target_crs is None:
            raise ValueError(f"No CRS in {files[0]}")

        with rasterio.open(files[0]) as first:
            first_dtype = first.dtypes[0]

        with rasterio.open(files[0]) as _:
            pass

        datasets = []
        try:
            for file in files:
                ds = rasterio.open(file)
                datasets.append(ds)

                if ds.crs != target_crs:
                    raise ValueError(
                        f"CRS mismatch in {file.name}"
                    )

                if not np.allclose(ds.res, target_res):
                    raise ValueError(
                        f"Resolution mismatch in {file.name}"
                    )

            mosaic, transform = merge(
                datasets,
                nodata=0,
                method="first",
            )

            profile = datasets[0].profile.copy()
            profile.update(
                driver="GTiff",
                height=mosaic.shape[1],
                width=mosaic.shape[2],
                count=1,
                transform=transform,
                compress="deflate",
                nodata=0,
                tiled=False,
            )
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)

            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(mosaic[0], 1)

        finally:
            for ds in datasets:
                ds.close()

    print(f"Mosaic created: {output_path.name}")
    print(f"  Input tiles: {len(files)}")
    print(f"  Dimensions: {mosaic.shape[2]} x {mosaic.shape[1]}")
    print(f"  Resolution: {target_res}")

    return mosaic[0], transform, target_crs, profile


print("=" * 65)
print("ISLAMABAD SATELLITE MOSAIC AND NDVI")
print("=" * 65)

for required in [PILOT, BOUNDARY_FILE]:
    if not required.exists():
        raise FileNotFoundError(f"Required path not found: {required}")

red_path = OUT / "red_mosaic_10m.tif"
nir_path = OUT / "nir_mosaic_10m.tif"
scl_path = OUT / "scl_mosaic_20m.tif"
scl_aligned_path = OUT / "scl_aligned_10m.tif"
ndvi_path = OUT / "ndvi_2024_10_16.tif"
mask_path = OUT / "ndvi_valid_mask.tif"
figure_path = FIGURES / "islamabad_ndvi_2024-10-16.png"

# 1. Mosaic red and NIR at their native resolution.
red, red_transform, red_crs, red_profile = mosaic_band(
    "*_red.tif", red_path
)
nir, nir_transform, nir_crs, nir_profile = mosaic_band(
    "*_nir.tif", nir_path
)

if nir_crs != red_crs:
    raise ValueError("Red and NIR mosaics use different CRSs.")

if nir.shape != red.shape or nir_transform != red_transform:
    print("Aligning NIR to the red-band grid.")
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
    nir_transform = red_transform

# 2. Mosaic SCL at its native resolution.
scl, scl_transform, scl_crs, scl_profile = mosaic_band(
    "*_scl.tif", scl_path
)

# 3. Align categorical SCL to the 10 m red-band grid.
# Nearest-neighbor is appropriate for categorical class values.
scl_on_red = np.zeros(red.shape, dtype=np.uint8)

reproject(
    source=scl.astype(np.uint8),
    destination=scl_on_red,
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
    height=scl_on_red.shape[0],
    width=scl_on_red.shape[1],
    transform=red_transform,
    compress="deflate",
    tiled=False,
)
scl_profile_out.pop("blockxsize", None)
scl_profile_out.pop("blockysize", None)

with rasterio.open(scl_aligned_path, "w", **scl_profile_out) as dst:
    dst.write(scl_on_red, 1)

# 4. Identify usable pixels and calculate NDVI.
red_float = red.astype(np.float32)
nir_float = nir.astype(np.float32)
denominator = nir_float + red_float

valid = (
    (red > 0)
    & (nir > 0)
    & (denominator > 0)
    & np.isin(scl_on_red, VALID_SCL_CLASSES)
)

ndvi = np.full(red.shape, NODATA_NDVI, dtype=np.float32)
ndvi[valid] = (
    (nir_float[valid] - red_float[valid])
    / denominator[valid]
)

# 5. Save NDVI and valid-pixel mask.
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

# 6. Calculate quality statistics.
classified = scl_on_red > 0
classified_count = int(classified.sum())
valid_count = int(valid.sum())

cloud_shadow = np.isin(
    scl_on_red, CLOUD_SHADOW_CLASSES
) & classified

cloud_shadow_pct = (
    100 * cloud_shadow.sum() / classified_count
    if classified_count else float("nan")
)

valid_pct = (
    100 * valid_count / classified_count
    if classified_count else float("nan")
)

valid_ndvi = ndvi[valid]
if valid_ndvi.size == 0:
    raise RuntimeError(
        "No valid NDVI pixels found. Inspect the mosaics and SCL."
    )

print("\nQUALITY AND NDVI SUMMARY")
print("Date:", DATE)
print("CRS:", red_crs)
print("Pixel size:", red_profile["transform"].a)
print("Classified SCL pixels:", classified_count)
print(f"Cloud/shadow/cirrus/snow-class percentage: {cloud_shadow_pct:.2f}%")
print(f"Pixels retained for NDVI: {valid_pct:.2f}%")
print(f"Mean NDVI: {float(valid_ndvi.mean()):.4f}")
print(f"Median NDVI: {float(np.median(valid_ndvi)):.4f}")
print(f"Minimum NDVI: {float(valid_ndvi.min()):.4f}")
print(f"Maximum NDVI: {float(valid_ndvi.max()):.4f}")

# 7. Plot the NDVI map with the administrative boundary.
boundary = gpd.read_file(BOUNDARY_FILE)
boundary = boundary[boundary["shapeName"] == CITY].copy()

if not boundary.empty:
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

if not boundary.empty:
    boundary.boundary.plot(
        ax=ax,
        color="black",
        linewidth=0.7,
    )

colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
colorbar.set_label("NDVI")

ax.set_title(
    "Islamabad NDVI — 16 October 2024\n"
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
print("Valid-pixel mask:", mask_path)
print("NDVI map:", figure_path)

print(
    "\nResearch caution: SCL is a categorical quality layer. "
    "The reported percentages describe the retained mosaic, "
    "not a full independent validation of cloud-free coverage."
)
