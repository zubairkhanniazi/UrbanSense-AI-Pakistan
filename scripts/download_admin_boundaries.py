from pathlib import Path
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "boundaries"
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://www.geoboundaries.org/api/current/gbOpen/PAK/ADM2/"

def download(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "UrbanSense-AI-Pakistan/0.1"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()

print("1. Retrieving boundary metadata...")
metadata = json.loads(download(API_URL).decode("utf-8-sig"))

if isinstance(metadata, list):
    if not metadata:
        raise RuntimeError("The boundary API returned no records.")
    metadata = metadata[0]

download_url = metadata.get("gjDownloadURL")
if not download_url:
    raise RuntimeError("No GeoJSON download URL was provided.")

metadata_path = OUT_DIR / "pakistan_adm2_metadata.json"
metadata_path.write_text(
    json.dumps(metadata, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("2. Downloading Pakistan ADM2 GeoJSON...")
geojson_bytes = download(download_url)

geojson_path = OUT_DIR / "pakistan_adm2.geojson"
geojson_path.write_bytes(geojson_bytes)

print("3. Inspecting downloaded features...")
geojson = json.loads(geojson_bytes.decode("utf-8-sig"))
features = geojson.get("features", [])

print("\nDOWNLOAD SUCCESSFUL")
print("Boundary level:", metadata.get("boundaryType"))
print("Boundary year:", metadata.get("boundaryYearRepresented"))
print("Source:", metadata.get("boundarySource"))
print("Administrative units reported:", metadata.get("admUnitCount"))
print("Features downloaded:", len(features))
print("GeoJSON file:", geojson_path)
print("Metadata file:", metadata_path)

if features:
    print("\nAvailable property fields:")
    print(list(features[0].get("properties", {}).keys()))

    city_names = ("lahore", "islamabad", "multan", "karachi")
    matches = []

    for feature in features:
        props = feature.get("properties", {})
        searchable = " ".join(str(v) for v in props.values()).lower()

        if any(name in searchable for name in city_names):
            matches.append(props)

    print("\nPossible matching administrative units:", len(matches))
    for props in matches:
        print(json.dumps(props, ensure_ascii=False))

print("\nNote: Administrative districts are not necessarily urban footprints.")
