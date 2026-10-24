from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "interim"

plan_file = DATA / "sentinel2_master_acquisition_plan.json"
summary_file = DATA / "sentinel2_master_plan_summary.csv"

with plan_file.open("r", encoding="utf-8") as f:
    plan = json.load(f)

summary = pd.read_csv(summary_file)

cities = [
    "Islamabad Capital Territory",
    "Karachi",
    "Lahore",
    "Multan",
]
years = list(range(2020, 2026))
expected = {(city, year) for city in cities for year in years}

actual = [
    (group["study_area"], int(group["year"]))
    for group in plan
]

print("=" * 65)
print("MASTER ACQUISITION PLAN VALIDATION")
print("=" * 65)

print("Expected city-year groups:", len(expected))
print("Actual city-year groups:", len(plan))
print("Duplicate groups:", len(actual) - len(set(actual)))
print("Missing city-year groups:", len(expected - set(actual)))

print("\nStatus counts:")
print(summary["status"].value_counts(dropna=False).to_string())

print("\nStrategy counts:")
print(summary["strategy"].value_counts(dropna=False).to_string())

print("\nGroups requiring review:")
review = summary[
    ~summary["status"].astype(str).str.startswith("PLANNED")
]

if review.empty:
    print("None")
else:
    print(
        review[
            ["study_area", "year", "scene_count", "status"]
        ].to_string(index=False)
    )

print("\nSelected scenes by city and year:")
print(
    summary.pivot(
        index="study_area",
        columns="year",
        values="scene_count",
    ).to_string()
)

print("\nValidation finished.")
