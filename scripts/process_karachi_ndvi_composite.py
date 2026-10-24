from pathlib import Path
from collections import Counter
import json
import math
import warnings

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import geometry_mask
from rasterio.transform import from_origin, array_bounds
from rasterio.windows import transform as window_transform
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    ROOT / "data" / "interim"
    / "pilot_karachi_2024_multidate"
)
MANIFEST = SOURCE_DIR / "download_manifest.json"
BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

OUT = ROOT / "data" / "processed" / "karachi_2024_multidate"
TEMP = OUT / "_aligned_tmp"
SCENE_OUT = OUT / "per_scene_ndvi"
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"

for folder in (OUT, TEMP, SCENE_OUT, TABLES, FIGURES):
    folder.mkdir(parents=True, exist_ok=True)

TARGET_CRS = "EPSG:32642"
PIXEL_SIZE = 10
NODATA_NDVI = -9999.0
VALID_SCL = [4, 5, 6]
CLOUD_CLASSES = [3, 8, 9, 10, 11]
DATES_EXPECTED = {
    "2024-10-09",
    "2024-11-06",
    "2024-11-26",
}

if not MANIFEST.exists():
    raise FileNotFoundError(f"Download manifest missing: {MANIFEST}")

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(f"Boundary file missing: {BOUNDARY_FILE}")

with MANIFEST.open("r", encoding="utf-8-sig") as f:
    manifest = json.load(f)

# Organize the downloaded assets by scene.
scenes = {}

for record in manifest:
    item_id = record.get("item_id")
    date = str(record.get("acquisition_date", ""))[:10]
    asset = record.get("asset")
    filename = record.get("file")

    if not item_id or not date or not asset or not filename:
        raise ValueError(f"Incomplete manifest record: {record}")

    entry = scenes.setdefault(
        item_id,
        {"date": date, "assets": {}},
    )

    if entry["date"] != date:
        raise ValueError(f"Conflicting dates for {item_id}")

    entry["assets"][asset] = SOURCE_DIR / filename

if len(scenes) != 3:
    raise RuntimeError(
        f"Expected 3 scenes, found {len(scenes)}."
    )

if {s["date"] for s in scenes.values()} != DATES_EXPECTED:
    raise RuntimeError(
        f"Unexpected scene dates: "
        f"{sorted(s['date'] for s in scenes.values())}"
    )

for item_id, scene in scenes.items():
    for asset in ("red", "nir", "scl"):
        path = scene["assets"].get(asset)

        if path is None or not path.exists():
            raise FileNotFoundError(
                f"{item_id}: missing {asset} asset: {path}"
            )

# Prepare the Karachi boundary and a shared 10 m grid.
boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

boundary = boundaries[
    boundaries["shapeName"] == "Karachi"
].copy()

if boundary.empty:
    raise ValueError("Karachi boundary not found.")

boundary_projected = boundary.to_crs(TARGET_CRS)

shapes = [
    geom.__geo_interface__
    for geom in boundary_projected.geometry
    if geom is not None and not geom.is_empty
]

minx, miny, maxx, maxy = boundary_projected.total_bounds

minx = math.floor(minx / PIXEL_SIZE) * PIXEL_SIZE
miny = math.floor(miny / PIXEL_SIZE) * PIXEL_SIZE
maxx = math.ceil(maxx / PIXEL_SIZE) * PIXEL_SIZE
maxy = math.ceil(maxy / PIXEL_SIZE) * PIXEL_SIZE

width = int(round((maxx - minx) / PIXEL_SIZE))
height = int(round((maxy - miny) / PIXEL_SIZE))
target_transform = from_origin(
    minx, maxy, PIXEL_SIZE, PIXEL_SIZE
)

base_profile = {
    "driver": "GTiff",
    "height": height,
    "width": width,
    "count": 1,
    "crs": TARGET_CRS,
    "transform": target_transform,
    "compress": "deflate",
    "tiled": True,
    "blockxsize": 256,
    "blockysize": 256,
}

print("=" * 70)
print("KARACHI MULTI-DATE NDVI PROCESSING")
print("=" * 70)
print("Scenes:", len(scenes))
print("Dates:", ", ".join(sorted(s["date"] for s in scenes.values())))
print("Target CRS:", TARGET_CRS)
print("Target resolution:", PIXEL_SIZE, "metres")
print("Grid dimensions:", width, "x", height)
print("SCL classes retained:", VALID_SCL)
print("Output directory:", OUT)

scene_rows = []
scene_ndvi_files = []

