from pathlib import Path
import json

import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_scene_search_results.json"
)

TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"

TABLE_DIR.mkdir(parents=True, exist_ok=True)
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

CITIES = [
    "Lahore",
    "Islamabad Capital Territory",
    "Multan",
    "Karachi",
]

YEARS = list(range(2020, 2026))

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Search results not found: {INPUT_FILE}"
    )

with INPUT_FILE.open("r", encoding="utf-8") as file:
    records = json.load(file)

if not records:
    raise ValueError("The search results contain no scenes.")

df = pd.DataFrame(records)

required = [
    "study_area",
    "year",
    "item_id",
    "datetime_utc",
    "cloud_cover_percent",
]

missing_columns = [col for col in required if col not in df.columns]

if missing_columns:
    raise ValueError(f"Missing fields: {missing_columns}")

df["year"] = pd.to_numeric(df["year"], errors="coerce")
df["cloud_cover_percent"] = pd.to_numeric(
    df["cloud_cover_percent"], errors="coerce"
)
df["datetime_utc"] = pd.to_datetime(
    df["datetime_utc"], errors="coerce", utc=True
)

# Check basic metadata quality.
invalid_cloud = (
    df["cloud_cover_percent"].isna()
    | ~df["cloud_cover_percent"].between(0, 100)
)

invalid_dates = df["datetime_utc"].isna()
duplicate_rows = df.duplicated(
    subset=["study_area", "year", "item_id"]
).sum()

print("=" * 65)
print("SENTINEL-2 METADATA QUALITY CONTROL")
print("=" * 65)
print("Total candidate records:", len(df))
print("Unique scene IDs:", df["item_id"].nunique())
print("Duplicate city/year/scene records:", duplicate_rows)
print("Invalid cloud-cover records:", int(invalid_cloud.sum()))
print("Invalid acquisition dates:", int(invalid_dates.sum()))

# Summarize selected candidates by city and year.
summary = (
    df.groupby(["study_area", "year"], as_index=False)
    .agg(
        candidate_count=("item_id", "size"),
        unique_scene_count=("item_id", "nunique"),
        mean_cloud_cover_pct=("cloud_cover_percent", "mean"),
        min_cloud_cover_pct=("cloud_cover_percent", "min"),
        max_cloud_cover_pct=("cloud_cover_percent", "max"),
        earliest_acquisition=("datetime_utc", "min"),
        latest_acquisition=("datetime_utc", "max"),
    )
)

summary["mean_cloud_cover_pct"] = (
    summary["mean_cloud_cover_pct"].round(2)
)
summary["min_cloud_cover_pct"] = (
    summary["min_cloud_cover_pct"].round(2)
)
summary["max_cloud_cover_pct"] = (
    summary["max_cloud_cover_pct"].round(2)
)

# Check coverage for every expected city/year combination.
expected = {
    (city, year)
    for city in CITIES
    for year in YEARS
}

observed = set(
    zip(
        summary["study_area"],
        summary["year"].astype(int),
    )
)

missing_combinations = sorted(expected - observed)

print("\nCandidate scenes per city/year:")
print(
    summary.pivot(
        index="study_area",
        columns="year",
        values="candidate_count",
    ).fillna(0).to_string()
)

print("\nMissing city/year combinations:", len(missing_combinations))

for combination in missing_combinations:
    print("Missing:", combination)

# Save a reproducible summary table.
csv_path = TABLE_DIR / "sentinel2_search_quality_summary.csv"

summary.to_csv(
    csv_path,
    index=False,
    date_format="%Y-%m-%dT%H:%M:%SZ",
)

# Plot mean scene-level cloud cover for selected candidates.
fig, ax = plt.subplots(figsize=(11, 6))

for city in CITIES:
    city_data = summary[
        summary["study_area"] == city
    ].sort_values("year")

    ax.plot(
        city_data["year"],
        city_data["mean_cloud_cover_pct"],
        marker="o",
        linewidth=2,
        label=city,
    )

ax.set_title(
    "Sentinel-2 Candidate Scenes: Mean Scene-Level Cloud Cover"
)
ax.set_xlabel("Year")
ax.set_ylabel("Mean cloud cover (%)")
ax.set_xticks(YEARS)
ax.set_ylim(bottom=0)
ax.grid(True, linestyle="--", alpha=0.35)
ax.legend()
fig.tight_layout()

plot_path = FIGURE_DIR / "sentinel2_candidate_cloud_summary.png"
fig.savefig(plot_path, dpi=200, bbox_inches="tight")
plt.close(fig)

print("\nOUTPUTS CREATED")
print("Summary CSV:", csv_path)
print("Cloud summary chart:", plot_path)

print("\nIMPORTANT RESEARCH LIMITATIONS")
print(
    "- Only up to five selected candidates per city/year "
    "were retained."
)
print(
    "- Cloud cover is a scene-level value, not the cloud "
    "percentage inside each study area."
)
print(
    "- These summaries do not establish temporal "
    "representativeness or scientific suitability."
)

if invalid_cloud.any() or invalid_dates.any():
    print("\nWARNING: Some records need metadata review.")

if missing_combinations:
    print("WARNING: Some city/year combinations are missing.")
else:
    print("Coverage check: all 24 city/year combinations present.")
