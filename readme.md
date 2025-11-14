# GeoPackage Attribute Filler (Streamlit App)

This app allows you to:

- Upload a GeoPackage (.gpkg)
- Upload a CSV or Excel file containing attribute data **or** pick a bundled reference Excel workbook from `reference_data/`
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

## Using built-in reference Excel workbooks

1. Place your curated Excel file(s) inside the `reference_data/` folder.
2. Restart the Streamlit app so it can detect the new workbook.
3. In the **Single File Upload** section choose **Use stored reference workbook**, select the workbook + sheet, and continue the merge as usual.

> ⚠️ Only store non-sensitive data inside the repository if it will be shared publicly.

### Need a sample workbook without committing binaries?

Run the helper script to generate a lightweight example workbook locally:

```bash
python scripts/generate_sample_reference.py
```

The script recreates `reference_data/sample_substations.xlsx` on demand using pandas + openpyxl, so the repository can stay binary-free while still giving you a ready-to-use template. You can inspect the expected schema in [`reference_data/TEMPLATE.md`](reference_data/TEMPLATE.md) before crafting your own workbook.
