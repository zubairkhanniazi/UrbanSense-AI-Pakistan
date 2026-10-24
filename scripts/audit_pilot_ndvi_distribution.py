from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

PILOTS = [
    {
        "city": "Islamabad Capital Territory",
        "date": "2024-10-16",
        "folder": ROOT / "data" / "processed"
            / "islamabad_2024_10_16",
        "ndvi": "ndvi_2024_10_16.tif",
    },
    {
        "city": "Lahore",
        "date": "2024-10-13",
        "folder": ROOT / "data" / "processed"
            / "lahore_2024_10_13",
        "ndvi": "ndvi_2024_10_13.tif",
    },
]

OUTPUT = (
    ROOT / "reports" / "tables"
    / "pilot_ndvi_distribution_audit.csv"
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

SCL_LABELS = {
    0: "No data",
    1: "Saturated/defective",
    2: "Dark area",
    3: "Cloud shadow",
    4: "Vegetation",
    5: "Not vegetated",
    6: "Water",
    7: "Unclassified",
    8: "Cloud medium probability",
    9: "Cloud high probability",
    10: "Thin cirrus",
    11: "Snow/ice",
}

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(BOUNDARY_FILE)

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

results = []

print("=" * 70)
print("NDVI DISTRIBUTION AND SCL QUALITY AUDIT")
print("=" * 70)

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
            raise FileNotFoundError(f"{city}: missing {name}: {path}")

    selected = boundaries[boundaries["shapeName"] == city]

    if selected.empty:
        raise ValueError(f"Boundary not found: {city}")

    with rasterio.open(paths["NDVI"]) as ndvi_src, \
         rasterio.open(paths["Red"]) as red_src, \
         rasterio.open(paths["NIR"]) as nir_src, \
         rasterio.open(paths["SCL"]) as scl_src, \
         rasterio.open(paths["Mask"]) as mask_src:

        reference = (
            ndvi_src.shape,
            ndvi_src.transform,
            ndvi_src.crs,
        )

        for name, src in [
            ("Red", red_src),
            ("NIR", nir_src),
            ("SCL", scl_src),
            ("Mask", mask_src),
        ]:
            if (
                src.shape != reference[0]
                or src.transform != reference[1]
                or src.crs != reference[2]
            ):
                raise ValueError(f"{city}: {name} grid mismatch.")

        ndvi = ndvi_src.read(1).astype(np.float64)
        red = red_src.read(1).astype(np.float64)
        nir = nir_src.read(1).astype(np.float64)
        scl = scl_src.read(1)
        saved_mask = mask_src.read(1) > 0

        boundary = selected.to_crs(ndvi_src.crs)
        shapes = [
            geom.__geo_interface__
            for geom in boundary.geometry
            if geom is not None and not geom.is_empty
        ]

        inside = geometry_mask(
            shapes,
            out_shape=ndvi_src.shape,
            transform=ndvi_src.transform,
            invert=True,
        )

        nodata = ndvi_src.nodata

        valid = (
            inside
            & saved_mask
            & np.isfinite(ndvi)
            & (ndvi >= -1)
            & (ndvi <= 1)
        )

        if nodata is not None:
            valid &= ndvi != nodata

        values = ndvi[valid]
        denominator = red + nir

        if values.size == 0:
            raise ValueError(f"{city}: no valid NDVI pixels.")

        recompute_ok = (
            valid
            & (red > 0)
            & (nir > 0)
            & (denominator > 0)
        )

        recalculated = (
            (nir[recompute_ok] - red[recompute_ok])
            / denominator[recompute_ok]
        )

        differences = (
            np.abs(ndvi[recompute_ok] - recalculated)
            if recalculated.size else np.array([])
        )

        print(f"\n{'=' * 60}")
        print(f"{city} | {pilot['date']}")
        print("=" * 60)
        print("Valid NDVI pixels:", values.size)
        print(f"NDVI minimum: {values.min():.6f}")
        print(f"NDVI 1st percentile: {np.percentile(values, 1):.6f}")
        print(f"NDVI median: {np.median(values):.6f}")
        print(f"NDVI 99th percentile: {np.percentile(values, 99):.6f}")
        print(f"NDVI maximum: {values.max():.6f}")

        low_extreme = int((values < -0.95).sum())
        high_extreme = int((values > 0.95).sum())

        print("\nExtreme NDVI pixels:")
        print(
            f"  Below -0.95: {low_extreme} "
            f"({100 * low_extreme / values.size:.4f}%)"
        )
        print(
            f"  Above +0.95: {high_extreme} "
            f"({100 * high_extreme / values.size:.4f}%)"
        )

        print("\nSCL class distribution inside the boundary:")
        scl_values = scl[inside]
        scl_total = scl_values.size

        for class_value in sorted(np.unique(scl_values)):
            count = int((scl_values == class_value).sum())
            percentage = 100 * count / scl_total if scl_total else 0

            print(
                f"  Class {class_value:2d} "
                f"({SCL_LABELS.get(int(class_value), 'Unknown')}): "
                f"{count:,} pixels ({percentage:.4f}%)"
            )

        cloud_classes = np.isin(scl_values, [3, 8, 9, 10, 11])
        classified = scl_values > 0

        classified_count = int(classified.sum())
        cloud_count = int((cloud_classes & classified).sum())

        cloud_pct = (
            100 * cloud_count / classified_count
            if classified_count else np.nan
        )

        print("\nCloud-related SCL class group:")
        print(f"  Pixels: {cloud_count:,}")
        print(f"  Percentage of nonzero SCL pixels: {cloud_pct:.6f}%")

        valid_denominator = denominator[recompute_ok]

        if valid_denominator.size:
            print("\nRed + NIR denominator diagnostics:")
            print(f"  Minimum: {valid_denominator.min():.6f}")
            print(f"  1st percentile: {np.percentile(valid_denominator, 1):.6f}")
            print(f"  Median: {np.median(valid_denominator):.6f}")
            print(
                "  Denominator below 100 (raw units):",
                int((valid_denominator < 100).sum()),
            )
            print(
                "  Denominator below 1000 (raw units):",
                int((valid_denominator < 1000).sum()),
            )

        max_difference = (
            float(differences.max())
            if differences.size else np.nan
        )

        print("\nStored versus recalculated NDVI:")
        print("  Maximum absolute difference:", max_difference)

        results.append({
            "study_area": city,
            "acquisition_date": pilot["date"],
            "valid_ndvi_pixels": int(values.size),
            "ndvi_min": float(values.min()),
            "ndvi_p01": float(np.percentile(values, 1)),
            "ndvi_median": float(np.median(values)),
            "ndvi_p99": float(np.percentile(values, 99)),
            "ndvi_max": float(values.max()),
            "pixels_below_minus_095": low_extreme,
            "pixels_above_plus_095": high_extreme,
            "scl_cloud_group_pixels": cloud_count,
            "scl_cloud_group_percent": cloud_pct,
            "max_ndvi_recalculation_difference": max_difference,
        })

pd.DataFrame(results).to_csv(
    OUTPUT, index=False, encoding="utf-8"
)

print("\n" + "=" * 70)
print("AUDIT FINISHED")
print("=" * 70)
print("Summary CSV:", OUTPUT)
print(
    "\nThis is a diagnostic audit, not proof of cloud-free imagery. "
    "Low denominators, extreme NDVI values, SCL class frequencies "
    "and any mismatch between stored and recalculated NDVI require "
    "interpretation before scientific conclusions are drawn."
)
