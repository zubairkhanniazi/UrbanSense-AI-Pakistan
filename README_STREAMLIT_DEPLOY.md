# UrbanSense AI Pakistan — Streamlit Deployment

## Run locally

Activate the project virtual environment, then run:

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m streamlit run app.py

## Deploy

1. Push app.py, requirements.txt, .streamlit/config.toml and required
   small report tables/figures to GitHub.
2. Open https://share.streamlit.io/
3. Select the repository, branch main and entrypoint app.py.
4. Deploy and inspect the application logs.

## Data availability

The application uses relative project paths. Local Windows files do not
automatically appear in Streamlit Community Cloud.

Commit the small CSV and figure assets needed by the application.
Avoid committing large satellite rasters. If full-resolution imagery is
required online, configure an appropriate remote data source or storage.

## Research integrity

The recorded four-city NDVI pilot is descriptive. The three single-date
observations and Karachi's three-date median composite are not directly
comparable without further harmonization.

Reflectance calibration, masking, temporal consistency, uncertainty and
independent validation must be resolved before strong scientific claims.

The dashboard describes planned environmental analyses separately from
completed work.
