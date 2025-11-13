import os
import tempfile
import zipfile

import geopandas as gpd
import pandas as pd
import streamlit as st


st.title("📌 Clean GPKG Attribute Filler – No Duplicate Columns")

# ---- Single file workflow --------------------------------------------------
gpkg_file = st.file_uploader("Upload GeoPackage (.gpkg)", type=["gpkg"])
data_file = st.file_uploader("Upload Data File (CSV or Excel)", type=["csv", "xlsx"])
output_name = st.text_input(
    "Name for the updated GeoPackage (without extension)",
    value="updated_clean",
    help="This will also be used for the GeoPackage layer name.",
).strip() or "updated_clean"

layer_name = output_name.replace(" ", "_")


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

    return gpd.GeoDataFrame(merged, geometry=gdf.geometry.name, crs=gdf.crs)


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
            if data_path.lower().endswith(".csv"):
                df = pd.read_csv(data_path)
            else:
                df = pd.read_excel(data_path)

            dataset_pairs.append(
                {
                    "base": base_name,
                    "gdf": gdf,
                    "df": df,
                    "source_zip": uploaded_zip.name,
                }
            )

    return dataset_pairs


if gpkg_file and data_file:
    gdf = gpd.read_file(gpkg_file)
    st.success("GeoPackage Loaded ✔")

    if data_file.name.endswith(".csv"):
        df = pd.read_csv(data_file)
    else:
        df = pd.read_excel(data_file)

    st.success("Data Loaded ✔")

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
                merged_gdf.to_file(temp_path, driver="GPKG", layer=layer_name)
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
            st.text_input(
                "Output file name (without extension)",
                value=f"{dataset['base']}_updated",
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
                    merged_gdf.to_file(temp_path, driver="GPKG", layer=layer_name)
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
