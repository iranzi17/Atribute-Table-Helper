import os
import tempfile
import zipfile
from pathlib import Path
import base64
import hashlib

import geopandas as gpd
import pandas as pd
import streamlit as st
from openpyxl import load_workbook
import json
from io import StringIO


REFERENCE_DATA_DIR = Path(__file__).parent / "reference_data"
HERO_IMAGE_PATH = Path(__file__).parent / "rwanda_small_map.jpg"
SUPPORTED_REFERENCE_EXTENSIONS = (".xlsx", ".xlsm")
PREVIEW_ROW_COUNT = 20

# Persistent name-memory file (maps equipment_type -> user-chosen filename)
NAME_MEMORY_PATH = Path(__file__).parent / "name_memory.json"
USER_DATABASE_PATH = Path(__file__).parent / "users.json"
ADMIN_ACCESS_CODE = os.getenv("ATTRIBUTE_HELPER_ADMIN_CODE", "approve-access")


def rerun_app():
    """Trigger a Streamlit rerun across both legacy and new APIs."""

    rerun_callback = getattr(st, "rerun", None)
    if rerun_callback is None:
        rerun_callback = getattr(st, "experimental_rerun", None)
    if rerun_callback is None:
        raise RuntimeError("Unable to rerun Streamlit app: rerun API not available")
    rerun_callback()


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

# Persistent UI settings (hero layout etc.)
UI_SETTINGS_PATH = Path(__file__).parent / "ui_settings.json"


