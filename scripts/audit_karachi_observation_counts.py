from pathlib import Path
import numpy as np
import rasterio

path = Path(
    "data/processed/karachi_2024_multidate/"
    "ndvi_observation_count_2024.tif"
)

if not path.exists():
    raise FileNotFoundError(f"Missing raster: {path}")

counts = np.zeros(4, dtype=np.int64)

with rasterio.open(path) as src:
    print("CRS:", src.crs)
    print("Resolution:", src.res)
    print("Dimensions:", src.width, "x", src.height)

    for _, window in src.block_windows(1):
        values = src.read(1, window=window)
        inside = values <= 3

        counts += np.bincount(
            values[inside].ravel(),
            minlength=4
        )[:4]

for n, count in enumerate(counts):
    print(f"Pixels with {n} valid observations: {count:,}")

print("Observation-count audit finished.")
