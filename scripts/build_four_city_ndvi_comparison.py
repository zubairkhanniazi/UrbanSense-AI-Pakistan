from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"

TABLES.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

SOURCES = [
    {
        "city": "Islamabad",
        "date": "2024-10-16",
        "file": TABLES / "islamabad_ndvi_pilot_summary.csv",
        "method": "Single-date observation",
    },
    {
        "city": "Lahore",
        "date": "2024-10-13",
        "file": TABLES / "lahore_ndvi_pilot_summary.csv",
        "method": "Single-date observation",
    },
    {
        "city": "Multan",
        "date": "2024-11-20",
        "file": TABLES / "multan_ndvi_2024-11-20.csv",
        "method": "Single-date observation",
    },
    {
        "city": "Karachi",
        "date": "2024-10-09; 2024-11-06; 2024-11-26",
        "file": TABLES / "karachi_ndvi_composite_summary_2024.csv",
        "method": "Three-date pixel-wise median composite",
    },
]

def number(row, candidates):
    for column in candidates:
        if column in row.index and pd.notna(row[column]):
            try:
                return float(row[column])
            except (ValueError, TypeError):
                continue
    return np.nan

def read_city(source):
    path = source["file"]

    if not path.exists():
        raise FileNotFoundError(
            f"Missing summary for {source['city']}: {path}"
        )

    df = pd.read_csv(path)

    if df.empty:
        raise ValueError(f"Summary is empty: {path}")

    # Islamabad and Lahore summaries contain several pixel groups.
    # Select the row representing all valid NDVI pixels.
    if "metric" in df.columns:
        match = df[
            df["metric"].astype(str).str.contains(
                "All valid clear-class NDVI pixels",
                case=False,
                regex=False,
            )
        ]
        if match.empty:
            raise ValueError(
                f"Could not identify the overall NDVI row in {path}"
            )
        row = match.iloc[0]
    else:
        row = df.iloc[0]

    mean_ndvi = number(row, ["mean_ndvi"])
    median_ndvi = number(
        row,
        ["median_ndvi", "approx_median_ndvi"],
    )
    valid_pixels = number(
        row,
        [
            "valid_ndvi_pixels",
            "valid_composite_pixels",
            "valid_pixels",
            "pixel_count",
        ],
    )
    coverage_percent = number(
        row,
        [
            "valid_ndvi_percent_of_classified",
            "valid_composite_pixel_percent",
            "valid_pixel_percent_of_boundary_grid",
        ],
    )

    if not np.isfinite(mean_ndvi) or not np.isfinite(median_ndvi):
        raise ValueError(
            f"Missing mean or median NDVI in {path}"
        )

    return {
        "city": source["city"],
        "acquisition_date": source["date"],
        "method": source["method"],
        "valid_ndvi_pixels": (
            int(valid_pixels) if np.isfinite(valid_pixels) else None
        ),
        "mean_ndvi": mean_ndvi,
        "median_ndvi": median_ndvi,
        "reported_valid_pixel_percent": coverage_percent,
        "comparison_status": "Preliminary; methods differ",
    }

print("=" * 70)
print("FOUR-CITY NDVI PILOT COMPARISON")
print("=" * 70)

rows = []

for source in SOURCES:
    print(f"Reading {source['city']}...")
    rows.append(read_city(source))

comparison = pd.DataFrame(rows)

csv_path = TABLES / "four_city_ndvi_pilot_comparison.csv"
comparison.to_csv(csv_path, index=False, encoding="utf-8")

print("\nCOMPARISON TABLE")
print(
    comparison[
        [
            "city",
            "mean_ndvi",
            "median_ndvi",
            "valid_ndvi_pixels",
            "method",
        ]
    ].to_string(index=False)
)

# Create a side-by-side descriptive comparison.
x = np.arange(len(comparison))
bar_width = 0.36

fig, ax = plt.subplots(figsize=(11, 6))

ax.bar(
    x - bar_width / 2,
    comparison["mean_ndvi"],
    bar_width,
    label="Mean NDVI",
)
ax.bar(
    x + bar_width / 2,
    comparison["median_ndvi"],
    bar_width,
    label="Median NDVI",
)

ax.set_xticks(x)
ax.set_xticklabels(comparison["city"])
ax.set_ylabel("NDVI")
ax.set_title(
    "Four-City NDVI Pilot Comparison — 2024\n"
    "Descriptive results; acquisition methods differ"
)
ax.axhline(0, linewidth=0.8)
ax.set_ylim(-1, 1)
ax.legend()
ax.grid(axis="y", alpha=0.25)

fig.text(
    0.5,
    0.015,
    "Karachi uses a multi-date median composite; other cities use "
    "single-date observations. Do not interpret differences as "
    "validated city rankings.",
    ha="center",
    fontsize=8,
    wrap=True,
)

fig.tight_layout(rect=[0, 0.06, 1, 1])

chart_path = FIGURES / "four_city_ndvi_pilot_comparison.png"
fig.savefig(chart_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nOUTPUTS CREATED")
print("Comparison CSV:", csv_path)
print("Comparison chart:", chart_path)

print(
    "\nRESEARCH LIMITATIONS\n"
    "- This is a preliminary descriptive comparison.\n"
    "- Acquisition dates and temporal compositing differ.\n"
    "- Reflectance scaling and offsets still require verification.\n"
    "- Valid-pixel percentages use different denominators in the "
    "existing summaries and should not be compared directly.\n"
    "- The results do not establish statistically significant "
    "differences between cities."
)
