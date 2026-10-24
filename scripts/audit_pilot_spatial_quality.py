from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_FILE = (
    ROOT / "data" / "processed"
    / "study_area_boundaries.geojson"
)

OUTPUT_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

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

SUMMARY_FILE = OUTPUT_DIR / "pilot_spatial_quality_audit.csv"
CHART_FILE = FIGURE_DIR / "pilot_ndvi_mean_comparison.png"

if not BOUNDARY_FILE.exists():
    raise FileNotFoundError(f"Missing boundary file: {BOUNDARY_FILE}")

boundaries = gpd.read_file(BOUNDARY_FILE)

if boundaries.crs is None:
    raise ValueError("Boundary file has no CRS.")

results = []

print("=" * 70)
print("URBANSENSE AI — PILOT SPATIAL QUALITY AUDIT")
print("=" * 70)

for pilot in PILOTS:
    city = pilot["city"]
    folder = pilot["folder"]

    ndvi_path = folder / pilot["ndvi"]
    red_path = folder / "red_mosaic_10m.tif"
    nir_path = folder / "nir_mosaic_10m.tif"
    scl_path = folder / "scl_aligned_10m.tif"

    required = [ndvi_path, red_path, nir_path, scl_path]

    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"{city}: missing {path}")

    city_boundary = boundaries[
        boundaries["shapeName"] == city
    ].copy()

    if city_boundary.empty:
        raise ValueError(f"Boundary not found for {city}")

    with rasterio.open(ndvi_path) as ndvi_src, \
         rasterio.open(red_path) as red_src, \
         rasterio.open(nir_path) as nir_src, \
         rasterio.open(scl_path) as scl_src:

        if ndvi_src.crs is None:
            raise ValueError(f"{city}: NDVI raster has no CRS.")

        reference = (
            ndvi_src.shape,
            ndvi_src.transform,
            ndvi_src.crs,
        )

        for name, src in [
            ("Red", red_src),
            ("NIR", nir_src),
            ("SCL", scl_src),
        ]:
            if (
                src.shape != reference[0]
                or src.transform != reference[1]
                or src.crs != reference[2]
            ):
                raise ValueError(
                    f"{city}: {name} grid does not match NDVI grid."
                )

        ndvi = ndvi_src.read(1).astype(np.float32)
        red = red_src.read(1)
        nir = nir_src.read(1)
        scl = scl_src.read(1)

        nodata = ndvi_src.nodata
        pixel_area = abs(
            ndvi_src.transform.a * ndvi_src.transform.e
            - ndvi_src.transform.b * ndvi_src.transform.d
        )

        projected_boundary = city_boundary.to_crs(ndvi_src.crs)
        geometry_list = [
            geom.__geo_interface__
            for geom in projected_boundary.geometry
            if geom is not None and not geom.is_empty
        ]

        if not geometry_list:
            raise ValueError(f"{city}: no valid boundary geometry.")

        # True for raster pixels whose centers fall inside the boundary.
        inside = geometry_mask(
            geometry_list,
            out_shape=ndvi_src.shape,
            transform=ndvi_src.transform,
            invert=True,
            all_touched=False,
        )

        polygon_area = projected_boundary.geometry.area.sum()

        if polygon_area <= 0:
            raise ValueError(f"{city}: invalid boundary area.")

        inside_count = int(inside.sum())

        red_valid = inside & (red > 0)
        nir_valid = inside & (nir > 0)
        scl_classified = inside & (scl > 0)

        ndvi_valid = (
            inside
            & np.isfinite(ndvi)
            & (ndvi >= -1)
            & (ndvi <= 1)
        )

        if nodata is not None:
            ndvi_valid &= ndvi != nodata

        values = ndvi[ndvi_valid]

        # Estimate the fraction of the entire administrative area
        # represented by rasterized pixels and valid NDVI pixels.
        grid_area_pct = 100 * inside_count * pixel_area / polygon_area
        ndvi_area_pct = 100 * ndvi_valid.sum() * pixel_area / polygon_area
        red_area_pct = 100 * red_valid.sum() * pixel_area / polygon_area
        nir_area_pct = 100 * nir_valid.sum() * pixel_area / polygon_area

        # These are pixel-count fractions within the rasterized boundary.
        cloud_shadow_classes = np.isin(scl, [3, 8, 9, 10, 11])
        cloud_shadow_count = int(
            (cloud_shadow_classes & scl_classified).sum()
        )

        cloud_shadow_pct = (
            100 * cloud_shadow_count / scl_classified.sum()
            if scl_classified.any() else np.nan
        )

        row = {
            "study_area": city,
            "acquisition_date": pilot["date"],
            "crs": str(ndvi_src.crs),
            "pixel_size_m": round(np.sqrt(pixel_area), 2),
            "administrative_area_km2": round(
                polygon_area / 1_000_000, 3
            ),
            "boundary_grid_coverage_est_percent": round(
                grid_area_pct, 3
            ),
            "red_area_coverage_est_percent": round(
                red_area_pct, 3
            ),
            "nir_area_coverage_est_percent": round(
                nir_area_pct, 3
            ),
            "valid_ndvi_area_est_percent": round(
                ndvi_area_pct, 3
            ),
            "valid_ndvi_pixels": int(values.size),
            "classified_scl_pixels": int(scl_classified.sum()),
            "cloud_shadow_cirrus_snow_class_percent": round(
                cloud_shadow_pct, 3
            ) if np.isfinite(cloud_shadow_pct) else None,
            "mean_ndvi": float(values.mean()) if values.size else None,
            "median_ndvi": float(np.median(values)) if values.size else None,
            "min_ndvi": float(values.min()) if values.size else None,
            "max_ndvi": float(values.max()) if values.size else None,
            "scl_vegetation_class_percent_of_valid_ndvi": (
                round(
                    100 * (ndvi_valid & (scl == 4)).sum()
                    / values.size,
                    3,
                ) if values.size else None
            ),
        }

        results.append(row)

        print(f"\n{city} | {pilot['date']}")
        print("-" * 55)
        print(f"Administrative area: {row['administrative_area_km2']} km²")
        print(
            "Raster-grid coverage estimate: "
            f"{row['boundary_grid_coverage_est_percent']:.2f}%"
        )
        print(
            "Valid NDVI area estimate: "
            f"{row['valid_ndvi_area_est_percent']:.2f}%"
        )
        print("Valid NDVI pixels:", row["valid_ndvi_pixels"])
        print("Mean NDVI:", row["mean_ndvi"])
        print("Median NDVI:", row["median_ndvi"])

