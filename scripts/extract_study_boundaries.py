from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "data" / "raw" / "boundaries" / "pakistan_adm2.geojson"
OUTPUT_DIR = ROOT / "data" / "processed"
FIGURE_DIR = ROOT / "reports" / "figures"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "Lahore",
    "Islamabad Capital Territory",
    "Multan",
    "Karachi",
}

print("Loading Pakistan administrative boundaries...")
boundaries = gpd.read_file(INPUT_FILE)

if boundaries.crs is None:
    raise ValueError("The input boundary dataset has no CRS defined.")

if "shapeName" not in boundaries.columns:
    raise ValueError("Expected property 'shapeName' was not found.")

# Select the four exact administrative units.
selected = boundaries[
    boundaries["shapeName"].isin(TARGETS)
].copy()

found = set(selected["shapeName"])
missing = TARGETS - found

if missing:
    raise ValueError(f"Missing expected study areas: {sorted(missing)}")

# Use a global equal-area projection for comparable area estimates.
equal_area = selected.to_crs("EPSG:6933")
selected["area_km2"] = equal_area.geometry.area / 1_000_000

# Save selected boundaries in geographic coordinates.
geojson_path = OUTPUT_DIR / "study_area_boundaries.geojson"
selected.to_file(geojson_path, driver="GeoJSON")

# Save a small table of study-area metadata and area estimates.
summary = pd.DataFrame({
    "study_area": selected["shapeName"].values,
    "boundary_type": selected["shapeType"].values,
    "source_reference_year": [2019] * len(selected),
    "area_km2_estimate": selected["area_km2"].round(2).values,
    "geometry_crs": ["EPSG:4326"] * len(selected),
})

csv_path = OUTPUT_DIR / "study_area_summary.csv"
summary.to_csv(csv_path, index=False)

# Calculate label positions in a projected CRS to avoid
# calculating centroids directly in longitude/latitude.
centroids = equal_area.geometry.centroid.to_crs("EPSG:4326")

# Create a map of the selected administrative boundaries.
fig, ax = plt.subplots(figsize=(11, 9))

selected.plot(
    ax=ax,
    column="shapeName",
    alpha=0.35,
    edgecolor="black",
    linewidth=1.0,
    legend=False,
)

for name, point in zip(selected["shapeName"], centroids.geometry):
    ax.annotate(
        name,
        (point.x, point.y),
        xytext=(5, 5),
        textcoords="offset points",
        fontsize=9,
    )

ax.set_xlim(60, 78)
ax.set_ylim(22, 36)
ax.set_xlabel("Longitude (degrees east)")
ax.set_ylabel("Latitude (degrees north)")
ax.set_title(
    "UrbanSense AI Pakistan\n"
    "Selected Administrative Study Areas — ADM2 (2019)"
)
ax.grid(True, linestyle="--", alpha=0.35)

fig.tight_layout()

map_path = FIGURE_DIR / "study_area_boundaries.png"
fig.savefig(map_path, dpi=220, bbox_inches="tight")
plt.close(fig)

print("\nSUCCESS: Four study-area boundaries extracted.")
print("\nArea estimates:")
print(summary.to_string(index=False))

print("\nFiles created:")
print("GeoJSON:", geojson_path)
print("Summary CSV:", csv_path)
print("Boundary map:", map_path)

print("\nArea estimates represent administrative units,")
print("not built-up urban footprints or current boundaries.")
