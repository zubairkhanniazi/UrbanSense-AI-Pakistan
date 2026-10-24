from pathlib import Path
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_master_acquisition_plan.json"
)

with PLAN_FILE.open("r", encoding="utf-8") as f:
    groups = json.load(f)

targets = [
    ("Islamabad Capital Territory", 2024),
    ("Lahore", 2024),
]

checked_urls = set()

print("=" * 70)
print("ORIGINAL SENTINEL-2 ASSET METADATA")
print("=" * 70)

for city, year in targets:
    matches = [
        g for g in groups
        if g.get("study_area") == city
        and int(g.get("year", 0)) == year
    ]

    print(f"\n{'=' * 60}")
    print(f"{city} | {year}")
    print("=" * 60)

    if len(matches) != 1:
        print("ERROR: Expected exactly one master-plan group.")
        continue

    for scene in matches[0].get("scenes", []):
        item_id = scene.get("item_id", "")
        url = scene.get("item_url", "")

        print(f"\nScene: {item_id}")

        if not url:
            print("ERROR: No original STAC item URL in the plan.")
            continue

        if url in checked_urls:
            print("Already inspected.")
            continue

        checked_urls.add(url)

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "UrbanSense-AI-Pakistan/1.0"},
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                item = json.loads(response.read().decode("utf-8"))

            print("STAC item ID:", item.get("id"))
            properties = item.get("properties", {})

            for key in (
                "s2:processing_baseline",
                "s2:product_uri",
                "datetime",
            ):
                if key in properties:
                    print(f"{key}: {properties[key]}")

            assets = item.get("assets", {})

            for asset_name in ("red", "nir", "scl"):
                asset = assets.get(asset_name)

                if asset is None:
                    print(f"\n{asset_name}: not found under this exact asset key")
                    continue

                bands = asset.get("raster:bands", [])
                print(f"\nAsset: {asset_name}")
                print("Media type:", asset.get("type"))
                print("Roles:", asset.get("roles"))

                if not bands:
                    print("No raster:bands scale metadata supplied.")
                    continue

                for index, band in enumerate(bands, start=1):
                    print(f"Band {index} metadata:")
                    print("  Data type:", band.get("data_type"))
                    print("  Scale:", band.get("scale"))
                    print("  Offset:", band.get("offset"))
                    print("  No-data:", band.get("nodata"))
                    print("  Unit:", band.get("unit"))
                    print("  Spatial resolution:", band.get("spatial_resolution"))

        except Exception as exc:
            print("METADATA REQUEST FAILED:")
            print(f"  {type(exc).__name__}: {exc}")

print("\nMetadata inspection finished.")
print(
    "If the catalog does not provide scale metadata, "
    "we must verify the provider's documentation before "
    "choosing a reflectance threshold."
)
