import os
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import streamlit as st
from openpyxl import load_workbook
import json


REFERENCE_DATA_DIR = Path(__file__).parent / "reference_data"
SUPPORTED_REFERENCE_EXTENSIONS = (".xlsx", ".xlsm")
PREVIEW_ROW_COUNT = 20

# Persistent name-memory file (maps equipment_type -> user-chosen filename)
NAME_MEMORY_PATH = Path(__file__).parent / "name_memory.json"


def load_name_memory() -> dict:
    """Load the name memory JSON file if present, otherwise return empty dict."""
    try:
        if NAME_MEMORY_PATH.exists():
            with open(NAME_MEMORY_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        # Corrupt or unreadable file — ignore and start fresh
        return {}
    return {}


def save_name_memory(mapping: dict):
    """Persist the mapping to disk (best-effort)."""
    try:
        with open(NAME_MEMORY_PATH, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Silently ignore failures to avoid disrupting the app UX
        pass


def set_saved_name(equipment_type: str, name: str, memory: dict):
    """Save a single mapping (in-memory and persist to disk)."""
    if not equipment_type or not name:
        return
    memory[equipment_type] = name
    save_name_memory(memory)


# Load memory on startup
name_memory = load_name_memory()


def _reset_stream(stream):
    """Seek to the beginning of a stream if possible."""

    if hasattr(stream, "seek"):
        try:
            stream.seek(0)
        except Exception:
            pass


def read_tabular_data(source):
    """Load a CSV/Excel file, handling common encoding issues for CSV uploads."""

    if isinstance(source, (str, Path)):
        suffix = Path(source).suffix.lower()
    else:
        suffix = Path(source.name).suffix.lower()

    if suffix == ".csv":
        # First, behave exactly like the previous implementation by allowing
        # pandas to pick its default encoding (UTF-8). This ensures that
        # uploads that already worked continue to do so without any changes.
        _reset_stream(source)
        try:
            return pd.read_csv(source)
        except UnicodeDecodeError:
            pass

        # If a UnicodeDecodeError occurs, iterate through a few common
        # fallbacks before resorting to a lossy-but-safe decode.
        encodings = ("utf-8-sig", "latin-1")
        for encoding in encodings:
            _reset_stream(source)
            try:
                return pd.read_csv(source, encoding=encoding)
            except UnicodeDecodeError:
                continue

        _reset_stream(source)
        return pd.read_csv(source, encoding="utf-8", errors="replace")

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        _reset_stream(source)
        return pd.read_excel(source)

    raise ValueError(f"Unsupported file type: {suffix}")


def clean_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop fully-empty rows and forward-fill partial empty rows.

    This helps spreadsheets where repeated groups omit repeated values
    (e.g., Substation/Bay/Name) on subsequent rows. Behaves as a best-effort
    preprocessing step and leaves non-DataFrame inputs untouched.
    """
    try:
        if not isinstance(df, pd.DataFrame):
            return df
        # Remove rows that are completely empty
        df = df.dropna(how="all")
        if df.empty:
            return df
        # Forward-fill remaining blanks so grouped rows inherit prior values
        df = df.ffill()
        return df
    except Exception:
        # On any failure, return the original DF to avoid breaking the workflow
        return df


def get_reference_workbooks():
    """Return mapping of workbook label -> path for bundled Excel files."""

    if not REFERENCE_DATA_DIR.exists():
        return {}

    workbooks = {}
    for workbook in sorted(
        p
        for p in REFERENCE_DATA_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_REFERENCE_EXTENSIONS
    ):
        label = workbook.relative_to(REFERENCE_DATA_DIR).as_posix()
        workbooks[label] = workbook

    return workbooks


def get_sheet_names(workbook_path: Path):
    """Return available sheet names for the selected workbook."""

    try:
        excel_file = pd.ExcelFile(workbook_path)
        return excel_file.sheet_names
    except Exception:
        return []


def describe_reference_sheet(workbook_path: Path, sheet_name: str):
    """Return metadata describing the requested worksheet."""

    wb = None
    try:
        wb = load_workbook(workbook_path, read_only=True, data_only=True)
        worksheet = wb[sheet_name]
        header_values = next(
            worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
            (),
        )
        headers = [value for value in header_values if value is not None]
        # subtract header row from total count if present
        row_count = max(worksheet.max_row - (1 if headers else 0), 0)
        column_count = worksheet.max_column
        return {
            "rows": row_count,
            "columns": column_count,
            "headers": headers,
        }
    except Exception:
        return None
    finally:
        if wb is not None:
            wb.close()


def load_reference_preview(workbook_path: Path, sheet_name: str, max_rows: int = PREVIEW_ROW_COUNT):
    """Return a lightweight preview of the sheet for UI display."""

    try:
        preview = pd.read_excel(
            workbook_path,
            sheet_name=sheet_name,
            nrows=max_rows,
        )
        return preview
    except Exception:
        return pd.DataFrame()


REFERENCE_DATA_DIR = Path(__file__).parent / "reference_data"


def get_reference_workbooks():
    """Return mapping of workbook label -> path for bundled Excel files."""

    if not REFERENCE_DATA_DIR.exists():
        return {}

    workbooks = {}
    for workbook in sorted(REFERENCE_DATA_DIR.glob("*.xlsx")):
        workbooks[workbook.name] = workbook
    return workbooks


def get_sheet_names(workbook_path: Path):
    """Return available sheet names for the selected workbook."""

    try:
        excel_file = pd.ExcelFile(workbook_path)
        return excel_file.sheet_names
    except Exception:
        return []


st.set_page_config(
    page_title="Clean GPKG Attribute Filler",
    page_icon="🗂️",
    layout="centered",
)

st.markdown(
    """
    <style>
    .stApp {
        font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
        background: #f3f6fb;
    }
    .main > div {
        padding-top: 1rem;
    }
    .app-card {
        background: #ffffff;
        padding: 2rem;
        border-radius: 18px;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
        border: 1px solid rgba(15, 23, 42, 0.06);
        margin-bottom: 1.5rem;
    }
    .app-card h3 {
        margin-top: 0;
        margin-bottom: 1.2rem;
        font-size: 1.35rem;
        font-weight: 600;
        color: #1f2a37;
    }
    .stFileUploader, .stTextInput, .stSelectbox, .stButton button {
        border-radius: 12px !important;
    }
    .stFileUploader > div {
        border-radius: 16px;
        border: 2px dashed rgba(37, 99, 235, 0.3);
        padding: 1rem;
        background: rgba(59, 130, 246, 0.05);
    }
    .stTextInput > div > div, .stSelectbox > div > div {
        border-radius: 12px;
    }
    .section-subtext {
        color: #4b5563;
        margin-bottom: 1rem;
    }
    .stButton button {
        font-weight: 600;
        padding: 0.6rem 1.4rem;
        border-radius: 12px;
    }
    footer {visibility: hidden;}
    .custom-footer {
        text-align: center;
        padding: 1.5rem 0 0.5rem;
        color: #6b7280;
        font-size: 0.95rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
<h1 style='font-weight:700; font-size:34px; margin-bottom:-5px;'>🌍 GeoData Fusion</h1>
<h3 style='color:#555; font-weight:500; margin-top:5px;'>Welcome to a smarter way to harmonize your GeoPackage data.</h3>

<p style='font-size:15.5px; color:#444; line-height:1.65; margin-top:12px;'>
A powerful yet simple tool crafted by <b>Eng. IRANZI Prince Jean Claude</b> 
to help you merge and manage GeoPackage attributes with clarity and confidence.<br>
Smart tools for smart engineers.
</p>

<hr style='margin-top:25px; margin-bottom:25px;'>
""",
    unsafe_allow_html=True,
)

st.title("Substations and Power Plants GIS Modelling")

# ---- Single file workflow --------------------------------------------------
reference_workbooks = get_reference_workbooks()

with st.container():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("### 📁 Single File Upload")
    st.markdown(
        "<p class='section-subtext'>Upload your GeoPackage and select how attribute data should be provided.</p>",
        unsafe_allow_html=True,
    )
    gpkg_file = st.file_uploader("Upload GeoPackage (.gpkg)", type=["gpkg"], key="single_gpkg")

    data_source = st.radio(
        "Attribute data source",
        (
            "Upload CSV/Excel file",
            "Use stored reference workbook",
        ),
        key="data_source_choice",
    )

    uploaded_data_file = None
    reference_sheet = None
    reference_path = None
    workbook_label = None

    if data_source == "Upload CSV/Excel file":
        uploaded_data_file = st.file_uploader(
            "Upload Data File (CSV or Excel)",
            type=["csv", "xlsx"],
            key="data_file_uploader",
        )
    else:
        if not reference_workbooks:
            st.info(
                "No reference workbooks found in `reference_data`. Add an Excel file to that folder to use this option."
            )
        else:
            workbook_label = st.selectbox(
                "Select stored workbook",
                list(reference_workbooks.keys()),
                key="reference_workbook_select",
            )
            reference_path = reference_workbooks.get(workbook_label)
            sheet_names = get_sheet_names(reference_path) if reference_path else []
            if sheet_names:
                reference_sheet = st.selectbox(
                    "Select worksheet",
                    sheet_names,
                    key="reference_sheet_select",
                )
            else:
                st.warning("Unable to read sheet names from the selected workbook.")
    st.markdown('</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("### 📝 Output Filename")
    st.markdown(
        "<p class='section-subtext'>Customize how the updated GeoPackage will be saved. The same name is used for the output layer.</p>",
        unsafe_allow_html=True,
    )
    # Detect equipment type for name-memory suggestions
    equipment_type = None
    if workbook_label:
        equipment_type = workbook_label
    elif uploaded_data_file is not None:
        try:
            equipment_type = Path(uploaded_data_file.name).stem
        except Exception:
            equipment_type = None

    # Auto-generated default name for this single-file workflow
    auto_name = "updated_clean"

    # Suggested name: either previously saved name for this equipment_type or the auto-generated name
    suggested_name = name_memory.get(equipment_type, auto_name) if equipment_type else auto_name

    output_name = st.text_input(
        "Name for the updated GeoPackage (without extension)",
        value=suggested_name,
        help="This will also be used for the GeoPackage layer name.",
    ).strip() or auto_name
    st.markdown('</div>', unsafe_allow_html=True)

layer_name = output_name.replace(" ", "_")


def sanitize_gdf_for_gpkg(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Prepare a GeoDataFrame for writing to GeoPackage by:
    - Converting unsupported types (object, datetime64 with tz) to string.
    - Removing columns with all NA/NaN values.
    - Truncating column names to 254 characters (GPKG limit).
    """
    gdf_copy = gdf.copy()
    cols_to_drop = []

    for col in gdf_copy.columns:
        if col == gdf_copy.geometry.name:
            continue

        # Drop entirely empty columns to avoid GPKG write errors
        if gdf_copy[col].isna().all():
            cols_to_drop.append(col)
            continue

        col_dtype = gdf_copy[col].dtype
        # Convert object dtype to string (safer for GPKG)
        if col_dtype == "object":
            try:
                gdf_copy[col] = gdf_copy[col].astype(str)
            except Exception:
                pass
        # Convert datetime with timezone to naive datetime or string
        elif "datetime64" in str(col_dtype) and hasattr(gdf_copy[col].dtype, "tz"):
            try:
                gdf_copy[col] = gdf_copy[col].dt.tz_localize(None)
            except Exception:
                gdf_copy[col] = gdf_copy[col].astype(str)

    # Remove empty columns
    if cols_to_drop:
        gdf_copy.drop(columns=cols_to_drop, inplace=True)

    # Truncate column names to 254 chars (GPKG limit)
    gdf_copy.columns = [col[:254] for col in gdf_copy.columns]

    return gdf_copy


def merge_without_duplicates(
    gdf: gpd.GeoDataFrame,
    df: pd.DataFrame,
    left_key: str,
    right_key: str,
) -> gpd.GeoDataFrame:
    """Join df onto gdf but avoid duplicate columns when names collide."""

    merged = gdf.merge(
        df,
        left_on=left_key,
        right_on=right_key,
        how="left",
        suffixes=("", "_incoming"),
    )

    incoming_cols = [c for c in df.columns if c != right_key]
    for col in incoming_cols:
        incoming_name = f"{col}_incoming"

        if col in gdf.columns:
            if incoming_name in merged.columns:
                merged[col] = merged[incoming_name].combine_first(merged[col])
                merged.drop(columns=[incoming_name], inplace=True)
        elif incoming_name in merged.columns:
            merged.rename(columns={incoming_name: col}, inplace=True)

    if right_key in merged.columns and right_key != left_key:
        merged.drop(columns=[right_key], inplace=True)

    # Ensure any incoming-only columns are present in the merged result.
    # Some join edge-cases (different dtypes, duplicate names, or unexpected suffixing)
    # can cause an incoming column to be missing. As a safe fallback, map values
    # from `df` by the right_key onto the merged frame using left_key.
    for col in incoming_cols:
        if col not in merged.columns:
            try:
                # Build mapping from right_key -> value for this column
                mapping = df.set_index(right_key)[col].to_dict()
                merged[col] = merged[left_key].map(mapping)
                # Cast to the same dtype as the source column when possible
                try:
                    merged[col] = merged[col].astype(df[col].dtype)
                except Exception:
                    pass
            except Exception:
                # If mapping fails for any reason, create an empty column
                merged[col] = pd.NA

    result = gpd.GeoDataFrame(merged, geometry=gdf.geometry.name, crs=gdf.crs)
    return sanitize_gdf_for_gpkg(result)


def read_pairs_from_zip(uploaded_zip):
    """Return list of datasets extracted from an uploaded ZIP archive."""

    dataset_pairs = []
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, uploaded_zip.name)
        with open(zip_path, "wb") as tmp_zip:
            tmp_zip.write(uploaded_zip.getbuffer())

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        paired_files = {}
        for root, _, files in os.walk(tmpdir):
            for file in files:
                base, ext = os.path.splitext(file)
                ext_lower = ext.lower()
                full_path = os.path.join(root, file)
                if ext_lower == ".gpkg":
                    paired_files.setdefault(base, {})["gpkg"] = full_path
                elif ext_lower in [".csv", ".xlsx"]:
                    paired_files.setdefault(base, {})["data"] = full_path

        for base_name, paths in paired_files.items():
            if "gpkg" not in paths or "data" not in paths:
                continue

            gdf = gpd.read_file(paths["gpkg"])
            data_path = paths["data"]
            try:
                df = read_tabular_data(data_path)
                df = clean_empty_rows(df)
            except Exception:
                continue

            dataset_pairs.append(
                {
                    "base": base_name,
                    "gdf": gdf,
                    "df": df,
                    "source_zip": uploaded_zip.name,
                }
            )

    return dataset_pairs


data_ready = uploaded_data_file is not None or (
    reference_path is not None and reference_sheet is not None
)

if gpkg_file and data_ready:
    gdf = gpd.read_file(gpkg_file)
    st.success("GeoPackage Loaded ✔")

    if uploaded_data_file is not None:
        try:
            df = read_tabular_data(uploaded_data_file)
            df = clean_empty_rows(df)
        except Exception as exc:
            st.error(f"Unable to read uploaded data file: {exc}")
            st.stop()
        st.success("Data Loaded ✔")
    elif reference_path and reference_sheet:
        df = pd.read_excel(reference_path, sheet_name=reference_sheet)
        df = clean_empty_rows(df)
        st.success(
            f"Reference workbook loaded ✔ ({workbook_label} • sheet: {reference_sheet})"
        )

    st.write("### Select join fields")
    left_key = st.selectbox("Field in GeoPackage", gdf.columns)
    right_key = st.selectbox("Field in Data File", df.columns)

    if st.button("Merge Without Duplicates"):
        try:
            merged_gdf = merge_without_duplicates(gdf, df, left_key, right_key)
            st.success("Attributes Merged Successfully ✔")
            st.dataframe(merged_gdf.head())

            with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
                temp_path = tmp.name

            try:
                # Sanitize one more time before writing to handle any edge cases
                safe_gdf = sanitize_gdf_for_gpkg(merged_gdf)
                # If an equipment_type was detected and the user typed a custom name,
                # persist it so future sessions reuse the name.
                try:
                    if equipment_type:
                        existing = name_memory.get(equipment_type)
                        # If output_name differs from saved mapping and differs from auto_name, save it
                        if output_name and output_name != existing and output_name != auto_name:
                            set_saved_name(equipment_type, output_name, name_memory)
                except Exception:
                    pass

                safe_gdf.to_file(temp_path, driver="GPKG", layer=layer_name)
                with open(temp_path, "rb") as updated:
                    data_bytes = updated.read()

                st.download_button(
                    "⬇ Download Updated GeoPackage",
                    data=data_bytes,
                    file_name=f"{output_name}.gpkg",
                    mime="application/geopackage+sqlite3",
                )
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except Exception as exc:
            st.error(f"Error while merging: {exc}")


# ---- ZIP bundle workflow ----------------------------------------------------
with st.container():
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.markdown("### 🗂️ Batch ZIP Processing")
    st.markdown(
        "<p class='section-subtext'>Process multiple GeoPackage + spreadsheet pairs by uploading ZIP archives that contain matching filenames.</p>",
        unsafe_allow_html=True,
    )
    st.write(
        "Upload one or more ZIP archives. Each ZIP should contain a GeoPackage and a matching "
        "CSV/Excel file that share the same base name (e.g., `roads.gpkg` + `roads.xlsx`)."
    )

    uploaded_zips = st.file_uploader(
        "Upload zipped GeoPackage + spreadsheet bundles",
        type=["zip"],
        accept_multiple_files=True,
    )

    all_datasets = []
    if uploaded_zips:
        for uploaded_zip in uploaded_zips:
            try:
                all_datasets.extend(read_pairs_from_zip(uploaded_zip))
            except zipfile.BadZipFile:
                st.error(f"{uploaded_zip.name} is not a valid ZIP archive.")
            except Exception as exc:
                st.error(f"Failed to read {uploaded_zip.name}: {exc}")

    if not uploaded_zips:
        st.info("Start by uploading at least one ZIP file.")
    elif not all_datasets:
        st.warning("No valid GeoPackage + spreadsheet pairs were found in the uploaded ZIPs.")
    else:
        st.success(f"Loaded {len(all_datasets)} dataset(s) from the uploaded ZIP files.")
        st.write(
            "Configure the join fields and output names for each dataset, then click "
            "`Merge All Bundles` to generate the updated GeoPackages."
        )

        for idx, dataset in enumerate(all_datasets):
            with st.expander(
                f"Dataset {idx + 1}: {dataset['base']} ({dataset['source_zip']})",
                expanded=True,
            ):
                st.write("Select join fields for this dataset:")
                st.selectbox(
                    "Field in GeoPackage",
                    dataset["gdf"].columns,
                    key=f"left_key_{idx}",
                )
                st.selectbox(
                    "Field in Spreadsheet",
                    dataset["df"].columns,
                    key=f"right_key_{idx}",
                )
                # Suggest previously saved name for this equipment (dataset base) if available
                ds_equipment_type = dataset["base"]
                ds_auto = f"{dataset['base']}_updated"
                ds_suggested = name_memory.get(ds_equipment_type, ds_auto)
                st.text_input(
                    "Output file name (without extension)",
                    value=ds_suggested,
                    key=f"output_name_{idx}",
                )

        if st.button("Merge All Bundles"):
            for idx, dataset in enumerate(all_datasets):
                left_key = st.session_state.get(f"left_key_{idx}")
                right_key = st.session_state.get(f"right_key_{idx}")
                output_name = (
                    st.session_state.get(f"output_name_{idx}", "").strip()
                    or f"{dataset['base']}_updated"
                )
                layer_name = output_name.replace(" ", "_")

                if not left_key or not right_key:
                    st.warning(
                        f"Dataset {dataset['base']} skipped: please select both join fields."
                    )
                    continue

                try:
                    merged_gdf = merge_without_duplicates(
                        dataset["gdf"], dataset["df"], left_key, right_key
                    )

                    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
                        temp_path = tmp.name

                    try:
                        # Sanitize one more time before writing to handle any edge cases
                        safe_gdf = sanitize_gdf_for_gpkg(merged_gdf)
                        # Persist custom output name for this dataset's equipment type if changed
                        try:
                            ds_equipment_type = dataset["base"]
                            existing = name_memory.get(ds_equipment_type)
                            ds_auto = f"{dataset['base']}_updated"
                            if output_name and output_name != existing and output_name != ds_auto:
                                set_saved_name(ds_equipment_type, output_name, name_memory)
                        except Exception:
                            pass

                        safe_gdf.to_file(temp_path, driver="GPKG", layer=layer_name)
                        with open(temp_path, "rb") as updated:
                            data_bytes = updated.read()

                        st.success(f"{output_name}.gpkg is ready")
                        st.dataframe(merged_gdf.head())
                        st.download_button(
                            f"⬇ Download {output_name}.gpkg",
                            data=data_bytes,
                            file_name=f"{output_name}.gpkg",
                            mime="application/geopackage+sqlite3",
                        )
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                except Exception as exc:
                    st.error(f"Failed to merge dataset {dataset['base']}: {exc}")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    "<div class='custom-footer'>Developed by Eng. IRANZI Prince Jean Claude</div>",
    unsafe_allow_html=True,
)
