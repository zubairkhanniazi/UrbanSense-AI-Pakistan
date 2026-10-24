from pathlib import Path
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]

PILOTS = [
    (
        "Islamabad",
        ROOT / "data" / "processed" / "islamabad_2024_10_16",
        "ndvi_2024_10_16.tif",
    ),
    (
        "Lahore",
        ROOT / "data" / "processed" / "lahore_2024_10_13",
        "ndvi_2024_10_13.tif",
    ),
]

LABELS = {
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

for city, folder, ndvi_name in PILOTS:
    print("\n" + "=" * 60)
    print(city.upper(), "SCL AND REFLECTANCE CHECK")
    print("=" * 60)

    paths = {
        "NDVI": folder / ndvi_name,
        "Red": folder / "red_mosaic_10m.tif",
        "NIR": folder / "nir_mosaic_10m.tif",
        "SCL": folder / "scl_aligned_10m.tif",
        "Mask": folder / "ndvi_valid_mask.tif",
    }

    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"{city}: missing {path}")

    with rasterio.open(paths["NDVI"]) as ds:
        ndvi = ds.read(1).astype(np.float64)
        transform = ds.transform
        crs = ds.crs
        nodata = ds.nodata

    arrays = {}
    for name in ("Red", "NIR", "SCL", "Mask"):
        with rasterio.open(paths[name]) as ds:
            if ds.crs != crs or ds.transform != transform:
                raise ValueError(f"{city}: {name} grid mismatch")
            arrays[name] = ds.read(1)

    red = arrays["Red"].astype(np.float64)
    nir = arrays["NIR"].astype(np.float64)
    scl = arrays["SCL"]
    valid_mask = arrays["Mask"] > 0

    inside_valid = (
        valid_mask
        & np.isfinite(ndvi)
        & (ndvi >= -1)
        & (ndvi <= 1)
    )

    if nodata is not None:
        inside_valid &= ndvi != nodata

    print("\nSCL class distribution across the entire raster:")
    total = scl.size

    for value in sorted(np.unique(scl)):
        count = int(np.count_nonzero(scl == value))
        pct = 100 * count / total
        print(
            f"Class {value:2d} | "
            f"{LABELS.get(int(value), 'Unknown'):26s} | "
            f"{count:>12,} | {pct:8.4f}%"
        )

    print("\nSCL class distribution within valid NDVI pixels:")
    total_valid = int(inside_valid.sum())

    for value in sorted(np.unique(scl[inside_valid])):
        count = int(np.count_nonzero(scl[inside_valid] == value))
        pct = 100 * count / total_valid if total_valid else 0
        print(
            f"Class {value:2d} | "
            f"{LABELS.get(int(value), 'Unknown'):26s} | "
            f"{count:>12,} | {pct:8.4f}%"
        )

    denominator = red + nir
    extreme = inside_valid & ((ndvi < -0.95) | (ndvi > 0.95))

    print("\nReflectance diagnostics for extreme NDVI pixels:")

    for label, condition in [
        ("NDVI below -0.95", inside_valid & (ndvi < -0.95)),
        ("NDVI above +0.95", inside_valid & (ndvi > 0.95)),
    ]:
        count = int(condition.sum())
        print(f"\n{label}: {count:,} pixels")

        if count:
            print("  Red min/median/max:",
                  np.min(red[condition]),
                  np.median(red[condition]),
                  np.max(red[condition]))
            print("  NIR min/median/max:",
                  np.min(nir[condition]),
                  np.median(nir[condition]),
                  np.max(nir[condition]))
            print("  Red+NIR min/median:",
                  np.min(denominator[condition]),
                  np.median(denominator[condition]))

    cloud_shadow_classes = np.isin(scl, [3, 8, 9, 10, 11])
    classified = scl > 0

    cloud_count = int((cloud_shadow_classes & classified).sum())
    classified_count = int(classified.sum())

    print("\nCloud-related SCL classes:", cloud_count)
    print("Nonzero SCL pixels:", classified_count)

print("\nInspection finished. No files were modified.")