df = pd.DataFrame(results)
df.to_csv(SUMMARY_FILE, index=False, encoding="utf-8")

# Exploratory chart: descriptive comparison, not a controlled
# city-to-city or year-to-year scientific conclusion.
plot_df = df.dropna(subset=["mean_ndvi"])

fig, ax = plt.subplots(figsize=(9, 5))

ax.bar(
    plot_df["study_area"],
    plot_df["mean_ndvi"],
)

ax.set_ylabel("Mean NDVI")
ax.set_title(
    "Pilot Mean NDVI Comparison\n"
    "Different cities, October 2024"
)
ax.set_ylim(-1, 1)
ax.tick_params(axis="x", rotation=15)
ax.grid(axis="y", alpha=0.25)

fig.tight_layout()
fig.savefig(CHART_FILE, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\n" + "=" * 70)
print("PILOT AUDIT SUMMARY")
print("=" * 70)
print(df.to_string(index=False))

print("\nSummary CSV:", SUMMARY_FILE)
print("Comparison chart:", CHART_FILE)

print(
    "\nIMPORTANT: Coverage estimates use raster pixel counts and "
    "nominal pixel area, so boundary-edge estimates are approximate. "
    "SCL classes 3, 8, 9, 10 and 11 are grouped here for screening; "
    "the group includes snow/ice as well as cloud-related classes. "
    "These checks do not independently validate every pixel or "
    "prove that the scenes are scientifically comparable."
)
