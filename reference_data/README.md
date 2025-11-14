# Reference Attribute Workbooks

Place pre-approved Excel workbooks in this folder to make them available inside the app without having to upload them each time.

Because the repository intentionally avoids tracking binary files, you can recreate the demo workbook locally with:

```bash
python scripts/generate_sample_reference.py
```

Need a quick refresher on the expected schema? See [`TEMPLATE.md`](TEMPLATE.md).

## Usage

1. Copy your formatted Excel template(s) into this directory.
2. Restart the Streamlit app.
3. Choose **Use stored reference workbook** in the UI and select the workbook + sheet to merge into your GeoPackage.

> ⚠️ Avoid storing confidential data here if the repository is public.
