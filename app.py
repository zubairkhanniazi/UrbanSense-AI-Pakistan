from pathlib import Path
from datetime import datetime, timezone
import json
import platform
import re
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import rasterio
    from rasterio.enums import Resampling
    RASTERIO_AVAILABLE = True
except Exception:
    rasterio = None
    Resampling = None
    RASTERIO_AVAILABLE = False


# ============================================================
# APP CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="UrbanSense AI Pakistan",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
TABLES = ROOT / "reports" / "tables"
FIGURES = ROOT / "reports" / "figures"
PROCESSED = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"

CITIES = [
    "Islamabad",
    "Lahore",
    "Multan",
    "Karachi",
]

MODULES = [
    "Command Center",
    "Four-City NDVI Analysis",
    "City Explorer",
    "Quality & Validation",
    "Data Catalog",
    "Environmental Research",
    "Research Roadmap",
    "Reproducibility & Deployment",
]

ALL_OPTION = "ALL MODULES"

PALETTE = [
    "#176B55",
    "#B68A3A",
    "#247D78",
    "#779A6C",
    "#53768C",
]

CITY_INFO = {
    "Islamabad": {
        "date": "2024-10-16",
        "method": "Single-date observation",
        "raster": PROCESSED / "islamabad_2024_10_16"
                  / "ndvi_2024_10_16.tif",
        "valid_mask": PROCESSED / "islamabad_2024_10_16"
                      / "ndvi_valid_mask.tif",
        "crs": "EPSG:32643",
    },
    "Lahore": {
        "date": "2024-10-13",
        "method": "Single-date observation",
        "raster": PROCESSED / "lahore_2024_10_13"
                  / "ndvi_2024_10_13.tif",
        "valid_mask": PROCESSED / "lahore_2024_10_13"
                      / "ndvi_valid_mask.tif",
        "crs": "EPSG:32643",
    },
    "Multan": {
        "date": "2024-11-20",
        "method": "Single-date observation",
        "raster": PROCESSED / "multan_2024_11_20"
                  / "ndvi_2024-11-20.tif",
        "valid_mask": PROCESSED / "multan_2024_11_20"
                      / "ndvi_valid_mask.tif",
        "crs": "EPSG:32642",
    },
    "Karachi": {
        "date": "2024 multi-date",
        "method": "Three-date pixel-wise median composite",
        "raster": PROCESSED / "karachi_2024_multidate"
                  / "ndvi_median_composite_2024.tif",
        "valid_mask": PROCESSED / "karachi_2024_multidate"
                      / "ndvi_valid_mask_2024.tif",
        "crs": "EPSG:32642",
    },
}


# ============================================================
# PROFESSIONAL DESIGN
# ============================================================