def load_ui_settings() -> dict:
    try:
        if UI_SETTINGS_PATH.exists():
            with open(UI_SETTINGS_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        return {}
    return {}


def save_ui_settings(mapping: dict):
    try:
        with open(UI_SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_base64_image(image_path: Path) -> str:
    """Return the base64 representation of an image, or empty string on failure."""

    try:
        with open(image_path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")
    except Exception:
        return ""


# load UI settings
ui_settings = load_ui_settings()

# Determine hero height (px) from saved UI settings, fall back to 320
DEFAULT_HERO_HEIGHT = 320
ui_hero_height = int(ui_settings.get("hero_height", DEFAULT_HERO_HEIGHT))
# Determine hero left column percentage (defaults to 35%)
DEFAULT_HERO_LEFT_PCT = 35
ui_hero_left_pct = int(ui_settings.get("hero_left_pct", DEFAULT_HERO_LEFT_PCT))
# Determine hero right column percentage (defaults to 65%)
DEFAULT_HERO_RIGHT_PCT = 65
ui_hero_right_pct = int(ui_settings.get("hero_right_pct", DEFAULT_HERO_RIGHT_PCT))
# Default fixed-left pixel width (used when locking left column in px)
DEFAULT_HERO_LEFT_PX = int(ui_settings.get("hero_left_px", 420))
# Default gradient overlay opacity stops
DEFAULT_HERO_GRADIENT_START = 0.35
DEFAULT_HERO_GRADIENT_END = 0.55
ui_hero_gradient_start = float(ui_settings.get("hero_gradient_start", DEFAULT_HERO_GRADIENT_START))
ui_hero_gradient_end = float(ui_settings.get("hero_gradient_end", DEFAULT_HERO_GRADIENT_END))

# Ensure session state defaults exist so slider changes will produce live preview
if "hero_height_slider" not in st.session_state:
    st.session_state["hero_height_slider"] = ui_settings.get("hero_height", DEFAULT_HERO_HEIGHT)
if "hero_left_pct" not in st.session_state:
    st.session_state["hero_left_pct"] = ui_settings.get("hero_left_pct", DEFAULT_HERO_LEFT_PCT)
if "hero_right_pct" not in st.session_state:
    st.session_state["hero_right_pct"] = ui_settings.get("hero_right_pct", DEFAULT_HERO_RIGHT_PCT)
if "hero_mode" not in st.session_state:
    # modes: 'percent' (default) or 'fixed_left'
    st.session_state["hero_mode"] = ui_settings.get("hero_mode", "percent")
if "hero_left_px" not in st.session_state:
    st.session_state["hero_left_px"] = ui_settings.get("hero_left_px", DEFAULT_HERO_LEFT_PX)
if "hero_gradient_start" not in st.session_state:
    st.session_state["hero_gradient_start"] = ui_settings.get(
        "hero_gradient_start", ui_hero_gradient_start
    )
if "hero_gradient_end" not in st.session_state:
    st.session_state["hero_gradient_end"] = ui_settings.get(
        "hero_gradient_end", ui_hero_gradient_end
    )

# Pre-load hero background image (best-effort)
hero_bg_data = load_base64_image(HERO_IMAGE_PATH)
# A subtle translucent gradient overlay keeps text readable without hiding the map
hero_gradient_start_used = float(
    min(max(st.session_state.get("hero_gradient_start", ui_hero_gradient_start), 0.0), 1.0)
)
hero_gradient_end_used = float(
    min(max(st.session_state.get("hero_gradient_end", ui_hero_gradient_end), 0.0), 1.0)
)
hero_background_layers = [
    "linear-gradient(135deg, rgba(255, 255, 255, {start:.2f}) 0%, rgba(248, 250, 252, {end:.2f}) 100%)".format(
        start=hero_gradient_start_used,
        end=hero_gradient_end_used,
    )
]
if hero_bg_data:
    hero_background_layers.append(f"url('data:image/jpeg;base64,{hero_bg_data}')")
hero_background_css = ", ".join(hero_background_layers)

# Pre-load hero background image (best-effort)
hero_bg_data = load_base64_image(HERO_IMAGE_PATH)
hero_background_layers = [
    "linear-gradient(135deg, rgba(255, 255, 255, 0.92) 0%, rgba(248, 250, 252, 0.95) 100%)"
]
if hero_bg_data:
    hero_background_layers.append(f"url('data:image/jpeg;base64,{hero_bg_data}')")
hero_background_css = ", ".join(hero_background_layers)

# Pre-load hero background image (best-effort)
hero_bg_data = load_base64_image(HERO_IMAGE_PATH)
if hero_bg_data:
    hero_background_css = f"url('data:image/jpeg;base64,{hero_bg_data}')"
else:
    hero_background_css = "none"


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


def load_user_database() -> dict:
    """Load account information from disk."""

    try:
        if USER_DATABASE_PATH.exists():
            with open(USER_DATABASE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
    except Exception:
        return {}
    return {}


def save_user_database(data: dict):
    """Persist user account data to disk (best effort)."""

    try:
        with open(USER_DATABASE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username: str, password: str):
    username = (username or "").strip()
    if not username or not password:
        return False, "Username and password are required."

    user_db = load_user_database()
    if username in user_db:
        return False, "That username is already registered."

    user_db[username] = {
        "password": hash_password(password),
        "approved": False,
    }
    save_user_database(user_db)
    return True, "Account created. Awaiting admin approval before login."


def authenticate_user(username: str, password: str):
    username = (username or "").strip()
    user_db = load_user_database()
    record = user_db.get(username)
    if not record:
        return False, "User not found."

    if record.get("password") != hash_password(password or ""):
        return False, "Incorrect password."

    if not record.get("approved"):
        return False, "Account pending admin approval."

    return True, ""


def render_admin_controls(user_db: dict):
    """Allow the owner to approve pending accounts with a shared code."""

    with st.sidebar.expander("Admin approval", expanded=False):
        st.caption(
            "Enter the admin access code to approve pending accounts."
            " Set ATTRIBUTE_HELPER_ADMIN_CODE to change the default code."
        )
        pending_users = [
            username
            for username, metadata in sorted(user_db.items())
            if not metadata.get("approved")
        ]
        if not pending_users:
            st.write("No pending registrations at the moment.")
            return

        selected_user = st.selectbox(
            "Pending user", pending_users, key="pending_user_select"
        )
        admin_code = st.text_input(
            "Admin access code",
            type="password",
            key="admin_code_input",
        )
        if st.button("Approve selected user", key="approve_user_button"):
            if admin_code == ADMIN_ACCESS_CODE:
                user_db[selected_user]["approved"] = True
                save_user_database(user_db)
                st.success(f"{selected_user} can now log in.")
                st.experimental_rerun()
            else:
                st.error("Incorrect admin code.")


def ensure_authenticated() -> bool:
    """Render login/register UI and gate the rest of the app."""

    st.sidebar.title("Account access")
    user_db = load_user_database()

    current_user = st.session_state.get("authenticated_user")
    if current_user:
        current_record = user_db.get(current_user)
        if not current_record:
            st.session_state.pop("authenticated_user", None)
            current_user = None
        elif not current_record.get("approved"):
            st.sidebar.warning("Your account still needs admin approval.")
            st.session_state.pop("authenticated_user", None)
            current_user = None

    if current_user:
        st.sidebar.success(f"Logged in as {current_user}")
        if st.sidebar.button("Log out"):
            st.session_state.pop("authenticated_user", None)
            st.experimental_rerun()
        render_admin_controls(user_db)
        return True

    auth_mode = st.sidebar.radio(
        "Need to log in or create an account?",
        ["Login", "Register"],
        key="auth_mode_choice",
    )

    if auth_mode == "Login":
        with st.sidebar.form("login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input(
                "Password", type="password", key="login_password"
            )
            login_submit = st.form_submit_button("Sign in")

        if login_submit:
            success, message = authenticate_user(login_username, login_password)
            if success:
                st.session_state["authenticated_user"] = login_username.strip()
                st.sidebar.success("Login successful.")
                st.experimental_rerun()
            else:
                st.sidebar.error(message)
    else:
        with st.sidebar.form("register_form"):
            register_username = st.text_input(
                "Choose a username", key="register_username"
            )
            register_password = st.text_input(
                "Choose a password", type="password", key="register_password"
            )
            confirm_password = st.text_input(
                "Confirm password", type="password", key="register_confirm_password"
            )
            register_submit = st.form_submit_button("Create account")

        if register_submit:
            if register_password != confirm_password:
                st.sidebar.error("Passwords do not match.")
            else:
                success, message = register_user(
                    register_username, register_password
                )
                if success:
                    st.sidebar.success(message)
                    user_db = load_user_database()
                else:
                    st.sidebar.error(message)

    render_admin_controls(user_db)
    st.sidebar.info(
        "Register for an account and wait for approval before accessing the tools."
    )
    return False


st.set_page_config(
    page_title="Clean GPKG Attribute Filler",
    page_icon="🗂️",
    layout="wide",
)

if not ensure_authenticated():
    st.stop()

# Use session-state values (if present) so slider changes show live preview
hero_height_used = int(st.session_state.get("hero_height_slider", ui_hero_height))
hero_left_pct_used = st.session_state.get("hero_left_pct", ui_hero_left_pct)
hero_right_pct_used = st.session_state.get("hero_right_pct", ui_hero_right_pct)
# Determine flex rules depending on mode
hero_mode_used = st.session_state.get("hero_mode", "percent")
if hero_mode_used == "fixed_left":
    # left fixed in px, right fills remaining space
    left_flex_css = "0 0 " + str(int(st.session_state.get("hero_left_px", DEFAULT_HERO_LEFT_PX))) + "px"
    right_flex_css = "1 1 auto"
else:
    left_flex_css = "0 0 " + str(int(hero_left_pct_used)) + "%"
    right_flex_css = "0 0 " + str(int(hero_right_pct_used)) + "%"

st.markdown("""
    <style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    .stApp {
        font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
        background: #f4f6f9;
    }
    .main {
        padding: 0 !important;
    }
    .main > div {
        width: 100% !important;
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    /* Aggressively override all Streamlit width constraints */
    main .block-container {
        width: 100% !important;
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] + div {
        width: 100% !important;
        max-width: 100% !important;
    }
    
    /* Hero Section - Full Width */
    .hero-container {
        display: flex;
        width: 100%;
        max-width: 100% !important;
        min-height: """ + str(hero_height_used) + """px;
        margin: 0 !important;
        padding: 0 !important;
        margin-bottom: 2.5rem;
        box-shadow: 0 8px 20px rgba(13, 71, 161, 0.15);
        border-radius: 0 !important;
        overflow: hidden;
    }
    
    /* Hero Left Column - Blue Branding */
    .hero-left {
        flex: """ + left_flex_css + """;
        background: linear-gradient(135deg, #0d47a1 0%, #1565c0 100%);
        color: #ffffff;
        padding: 3rem 2.5rem;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
    }
    .hero-left h2 {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
        letter-spacing: -0.8px;
    }
    .hero-left .tagline {
        font-size: 1rem;
        font-weight: 500;
        color: #bbdefb;
        margin-bottom: 1rem;
        line-height: 1.5;
    }
    .hero-left .byline {
        font-size: 0.9rem;
        color: #90caf9;
        font-style: italic;
        margin-top: 2rem;
        padding-top: 1.5rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Hero Right Column - Product Title + Background */
    .hero-right {
        flex: """ + right_flex_css + """;
        background: linear-gradient(135deg, #f0f4f8 0%, #e8eef7 100%);
        background-image: """ + hero_background_css + """;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        padding: 3rem 2.5rem;
        text-align: center;
        position: relative;
    }
    .hero-right::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: none;
        z-index: 1;
    }
    .hero-right h1,
    .hero-right .subtitle {
        position: relative;
        z-index: 2;
    }
    .hero-right h1 {
        font-size: 2.4rem;
        font-weight: 700;
        color: #0d47a1;
        line-height: 1.3;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        margin: 0;
        letter-spacing: -0.5px;
    }
    .hero-right .subtitle {
        font-size: 1rem;
        color: #1565c0;
        margin-top: 1rem;
        font-weight: 500;
    }
    
    /* Content Wrapper - Full width, center child elements */
    .content-wrapper {
        width: 100% !important;
        max-width: 100% !important;
        padding: 2rem !important;
        margin: 0 !important;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    
    .content-wrapper > * {
        width: 100%;
        max-width: 980px;
        margin-left: auto;
        margin-right: auto;
    }
    
    /* Header Box - Professional landing section */
    .header-box {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: #ffffff;
        padding: 3rem 2rem;
        border-radius: 12px;
        margin-bottom: 2.5rem;
        box-shadow: 0 8px 16px rgba(30, 60, 114, 0.2);
    }
    .header-box h1 {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }
    .header-box h3 {
        font-size: 1.3rem;
        font-weight: 500;
        margin-bottom: 1rem;
        color: #e0e7ff;
    }
    .header-box p {
        font-size: 1rem;
        line-height: 1.6;
        color: #c7d2e0;
    }
    
    /* Section Box - Main workflow containers */
    .section-box {
        background: #ffffff;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
        border-left: 4px solid #2a5298;
        margin-bottom: 2rem;
    }
    .section-box.alt {
        border-left-color: #5a67d8;
    }
    .section-box.tertiary {
        border-left-color: #3b82f6;
    }
    
    /* Section Title */
    .section-title {
        font-size: 1.4rem;
        font-weight: 600;
        color: #1f2a37;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .section-title::before {
        content: "";
        display: inline-block;
        width: 4px;
        height: 1.4rem;
        background: #2a5298;
        border-radius: 2px;
    }
    
    /* Subsection text */
    .section-subtext {
        color: #4b5563;
        margin-bottom: 1.5rem;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    
    /* File Uploader styling */
    .stFileUploader {
        border-radius: 12px !important;
    }
    .stFileUploader > div {
        border-radius: 12px !important;
        border: 2px dashed #3b82f6 !important;
        padding: 1.5rem !important;
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(79, 172, 254, 0.02) 100%) !important;
    }
    
    /* Inputs and Selectbox */
    .stTextInput > div > div,
    .stSelectbox > div > div,
    .stDataEditor > div {
        border-radius: 8px !important;
        border: 1px solid #e5e7eb !important;
    }
    .stTextInput > div > div:focus-within,
    .stSelectbox > div > div:focus-within {
        border-color: #2a5298 !important;
        box-shadow: 0 0 0 3px rgba(42, 82, 152, 0.1) !important;
    }
    
    /* Radio button styling */
    .stRadio > label {
        font-weight: 500;
        color: #1f2a37;
    }
    .stRadio > div {
        gap: 1rem;
    }
    
    /* Button styling */
    .stButton button {
        font-weight: 600;
        padding: 0.75rem 1.5rem !important;
        border-radius: 8px !important;
        background: linear-gradient(135deg, #2a5298 0%, #3b82f6 100%) !important;
        color: #ffffff !important;
        border: none !important;
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        box-shadow: 0 4px 12px rgba(42, 82, 152, 0.3);
        transform: translateY(-2px);
    }
    
    /* Success/Warning/Info messages */
    .stSuccess, .stWarning, .stInfo {
        border-radius: 8px !important;
        padding: 1rem !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #f9fafb;
        border-radius: 8px;
        font-weight: 600;
        color: #1f2a37;
    }
    
    /* Data editor styling */
    .stDataEditor {
        border-radius: 8px !important;
    }
    
    /* Footer */
    footer {
        visibility: hidden;
    }
    .custom-footer {
        text-align: center;
        padding: 2rem 0 1rem;
        color: #6b7280;
        font-size: 0.9rem;
        border-top: 1px solid #e5e7eb;
        margin-top: 3rem;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .hero-container {
            flex-direction: column;
            min-height: auto;
        }
        .hero-left,
        .hero-right {
            flex: 0 0 100%;
        }
        .hero-left h2 {
            font-size: 1.8rem;
        }
        .hero-right h1 {
            font-size: 1.8rem;
        }
        .header-box h1 {
            font-size: 2rem;
        }
        .section-box {
            padding: 1.5rem;
        }
        .content-wrapper {
            padding: 1rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero-container">
    <div class="hero-left">
        <h2>🌍 GeoData Fusion</h2>
        <div class="tagline">
            <strong>Smart Attribute Mapping</strong><br>
            Harmonize GeoPackage data with precision
        </div>
        <div class="byline">
            Built by Eng. IRANZI Prince Jean Claude<br>
            For engineers, by engineers.
        </div>
    </div>
    <div class="hero-right">
        <h1>Substations and Power Plants GIS Modelling</h1>
        <div class="subtitle">Professional geospatial data management for Rwanda's infrastructure</div>
    </div>
</div>

<div class="content-wrapper">
""",
    unsafe_allow_html=True,
)

# Small UI to let users resize the hero and persist the setting
with st.expander("UI Settings", expanded=False):
    try:
        hero_height_new = st.slider(
            "Hero height (px)",
            min_value=200,
            max_value=800,
            value=st.session_state.get("hero_height_slider", ui_hero_height),
            step=10,
            key="hero_height_slider",
        )

        st.markdown("**Hero background gradient overlay**")
        hero_gradient_start_new = st.slider(
            "Gradient start opacity (0 = transparent, 1 = solid)",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("hero_gradient_start", hero_gradient_start_used)),
            step=0.05,
            key="hero_gradient_start",
        )
        hero_gradient_end_new = st.slider(
            "Gradient end opacity (0 = transparent, 1 = solid)",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("hero_gradient_end", hero_gradient_end_used)),
            step=0.05,
            key="hero_gradient_end",
        )

        # Sizing mode: percent-based or fixed-left (px) where right column expands
        st.markdown("**Hero sizing mode**")
        hero_mode_new = st.radio(
            "Choose how the hero columns size:",
            ("percent", "fixed_left"),
            index=0 if st.session_state.get("hero_mode", "percent") == "percent" else 1,
            key="hero_mode",
        )

        if st.session_state.get("hero_mode", "percent") == "percent":
            # Allow unbounded numeric input for left/right percentages so user can extend freely
            hero_left_new = st.number_input(
                "Hero left column width (%) - enter any integer (no limit)",
                value=int(st.session_state.get("hero_left_pct", ui_hero_left_pct)),
                step=1,
                key="hero_left_pct",
            )

            hero_right_new = st.number_input(
                "Hero right column width (%) - enter any integer (no limit)",
                value=int(st.session_state.get("hero_right_pct", ui_hero_right_pct)),
                step=1,
                key="hero_right_pct",
            )
        else:
            # Fixed-left mode: left column is a fixed pixel width, right column flexes to fill
            hero_left_px_new = st.number_input(
                "Hero left column width (px)",
                value=int(st.session_state.get("hero_left_px", DEFAULT_HERO_LEFT_PX)),
                step=1,
                key="hero_left_px",
            )

        st.markdown("*Live preview updates as you change values. Click Save to persist.*")

        if st.button("Save UI settings", key="save_ui_settings_btn"):
            ui_settings["hero_height"] = int(st.session_state.get("hero_height_slider", hero_height_new))
            ui_settings["hero_mode"] = st.session_state.get("hero_mode", "percent")
            ui_settings["hero_gradient_start"] = float(
                st.session_state.get("hero_gradient_start", hero_gradient_start_new)
            )
            ui_settings["hero_gradient_end"] = float(
                st.session_state.get("hero_gradient_end", hero_gradient_end_new)
            )
            if ui_settings["hero_mode"] == "percent":
                ui_settings["hero_left_pct"] = int(st.session_state.get("hero_left_pct", hero_left_new))
                ui_settings["hero_right_pct"] = int(st.session_state.get("hero_right_pct", hero_right_new))
                # remove fixed-left px if present
                ui_settings.pop("hero_left_px", None)
            else:
                ui_settings["hero_left_px"] = int(st.session_state.get("hero_left_px", hero_left_px_new))
                # remove percent keys if present
                ui_settings.pop("hero_left_pct", None)
                ui_settings.pop("hero_right_pct", None)
            save_ui_settings(ui_settings)
            st.success("Saved UI settings")
            rerun_app()
        if st.button("Reset to defaults", key="reset_ui_settings_btn"):
            # Remove saved values and reset session sliders to defaults
            ui_settings.pop("hero_height", None)
            ui_settings.pop("hero_left_pct", None)
            ui_settings.pop("hero_right_pct", None)
            ui_settings.pop("hero_mode", None)
            ui_settings.pop("hero_left_px", None)
            ui_settings.pop("hero_gradient_start", None)
            ui_settings.pop("hero_gradient_end", None)
            save_ui_settings(ui_settings)
            st.session_state["hero_height_slider"] = DEFAULT_HERO_HEIGHT
            st.session_state["hero_left_pct"] = DEFAULT_HERO_LEFT_PCT
            st.session_state["hero_right_pct"] = DEFAULT_HERO_RIGHT_PCT
            st.session_state["hero_mode"] = "percent"
            st.session_state["hero_left_px"] = DEFAULT_HERO_LEFT_PX
            st.session_state["hero_gradient_start"] = DEFAULT_HERO_GRADIENT_START
            st.session_state["hero_gradient_end"] = DEFAULT_HERO_GRADIENT_END
            st.success("Reset UI settings to defaults")
            rerun_app()
    except Exception:
        # UI should not crash the app; silently ignore
        pass

# ---- Single file workflow --------------------------------------------------
reference_workbooks = get_reference_workbooks()

with st.container():
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Single File Upload</div>', unsafe_allow_html=True)
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
            "Paste data directly",
        ),
        key="data_source_choice",
    )

    uploaded_data_file = None
    reference_sheet = None
    reference_path = None
    workbook_label = None
    pasted_df = None

    # Show paste editor only when "Paste data directly" is selected
    if data_source == "Paste data directly":
        with st.container():
            st.markdown("##### Paste Your Tabular Data")
            st.markdown(
                "Paste raw tabular data (Ctrl+C from Excel → Ctrl+V here). The app will parse TSV/CSV, show it for editing, and use it for merging."
            )
            paste_text = st.text_area(
                "Paste your data here (TSV/CSV format)",
                height=150,
                placeholder="Paste tabular data here...",
                key="paste_text_direct",
            )

            if isinstance(paste_text, str) and paste_text.strip():
                parsed = None
                # Try autodetecting separator first
                try:
                    parsed = pd.read_csv(StringIO(paste_text), sep=None, engine="python")
                except Exception:
                    # Fallbacks: try tab, then comma
                    try:
                        parsed = pd.read_csv(StringIO(paste_text), sep="\t")
                    except Exception:
                        try:
                            parsed = pd.read_csv(StringIO(paste_text), sep=",")
                        except Exception:
                            parsed = None

                if isinstance(parsed, pd.DataFrame):
                    # Show parsed DataFrame in an editable grid so users can tweak before merging
                    edited = st.data_editor(parsed, num_rows="dynamic", key="pasted_data_editor_direct")
                    if isinstance(edited, pd.DataFrame) and not edited.dropna(how="all").empty:
                        pasted_df = clean_empty_rows(edited)
                        # Persist pasted DataFrame into session_state so it survives reruns
                        try:
                            st.session_state["df_from_paste"] = pasted_df
                        except Exception:
                            pass
                        st.success("Pasted data detected — it will be used for merging.")
                else:
                    st.warning("Unable to parse pasted text as a table. Please ensure it's tabular (TSV/CSV) or paste directly from Excel cells.")
            # If the text area is empty, remove any previously saved pasted DF from session state
            if not paste_text or not str(paste_text).strip():
                if "df_from_paste" in st.session_state:
                    try:
                        del st.session_state["df_from_paste"]
                    except Exception:
                        pass

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
    st.markdown('<div class="section-box alt">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Output Filename</div>', unsafe_allow_html=True)
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

    # Prefer session-stored pasted DF if available; otherwise fall back to uploaded file or stored reference
    df_from_paste = st.session_state.get("df_from_paste")
    if isinstance(df_from_paste, pd.DataFrame) and not df_from_paste.dropna(how="all").empty:
        df = df_from_paste
        st.success("Using pasted data ✔")
    elif uploaded_data_file is not None:
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

    st.markdown('<div class="section-title">Select join fields</div>', unsafe_allow_html=True)
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


