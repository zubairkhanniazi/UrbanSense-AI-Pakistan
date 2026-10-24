"""Study-area configuration for UrbanSense AI Pakistan."""

PROJECT_NAME = "UrbanSense AI Pakistan"

ANALYSIS_START = "2020-01-01"
ANALYSIS_END = "2025-12-31"

CITIES = {
    "Lahore": {
        "latitude": 31.5204,
        "longitude": 74.3587,
    },
    "Islamabad": {
        "latitude": 33.6844,
        "longitude": 73.0479,
    },
    "Multan": {
        "latitude": 30.1575,
        "longitude": 71.5249,
    },
    "Karachi": {
        "latitude": 24.8607,
        "longitude": 67.0011,
    },
}

SATELLITE_DATA_SOURCES = {
    "sentinel1": "SAR flood mapping",
    "sentinel2": "Multispectral land-cover analysis",
    "landsat": "Land-surface temperature analysis",
    "viirs": "Nighttime-light analysis",
}

if __name__ == "__main__":
    print(f"Project: {PROJECT_NAME}")
    print(f"Analysis period: {ANALYSIS_START} to {ANALYSIS_END}")
    print(f"Study cities: {', '.join(CITIES.keys())}")
    print(f"Planned satellite sources: {len(SATELLITE_DATA_SOURCES)}")
