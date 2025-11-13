# GeoPackage Attribute Filler (Streamlit App)

This app allows you to:

- Upload a GeoPackage (.gpkg)
- Upload a CSV or Excel file containing attribute data
- Join the data on a selected key field
- Download the updated GeoPackage
- Upload one or more ZIP bundles, each containing a GeoPackage (`.gpkg`) and a CSV/Excel file that share the same base name
- Configure the join fields for every bundle individually
- Merge the attributes without creating duplicate columns
- Download a cleaned GeoPackage output for each uploaded bundle

## How to run locally:

```bash
pip install -r requirements.txt
streamlit run app.py
```