# ---- Geometry conversion (Polygon -> Point) ---------------------------------
with st.container():
    st.markdown('<div class="section-box tertiary">', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">Geometry Conversion (Polygons → Points)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p class='section-subtext'>Upload a GeoPackage to convert all polygon features into centroid points while keeping every attribute intact.</p>",
        unsafe_allow_html=True,
    )

    polygon_conversion_file = st.file_uploader(
        "Upload GeoPackage (.gpkg) for centroid conversion",
        type=["gpkg"],
        key="polygon_to_point_gpkg",
    )

    conversion_gdf = None
    if polygon_conversion_file is not None:
        temp_input_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp_in:
                tmp_in.write(polygon_conversion_file.getbuffer())
                temp_input_path = tmp_in.name

            conversion_gdf = gpd.read_file(temp_input_path)
            st.success(
                f"Loaded GeoPackage with {len(conversion_gdf):,} feature(s) ready for conversion."
            )
        except Exception as exc:
            conversion_gdf = None
            st.error(f"Unable to read the uploaded GeoPackage: {exc}")
        finally:
            if temp_input_path and os.path.exists(temp_input_path):
                os.remove(temp_input_path)

    if conversion_gdf is not None:
        geom_types_raw = conversion_gdf.geom_type.dropna().unique().tolist()
        geom_types_clean = sorted(
            {str(gt) for gt in geom_types_raw if str(gt).strip()}
        )
        geom_types_display = ", ".join(geom_types_clean) if geom_types_clean else "Unknown"
        st.markdown(f"**Detected geometry types:** {geom_types_display}")

        has_polygon_geometry = any(
            "polygon" in str(geom_type).lower()
            for geom_type in geom_types_raw
        )

        if has_polygon_geometry:
            try:
                points_gdf = conversion_gdf.copy()
                points_gdf["geometry"] = conversion_gdf.geometry.centroid
                st.success("Centroid points generated for all polygon features.")
                st.dataframe(points_gdf.head())

                centroid_bytes = None
                temp_output_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp_out:
                        temp_output_path = tmp_out.name

                    safe_points = sanitize_gdf_for_gpkg(points_gdf)
                    safe_points.to_file(
                        temp_output_path,
                        driver="GPKG",
                        layer="centroid_points",
                    )
                    with open(temp_output_path, "rb") as converted:
                        centroid_bytes = converted.read()
                except Exception as exc:
                    centroid_bytes = None
                    st.error(f"Failed to prepare centroid GeoPackage: {exc}")
                finally:
                    if temp_output_path and os.path.exists(temp_output_path):
                        os.remove(temp_output_path)

                if centroid_bytes:
                    st.download_button(
                        "⬇ Download centroid points",
                        data=centroid_bytes,
                        file_name="centroid_points.gpkg",
                        mime="application/geopackage+sqlite3",
                    )
            except Exception as exc:
                st.error(f"Failed to generate centroids: {exc}")
        else:
            st.info(
                "The uploaded GeoPackage does not contain Polygon or MultiPolygon geometries, so no centroid conversion was performed."
            )

    st.markdown('</div>', unsafe_allow_html=True)


# ---- ZIP bundle workflow ----------------------------------------------------
with st.container():
    st.markdown('<div class="section-box tertiary">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Batch ZIP Processing</div>', unsafe_allow_html=True)
    st.markdown(
        "<p class='section-subtext'>Process multiple GeoPackage + spreadsheet pairs by uploading ZIP archives that contain matching filenames.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
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
    """
</div>

<div class='custom-footer'>Developed by Eng. IRANZI Prince Jean Claude</div>
""",
    unsafe_allow_html=True,
)