def align_asset(source_path, destination_path, dtype, resampling):
    profile = base_profile.copy()
    profile.update(dtype=dtype, nodata=0)

    with rasterio.open(source_path) as src:
        if src.crs is None:
            raise ValueError(f"Source has no CRS: {source_path}")

        with rasterio.open(
            destination_path, "w", **profile
        ) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=(
                    src.nodata if src.nodata is not None else 0
                ),
                dst_transform=target_transform,
                dst_crs=TARGET_CRS,
                dst_nodata=0,
                resampling=resampling,
                init_dest_nodata=True,
                num_threads=2,
            )

def inside_boundary(window):
    return geometry_mask(
        shapes,
        out_shape=(
            int(window.height),
            int(window.width),
        ),
        transform=window_transform(window, target_transform),
        invert=True,
    )

# Process each acquisition separately before compositing.
for index, (item_id, scene) in enumerate(
    sorted(scenes.items(), key=lambda pair: pair[1]["date"]),
    start=1,
):
    date = scene["date"]
    safe_id = "".join(
        char if char.isalnum() or char in "_-" else "_"
        for char in item_id
    )

    red_tmp = TEMP / f"{safe_id}_red.tif"
    nir_tmp = TEMP / f"{safe_id}_nir.tif"
    scl_tmp = TEMP / f"{safe_id}_scl.tif"

    print(f"\n[{index}/3] Scene: {item_id}")
    print("Acquisition date:", date)

    align_asset(
        scene["assets"]["red"],
        red_tmp,
        "float32",
        Resampling.bilinear,
    )
    align_asset(
        scene["assets"]["nir"],
        nir_tmp,
        "float32",
        Resampling.bilinear,
    )
    align_asset(
        scene["assets"]["scl"],
        scl_tmp,
        "uint8",
        Resampling.nearest,
    )

    ndvi_path = SCENE_OUT / f"ndvi_{date}_{safe_id}.tif"
    ndvi_profile = base_profile.copy()
    ndvi_profile.update(
        dtype="float32",
        nodata=NODATA_NDVI,
    )

    valid_pixels = 0
    boundary_pixels = 0
    sum_ndvi = 0.0
    min_ndvi = float("inf")
    max_ndvi = float("-inf")
    class_counts = Counter()
    cloud_count = 0

    with rasterio.open(red_tmp) as red_ds, \
         rasterio.open(nir_tmp) as nir_ds, \
         rasterio.open(scl_tmp) as scl_ds, \
         rasterio.open(ndvi_path, "w", **ndvi_profile) as dst:

        for _, window in dst.block_windows(1):
            red = red_ds.read(1, window=window)
            nir = nir_ds.read(1, window=window)
            scl = scl_ds.read(1, window=window)

            inside = inside_boundary(window)
            boundary_pixels += int(inside.sum())

            for value, count in zip(
                *np.unique(scl[inside], return_counts=True)
            ):
                class_counts[int(value)] += int(count)

            cloud_count += int(
                (np.isin(scl, CLOUD_CLASSES) & inside).sum()
            )

            denominator = red + nir

            valid = (
                inside
                & (red > 0)
                & (nir > 0)
                & (denominator > 0)
                & np.isin(scl, VALID_SCL)
            )

            tile_ndvi = np.full(
                red.shape,
                NODATA_NDVI,
                dtype=np.float32,
            )

            tile_ndvi[valid] = (
                (nir[valid] - red[valid])
                / denominator[valid]
            )

            dst.write(tile_ndvi, 1, window=window)

            values = tile_ndvi[valid]

            if values.size:
                valid_pixels += int(values.size)
                sum_ndvi += float(values.sum(dtype=np.float64))
                min_ndvi = min(min_ndvi, float(values.min()))
                max_ndvi = max(max_ndvi, float(values.max()))

    mean_ndvi = (
        sum_ndvi / valid_pixels
        if valid_pixels else float("nan")
    )

    row = {
        "scene_id": item_id,
        "acquisition_date": date,
        "valid_pixels": valid_pixels,
        "boundary_grid_pixels": boundary_pixels,
        "valid_pixel_percent_of_boundary_grid": (
            100 * valid_pixels / boundary_pixels
            if boundary_pixels else float("nan")
        ),
        "cloud_shadow_cirrus_snow_class_pixels": cloud_count,
        "mean_ndvi": mean_ndvi,
        "minimum_ndvi": (
            min_ndvi if valid_pixels else float("nan")
        ),
        "maximum_ndvi": (
            max_ndvi if valid_pixels else float("nan")
        ),
        "ndvi_file": str(ndvi_path),
    }

    for scl_class in range(12):
        row[f"scl_class_{scl_class}_pixels"] = class_counts[scl_class]

    scene_rows.append(row)
    scene_ndvi_files.append(ndvi_path)

    print("Valid NDVI pixels:", f"{valid_pixels:,}")
    print("Cloud-related SCL pixels:", f"{cloud_count:,}")
    print("Mean NDVI:", mean_ndvi)
    print("Individual NDVI raster:", ndvi_path)

    # Release temporary aligned files after each scene.
    for path in (red_tmp, nir_tmp, scl_tmp):
        path.unlink(missing_ok=True)

