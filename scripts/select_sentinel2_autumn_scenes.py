from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

INPUT = (
    ROOT / "data" / "interim"
    / "sentinel2_same_day_tile_coverage.csv"
)
OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT = OUTPUT_DIR / "sentinel2_autumn_full_coverage_candidates.csv"

if not INPUT.exists():
    raise FileNotFoundError(f"Coverage results not found: {INPUT}")

df = pd.read_csv(INPUT)

required = [
    "study_area",
    "year",
    "acquisition_date",
    "tile_count",
    "boundary_coverage_percent",
    "mean_scene_cloud_percent",
    "item_ids",
]

missing_columns = [c for c in required if c not in df.columns]
if missing_columns:
    raise ValueError(f"Missing columns: {missing_columns}")

df["year"] = pd.to_numeric(df["year"], errors="coerce")
df["acquisition_date"] = pd.to_datetime(
    df["acquisition_date"], errors="coerce"
)
df["boundary_coverage_percent"] = pd.to_numeric(
    df["boundary_coverage_percent"], errors="coerce"
)
df["mean_scene_cloud_percent"] = pd.to_numeric(
    df["mean_scene_cloud_percent"], errors="coerce"
)

df = df.dropna(
    subset=[
        "study_area",
        "year",
        "acquisition_date",
        "boundary_coverage_percent",
        "mean_scene_cloud_percent",
    ]
).copy()

df["year"] = df["year"].astype(int)
df["month"] = df["acquisition_date"].dt.month

# Provisional seasonal window: October and November.
# Require at least 99% geometric coverage.
autumn = df[
    df["month"].isin([10, 11])
    & (df["boundary_coverage_percent"] >= 99.0)
].copy()

cities = [
    "Islamabad Capital Territory",
    "Karachi",
    "Lahore",
    "Multan",
]
years = list(range(2020, 2026))

print("=" * 65)
print("AUTUMN SENTINEL-2 COVERAGE SCREENING")
print("=" * 65)
print("All recorded date groups:", len(df))
print("October-November groups with >=99% coverage:", len(autumn))

if not autumn.empty:
    print("\nQualifying candidates per city and year:")
    counts = (
        autumn.groupby(["study_area", "year"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=cities, columns=years, fill_value=0)
    )
    print(counts.to_string())

    # Prefer lower cloud cover, then greater coverage, then earlier date.
    autumn = autumn.sort_values(
        [
            "study_area",
            "year",
            "mean_scene_cloud_percent",
            "boundary_coverage_percent",
            "acquisition_date",
        ],
        ascending=[True, True, True, False, True],
    )

    selected = autumn.drop_duplicates(
        subset=["study_area", "year"],
        keep="first",
    ).copy()

    selected["acquisition_date"] = (
        selected["acquisition_date"].dt.strftime("%Y-%m-%d")
    )

    selected.to_csv(OUTPUT, index=False, encoding="utf-8")

    print("\nPRELIMINARY AUTUMN SELECTIONS")
    print(
        selected[
            [
                "study_area",
                "year",
                "acquisition_date",
                "tile_count",
                "boundary_coverage_percent",
                "mean_scene_cloud_percent",
            ]
        ].to_string(index=False)
    )

    chosen = set(zip(selected["study_area"], selected["year"]))
else:
    selected = pd.DataFrame()
    chosen = set()
    print("\nNo qualifying October-November groups were found.")
    print("We will need to evaluate a wider seasonal window.")

expected = {
    (city, year)
    for city in cities
    for year in years
}
missing = sorted(expected - chosen)

print("\nSelected city-year combinations:", len(chosen), "of", len(expected))
print("Combinations still needing a suitable scene:", len(missing))

for city, year in missing:
    print("NEEDS REVIEW:", city, year)

print("\nOutput file:", OUTPUT)
print(
    "\nIMPORTANT: This is a preliminary geometric and scene-level "
    "cloud screen. Pixel-level cloud masking and seasonal "
    "consistency still need validation."
)
