from pathlib import Path
import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"

RASTERS = [
    ("Islamabad", ROOT / "data/processed/islamabad_2024_10_16/ndvi_2024_10_16.tif"),
    ("Lahore", ROOT / "data/processed/lahore_2024_10_13/ndvi_2024_10_13.tif"),
    ("Multan", ROOT / "data/processed/multan_2024_11_20/ndvi_2024-11-20.tif"),
    ("Karachi", ROOT / "data/processed/karachi_2024_multidate/ndvi_median_composite_2024.tif"),
]

COMPARISON_FILE = TABLES / "four_city_ndvi_pilot_comparison.csv"
REPORT_FILE = TABLES / "four_city_ndvi_raster_quality_audit.csv"

print("=" * 70)
print("FOUR-CITY NDVI RASTER QUALITY AUDIT")
print("=" * 70)

comparison = {}

if COMPARISON_FILE.exists():
    df = pd.read_csv(COMPARISON_FILE)
    for _, row in df.iterrows():
        comparison[str(row["city"]).strip()] = row.to_dict()

rows = []

for city, path in RASTERS:
    if not path.exists():
        raise FileNotFoundError(f"{city}: raster missing: {path}")

    valid_count = 0
    nodata_count = 0
    out_of_range = 0
    total_sum = 0.0
    minimum = float("inf")
    maximum = float("-inf")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{city}: CRS is missing.")
        if src.count != 1:
            raise ValueError(f"{city}: expected a single NDVI band.")

        crs = str(src.crs)
        resolution_x, resolution_y = src.res
        width, height = src.width, src.height
        nodata_value = src.nodata

        for _, window in src.block_windows(1):
            data = src.read(1, window=window)
            usable = np.isfinite(data)

            if nodata_value is not None:
                missing = data == nodata_value
            else:
                missing = np.zeros(data.shape, dtype=bool)

            nodata_count += int(missing.sum())
            usable &= ~missing

            bad = usable & ((data < -1.0) | (data > 1.0))
            out_of_range += int(bad.sum())
            usable &= ~bad

            values = data[usable]
            if values.size:
                valid_count += int(values.size)
                total_sum += float(values.sum(dtype=np.float64))
                minimum = min(minimum, float(values.min()))
                maximum = max(maximum, float(values.max()))

    if valid_count == 0:
        raise ValueError(f"{city}: no valid NDVI pixels found.")

    mean_ndvi = total_sum / valid_count
    reference = comparison.get(city, {})

    reference_mean = reference.get("mean_ndvi", np.nan)
    reference_count = reference.get("valid_ndvi_pixels", np.nan)

    try:
        reference_mean = float(reference_mean)
    except (ValueError, TypeError):
        reference_mean = np.nan

    try:
        reference_count = float(reference_count)
    except (ValueError, TypeError):
        reference_count = np.nan

    mean_difference = (
        mean_ndvi - reference_mean
        if np.isfinite(reference_mean) else np.nan
    )

    count_matches = (
        valid_count == int(reference_count)
        if np.isfinite(reference_count) else None
    )

    row = {
        "city": city,
        "raster_path": str(path.relative_to(ROOT)),
        "crs": crs,
        "pixel_width": resolution_x,
        "pixel_height": resolution_y,
        "width_pixels": width,
        "height_pixels": height,
        "valid_ndvi_pixels": valid_count,
        "nodata_pixels": nodata_count,
        "pixels_outside_ndvi_range": out_of_range,
        "mean_ndvi_from_raster": mean_ndvi,
        "minimum_ndvi": minimum,
        "maximum_ndvi": maximum,
        "comparison_csv_mean_ndvi": reference_mean,
        "mean_difference": mean_difference,
        "pixel_count_matches_comparison": count_matches,
        "range_check_passed": out_of_range == 0,
    }
    rows.append(row)

    print(f"\n{city}")
    print("  CRS:", crs)
    print("  Resolution:", resolution_x, resolution_y)
    print("  Valid pixels:", f"{valid_count:,}")
    print("  Mean NDVI:", round(mean_ndvi, 6))
    print("  NDVI range:", round(minimum, 6), "to", round(maximum, 6))
    print("  Out-of-range pixels:", out_of_range)
    print("  Matches comparison pixel count:", count_matches)

result = pd.DataFrame(rows)
result.to_csv(REPORT_FILE, index=False, encoding="utf-8")

print("\n" + "=" * 70)
print("QUALITY AUDIT SUMMARY")
print("=" * 70)
print(result[[
    "city",
    "crs",
    "valid_ndvi_pixels",
    "mean_ndvi_from_raster",
    "minimum_ndvi",
    "maximum_ndvi",
    "pixels_outside_ndvi_range",
]].to_string(index=False))

print("\nCOMPARISON-TABLE CONSISTENCY")
print(result[[
    "city",
    "mean_difference",
    "pixel_count_matches_comparison",
]].to_string(index=False))

print("\nAudit CSV:", REPORT_FILE)
print("No source rasters were modified.")
print(
    "\nNote: This audit checks raster integrity and saved-statistic "
    "consistency. It does not independently validate reflectance "
    "scaling, cloud masking, or scientific comparability."
)
