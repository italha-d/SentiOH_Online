from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "assets" / "sentioh_logo.png"


def render_brand_header(st, width=650):
    """Render the supplied SentiOH brand artwork without modifying it."""
    if LOGO_PATH.exists():
        st.image(
            str(LOGO_PATH),
            width=width,
        )
    else:
        # Safe fallback if someone deploys only the Python files without assets.
        st.title("SentiOH")


def inject_brand_typography(st):
    """Apply SentiOH typography consistently across Streamlit surfaces.

    Kiro is a licensed typeface and is intentionally not redistributed with
    this repository. The CSS uses a locally installed Kiro font when present
    and falls back to a condensed system sans-serif otherwise.
    """
    st.markdown(
        """
        <style>
        @font-face {
            font-family: "Kiro";
            src: local("Kiro Regular"), local("Kiro");
            font-style: normal;
            font-weight: 100 900;
            font-display: swap;
        }

        :root {
            --sentioh-font: "Kiro", "Arial Narrow", Arial, sans-serif;
        }

        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stSidebar"] {
            font-family: var(--sentioh-font) !important;
        }

        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp p, .stApp li, .stApp label, .stApp small,
        .stApp button, .stApp input, .stApp textarea,
        .stApp [role="tab"], .stApp [role="option"],
        .stApp [data-baseweb="select"],
        .stApp [data-testid="stMetricLabel"],
        .stApp [data-testid="stMetricValue"],
        .stApp [data-testid="stCaptionContainer"] {
            font-family: var(--sentioh-font) !important;
        }

        /* Never hide regulatory or workflow text because a card is narrow. */
        .stApp [data-testid="stMarkdownContainer"] p,
        .stApp [data-testid="stMarkdownContainer"] li,
        .stApp [data-testid="stCaptionContainer"],
        .stApp [data-testid="stAlertContentInfo"],
        .stApp [data-testid="stAlertContentSuccess"],
        .stApp [data-testid="stAlertContentWarning"],
        .stApp [data-testid="stAlertContentError"] {
            white-space: normal !important;
            overflow: visible !important;
            overflow-wrap: anywhere !important;
            word-break: normal !important;
            text-overflow: clip !important;
        }

        .stApp button {
            white-space: normal !important;
            height: auto !important;
            min-height: 2.5rem;
            line-height: 1.2 !important;
        }

        .stApp [data-baseweb="select"] > div {
            min-height: 2.75rem !important;
            height: auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
