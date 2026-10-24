from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]

PILOTS = [
    {
        "city": "Islamabad",
        "folder": ROOT / "data" / "processed"
            / "islamabad_2024_10_16",
        "ndvi": "ndvi_2024_10_16.tif",
    },
    {
        "city": "Lahore",
        "folder": ROOT / "data" / "processed"
            / "lahore_2024_10_13",
        "ndvi": "ndvi_2024_10_13.tif",
    },
]

# Exploratory thresholds in the stored Sentinel-2 band units.
# They are sensitivity tests, not predetermined filtering rules.
THRESHOLDS = [0, 100, 500, 1000, 2000]

OUTPUT = (
    ROOT / "reports" / "tables"
    / "pilot_ndvi_reflectance_sensitivity.csv"
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

results = []

print("=" * 70)
print("NDVI LOW-REFLECTANCE SENSITIVITY TEST")
print("=" * 70)
print("No existing files will be changed.")

for pilot in PILOTS:
    city = pilot["city"]
    folder = pilot["folder"]

    paths = {
        "NDVI": folder / pilot["ndvi"],
        "Red": folder / "red_mosaic_10m.tif",
        "NIR": folder / "nir_mosaic_10m.tif",
        "SCL": folder / "scl_aligned_10m.tif",
        "Mask": folder / "ndvi_valid_mask.tif",
    }

    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"{city}: missing {path}")

    with rasterio.open(paths["NDVI"]) as src:
        ndvi = src.read(1).astype(np.float64)
        ndvi_nodata = src.nodata
        ndvi_crs = src.crs
        ndvi_transform = src.transform
        ndvi_shape = src.shape

    arrays = {}
    band_metadata = {}

    for name in ("Red", "NIR", "SCL", "Mask"):
        with rasterio.open(paths[name]) as src:
            if (
                src.crs != ndvi_crs
                or src.transform != ndvi_transform
                or src.shape != ndvi_shape
            ):
                raise ValueError(f"{city}: {name} grid mismatch.")

            arrays[name] = src.read(1)

            if name in ("Red", "NIR"):
                band_metadata[name] = {
                    "scale": src.scales[0],
                    "offset": src.offsets[0],
                    "dtype": src.dtypes[0],
                    "nodata": src.nodata,
                }

    red = arrays["Red"].astype(np.float64)
    nir = arrays["NIR"].astype(np.float64)
    scl = arrays["SCL"]
    saved_mask = arrays["Mask"] > 0

    valid = (
        saved_mask
        & np.isfinite(ndvi)
        & (ndvi >= -1)
        & (ndvi <= 1)
        & (red > 0)
        & (nir > 0)
    )

    if ndvi_nodata is not None:
        valid &= ndvi != ndvi_nodata

    denominator = red + nir
    valid_count = int(valid.sum())

    if valid_count == 0:
        raise ValueError(f"{city}: no valid pixels for sensitivity test.")

    print(f"\n{'-' * 60}")
    print(city.upper())
    print("-" * 60)
    print("Red band metadata:", band_metadata["Red"])
    print("NIR band metadata:", band_metadata["NIR"])
    print("Baseline valid pixels:", valid_count)

    base_values = ndvi[valid]

    print("Baseline mean NDVI:", round(float(base_values.mean()), 6))
    print("Baseline median NDVI:", round(float(np.median(base_values)), 6))

    for threshold in THRESHOLDS:
        keep = valid & (denominator >= threshold)
        values = ndvi[keep]
        count = int(keep.sum())

        if count == 0:
            mean = median = low_extreme_pct = high_extreme_pct = np.nan
        else:
            mean = float(values.mean())
            median = float(np.median(values))
            low_extreme_pct = 100 * np.mean(values < -0.95)
            high_extreme_pct = 100 * np.mean(values > 0.95)

        retained_pct = 100 * count / valid_count

        row = {
            "study_area": city,
            "denominator_threshold_raw_units": threshold,
            "baseline_valid_pixels": valid_count,
            "retained_pixels": count,
            "retained_percent": retained_pct,
            "excluded_pixels": valid_count - count,
            "mean_ndvi": mean,
            "median_ndvi": median,
            "ndvi_below_minus_095_percent": low_extreme_pct,
            "ndvi_above_plus_095_percent": high_extreme_pct,
        }

        results.append(row)

        print(
            f"\nThreshold >= {threshold:4d} raw units | "
            f"retained {count:,} ({retained_pct:.2f}%)"
        )
        print(f"  Excluded pixels: {valid_count - count:,}")
        print(f"  Mean NDVI: {mean:.6f}")
        print(f"  Median NDVI: {median:.6f}")
        print(f"  NDVI below -0.95: {low_extreme_pct:.4f}%")
        print(f"  NDVI above +0.95: {high_extreme_pct:.4f}%")

pd.DataFrame(results).to_csv(
    OUTPUT, index=False, encoding="utf-8"
)

print("\n" + "=" * 70)
print("SENSITIVITY TEST FINISHED")
print("=" * 70)
print("CSV:", OUTPUT)
print(
    "\nInterpretation note: Thresholds are in stored band units. "
    "Confirm the data provider's scale, offset and no-data handling "
    "before choosing a threshold. A higher threshold removes more "
    "pixels and can bias results; do not automatically adopt it."
)
