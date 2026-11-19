"""Institutional Dark Terminal CSS Design System for Streamlit."""

GLOBAL_TERMINAL_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background: transparent !important;}
    [data-testid="stAppDeployButton"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}

    /* Global Workspace Layout & Native Dark UI */
    :root, html {
        color-scheme: dark;
        --scrollbar-thumb: #334155;
        --scrollbar-track: #0B0F19;
        scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
        scrollbar-width: thin;
    }

    @supports not (scrollbar-color: auto) {
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-thumb {
            background: var(--scrollbar-thumb);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-track {
            background: var(--scrollbar-track);
        }
    }

    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        background-color: #0B0F19 !important;
        color: #F8FAFC !important;
    }

    [data-testid="stSidebar"] {
        background-color: #0D131F !important;
        border-right: 1px solid #1E293B !important;
    }

    /* Section Eyebrow & Headings */
    .section-eyebrow {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #38BDF8;
        margin-bottom: 4px;
        margin-top: 20px;
    }
    .section-heading, h1, h2, h3, h4, h5 {
        text-wrap: balance;
    }
    .section-heading {
        font-size: 1.25rem;
        font-weight: 700;
        color: #F8FAFC;
        letter-spacing: -0.015em;
        margin-bottom: 14px;
        padding-bottom: 6px;
        border-bottom: 1px solid #1E293B;
    }

    /* High-Density Tabular Metric Cards */
    [data-testid="stMetric"] {
        background: #111827 !important;
        border: 1px solid #1E293B !important;
        border-radius: 6px !important;
        padding: 12px 14px !important;
        box-shadow: none !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.74rem !important;
        font-weight: 600 !important;
        color: #94A3B8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
        letter-spacing: -0.02em !important;
        font-feature-settings: "tnum" 1 !important;
        font-variant-numeric: tabular-nums !important;
        font-family: 'JetBrains Mono', 'Inter', monospace !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        font-feature-settings: "tnum" 1 !important;
        font-variant-numeric: tabular-nums !important;
    }

    /* Content Cards & Containers */
    .metric-card-box {
        background-color: #111827 !important;
        border: 1px solid #1E293B !important;
        border-radius: 6px !important;
        padding: 14px 16px !important;
        margin-bottom: 12px !important;
        color: #F8FAFC !important;
    }

    /* Tabs Styling */
    [data-baseweb="tab-list"] {
        border-bottom: 1px solid #1E293B !important;
        gap: 8px !important;
        background-color: transparent !important;
    }
    [data-baseweb="tab"] {
        color: #94A3B8 !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        padding: 8px 14px !important;
        border-radius: 4px 4px 0 0 !important;
        background-color: transparent !important;
    }
    [data-baseweb="tab"][aria-selected="true"] {
        color: #38BDF8 !important;
        border-bottom: 2px solid #38BDF8 !important;
    }

    /* Clean Streamlit Buttons */
    .stButton>button {
        border-radius: 4px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        border: 1px solid #334155 !important;
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        transition: background-color 150ms ease-out, border-color 150ms ease-out, color 150ms ease-out, box-shadow 150ms ease-out, scale 150ms ease-out !important;
    }
    .stButton>button:hover {
        border-color: #38BDF8 !important;
        color: #38BDF8 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    .stButton>button:active {
        scale: 0.98 !important;
    }
    .stButton>button:focus-visible {
        outline: 2px solid #38BDF8 !important;
        outline-offset: 2px !important;
    }
    .stButton>button[kind="primary"] {
        background-color: #0284C7 !important;
        border-color: #0284C7 !important;
        color: #FFFFFF !important;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #0369A1 !important;
        border-color: #0369A1 !important;
    }

    /* Accessible Responsive Table Wrapper */
    .holdings-table-wrap {
        background: #0B0F19;
        border-radius: 6px;
        padding: 4px 8px;
        border: 1px solid #1E293B;
        overflow-x: auto;
        max-inline-size: 100%;
        scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
        scrollbar-width: thin;
    }
    .holdings-table-wrap:focus-visible {
        outline: 2px solid #38BDF8;
        outline-offset: 2px;
    }

    /* Clean Expander */
    [data-testid="stExpander"] {
        background-color: #111827 !important;
        border: 1px solid #1E293B !important;
        border-radius: 6px !important;
    }

    /* Status Badges */
    .badge-subtle {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        padding: 2px 7px;
        border-radius: 4px;
        font-feature-settings: 'tnum' 1;
    }
    .badge-blue {
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.28);
    }
    .badge-emerald {
        background: rgba(16, 185, 129, 0.12);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.28);
    }
    .badge-amber {
        background: rgba(245, 158, 11, 0.12);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.28);
    }
    .badge-slate {
        background: rgba(148, 163, 184, 0.12);
        color: #CBD5E1;
        border: 1px solid rgba(148, 163, 184, 0.28);
    }
</style>
"""


def inject_global_terminal_styles(st_module):
    """Inject the institutional dark terminal CSS into Streamlit."""
    st_module.markdown(GLOBAL_TERMINAL_CSS, unsafe_allow_html=True)