scene_summary_path = TABLES / "karachi_ndvi_scene_quality_2024.csv"
pd.DataFrame(scene_rows).to_csv(
    scene_summary_path, index=False, encoding="utf-8"
)

# Combine observations using the median of valid NDVI values.
composite_path = OUT / "ndvi_median_composite_2024.tif"
count_path = OUT / "ndvi_observation_count_2024.tif"
mask_path = OUT / "ndvi_valid_mask_2024.tif"

composite_profile = base_profile.copy()
composite_profile.update(
    dtype="float32",
    nodata=NODATA_NDVI,
)

count_profile = base_profile.copy()
count_profile.update(dtype="uint8", nodata=0)

mask_profile = base_profile.copy()
mask_profile.update(dtype="uint8", nodata=0)

histogram_edges = np.linspace(-1, 1, 2001)
histogram = np.zeros(len(histogram_edges) - 1, dtype=np.int64)

total_boundary_pixels = 0
valid_composite_pixels = 0
sum_composite = 0.0
minimum = float("inf")
maximum = float("-inf")
observation_distribution = np.zeros(4, dtype=np.int64)

print("\nBuilding pixel-wise median composite...")

with rasterio.open(scene_ndvi_files[0]) as first:
    for path in scene_ndvi_files[1:]:
        with rasterio.open(path) as check:
            if (
                check.crs != first.crs
                or check.transform != first.transform
                or check.shape != first.shape
            ):
                raise ValueError(
                    "Per-scene NDVI rasters do not share the same grid."
                )