st.markdown("""
<style>
:root {
    --forest: #102D23;
    --emerald: #176B55;
    --teal: #247D78;
    --gold: #B68A3A;
    --ivory: #F4F7F2;
    --border: #D8E5D9;
    --text: #17352A;
    --muted: #61786A;
}

.stApp {
    background: #F4F7F2;
    color: #17352A;
}

[data-testid="stHeader"] {
    background: rgba(244,247,242,.94);
}

[data-testid="stSidebar"] {
    background: linear-gradient(
        180deg, #102D23 0%, #183D30 65%, #102D23 100%
    );
    border-right: 1px solid #294B3B;
}

[data-testid="stSidebar"] * {
    color: #EAF2EB;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #B9D0BF;
}

.block-container {
    max-width: 1700px;
    padding-top: 1.4rem;
    padding-bottom: 3rem;
}

.hero {
    background: linear-gradient(
        115deg, #102D23 0%, #176B55 65%, #247D78 100%
    );
    border: 1px solid #39735A;
    border-bottom: 3px solid #B68A3A;
    border-radius: 18px;
    padding: 30px;
    margin-bottom: 22px;
    box-shadow: 0 9px 28px rgba(16,45,35,.12);
}

.hero h1 {
    color: #FFFFFF;
    font-size: clamp(1.8rem, 3vw, 2.5rem);
    font-weight: 800;
    letter-spacing: -1px;
    margin: 0;
}

.hero p {
    color: #DCECE2;
    font-size: 1rem;
    line-height: 1.7;
    margin: 12px 0 0;
}

h1, h2, h3 {
    color: #173D2D;
    letter-spacing: -.3px;
}

div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #D8E5D9;
    border-top: 3px solid #176B55;
    border-radius: 13px;
    padding: 16px;
    box-shadow: 0 4px 16px rgba(16,45,35,.05);
}

div[data-testid="stMetricLabel"] {
    color: #61786A;
}

div[data-testid="stMetricValue"] {
    color: #102D23;
    font-weight: 780;
}

.stButton > button,
.stDownloadButton > button {
    background: #176B55;
    color: #FFFFFF !important;
    border: 1px solid #176B55;
    border-radius: 9px;
    font-weight: 650;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background: #102D23;
    border-color: #B68A3A;
}

[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid #D8E5D9;
    border-radius: 11px;
    overflow: hidden;
}

[data-testid="stExpander"] {
    background: #FFFFFF;
    border: 1px solid #D8E5D9;
    border-radius: 10px;
}

.stTabs [data-baseweb="tab"] {
    background: #E7F0E8;
    border-radius: 8px 8px 0 0;
}

.stTabs [aria-selected="true"] {
    background: #176B55 !important;
    color: #FFFFFF !important;
    border-bottom: 3px solid #B68A3A !important;
}

a {
    color: #176B55;
}

hr {
    border-color: #D8E5D9;
}

.small-note {
    color: #61786A;
    font-size: .88rem;
    line-height: 1.6;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: .8rem;
        padding-right: .8rem;
    }
    .hero {
        padding: 20px;
    }
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILITIES
# ============================================================

def canonical_city(value):
    text = str(value or "").strip().lower()

    if "islamabad" in text or text == "ict":
        return "Islamabad"
    if "lahore" in text:
        return "Lahore"
    if "multan" in text:
        return "Multan"
    if "karachi" in text:
        return "Karachi"

    return str(value or "Unknown")


def read_csv(path):
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def find_column(frame, choices):
    lower_map = {
        str(column).strip().lower(): column
        for column in frame.columns
    }

    for choice in choices:
        if choice.lower() in lower_map:
            return lower_map[choice.lower()]

    return None


def inventory_files():
    roots = [
        (PROCESSED, "Processed data"),
        (INTERIM, "Interim data"),
        (TABLES, "Research tables"),
        (FIGURES, "Research figures"),
        (ROOT / "scripts", "Python scripts"),
    ]

    rows = []

    for folder, category in roots:
        if not folder.exists():
            continue

        try:
            paths = folder.rglob("*")
            for path in paths:
                if not path.is_file():
                    continue

                try:
                    stat = path.stat()
                    rows.append({
                        "filename": path.name,
                        "relative_path": str(
                            path.relative_to(ROOT)
                        ).replace("\\", "/"),
                        "category": category,
                        "extension": path.suffix.lower(),
                        "size_mb": round(
                            stat.st_size / (1024 * 1024), 3
                        ),
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(timespec="seconds"),
                    })
                except OSError:
                    continue
        except OSError:
            continue

    columns = [
        "filename", "relative_path", "category",
        "extension", "size_mb", "modified",
    ]

    return pd.DataFrame(rows, columns=columns)


# The pilot numbers below are fallback reference values from the
# previously recorded analysis. Existing CSV files take precedence.
PILOT_FALLBACK = pd.DataFrame([
    {
        "city": "Islamabad",
        "mean_ndvi": 0.426811,
        "median_ndvi": 0.413273,
        "valid_ndvi_pixels": 8859022,
        "method": "Single-date observation",
    },
    {
        "city": "Lahore",
        "mean_ndvi": 0.380551,
        "median_ndvi": 0.330091,
        "valid_ndvi_pixels": 16679259,
        "method": "Single-date observation",
    },
    {
        "city": "Multan",
        "mean_ndvi": 0.329971,
        "median_ndvi": 0.266264,
        "valid_ndvi_pixels": 35790342,
        "method": "Single-date observation",
    },
    {
        "city": "Karachi",
        "mean_ndvi": 0.193795,
        "median_ndvi": 0.174500,
        "valid_ndvi_pixels": 35411458,
        "method": "Three-date pixel-wise median composite",
    },
])


def build_comparison():
    path = TABLES / "four_city_ndvi_pilot_comparison.csv"
    raw = read_csv(path)

    if raw.empty:
        result = PILOT_FALLBACK.copy()
        result["evidence_source"] = "Recorded pilot fallback"
        return result

    city_col = find_column(
        raw, ["city", "study_area", "study area"]
    )
    mean_col = find_column(
        raw, ["mean_ndvi", "mean_ndvi_from_raster"]
    )

    if city_col is None or mean_col is None:
        result = PILOT_FALLBACK.copy()
        result["evidence_source"] = "Recorded pilot fallback"
        return result

    median_col = find_column(raw, ["median_ndvi"])
    pixels_col = find_column(
        raw, ["valid_ndvi_pixels", "valid_pixels"]
    )
    method_col = find_column(raw, ["method"])

    raw = raw.copy()
    raw["_city"] = raw[city_col].map(canonical_city)

    rows = []

    for _, fallback in PILOT_FALLBACK.iterrows():
        matches = raw[raw["_city"] == fallback["city"]]

        if matches.empty:
            row = fallback.to_dict()
            row["evidence_source"] = "Recorded pilot fallback"
            rows.append(row)
            continue

        record = matches.iloc[0]

        def number_or_default(column, default):
            if column is None:
                return default
            try:
                value = pd.to_numeric(
                    pd.Series([record[column]]),
                    errors="coerce",
                ).iloc[0]
                return float(value) if pd.notna(value) else default
            except Exception:
                return default

        method = fallback["method"]
        if method_col is not None and pd.notna(record[method_col]):
            method = str(record[method_col])

        rows.append({
            "city": fallback["city"],
            "mean_ndvi": number_or_default(
                mean_col, fallback["mean_ndvi"]
            ),
            "median_ndvi": number_or_default(
                median_col, fallback["median_ndvi"]
            ),
            "valid_ndvi_pixels": int(number_or_default(
                pixels_col, fallback["valid_ndvi_pixels"]
            )),
            "method": method,
            "evidence_source": "Local comparison CSV",
        })

    return pd.DataFrame(rows)


def build_quality():
    path = TABLES / "four_city_ndvi_raster_quality_audit.csv"
    raw = read_csv(path)

    if not raw.empty:
        city_col = find_column(raw, ["city", "study_area"])
        if city_col is not None:
            raw = raw.copy()
            raw["city"] = raw[city_col].map(canonical_city)
            raw["evidence_source"] = "Local quality audit CSV"
            return raw

    return pd.DataFrame([
        {
            "city": "Islamabad",
            "crs": "EPSG:32643",
            "valid_ndvi_pixels": 8859022,
            "mean_ndvi_from_raster": 0.426811,
            "minimum_ndvi": -0.816216,
            "maximum_ndvi": 0.917051,
            "pixels_outside_ndvi_range": 0,
            "evidence_source": "Recorded quality audit",
        },
        {
            "city": "Lahore",
            "crs": "EPSG:32643",
            "valid_ndvi_pixels": 16679259,
            "mean_ndvi_from_raster": 0.380552,
            "minimum_ndvi": -0.997709,
            "maximum_ndvi": 0.999691,
            "pixels_outside_ndvi_range": 0,
            "evidence_source": "Recorded quality audit",
        },
        {
            "city": "Multan",
            "crs": "EPSG:32642",
            "valid_ndvi_pixels": 35790342,
            "mean_ndvi_from_raster": 0.329971,
            "minimum_ndvi": -0.995546,
            "maximum_ndvi": 0.999404,
            "pixels_outside_ndvi_range": 0,
            "evidence_source": "Recorded quality audit",
        },
        {
            "city": "Karachi",
            "crs": "EPSG:32642",
            "valid_ndvi_pixels": 35411458,
            "mean_ndvi_from_raster": 0.193795,
            "minimum_ndvi": -0.998733,
            "maximum_ndvi": 0.999586,
            "pixels_outside_ndvi_range": 0,
            "evidence_source": "Recorded quality audit",
        },
    ])


@st.cache_data(show_spinner=False)
def load_raster_preview(path_string, modified_time, max_side=650):
    if not RASTERIO_AVAILABLE:
        return None, None

    try:
        with rasterio.open(path_string) as src:
            factor = min(
                1.0,
                max_side / max(src.width, src.height),
            )

            out_width = max(1, int(src.width * factor))
            out_height = max(1, int(src.height * factor))

            band = src.read(
                1,
                out_shape=(out_height, out_width),
                masked=True,
                resampling=Resampling.nearest,
            )

            values = np.ma.array(
                band, dtype=np.float32
            ).filled(np.nan)

            values[
                (~np.isfinite(values))
                | (values < -1.01)
                | (values > 1.01)
            ] = np.nan

            metadata = {
                "crs": str(src.crs),
                "resolution": str(src.res),
                "width": src.width,
                "height": src.height,
                "nodata": src.nodata,
                "bounds": str(src.bounds),
                "preview_shape": str(values.shape),
            }

            return values, metadata

    except Exception as exc:
        return None, {"error": str(exc)}


def figure_for_city(city):
    token = city.lower()

    if not FIGURES.exists():
        return None

    matches = [
        path for path in FIGURES.glob("*")
        if path.is_file()
        and token in path.name.lower()
        and path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]
    ]

    matches = sorted(matches)

    return matches[0] if matches else None


def source_registry():
    return pd.DataFrame([
        {
            "Dataset": "Sentinel-1 SAR",
            "Potential use": "Flood extent and radar change detection",
            "Official source": "ASF DAAC",
            "URL": "https://asf.alaska.edu/",
            "Project status": "Research extension; verify acquired assets",
        },
        {
            "Dataset": "Sentinel-2",
            "Potential use": "Vegetation and optical indices",
            "Official source": "Copernicus Data Space",
            "URL": "https://dataspace.copernicus.eu/",
            "Project status": "Four-city 2024 NDVI pilot exists",
        },
        {
            "Dataset": "Landsat Collection 2",
            "Potential use": "Land-surface temperature",
            "Official source": "USGS",
            "URL": "https://www.usgs.gov/landsat-missions",
            "Project status": "Planned extension",
        },
        {
            "Dataset": "VIIRS nighttime lights",
            "Potential use": "Nighttime illumination patterns",
            "Official source": "NASA LAADS DAAC",
            "URL": "https://ladsweb.modaps.eosdis.nasa.gov/",
            "Project status": "Planned extension",
        },
        {
            "Dataset": "CHIRPS",
            "Potential use": "Historical precipitation",
            "Official source": "Climate Hazards Center",
            "URL": "https://www.chc.ucsb.edu/data",
            "Project status": "Planned extension",
        },
        {
            "Dataset": "ERA5-Land",
            "Potential use": "Historical land and climate variables",
            "Official source": "Copernicus Climate Data Store",
            "URL": "https://cds.climate.copernicus.eu/",
            "Project status": "Planned extension",
        },
        {
            "Dataset": "WorldPop",
            "Potential use": "Population distribution and exposure context",
            "Official source": "WorldPop",
            "URL": "https://hub.worldpop.org/",
            "Project status": "Optional extension",
        },
    ])


# ============================================================
# LOAD PROJECT DATA
# ============================================================

comparison = build_comparison()
quality = build_quality()
inventory = inventory_files()

raster_inventory = inventory[
    inventory["extension"].isin([".tif", ".tiff"])
].copy()

csv_inventory = inventory[
    inventory["extension"] == ".csv"
].copy()

figure_inventory = inventory[
    inventory["extension"].isin(
        [".png", ".jpg", ".jpeg", ".webp"]
    )
].copy()

script_inventory = inventory[
    inventory["extension"] == ".py"
].copy()

comparison_path = TABLES / "four_city_ndvi_pilot_comparison.csv"
quality_path = TABLES / "four_city_ndvi_raster_quality_audit.csv"


# ============================================================
# SIDEBAR AND MULTI-MODULE WORKSPACE
# ============================================================

with st.sidebar:
    st.markdown("## 🌍 UrbanSense AI")
    st.caption("PAKISTAN · GEOSPATIAL RESEARCH")
    st.divider()

    selected_modules = st.multiselect(
        "INTELLIGENCE MODULES",
        options=[ALL_OPTION] + MODULES,
        default=["Command Center"],
        help=(
            "Choose one module, multiple modules, or ALL MODULES. "
            "Selected sections will appear together on the same page."
        ),
        key="final_module_selector",
    )

    if ALL_OPTION in selected_modules:
        active_modules = MODULES.copy()
    else:
        active_modules = selected_modules.copy()

    st.divider()

    focus_city = st.selectbox(
        "FOCUS CITY",
        ["All cities"] + CITIES,
        index=0,
    )

    st.caption("Research period: 2020–2025")
    st.caption("Current pilot: 2024")
    st.caption(
        "Local files detected at runtime are not automatically "
        "available on a remote deployment."
    )


# ============================================================
# GLOBAL HEADER
# ============================================================

st.markdown("""
<div class="hero">
    <h1>UrbanSense AI Pakistan</h1>
    <p>
        Multimodal Earth Observation · Urban Environmental Change ·
        Geospatial Analytics · Research Reproducibility
    </p>
</div>
""", unsafe_allow_html=True)

top = st.columns(4)
top[0].metric("Study cities", "4")
top[1].metric("Recorded NDVI pilots", f"{len(comparison)}")
top[2].metric("Local raster files", f"{len(raster_inventory):,}")
top[3].metric("Indexed research files", f"{len(inventory):,}")

st.caption(
    f"Dashboard generated at {datetime.now().astimezone().isoformat(timespec='seconds')}. "
    "Metrics describe local files and recorded pilot results, not independent "
    "validation of the complete research programme."
)

st.divider()


# ============================================================
# 1. COMMAND CENTER
# ============================================================

if "Command Center" in active_modules:
    st.header("01 · Research Command Center")

    st.write(
        "A high-level view of the four-city NDVI pilot, available project "
        "outputs and current scientific limitations."
    )

    a, b, c, d = st.columns(4)

    a.metric(
        "Mean NDVI · Islamabad",
        f"{comparison.loc[comparison['city']=='Islamabad', 'mean_ndvi'].iloc[0]:.3f}",
    )
    b.metric(
        "Mean NDVI · Lahore",
        f"{comparison.loc[comparison['city']=='Lahore', 'mean_ndvi'].iloc[0]:.3f}",
    )
    c.metric(
        "Mean NDVI · Multan",
        f"{comparison.loc[comparison['city']=='Multan', 'mean_ndvi'].iloc[0]:.3f}",
    )
    d.metric(
        "Mean NDVI · Karachi",
        f"{comparison.loc[comparison['city']=='Karachi', 'mean_ndvi'].iloc[0]:.3f}",
    )

    fig = px.bar(
        comparison,
        x="city",
        y="mean_ndvi",
        color="city",
        color_discrete_sequence=PALETTE,
        title="Recorded Mean NDVI — Four-City 2024 Pilot",
        labels={
            "city": "Study area",
            "mean_ndvi": "Mean NDVI",
        },
    )

    fig.update_layout(
        template="plotly_white",
        showlegend=False,
        yaxis_range=[-1, 1],
        paper_bgcolor="#F4F7F2",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=15, r=15, t=60, b=15),
    )

    st.plotly_chart(fig, width="stretch")

    st.markdown("### Current pilot summary")
    st.dataframe(
        comparison,
        hide_index=True,
        width="stretch",
    )

    st.warning(
        "Scientific comparison limitation: Islamabad, Lahore and Multan "
        "use single-date observations, whereas Karachi uses a three-date "
        "median composite. Acquisition dates, valid-pixel denominators and "
        "compositing methods differ. These means are descriptive and should "
        "not be presented as a controlled city ranking."
    )

    st.download_button(
        "Download four-city pilot summary",
        comparison.to_csv(index=False).encode("utf-8"),
        "urbansense_four_city_ndvi_summary.csv",
        "text/csv",
        key="download_command_summary",
    )


# ============================================================
# 2. FOUR-CITY NDVI ANALYSIS
# ============================================================

if "Four-City NDVI Analysis" in active_modules:
    st.divider()
    st.header("02 · Four-City NDVI Analysis")

    st.markdown("""
    **Research objective:** describe the distribution of satellite-derived
    vegetation indices across four Pakistani cities and establish a
    consistent basis for future temporal analysis.
    """)

    left, right = st.columns(2)

    with left:
        fig_mean = px.bar(
            comparison,
            x="city",
            y="mean_ndvi",
            color="city",
            color_discrete_sequence=PALETTE,
            title="Mean NDVI",
            labels={"city": "Study area", "mean_ndvi": "Mean NDVI"},
        )
        fig_mean.update_layout(
            template="plotly_white",
            showlegend=False,
            paper_bgcolor="#F4F7F2",
            plot_bgcolor="#FFFFFF",
        )
        st.plotly_chart(fig_mean, width="stretch")

    with right:
        fig_median = px.bar(
            comparison,
            x="city",
            y="median_ndvi",
            color="city",
            color_discrete_sequence=PALETTE,
            title="Median NDVI",
            labels={"city": "Study area", "median_ndvi": "Median NDVI"},
        )
        fig_median.update_layout(
            template="plotly_white",
            showlegend=False,
            paper_bgcolor="#F4F7F2",
            plot_bgcolor="#FFFFFF",
        )
        st.plotly_chart(fig_median, width="stretch")

    st.markdown("### Recorded valid-pixel counts")

    fig_pixels = px.bar(
        comparison,
        x="city",
        y="valid_ndvi_pixels",
        color="city",
        color_discrete_sequence=PALETTE,
        title="Number of valid NDVI pixels",
        labels={
            "city": "Study area",
            "valid_ndvi_pixels": "Valid pixels",
        },
    )
    fig_pixels.update_layout(
        template="plotly_white",
        showlegend=False,
        paper_bgcolor="#F4F7F2",
        plot_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig_pixels, width="stretch")

    st.markdown("### Interpretation guidance")
    st.markdown("""
    - NDVI describes relative vegetation greenness, not a direct measurement
      of biomass, ecological health or tree cover.
    - Negative and extreme values need interpretation using surface type,
      no-data handling and the source reflectance bands.
    - Pixel counts cannot be compared as city area unless the grids,
      pixel sizes, masks and boundary denominators are compatible.
    - A valid multi-year trend requires comparable seasonal windows,
      documented data quality and a consistent processing method.
    """)

    st.download_button(
        "Export NDVI comparison",
        comparison.to_csv(index=False).encode("utf-8"),
        "urbansense_ndvi_comparison.csv",
        "text/csv",
        key="download_ndvi_analysis",
    )


# ============================================================
# 3. CITY EXPLORER
# ============================================================

if "City Explorer" in active_modules:
    st.divider()
    st.header("03 · City Explorer")

    if focus_city == "All cities":
        selected_city = st.selectbox(
            "Choose a city for detailed inspection",
            CITIES,
            key="city_explorer_select",
        )
    else:
        selected_city = focus_city

    info = CITY_INFO[selected_city]
    row = comparison[comparison["city"] == selected_city].iloc[0]

    a, b, c = st.columns(3)

    a.metric("Mean NDVI", f"{row['mean_ndvi']:.5f}")
    b.metric("Median NDVI", f"{row['median_ndvi']:.5f}")
    c.metric(
        "Valid pixels",
        f"{int(row['valid_ndvi_pixels']):,}",
    )

    st.markdown(f"### {selected_city} — Pilot record")

    details = pd.DataFrame([{
        "City": selected_city,
        "Acquisition / composite": info["date"],
        "Method": info["method"],
        "Expected CRS": info["crs"],
        "Raster exists locally": info["raster"].exists(),
        "Valid mask exists locally": info["valid_mask"].exists(),
    }])

    st.dataframe(
        details,
        hide_index=True,
        width="stretch",
    )

    image_path = figure_for_city(selected_city)

    if image_path is not None:
        st.markdown("### Saved figure")
        st.image(
            str(image_path),
            caption=f"Existing local figure: {image_path.name}",
            width="stretch",
        )

    if info["raster"].exists():
        st.markdown("### NDVI raster preview")

        if RASTERIO_AVAILABLE:
            try:
                modified = info["raster"].stat().st_mtime

                with st.spinner("Reading raster preview..."):
                    raster, metadata = load_raster_preview(
                        str(info["raster"]),
                        modified,
                    )

                if raster is not None:
                    fig = px.imshow(
                        raster,
                        zmin=-1,
                        zmax=1,
                        color_continuous_scale=[
                            [0.0, "#8C5A44"],
                            [0.35, "#D8C9A2"],
                            [0.5, "#F7F7E8"],
                            [0.7, "#83B66D"],
                            [1.0, "#14532D"],
                        ],
                        aspect="auto",
                        origin="upper",
                        title=f"{selected_city} NDVI — Downsampled Preview",
                        labels={"color": "NDVI"},
                    )

                    fig.update_layout(
                        template="plotly_white",
                        paper_bgcolor="#F4F7F2",
                        plot_bgcolor="#FFFFFF",
                    )

                    st.plotly_chart(fig, width="stretch")

                    st.caption(
                        "This is a downsampled raster preview. It is not a "
                        "georeferenced web map. No new raster was generated."
                    )

                    with st.expander("Raster metadata"):
                        st.json(metadata)

                elif metadata:
                    st.warning(
                        f"Raster preview unavailable: "
                        f"{metadata.get('error', 'unknown error')}"
                    )

            except Exception as exc:
                st.warning(f"Raster inspection failed: {exc}")

        else:
            st.info(
                "Rasterio is not installed. Install the requirements "
                "to enable local GeoTIFF previews."
            )

    else:
        st.info(
            "The full-resolution raster is not available at this location. "
            "The summary statistics above come from the local comparison "
            "CSV when present, otherwise from the recorded pilot fallback."
        )

    st.markdown("### Research questions for this city")
    st.markdown("""
    1. How does NDVI vary across the city boundary?
    2. How sensitive are the summary statistics to masking and no-data rules?
    3. Can comparable observations be assembled for 2020–2025?
    4. How does vegetation change relate to land-surface temperature?
    """)


# ============================================================
# 4. QUALITY AND VALIDATION
# ============================================================

if "Quality & Validation" in active_modules:
    st.divider()
    st.header("04 · Quality & Validation Center")

    st.write(
        "The quality audit checks raster value ranges and the consistency "
        "of recorded statistics. It is not, by itself, independent "
        "validation of the source imagery or scientific interpretation."
    )

    if focus_city == "All cities":
        quality_view = quality.copy()
    else:
        quality_view = quality[
            quality["city"].map(canonical_city) == focus_city
        ].copy()

    st.dataframe(
        quality_view,
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Essential scientific checks")

    checks = [
        (
            "Reflectance scaling",
            "Verify provider-specific scale, offset, units and no-data handling.",
        ),
        (
            "Cloud and shadow masking",
            "Inspect Sentinel-2 SCL classes and validate the masking logic.",
        ),
        (
            "Spatial consistency",
            "Check CRS, grid alignment, boundary coverage and valid-pixel denominators.",
        ),
        (
            "Temporal consistency",
            "Use comparable seasons and documented compositing methods.",
        ),
        (
            "Independent validation",
            "Compare classifications with suitable reference labels where available.",
        ),
        (
            "Uncertainty",
            "Quantify sensitivity to thresholds, masking and observation availability.",
        ),
    ]

    for title, detail in checks:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.write(detail)

    sensitivity_path = TABLES / "pilot_ndvi_reflectance_sensitivity.csv"
    sensitivity = read_csv(sensitivity_path)

    if not sensitivity.empty:
        st.markdown("### Recorded reflectance sensitivity experiment")
        st.dataframe(
            sensitivity,
            hide_index=True,
            width="stretch",
        )

        st.caption(
            "Thresholds in this experiment use stored band units. "
            "Do not treat them as calibrated reflectance thresholds "
            "without verifying provider documentation."
        )

    distribution_path = TABLES / "pilot_ndvi_distribution_audit.csv"
    distribution = read_csv(distribution_path)

    if not distribution.empty:
        st.markdown("### NDVI distribution audit")
        st.dataframe(
            distribution,
            hide_index=True,
            width="stretch",
        )

    spatial_path = TABLES / "pilot_spatial_quality_audit.csv"
    spatial = read_csv(spatial_path)

    if not spatial.empty:
        st.markdown("### Spatial quality audit")
        st.dataframe(
            spatial,
            hide_index=True,
            width="stretch",
        )

    st.download_button(
        "Download displayed quality audit",
        quality_view.to_csv(index=False).encode("utf-8"),
        "urbansense_quality_audit.csv",
        "text/csv",
        key="download_quality_audit",
    )


# ============================================================
# 5. DATA CATALOG
# ============================================================

if "Data Catalog" in active_modules:
    st.divider()
    st.header("05 · Research Data Catalog")

    st.write(
        "An inventory of files detected within the project workspace. "
        "The catalog uses relative paths so it can run on another machine."
    )

    a, b, c, d = st.columns(4)

    a.metric("Indexed files", f"{len(inventory):,}")
    b.metric("Raster files", f"{len(raster_inventory):,}")
    c.metric("CSV files", f"{len(csv_inventory):,}")
    d.metric("Figures", f"{len(figure_inventory):,}")

    if inventory.empty:
        st.warning(
            "No files were detected in the indexed directories. "
            "Check that data/processed, reports and scripts are present."
        )
    else:
        search_text = st.text_input(
            "Search by filename or relative path",
            key="catalog_search",
        )

        categories = sorted(
            inventory["category"].dropna().unique().tolist()
        )

        selected_categories = st.multiselect(
            "File categories",
            categories,
            default=categories,
            key="catalog_categories",
        )

        catalog = inventory[
            inventory["category"].isin(selected_categories)
        ].copy()

        if search_text.strip():
            mask = (
                catalog["filename"].str.contains(
                    search_text, case=False, na=False
                )
                | catalog["relative_path"].str.contains(
                    search_text, case=False, na=False
                )
            )
            catalog = catalog[mask]

        a, b = st.columns(2)
        a.metric("Matching files", f"{len(catalog):,}")
        b.metric(
            "Combined size",
            f"{catalog['size_mb'].sum():,.2f} MB",
        )

        st.dataframe(
            catalog,
            hide_index=True,
            width="stretch",
        )

        st.download_button(
            "Export file catalog",
            catalog.to_csv(index=False).encode("utf-8"),
            "urbansense_data_catalog.csv",
            "text/csv",
            key="download_data_catalog",
        )

    st.markdown("### Recorded research tables")

    if not csv_inventory.empty:
        st.dataframe(
            csv_inventory,
            hide_index=True,
            width="stretch",
        )

    st.markdown("### Recorded research figures")

    if not figure_inventory.empty:
        st.dataframe(
            figure_inventory,
            hide_index=True,
            width="stretch",
        )


# ============================================================
# 6. ENVIRONMENTAL RESEARCH
# ============================================================

if "Environmental Research" in active_modules:
    st.divider()
    st.header("06 · Environmental Research Portfolio")

    st.write(
        "A research portfolio for extending the Sentinel-2 NDVI pilot "
        "into multimodal urban environmental analysis."
    )

    modules = [
        {
            "name": "Sentinel-2 vegetation",
            "purpose": "Vegetation indices and multi-year land-surface analysis.",
            "data": "Sentinel-2 surface reflectance and SCL quality information.",
            "outputs": "NDVI rasters, temporal summaries, coverage and quality reports.",
            "source": "https://dataspace.copernicus.eu/",
            "status": "2024 four-city pilot exists; multi-year consistency remains.",
        },
        {
            "name": "Sentinel-1 flood mapping",
            "purpose": "Radar-based candidate inundation mapping.",
            "data": "Suitable pre-event and post-event Sentinel-1 GRD scenes.",
            "outputs": "Flood extent maps, event summaries and validation metrics.",
            "source": "https://asf.alaska.edu/",
            "status": "Research extension; validate data and implementation.",
        },
        {
            "name": "Landsat surface temperature",
            "purpose": "Land-surface temperature and urban heat patterns.",
            "data": "Landsat Collection 2 Level-2 ST and quality bands.",
            "outputs": "Temperature rasters, seasonal statistics and heat comparisons.",
            "source": "https://www.usgs.gov/landsat-missions",
            "status": "Research extension; acquisition and processing required.",
        },
        {
            "name": "VIIRS nighttime lights",
            "purpose": "Spatial and temporal analysis of nighttime radiance.",
            "data": "Appropriate VIIRS nighttime-light products and quality flags.",
            "outputs": "Radiance summaries, temporal charts and change maps.",
            "source": "https://eogdata.mines.edu/products/vnl/",
            "status": "Research extension; data integration required.",
        },
        {
            "name": "Climate and rainfall",
            "purpose": "Historical precipitation and climate context.",
            "data": "CHIRPS, ERA5-Land or other documented products.",
            "outputs": "Monthly summaries, anomalies and city-level comparisons.",
            "source": "https://cds.climate.copernicus.eu/",
            "status": "Research extension; units and time coverage must be documented.",
        },
    ]

    for item in modules:
        with st.expander(item["name"], expanded=False):
            st.markdown(f"**Research objective:** {item['purpose']}")
            st.markdown(f"**Required data:** {item['data']}")
            st.markdown(f"**Potential deliverables:** {item['outputs']}")
            st.markdown(f"**Current project status:** {item['status']}")
            st.markdown(f"[Official data source]({item['source']})")

    st.markdown("### Multimodal integration principles")

    st.markdown("""
    - Harmonize spatial grids and administrative boundaries.
    - Document acquisition dates and justified temporal windows.
    - Preserve quality masks and valid-observation information.
    - Keep data provenance for every feature and output.
    - Avoid causal claims from simple correlations.
    - Use independent reference data before making predictive claims.
    """)

    st.warning(
        "This section defines research directions and potential outputs. "
        "A listed data source or methodology is not evidence that the "
        "corresponding dataset has been downloaded or analysed."
    )


# ============================================================
# 7. RESEARCH ROADMAP
# ============================================================

if "Research Roadmap" in active_modules:
    st.divider()
    st.header("07 · Research Roadmap")

    roadmap = pd.DataFrame([
        {
            "Phase": 1,
            "Workstream": "2024 pilot scientific audit",
            "Deliverable": "Verified scaling, masks, coverage and limitations",
            "Priority": "Critical",
            "Status": "Existing audits available; unresolved checks remain",
        },
        {
            "Phase": 2,
            "Workstream": "2020–2025 Sentinel-2 time series",
            "Deliverable": "Consistent annual and seasonal city products",
            "Priority": "High",
            "Status": "Requires multi-year acquisition and processing",
        },
        {
            "Phase": 3,
            "Workstream": "Statistical analysis and uncertainty",
            "Deliverable": "Trend estimates, sensitivity and confidence intervals",
            "Priority": "High",
            "Status": "Requires validated comparable observations",
        },
        {
            "Phase": 4,
            "Workstream": "Landsat urban heat",
            "Deliverable": "Quality-screened surface temperature analysis",
            "Priority": "High",
            "Status": "Planned extension",
        },
        {
            "Phase": 5,
            "Workstream": "Radar flood or climate extension",
            "Deliverable": "Documented analysis and suitable validation",
            "Priority": "Medium",
            "Status": "Planned extension",
        },
        {
            "Phase": 6,
            "Workstream": "Reproducible research publication",
            "Deliverable": "Report, figures, GitHub documentation and poster",
            "Priority": "High",
            "Status": "Build from verified results",
        },
    ])

    st.dataframe(
        roadmap,
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Proposed research questions")

    research_questions = [
        "How does vegetation vary seasonally and annually across the four cities?",
        "How sensitive are the results to cloud masking and valid-pixel criteria?",
        "Where are persistent vegetation change hotspots?",
        "How is vegetation associated with land-surface temperature?",
        "Can independently validated radar observations support event-specific flood mapping?",
    ]

    for index, question in enumerate(research_questions, 1):
        st.markdown(f"**RQ{index}.** {question}")

    st.markdown("### Suggested academic deliverables")
    st.markdown("""
    1. A thesis-style research report.
    2. A documented and reproducible GitHub repository.
    3. An academic research poster.
    4. A short research presentation.
    5. A clear record of contributions, limitations and validation.
    """)

    st.download_button(
        "Download research roadmap",
        roadmap.to_csv(index=False).encode("utf-8"),
        "urbansense_research_roadmap.csv",
        "text/csv",
        key="download_roadmap",
    )


# ============================================================
# 8. REPRODUCIBILITY AND DEPLOYMENT
# ============================================================

if "Reproducibility & Deployment" in active_modules:
    st.divider()
    st.header("08 · Reproducibility & Deployment")

    st.markdown("### Application environment")

    environment = pd.DataFrame([
        {"Property": "Python", "Value": sys.version.split()[0]},
        {"Property": "Platform", "Value": platform.platform()},
        {"Property": "Project root", "Value": str(ROOT)},
        {"Property": "Streamlit", "Value": st.__version__},
        {"Property": "Rasterio available", "Value": str(RASTERIO_AVAILABLE)},
        {"Property": "Comparison CSV", "Value": str(comparison_path.exists())},
        {"Property": "Quality audit CSV", "Value": str(quality_path.exists())},
    ])

    st.dataframe(
        environment,
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Reproducibility checklist")

    for item in [
        "Record source product identifiers and acquisition dates.",
        "Keep processing scripts and parameter choices under version control.",
        "Document reflectance scale, offset and no-data handling.",
        "Use consistent boundaries, spatial grids and temporal windows.",
        "Keep validation outputs separate from model training data.",
        "Report limitations and uncertainty alongside results.",
        "Retain small CSV summaries and figures needed by the deployed app.",
    ]:
        st.markdown(f"- {item}")

    manifest = {
        "project": "UrbanSense AI Pakistan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "study_cities": CITIES,
        "target_period": "2020-2025",
        "pilot_comparison_csv_available": comparison_path.exists(),
        "quality_audit_csv_available": quality_path.exists(),
        "comparison_source": (
            "Local comparison CSV"
            if comparison_path.exists()
            else "Recorded pilot fallback"
        ),
        "quality_source": (
            "Local quality audit CSV"
            if quality_path.exists()
            else "Recorded quality audit fallback"
        ),
        "rasterio_available": RASTERIO_AVAILABLE,
        "indexed_file_count": int(len(inventory)),
        "raster_file_count": int(len(raster_inventory)),
        "figure_file_count": int(len(figure_inventory)),
        "modules": MODULES,
        "scientific_status": (
            "Pilot dashboard; additional validation and planned analyses "
            "must be completed before scientific conclusions."
        ),
    }

    st.download_button(
        "Download project manifest (JSON)",
        json.dumps(manifest, indent=2).encode("utf-8"),
        "urbansense_project_manifest.json",
        "application/json",
        key="download_manifest",
    )

    report = f"""# UrbanSense AI Pakistan

## Project summary

UrbanSense AI Pakistan is a geospatial research application for
satellite-based environmental analysis across Islamabad, Lahore,
Multan and Karachi.

## Current pilot

- Target research period: 2020–2025
- Existing recorded pilot: 2024
- Primary existing analysis: Sentinel-2 NDVI
- Application: Streamlit
- Research focus: environmental change, quality assurance and
  reproducible geospatial processing

## Current data evidence

Comparison CSV available: {comparison_path.exists()}

Quality audit CSV available: {quality_path.exists()}

Indexed local files: {len(inventory)}

Raster files detected: {len(raster_inventory)}

## Important scientific limitation

The four-city pilot combines single-date observations for Islamabad,
Lahore and Multan with a three-date median composite for Karachi.
The results are descriptive and are not a controlled city ranking.

Reflectance scaling, masking, valid-pixel denominators, temporal
comparability and independent validation must be resolved before
strong scientific conclusions are drawn.

## Proposed extensions

1. Consistent multi-year Sentinel-2 analysis.
2. Statistical trends and uncertainty.
3. Landsat surface temperature.
4. Sentinel-1 flood mapping.
5. Climate data integration.
6. Reproducible research publication.

Planned extensions must not be represented as completed analyses.
"""

    st.download_button(
        "Download project summary report",
        report.encode("utf-8"),
        "urbansense_project_summary.md",
        "text/markdown",
        key="download_project_report",
    )

    st.markdown("### Deploy to Streamlit Community Cloud")

    st.markdown("""
    1. Push the project to a GitHub repository.
    2. Ensure `app.py`, `requirements.txt`, and required small report
       assets are committed.
    3. Open [Streamlit Community Cloud](https://share.streamlit.io/).
    4. Connect the repository and select branch `main`.
    5. Set the application entrypoint to `app.py`.
    6. Deploy and inspect the logs.

    **Important:** deployment runs on a remote server. Files on your
    Windows computer are not automatically uploaded. Large satellite
    rasters should normally remain outside Git; use an appropriate
    cloud data source or external storage if the deployed app needs them.
    """)


# ============================================================
# EMPTY SELECTION
# ============================================================

if not active_modules:
    st.info(
        "No modules selected. Choose one or more Intelligence Modules "
        "from the sidebar, or select ALL MODULES."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown("""
<div class="small-note">
<strong>UrbanSense AI Pakistan</strong><br>
Geospatial research application · Four Pakistani study cities ·
Sentinel-2 NDVI pilot · Reproducibility-first design<br><br>
Scientific integrity: visualizations and recorded pilot statistics do not
by themselves establish independent validation, causation, or scientific
comparability. Planned research modules are identified separately from
implemented analyses.
</div>
""", unsafe_allow_html=True)
