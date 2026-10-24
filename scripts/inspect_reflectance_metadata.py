from pathlib import Path
import rasterio

ROOT = Path(__file__).resolve().parents[1]

PILOTS = [
    ("Islamabad", ROOT / "data" / "processed"
     / "islamabad_2024_10_16"),
    ("Lahore", ROOT / "data" / "processed"
     / "lahore_2024_10_13"),
]

for city, folder in PILOTS:
    print("\n" + "=" * 60)
    print(city.upper(), "REFLECTANCE METADATA")
    print("=" * 60)

    for band in ("red_mosaic_10m.tif", "nir_mosaic_10m.tif"):
        path = folder / band

        with rasterio.open(path) as src:
            print(f"\nFile: {band}")
            print("Data type:", src.dtypes[0])
            print("No-data value:", src.nodata)
            print("Scale:", src.scales[0])
            print("Offset:", src.offsets[0])
            print("Units:", src.units[0] if src.units else None)

            tags = src.tags()
            print("Dataset metadata tags:", tags)

            band_tags = src.tags(1)
            print("Band metadata tags:", band_tags)

print("\nMetadata inspection finished. No files changed.")