with rasterio.open(scene_ndvi_files[0]) as ds0, \
     rasterio.open(scene_ndvi_files[1]) as ds1, \
     rasterio.open(scene_ndvi_files[2]) as ds2, \
     rasterio.open(composite_path, "w", **composite_profile) as comp_dst, \
     rasterio.open(count_path, "w", **count_profile) as count_dst, \
     rasterio.open(mask_path, "w", **mask_profile) as mask_dst:

    inputs = [ds0, ds1, ds2]

    for _, window in comp_dst.block_windows(1):
        arrays = [
            ds.read(1, window=window)
            for ds in inputs
        ]

        stack = np.stack(arrays, axis=0)

        inside = inside_boundary(window)
        total_boundary_pixels += int(inside.sum())

        observation_valid = (
            np.isfinite(stack)
            & (stack != NODATA_NDVI)
        )
        observation_valid &= inside[np.newaxis, :, :]

        count = observation_valid.sum(axis=0).astype(np.uint8)
        observation_distribution += np.bincount(
            count[inside].ravel(),
            minlength=4,
        )[:4]

        masked_stack = np.where(
            observation_valid,
            stack,
            np.nan,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            median = np.nanmedian(masked_stack, axis=0)

        valid_composite = count > 0

        output = np.full(
            count.shape,
            NODATA_NDVI,
            dtype=np.float32,
        )
        output[valid_composite] = median[valid_composite]

        comp_dst.write(output, 1, window=window)
        count_dst.write(count, 1, window=window)
        mask_dst.write(
            valid_composite.astype(np.uint8),
            1,
            window=window,
        )

        values = output[valid_composite]

        if values.size:
            valid_composite_pixels += int(values.size)
            sum_composite += float(values.sum(dtype=np.float64))
            minimum = min(minimum, float(values.min()))
            maximum = max(maximum, float(values.max()))
            histogram += np.histogram(
                values,
                bins=histogram_edges,
            )[0]

if valid_composite_pixels == 0:
    raise RuntimeError("No valid pixels in the Karachi composite.")

median_bin = int(
    np.searchsorted(
        np.cumsum(histogram),
        (valid_composite_pixels + 1) // 2,
    )
)
median_estimate = float(
    (histogram_edges[median_bin]
     + histogram_edges[median_bin + 1]) / 2
)

coverage_percent = (
    100 * valid_composite_pixels / total_boundary_pixels
    if total_boundary_pixels else float("nan")
)

composite_summary = {
    "study_area": "Karachi",
    "year": 2024,
    "acquisition_dates": "; ".join(
        sorted(scene["date"] for scene in scenes.values())
    ),
    "target_crs": TARGET_CRS,
    "pixel_size_m": PIXEL_SIZE,
    "boundary_grid_pixels": total_boundary_pixels,
    "valid_composite_pixels": valid_composite_pixels,
    "valid_composite_pixel_percent": coverage_percent,
    "approx_valid_area_km2": (
        valid_composite_pixels * PIXEL_SIZE**2 / 1_000_000
    ),
    "mean_ndvi": sum_composite / valid_composite_pixels,
    "approx_median_ndvi": median_estimate,
    "minimum_ndvi": minimum,
    "maximum_ndvi": maximum,
    "pixels_with_1_observation": int(observation_distribution[1]),
    "pixels_with_2_observations": int(observation_distribution[2]),
    "pixels_with_3_observations": int(observation_distribution[3]),
    "pixels_with_no_observations_inside_grid": int(
        observation_distribution[0]
    ),
}

composite_summary_path = TABLES / "karachi_ndvi_composite_summary_2024.csv"
pd.DataFrame([composite_summary]).to_csv(
    composite_summary_path,
    index=False,
    encoding="utf-8",
)

# Render a downsampled map so large rasters do not need to be loaded
# into memory at full resolution.
map_path = FIGURES / "karachi_ndvi_median_composite_2024.png"
count_map_path = FIGURES / "karachi_ndvi_observation_count_2024.png"

with rasterio.open(composite_path) as src:
    scale = min(1.0, 1800 / max(src.width, src.height))
    out_width = max(1, int(src.width * scale))
    out_height = max(1, int(src.height * scale))

    data = src.read(
        1,
        out_shape=(out_height, out_width),
        resampling=Resampling.average,
    )

    display_transform = src.transform * Affine.scale(
        src.width / out_width,
        src.height / out_height,
    )

    west, south, east, north = array_bounds(
        out_height,
        out_width,
        display_transform,
    )

plot_data = np.ma.masked_where(
    data == NODATA_NDVI,
    data,
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
    ax=ax, color="black", linewidth=0.7
)
fig.colorbar(image, ax=ax, shrink=0.8, label="NDVI")
ax.set_title(
    "Karachi Median NDVI Composite — 2024\n"
    "Three Sentinel-2 acquisition dates"
)
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig(map_path, dpi=200, bbox_inches="tight")
plt.close(fig)

with rasterio.open(count_path) as src:
    count_data = src.read(
        1,
        out_shape=(out_height, out_width),
        resampling=Resampling.nearest,
    )

fig, ax = plt.subplots(figsize=(10, 9))
count_plot = np.ma.masked_where(count_data == 0, count_data)
image = ax.imshow(
    count_plot,
    extent=(west, east, south, north),
    origin="upper",
    cmap="viridis",
    vmin=1,
    vmax=3,
    interpolation="nearest",
)
boundary_projected.boundary.plot(
    ax=ax, color="black", linewidth=0.7
)
fig.colorbar(
    image,
    ax=ax,
    shrink=0.8,
    ticks=[1, 2, 3],
    label="Number of valid observations",
)
ax.set_title("Karachi NDVI Observation Count — 2024")
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig(count_map_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\n" + "=" * 70)
print("KARACHI NDVI COMPOSITE FINISHED")
print("=" * 70)

print("\nPER-SCENE QUALITY SUMMARY")
print(pd.DataFrame(scene_rows)[[
    "scene_id",
    "acquisition_date",
    "valid_pixels",
    "cloud_shadow_cirrus_snow_class_pixels",
    "mean_ndvi",
]].to_string(index=False))

print("\nCOMPOSITE SUMMARY")
for key, value in composite_summary.items():
    print(f"{key}: {value}")

print("\nOUTPUTS CREATED")
print("Composite NDVI:", composite_path)
print("Observation count:", count_path)
print("Valid mask:", mask_path)
print("Individual scene NDVI folder:", SCENE_OUT)
print("Scene quality CSV:", scene_summary_path)
print("Composite summary CSV:", composite_summary_path)
print("NDVI map:", map_path)
print("Observation-count map:", count_map_path)

# Remove only the temporary aligned rasters created by this script.
for path in TEMP.glob("*.tif"):
    path.unlink(missing_ok=True)

try:
    TEMP.rmdir()
except OSError:
    pass

print(
    "\nResearch caution: This is a preliminary multi-date composite. "
    "The SCL mask retains classes 4, 5 and 6. Reflectance scaling "
    "and offsets must be verified against original provider metadata. "
    "The three dates may differ in phenology, atmosphere and illumination. "
    "The composite is not an independently validated cloud-free product."
)
