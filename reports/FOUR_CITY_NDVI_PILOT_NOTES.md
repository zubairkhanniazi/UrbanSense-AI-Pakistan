# UrbanSense AI Pakistan — Four-City NDVI Pilot

## 1. Purpose

This pilot establishes an initial satellite-based vegetation-analysis
workflow for Islamabad, Lahore, Multan and Karachi.

The current comparison uses Sentinel-2 imagery from 2024. It is a
preliminary milestone, not the completed 2020–2025 study.

## 2. Study areas and acquisition dates

| Study area | Acquisition date(s) | Processing method |
|---|---|---|
| Islamabad Capital Territory | 2024-10-16 | Single-date NDVI |
| Lahore | 2024-10-13 | Single-date NDVI |
| Multan | 2024-11-20 | Single-date NDVI |
| Karachi | 2024-10-09, 2024-11-06, 2024-11-26 | Pixel-wise median of valid observations |

The four city-level means are descriptive statistics. They must not
be interpreted as a scientifically validated ranking because the
acquisition dates and temporal compositing methods differ.

## 3. Preliminary results

| City | Mean NDVI | Median NDVI | Valid NDVI pixels |
|---|---:|---:|---:|
| Islamabad | 0.426811 | 0.413273 | 8,859,022 |
| Lahore | 0.380551 | 0.330091 | 16,679,259 |
| Multan | 0.329971 | 0.266264 | 35,790,342 |
| Karachi | 0.193795 | 0.174500 | 35,411,458 |

These values reproduce the current raster-derived comparison.
They are preliminary and should not yet support definitive
environmental conclusions.

## 4. Technical audit

The raster audit reported:

- All four NDVI rasters were readable.
- All four rasters had defined coordinate reference systems.
- No stored valid NDVI pixels were outside [-1, 1].
- Raster-derived means agreed with the comparison table within
  approximately 0.000001.
- Valid pixel counts matched the comparison table.
- Islamabad and Lahore use EPSG:32643.
- Multan and Karachi use EPSG:32642.

Different local UTM zones are acceptable for individual city
processing, but must be considered when preparing common-grid
spatial analyses.

## 5. Karachi multi-date observation limitations

The current Karachi observation-count raster reports:

- 56,978,697 pixels with zero valid observations.
- 31,703,690 pixels with one valid observation.
- 3,707,768 pixels with two valid observations.
- Zero pixels with three valid observations.

The observation-count raster covers a rectangular grid around
Karachi. Zero counts include pixels outside the administrative
boundary, so they must not be interpreted as missing observations
inside the city without applying the city-boundary mask.

No grid pixels had three valid observations. This limitation must
be investigated before drawing conclusions about the composite.

## 6. Outstanding scientific quality checks

Before final scientific reporting:

1. Verify Sentinel-2 reflectance scaling, offsets and no-data
   handling against the source metadata.
2. Investigate near-extreme NDVI values, especially values close
   to -1 and +1, using red and NIR reflectance diagnostics.
3. Independently review pixel-level cloud, shadow and cirrus
   masking, including SCL class handling.
4. Calculate valid coverage inside each actual study-area polygon.
5. Assess temporal consistency and the consequences of comparing
   single-date scenes with a three-date median composite.
6. Define a consistent seasonal and annual compositing protocol
   before extending the analysis to 2020–2025.
7. Document validation methods, uncertainty and any excluded pixels.

The current checks establish raster integrity and numerical
consistency, not independent scientific validation.

## 7. Current outputs

Comparison table:
reports/tables/four_city_ndvi_pilot_comparison.csv

Raster quality audit:
reports/tables/four_city_ndvi_raster_quality_audit.csv

Comparison chart:
reports/figures/four_city_ndvi_pilot_comparison.png

Karachi composite:
data/processed/karachi_2024_multidate/ndvi_median_composite_2024.tif

Karachi observation count:
data/processed/karachi_2024_multidate/ndvi_observation_count_2024.tif

## 8. Project status

Completed preliminary milestone:
- Administrative study-area boundaries.
- Sentinel-2 scene discovery and acquisition planning.
- Initial NDVI processing for four study areas.
- Preliminary four-city comparison.
- Raster integrity and numerical consistency audit.

Still pending:
- Further scientific quality validation.
- Consistent multi-year and multi-sensor processing.
- Sentinel-1 flood analysis.
- Landsat surface-temperature analysis.
- VIIRS and climate-data integration.
- Validated machine-learning models.
- Interactive dashboard and final research report.

Do not describe the full UrbanSense AI Pakistan project as complete
until these remaining research and software components are implemented
and evaluated.
