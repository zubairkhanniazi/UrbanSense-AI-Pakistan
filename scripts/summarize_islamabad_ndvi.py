from pathlib import Path
import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]

FOLDER = ROOT / "data" / "processed" / "islamabad_2024_10_16"
NDVI_FILE = FOLDER / "ndvi_2024_10_16.tif"
SCL_FILE = FOLDER / "scl_aligned_10m.tif"
MASK_FILE = FOLDER / "ndvi_valid_mask.tif"

OUTPUT_DIR = ROOT / "reports" / "tables"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "islamabad_ndvi_pilot_summary.csv"

for path in (NDVI_FILE, SCL_FILE, MASK_FILE):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")

with rasterio.open(NDVI_FILE) as src:
    ndvi = src.read(1).astype(np.float32)
    transform = src.transform
    nodata = src.nodata
    ndvi_crs = src.crs

with rasterio.open(SCL_FILE) as src:
    scl = src.read(1)
    if src.crs != ndvi_crs or src.shape != ndvi.shape:
        raise ValueError("SCL and NDVI grids do not match.")

with rasterio.open(MASK_FILE) as src:
    valid_mask = src.read(1) > 0
    if src.shape != ndvi.shape:
        raise ValueError("Valid mask and NDVI grids do not match.")

if transform.a == 0 or transform.e == 0:
    raise ValueError("Invalid pixel dimensions.")

pixel_area_m2 = abs(transform.a * transform.e)

# Use the saved mask and exclude no-data/non-finite values.
valid = valid_mask & np.isfinite(ndvi)

if nodata is not None:
    valid &= ndvi != nodata

valid &= (ndvi >= -1) & (ndvi <= 1)

# Sentinel-2 SCL classes:
# 3 = cloud shadow
# 4 = vegetation
# 5 = not vegetated
# 6 = water
# 8 = medium-probability cloud
# 9 = high-probability cloud
# 10 = cirrus
# 11 = snow/ice
classified = scl > 0
vegetation_class = valid & (scl == 4)
bare_class = valid & (scl == 5)
water_class = valid & (scl == 6)

cloud_shadow_classes = np.isin(scl, [3, 8, 9, 10, 11])
cloud_shadow = classified & cloud_shadow_classes

# Exploratory threshold only; not a validated land-cover classifier.
threshold_vegetation = valid & (ndvi >= 0.30)

def area_km2(count):
    # Nominal pixel area; boundary-edge pixels may be partial.
    return count * pixel_area_m2 / 1_000_000

def stats_for(mask, label):
    values = ndvi[mask]
    return {
        "metric": label,
        "pixel_count": int(values.size),
        "area_km2_approx": round(area_km2(values.size), 4),
        "mean_ndvi": round(float(values.mean()), 6)
            if values.size else None,
        "median_ndvi": round(float(np.median(values)), 6)
            if values.size else None,
    }

valid_count = int(valid.sum())
classified_count = int(classified.sum())

rows = [
    stats_for(valid, "All valid clear-class NDVI pixels"),
    stats_for(vegetation_class, "SCL class 4: vegetation"),
    stats_for(bare_class, "SCL class 5: not vegetated"),
    stats_for(water_class, "SCL class 6: water"),
    stats_for(threshold_vegetation, "Exploratory NDVI >= 0.30"),
]

print("=" * 65)
print("ISLAMABAD NDVI PILOT STATISTICS")
print("=" * 65)
print("Acquisition date: 2024-10-16")
print("CRS:", ndvi_crs)
print(f"Nominal pixel area: {pixel_area_m2:.2f} m²")
print("SCL classified pixels:", classified_count)
print("Valid NDVI pixels:", valid_count)

if classified_count:
    print(
        "Valid NDVI / classified pixels:",
        f"{100 * valid_count / classified_count:.2f}%"
    )

if valid_count:
    print(
        "SCL vegetation class / valid NDVI pixels:",
        f"{100 * vegetation_class.sum() / valid_count:.2f}%"
    )
    print(
        "Exploratory NDVI >= 0.30 / valid NDVI pixels:",
        f"{100 * threshold_vegetation.sum() / valid_count:.2f}%"
    )

print("\nSTATISTICS BY PIXEL GROUP")
print(pd.DataFrame(rows).to_string(index=False))

pd.DataFrame(rows).to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8",
)

print("\nReport saved:", OUTPUT_FILE)
print(
    "\nCaution: SCL class 4 and NDVI >= 0.30 are different "
    "definitions. The NDVI threshold is exploratory, and "
    "area estimates are approximate. Neither should be "
    "presented as a validated vegetation-area measurement yet."
)
