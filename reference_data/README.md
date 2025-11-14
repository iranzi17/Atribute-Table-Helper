# Reference Attribute Workbooks

Place pre-approved Excel workbooks anywhere under this folder tree to make them available inside the app without having to upload them each time (subfolders are supported, so feel free to organize by project or region).

Because the repository intentionally avoids tracking binary files, you can recreate the demo workbook locally with:

```bash
python scripts/generate_sample_reference.py
```

Need a quick refresher on the expected schema? See [`TEMPLATE.md`](TEMPLATE.md).

## Usage

1. Copy your formatted `.xlsx` or `.xlsm` template(s) into this directory (or a subdirectory).
2. Restart the Streamlit app.
3. Choose **Use stored reference workbook** in the UI, select the workbook + sheet, review the automatic schema preview, and merge into your GeoPackage as usual. When a sheet stores multiple substations or administrative areas, pick the relevant column + value so only those rows are merged.
4. The first few rows are rendered inside the UI so you can verify that you picked the right sheet/key before running the merge.

All Excel artifacts inside this folder are ignored by `.gitignore`, so you can keep local, potentially sensitive workbooks out of version control while still benefiting from the streamlined workflow.

> ⚠️ Avoid storing confidential data here if the repository is public.
