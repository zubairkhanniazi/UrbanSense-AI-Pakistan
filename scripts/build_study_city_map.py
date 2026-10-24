from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import geopandas as gpd
import matplotlib.pyplot as plt

from urbansense.config.cities import (
    PROJECT_NAME,
    ANALYSIS_START,
    ANALYSIS_END,
    CITIES,
)

# Prepare the four study-city reference points
records = [
    {
        "city": name,
        "longitude": info["longitude"],
        "latitude": info["latitude"],
    }
    for name, info in CITIES.items()
]

gdf = gpd.GeoDataFrame(
    records,
    geometry=gpd.points_from_xy(
        [item["longitude"] for item in records],
        [item["latitude"] for item in records],
    ),
    crs="EPSG:4326",
)

# Define output locations
figure_dir = PROJECT_ROOT / "reports" / "figures"
data_dir = PROJECT_ROOT / "data" / "processed"

figure_dir.mkdir(parents=True, exist_ok=True)
data_dir.mkdir(parents=True, exist_ok=True)

map_path = figure_dir / "study_city_reference_map.png"
geojson_path = data_dir / "study_city_reference_points.geojson"

# Export geospatial reference data
gdf.to_file(geojson_path, driver="GeoJSON")

# Create the first research visualization
fig, ax = plt.subplots(figsize=(10, 8))

gdf.plot(
    ax=ax,
    markersize=100,
    edgecolor="black",
)

for _, city in gdf.iterrows():
    ax.annotate(
        city["city"],
        (city.geometry.x, city.geometry.y),
        xytext=(8, 7),
        textcoords="offset points",
        fontsize=10,
    )

ax.set_title(
    f"{PROJECT_NAME}\n"
    f"Study Cities: {ANALYSIS_START[:4]}–{ANALYSIS_END[:4]}"
)

ax.set_xlabel("Longitude (degrees east)")
ax.set_ylabel("Latitude (degrees north)")
ax.set_xlim(65, 77)
ax.set_ylim(22, 36)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(map_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nSUCCESS: Study-city map created.")
print("Map:", map_path)
print("GeoJSON:", geojson_path)
print("Cities:", ", ".join(gdf["city"]))
print("CRS:", gdf.crs)
print("Note: Reference points are approximate, not city boundaries.")
