from pathlib import Path
import numpy as np
import rasterio

root = Path(__file__).resolve().parents[1]
folder = root / "data" / "processed" / "islamabad_2024_10_16"

files = {
    "Red mosaic": folder / "red_mosaic_10m.tif",
    "NIR mosaic": folder / "nir_mosaic_10m.tif",
    "SCL mosaic": folder / "scl_mosaic_20m.tif",
    "Aligned SCL": folder / "scl_aligned_10m.tif",
    "NDVI raster": folder / "ndvi_2024_10_16.tif",
    "Valid-pixel mask": folder / "ndvi_valid_mask.tif",
}

print("=" * 55)
print("ISLAMABAD NDVI OUTPUT VERIFICATION")
print("=" * 55)

missing = []

for name, path in files.items():
    if not path.exists():
        print(f"MISSING: {name} -> {path.name}")
        missing.append(name)
        continue

    with rasterio.open(path) as src:
        print(f"\n{name}: {path.name}")
        print(f"  Dimensions: {src.width} x {src.height}")
        print(f"  CRS: {src.crs}")
        print(f"  Pixel size: {src.res}")
        print(f"  File size: {path.stat().st_size / 1e6:.2f} MB")

ndvi_path = files["NDVI raster"]

if ndvi_path.exists():
    with rasterio.open(ndvi_path) as src:
        data = src.read(1, masked=True).astype("float32")
        values = data.compressed()
        values = values[np.isfinite(values)]

        print("\nNDVI QUALITY CHECK")

        if values.size:
            print("Valid NDVI pixels:", values.size)
            print(f"Minimum: {values.min():.4f}")
            print(f"Maximum: {values.max():.4f}")
            print(f"Mean: {values.mean():.4f}")
            print(f"Median: {np.median(values):.4f}")
            print("All values within [-1, 1]:",
                  bool(np.all((values >= -1) & (values <= 1))))
        else:
            print("WARNING: No valid NDVI pixels found.")

figure = root / "reports" / "figures" / "islamabad_ndvi_2024-10-16.png"

print("\nNDVI MAP EXISTS:", figure.exists())

if missing:
    print("\nVERIFICATION INCOMPLETE. Missing files:", missing)
else:
    print("\nAll six expected raster outputs exist.")

print("\nVerification finished.")
