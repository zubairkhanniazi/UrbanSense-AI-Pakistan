from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT / "data" / "interim"
    / "sentinel2_scene_search_results.json"
)

OUTPUT_DIR = ROOT / "data" / "interim"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Search results not found: {INPUT_FILE}"
    )

with INPUT_FILE.open("r", encoding="utf-8") as file:
    records = json.load(file)

if not records:
    raise ValueError("No Sentinel-2 candidates were found.")

df = pd.DataFrame(records)

required = [
    "study_area",
    "year",
    "item_id",
    "datetime_utc",
    "cloud_cover_percent",
    "assets",
]

missing = [column for column in required if column not in df.columns]
if missing:
    raise ValueError(f"Missing required fields: {missing}")

df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
df["cloud_cover_percent"] = pd.to_numeric(
    df["cloud_cover_percent"], errors="raise"
)

df["acquisition_datetime"] = pd.to_datetime(
    df["datetime_utc"], errors="coerce", utc=True
)

if df["acquisition_datetime"].isna().any():
    raise ValueError("Some candidate scenes have invalid dates.")

if not df["cloud_cover_percent"].between(0, 30).all():
    print("WARNING: Some scenes exceed the intended 30% cloud limit.")

# Extract acquisition month for later seasonal matching.
df["acquisition_date"] = (
    df["acquisition_datetime"].dt.strftime("%Y-%m-%d")
)
df["acquisition_month"] = df["acquisition_datetime"].dt.month

# Rank candidates within each city and year.
df = df.sort_values(
    [
        "study_area",
        "year",
        "cloud_cover_percent",
        "acquisition_datetime",
        "item_id",
    ],
    ascending=True,
)

# Save the complete ranked shortlist.
ranked_path = OUTPUT_DIR / "sentinel2_ranked_candidates.csv"

ranked = df.copy()
ranked["assets"] = ranked["assets"].apply(
    lambda value: json.dumps(value, ensure_ascii=False)
)

ranked.to_csv(ranked_path, index=False, encoding="utf-8")

# Select one lowest-cloud candidate per city and year.
best = df.drop_duplicates(
    subset=["study_area", "year"],
    keep="first",
).copy()

expected_count = 4 * 6
if len(best) != expected_count:
    raise ValueError(
        f"Expected {expected_count} city-year selections, "
        f"but found {len(best)}."
    )

# Record asset names, but do not download imagery yet.
best["asset_names"] = best["assets"].apply(
    lambda assets: ", ".join(sorted(assets.keys()))
    if isinstance(assets, dict) else ""
)

selection_columns = [
    "study_area",
    "year",
    "acquisition_date",
    "acquisition_month",
    "cloud_cover_percent",
    "item_id",
    "mgrs_tile",
    "item_url",
    "asset_names",
]

selection = best[selection_columns].copy()

selection_path = (
    OUTPUT_DIR / "sentinel2_best_cloud_candidates.csv"
)
selection.to_csv(selection_path, index=False, encoding="utf-8")

print("=" * 70)
print("SENTINEL-2 PRELIMINARY CANDIDATE SELECTION")
print("=" * 70)

print("Candidates ranked:", len(df))
print("City-year selections:", len(selection))

print("\nLowest-cloud candidate for each city and year:")
print(selection.to_string(index=False))

print("\nAcquisition-month distribution among retained candidates:")
print(
    df["acquisition_month"]
    .value_counts()
    .sort_index()
    .rename_axis("month")
    .to_string()
)

all_asset_names = sorted({
    key
    for assets in df["assets"]
    if isinstance(assets, dict)
    for key in assets
})

print("\nAvailable asset names:")
print(", ".join(all_asset_names))

print("\nFILES CREATED")
print("Ranked shortlist:", ranked_path)
print("Preliminary selections:", selection_path)

print("\nIMPORTANT")
print(
    "These are the lowest-cloud candidates among the retained "
    "search results, not necessarily the best scenes in the "
    "complete satellite archive."
)
print(
    "Scene coverage and seasonal consistency must be checked "
    "before selecting imagery for scientific analysis."
)
