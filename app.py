"""
app.py
======
ConstraintGuard Streamlit Web Application
Professional AI Coding Agent & Developer IDE Interface with Glassmorphic Panels.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from constraint_guard.extractor import extract
from constraint_guard.graph import VersionedConstraintGraph
from constraint_guard.llm.catalog import DEFAULT_GROQ_MODEL, get_model_catalog
from constraint_guard.llm.errors import LLMProviderError
from constraint_guard.llm.provider import (
    DeterministicMockProvider,
    OpenAICompatibleProvider,
    get_default_provider,
)
from constraint_guard.llm.service import generate_code
from constraint_guard.repair.loop import RepairHistory, run_repair_loop
from constraint_guard.repair.repairer import repair_code
from constraint_guard.resolver import ConstraintResolver
from constraint_guard.verifier.engine import VerificationEngine


# Streamlit Page Config
st.set_page_config(
    page_title="ConstraintGuard — AI Coding Agent & Verifier",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS: Transparent Glassmorphic Dark IDE Theme ────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap');

/* Root & Global Background */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main .block-container {
    background-color: #070709 !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background-color: rgba(10, 10, 14, 0.90) !important;
    backdrop-filter: blur(16px) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}
[data-testid="stSidebar"] * {
    color: #94a3b8 !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.08) !important;
}

/* Glassmorphic Container Cards */
.cg-card {
    background: rgba(18, 18, 24, 0.55) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin-bottom: 14px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35) !important;
}

/* Top Header Bar */
.cg-top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(15, 15, 22, 0.80);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 12px;
    padding: 10px 18px;
    margin-bottom: 16px;
}
.cg-top-left {
    display: flex;
    align-items: center;
    gap: 12px;
}
.cg-top-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.02em;
}
.cg-top-sub {
    font-size: 0.75rem;
    color: #64748b;
    font-weight: 400;
}

/* Pill Badges */
.cg-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #cbd5e1;
}
.cg-pill.green {
    background: rgba(34, 197, 94, 0.12);
    border-color: rgba(34, 197, 94, 0.30);
    color: #4ade80;
}
.cg-pill.red {
    background: rgba(239, 68, 68, 0.12);
    border-color: rgba(239, 68, 68, 0.30);
    color: #f87171;
}
.cg-pill.purple {
    background: rgba(168, 85, 247, 0.14);
    border-color: rgba(168, 85, 247, 0.35);
    color: #c084fc;
}
.cg-pill.blue {
    background: rgba(59, 130, 246, 0.14);
    border-color: rgba(59, 130, 246, 0.35);
    color: #60a5fa;
}

/* Hero Greeting Banner */
.cg-hero {
    background: rgba(18, 18, 26, 0.50);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 16px;
}
.cg-hero-title {
    font-size: 1.30rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 4px;
}
.cg-hero-sub {
    font-size: 0.85rem;
    color: #94a3b8;
}

/* Chat Message Bubbles */
.cg-chat-msg {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 10px;
    margin-bottom: 8px;
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.82rem;
}
.cg-avatar {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
}
.cg-avatar.user { background: #2563eb; color: #ffffff; }
.cg-avatar.assistant { background: #0284c7; color: #ffffff; }
.cg-msg-header {
    font-size: 0.70rem;
    font-family: 'JetBrains Mono', monospace;
    color: #64748b;
    margin-bottom: 2px;
    display: flex;
    justify-content: space-between;
}

/* Section Titles */
.cg-card-title {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

/* Form Inputs & Selects */
.stTextInput input,
.stTextArea textarea,
[data-baseweb="select"] > div:first-child {
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: rgba(59, 130, 246, 0.50) !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15) !important;
}

/* Buttons */
.stButton > button {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
    color: #cbd5e1 !important;
    border-radius: 8px !important;
    font-size: 0.80rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
}
.stButton > button:hover {
    background: rgba(255, 255, 255, 0.09) !important;
    border-color: rgba(255, 255, 255, 0.22) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: #2563eb !important;
    border-color: #3b82f6 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1d4ed8 !important;
    border-color: #60a5fa !important;
}

/* Status Card Row */
.cg-status-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-size: 0.78rem;
}
.cg-status-row:last-child { border-bottom: none; }
.cg-status-lbl { color: #94a3b8; display: flex; align-items: center; gap: 6px; }
.cg-status-val { color: #f1f5f9; font-weight: 500; font-family: 'JetBrains Mono', monospace; }

/* Constraint Item Card */
.cg-constraint-card {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
}
.cg-c-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
}
.cg-c-id {
    font-size: 0.70rem;
    font-weight: 700;
    color: #ef4444;
    background: rgba(239, 68, 68, 0.15);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}
.cg-c-text {
    font-size: 0.80rem;
    color: #cbd5e1;
}

/* Activity Log Box */
.cg-activity-box {
    background: rgba(5, 5, 8, 0.70);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
    padding: 10px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #94a3b8;
    max-height: 120px;
    overflow-y: auto;
    line-height: 1.6;
}

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden !important; }
[data-testid="stToolbar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# Initialize Session State Defaults
if "selected_model" not in st.session_state:
    st.session_state.selected_model = os.getenv("LLM_MODEL", DEFAULT_GROQ_MODEL)
if "model_status" not in st.session_state:
    st.session_state.model_status = "🟡 Availability not checked"
if "discovered_models" not in st.session_state:
    st.session_state.discovered_models = []
if "execution_mode" not in st.session_state:
    st.session_state.execution_mode = "Deterministic Demo Mode 🎯" if not os.getenv("LLM_API_KEY") else "Live LLM Mode ⚡"

# Default Initial Scenario A
default_init_conv = [
    {"turn": 1, "text": "Write a function that finds the maximum value in a list. Do not use max()."},
    {"turn": 2, "text": "Also handle an empty list gracefully by returning None."},
    {"turn": 3, "text": "Keep the previous restrictions."},
]
default_init_code = "def find_max(lst):\n    if not lst:\n        return None\n    return max(lst)"

if "conversation" not in st.session_state:
    st.session_state.conversation = default_init_conv
if "conv_raw_text" not in st.session_state:
    st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in default_init_conv])
if "code" not in st.session_state:
    st.session_state.code = default_init_code
if "report" not in st.session_state:
    st.session_state.report = None
if "repair_history" not in st.session_state:
    st.session_state.repair_history = None
if "cg_activity_log" not in st.session_state:
    st.session_state.cg_activity_log = [
        f"[{datetime.now().strftime('%H:%M:%S')}] ConstraintGuard AI Engine Initialized"
    ]

def log_activity(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.cg_activity_log.insert(0, f"[{timestamp}] {msg}")

def set_conversation(conv_list, initial_code=None):
    st.session_state.conversation = conv_list
    st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in conv_list])
    if initial_code is not None:
        st.session_state.code = initial_code
    st.session_state.report = None
    st.session_state.repair_history = None


# ── Top Glass Header & AI Agent Selector ──────────────────────────────────────
catalog = get_model_catalog()
all_models = list(catalog)
for m in st.session_state.discovered_models:
    if m not in all_models:
        all_models.append(m)
if st.session_state.selected_model not in all_models:
    all_models.insert(0, st.session_state.selected_model)

try:
    current_model_idx = all_models.index(st.session_state.selected_model)
except ValueError:
    current_model_idx = 0

is_demo = "Demo" in st.session_state.execution_mode

# Top Header Layout
header_col1, header_col2, header_col3 = st.columns([8, 8, 4])

with header_col1:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;">
      <span style="font-size:1.6rem;">🛡️</span>
      <div>
        <div style="font-size:1.3rem;font-weight:700;color:#ffffff;line-height:1.2;">ConstraintGuard</div>
        <div style="font-size:0.75rem;color:#64748b;">Autonomous Safe Code Verification Agent</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

with header_col2:
    if not is_demo:
        chosen_header_model = st.selectbox(
            "🤖 Choose AI Agent / Groq Model:",
            options=all_models,
            index=current_model_idx,
            key="header_agent_selector",
            help="Select the Groq LLM Agent used for code generation and repair.",
        )
        if chosen_header_model != st.session_state.selected_model:
            st.session_state.selected_model = chosen_header_model
            st.session_state.model_status = "🟡 Availability not checked"
            log_activity(f"AI Agent model changed to: {chosen_header_model}")
            st.rerun()
    else:
        st.markdown('<div class="cg-pill purple" style="margin-top:8px;">🎯 Offline Deterministic Agent (Mock Mode)</div>', unsafe_allow_html=True)

with header_col3:
    mode_status_txt = "DEMO (Mock)" if is_demo else ("CONNECTED" if "🟢" in st.session_state.model_status else "UNCHECKED")
    st.markdown(f"""
    <div style="text-align:right;margin-top:6px;">
      <span class="cg-pill green">✔ Verifier Ready</span>
      <span class="cg-pill blue">{mode_status_txt}</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")


# ── Sidebar Navigation & Configuration ─────────────────────────────────────────
st.sidebar.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
  <span style="font-size:1.4rem;">🛡️</span>
  <span style="font-size:1.05rem;font-weight:700;color:#ffffff;">ConstraintGuard IDE</span>
</div>
""", unsafe_allow_html=True)

# Navigation Items
st.sidebar.markdown("""
<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:16px;">
  <div style="background:rgba(59,130,246,0.20);border:1px solid rgba(59,130,246,0.40);color:#ffffff;padding:7px 10px;border-radius:8px;font-size:0.80rem;font-weight:600;">💬 Multi-Turn Workspace</div>
  <div style="padding:6px 10px;color:#64748b;font-size:0.80rem;">🕸️ Versioned Constraint Graph</div>
  <div style="padding:6px 10px;color:#64748b;font-size:0.80rem;">🛡️ Hybrid Verifier</div>
  <div style="padding:6px 10px;color:#64748b;font-size:0.80rem;">🔧 Repair Loop Stepper</div>
  <div style="padding:6px 10px;color:#64748b;font-size:0.80rem;">⚙️ LLM Provider Settings</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown('<div class="cg-card-title">Execution Mode</div>', unsafe_allow_html=True)
mode_choice = st.sidebar.radio(
    "Execution Mode:",
    ["Deterministic Demo Mode 🎯", "Live LLM Mode ⚡"],
    key="execution_mode",
    label_visibility="collapsed",
)

is_demo = "Demo" in mode_choice

if not is_demo:
    st.sidebar.markdown("---")
    st.sidebar.markdown('<div class="cg-card-title">🤖 AI Agent / Provider Config</div>', unsafe_allow_html=True)
    st.sidebar.markdown("<span style='font-size:0.75rem;color:#64748b;'>Groq (OpenAI-Compatible Endpoint)</span>", unsafe_allow_html=True)
    
    api_key_input = st.sidebar.text_input(
        "API Key (LLM_API_KEY)",
        value=os.getenv("LLM_API_KEY", ""),
        type="password",
    )
    base_url_input = st.sidebar.text_input(
        "Base URL (LLM_BASE_URL)",
        value=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    
    if api_key_input:
        provider = OpenAICompatibleProvider(
            base_url=base_url_input,
            api_key=api_key_input,
            model=st.session_state.selected_model,
        )
    else:
        st.sidebar.warning("⚠️ No API Key entered. Falling back to Mock Provider.")
        provider = get_default_provider()

    sidebar_model = st.sidebar.selectbox(
        "Select Groq AI Model",
        options=all_models,
        index=current_model_idx,
        key="sb_agent_selector",
    )
    if sidebar_model != st.session_state.selected_model:
        st.session_state.selected_model = sidebar_model
        st.session_state.model_status = "🟡 Availability not checked"
        if hasattr(provider, "model"):
            provider.model = sidebar_model
        log_activity(f"Selected AI Model changed to: {sidebar_model}")
        st.rerun()

    st.sidebar.markdown(
        f"<div style='background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.25);border-radius:8px;padding:8px 10px;margin-top:6px;font-size:0.72rem;color:#4ade80;'>"
        f"<b>Status</b>: {st.session_state.model_status}"
        f"</div>",
        unsafe_allow_html=True,
    )

    sb_btn1, sb_btn2 = st.sidebar.columns(2)
    with sb_btn1:
        if st.button("🔄 Refresh Models", key="sb_refresh_models"):
            models_data = provider.list_models()
            if models_data:
                model_ids = [m["id"] for m in models_data if isinstance(m, dict) and "id" in m]
                st.session_state.discovered_models = model_ids
                st.sidebar.success(f"Found {len(model_ids)} online models.")
                log_activity(f"Discovered {len(model_ids)} online Groq models.")
            else:
                st.sidebar.warning("No online models returned.")

    with sb_btn2:
        if st.button("🧪 Test Agent", key="sb_test_model"):
            with st.spinner("Testing AI Agent access..."):
                res = provider.test_model_availability(st.session_state.selected_model)
                st.session_state.model_status = res["status_label"]
                if res["available"]:
                    st.sidebar.success(res["message"])
                else:
                    st.sidebar.error(res["message"])
                log_activity(f"Model test ({st.session_state.selected_model}): {res['status_label']}")

else:
    provider = DeterministicMockProvider(
        response_map={
            "Do not use max()": """def find_max(lst):
    if not lst:
        return None
    curr = lst[0]
    for x in lst[1:]:
        if x > curr:
            curr = x
    return curr"""
        },
        default_response="""def process_data(lst):
    if not lst:
        return None
    return lst[0]""",
    )
    st.sidebar.info("🎯 Running in Offline Deterministic Demo Mode")


# ── Hero Scenario Selector Banner ──────────────────────────────────────────────
st.markdown("""
<div class="cg-hero">
  <div class="cg-hero-title">👋 How can I help you verify code today?</div>
  <div class="cg-hero-sub">Select a multi-turn scenario preset or add custom requirements below.</div>
</div>
""", unsafe_allow_html=True)

preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
with preset_col1:
    if st.button("🚫 Scenario A: Built-in max() Prohibition", key="scen_a_btn"):
        set_conversation(
            [
                {"turn": 1, "text": "Write a function that finds the maximum value in a list. Do not use max()."},
                {"turn": 2, "text": "Also handle an empty list gracefully by returning None."},
                {"turn": 3, "text": "Keep the previous restrictions."},
            ],
            code_text="def find_max(lst):\n    if not lst:\n        return None\n    return max(lst)"
        )
        log_activity("Loaded Scenario A preset.")
        st.rerun()

with preset_col2:
    if st.button("🔄 Scenario B: Recursion Supersession", key="scen_b_btn"):
        set_conversation(
            [
                {"turn": 1, "text": "Use recursion to compute factorial."},
                {"turn": 2, "text": "Do not use recursion. Write an iterative solution instead."},
            ],
            code_text="def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)"
        )
        log_activity("Loaded Scenario B preset.")
        st.rerun()

with preset_col3:
    if st.button("⚠️ Scenario C: Unresolved Conflict", key="scen_c_btn"):
        set_conversation(
            [
                {"turn": 1, "text": "Return None for empty input."},
                {"turn": 2, "text": "Raise ValueError for empty input."},
            ],
            code_text="def process_data(lst):\n    if not lst:\n        return None\n    return lst[0]"
        )
        log_activity("Loaded Scenario C preset.")
        st.rerun()

with preset_col4:
    if st.button("🗑️ Clear Workspace", key="clear_all_btn"):
        set_conversation([], code_text="")
        log_activity("Workspace cleared.")
        st.rerun()


# Compute extracted graph and resolved state
parsed_conv = st.session_state.conversation
if parsed_conv:
    extracted_res = extract(parsed_conv)
    graph = VersionedConstraintGraph.build_from_constraints(extracted_res.constraints)
    resolver = ConstraintResolver()
    resolved_state = resolver.resolve(graph)
else:
    graph = VersionedConstraintGraph()
    resolved_state = resolver = None


# ── Main 3-Column IDE Layout ───────────────────────────────────────────────────
col_left, col_mid, col_right = st.columns([10, 12, 8])

do_generate = False
do_verify = False
do_repair = False
do_autoloop = False

# ── COLUMN 1: Conversation History & Quick Prompts ─────────────────────────────
with col_left:
    st.markdown(f"""
    <div class="cg-card">
      <div class="cg-card-title">
        <span>💬 Multi-Turn Conversation History</span>
        <span class="cg-pill blue">{len(parsed_conv)} turns</span>
      </div>
    """, unsafe_allow_html=True)

    if parsed_conv:
        for t in parsed_conv:
            st.markdown(f"""
            <div class="cg-chat-msg">
              <div class="cg-avatar user">Y</div>
              <div style="flex-grow:1;">
                <div class="cg-msg-header"><span>You</span><span>Turn {t['turn']}</span></div>
                <div style="color:#e2e8f0;font-weight:500;">{t['text']}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # Chat Input Box for New Requirement / Turn
    st.markdown('<div style="font-size:0.70rem;font-weight:600;color:#64748b;margin-top:10px;margin-bottom:4px;">➕ ADD NEW REQUIREMENT TURN:</div>', unsafe_allow_html=True)
    new_turn_input = st.text_input(
        "Type your prompt or constraint here...",
        key="new_turn_input_box",
        placeholder="e.g. Do not use built-in sum() or handle negative numbers",
        label_visibility="collapsed",
    )
    if st.button("🚀 Add Turn & Extract Constraints", key="add_turn_btn", type="primary"):
        if new_turn_input.strip():
            next_turn_num = len(st.session_state.conversation) + 1
            st.session_state.conversation.append({"turn": next_turn_num, "text": new_turn_input.strip()})
            st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in st.session_state.conversation])
            log_activity(f"Added Turn {next_turn_num}: {new_turn_input.strip()}")
            st.rerun()

    # Raw Turn Lines Editor Expander
    with st.expander("📝 View / Edit All Raw Conversation Turn Lines", expanded=not bool(parsed_conv)):
        edited_raw_text = st.text_area(
            "Raw Turn Lines",
            value=st.session_state.conv_raw_text,
            height=140,
            key="conv_raw_textarea",
        )
        if edited_raw_text != st.session_state.conv_raw_text:
            st.session_state.conv_raw_text = edited_raw_text
            new_parsed = []
            for line in edited_raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if ":" in line and line.lower().startswith("turn"):
                    parts = line.split(":", 1)
                    turn_num = int("".join(filter(str.isdigit, parts[0])) or "1")
                    text = parts[1].strip()
                    new_parsed.append({"turn": turn_num, "text": text})
                else:
                    new_parsed.append({"turn": len(new_parsed) + 1, "text": line})
            st.session_state.conversation = new_parsed

    st.markdown("</div>", unsafe_allow_html=True)

    # Quick Prompt Shortcuts Card
    st.markdown("""
    <div class="cg-card">
      <div class="cg-card-title">⚡ Quick Constraint Shortcuts</div>
    """, unsafe_allow_html=True)
    
    qp_col1, qp_col2 = st.columns(2)
    with qp_col1:
        if st.button("🚫 Do not use max()", key="qp_max"):
            st.session_state.conversation.append({"turn": len(st.session_state.conversation) + 1, "text": "Do not use built-in max()."})
            st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in st.session_state.conversation])
            log_activity("Added quick prompt: Do not use max()")
            st.rerun()
        if st.button("🛡️ Handle empty input", key="qp_empty"):
            st.session_state.conversation.append({"turn": len(st.session_state.conversation) + 1, "text": "Handle an empty list gracefully by returning None."})
            st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in st.session_state.conversation])
            log_activity("Added quick prompt: Handle empty input")
            st.rerun()
    with qp_col2:
        if st.button("🔄 No recursion", key="qp_recur"):
            st.session_state.conversation.append({"turn": len(st.session_state.conversation) + 1, "text": "Do not use recursion. Write an iterative solution instead."})
            st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in st.session_state.conversation])
            log_activity("Added quick prompt: No recursion")
            st.rerun()
        if st.button("⚠️ Raise ValueError", key="qp_valerr"):
            st.session_state.conversation.append({"turn": len(st.session_state.conversation) + 1, "text": "Raise ValueError for empty or invalid input."})
            st.session_state.conv_raw_text = "\n".join([f"Turn {t['turn']}: {t['text']}" for t in st.session_state.conversation])
            log_activity("Added quick prompt: Raise ValueError")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ── COLUMN 2: Code Editor Workspace & Live Repair ──────────────────────────────
with col_mid:
    # Toolbar Action Row
    tb1, tb2, tb3, tb4 = st.columns(4)
    with tb1:
        mb_gen = st.button("🤖 Generate Code", key="mb_gen_btn", type="primary")
    with tb2:
        mb_ver = st.button("🔍 Verify Code", key="mb_ver_btn")
    with tb3:
        mb_rep = st.button("🔧 Repair Violations", key="mb_rep_btn")
    with tb4:
        mb_loop = st.button("🔄 Auto Repair Loop", key="mb_loop_btn")

    do_generate = mb_gen
    do_verify = mb_ver
    do_repair = mb_rep
    do_autoloop = mb_loop

    # Code Editor Window
    st.markdown("""
    <div class="cg-card">
      <div class="cg-card-title">
        <span>💻 Candidate Python Code Editor</span>
        <span class="cg-pill">Python 3.10</span>
      </div>
    """, unsafe_allow_html=True)

    edited_code = st.text_area(
        "Python Candidate Code Editor",
        value=st.session_state.code,
        height=240,
        label_visibility="collapsed",
    )
    if edited_code != st.session_state.code:
        st.session_state.code = edited_code

    st.markdown("</div>", unsafe_allow_html=True)

    # Code Controls bar below code
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        c_ver = st.button("▶ Verify Candidate Code", key="cc_ver", type="primary")
    with cc2:
        c_rep = st.button("🔧 Repair Violations", key="cc_rep")
    with cc3:
        c_loop = st.button("🔄 Auto Repair Loop", key="cc_loop")

    if c_ver: do_verify = True
    if c_rep: do_repair = True
    if c_loop: do_autoloop = True

    # Perform Actions
    if do_generate:
        try:
            with st.spinner("AI Agent generating candidate code..."):
                code_gen = generate_code(st.session_state.conversation, provider=provider)
                st.session_state.code = code_gen
                st.session_state.repair_history = None
                st.session_state.model_status = "🟢 Available"
                log_activity("Candidate code generated successfully by AI Agent.")
                st.rerun()
        except LLMProviderError as err:
            st.session_state.model_status = "🔴 Unavailable"
            st.error(f"⚠️ LLM Provider Error ({err.error_category.value}): {err.message}")
            log_activity(f"LLM Error during Code Generation: {err.error_category.value}")
        except Exception as err:
            st.session_state.model_status = "🔴 Unavailable"
            st.error(f"⚠️ Error: {err}")
            log_activity(f"Error during Code Generation: {err}")

    if do_verify:
        if parsed_conv and st.session_state.code:
            engine = VerificationEngine()
            st.session_state.report = engine.verify(
                st.session_state.code, graph.get_all_constraints()
            )
            log_activity(f"Code verified. Verdict: {st.session_state.report.overall_status}")
            st.rerun()

    if do_repair:
        if st.session_state.report:
            try:
                with st.spinner("AI Agent generating repair fix..."):
                    repaired_code_res = repair_code(
                        conversation=st.session_state.conversation,
                        code=st.session_state.code,
                        verification_report=st.session_state.report,
                        active_constraints=resolved_state.active,
                        provider=provider,
                    )
                    st.session_state.code = repaired_code_res
                    engine = VerificationEngine()
                    st.session_state.report = engine.verify(
                        st.session_state.code, graph.get_all_constraints()
                    )
                    st.session_state.model_status = "🟢 Available"
                    log_activity(f"Repair generated. Re-verification verdict: {st.session_state.report.overall_status}")
                    st.rerun()
            except Exception as err:
                st.session_state.model_status = "🔴 Unavailable"
                st.error(f"⚠️ LLM Repair Error: {err}")
                log_activity(f"Error during Repair: {err}")

    if do_autoloop:
        try:
            with st.spinner("Running Closed-Loop Repair Loop..."):
                history: RepairHistory = run_repair_loop(
                    conversation=st.session_state.conversation,
                    initial_code=st.session_state.code,
                    max_iterations=2,
                    provider=provider,
                )
                st.session_state.repair_history = history
                st.session_state.code = history.final_code
                st.session_state.report = history.final_report
                st.session_state.model_status = "🟢 Available"
                log_activity(f"Auto Repair Loop finished in {history.iterations_used} iter(s). Final verdict: {history.final_report.overall_status}")
                st.rerun()
        except Exception as err:
            st.session_state.model_status = "🔴 Unavailable"
            st.error(f"⚠️ Auto Repair Error: {err}")

    # Execution Status Box
    st.markdown("""
    <div class="cg-card">
      <div class="cg-card-title">⚡ Live Engine Execution Status</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:#94a3b8;">
        Candidate code is loaded. Click <b>▶ Verify Candidate Code</b> to test against active extracted constraints.
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── COLUMN 3: Right Side Panel (Status, Constraints, Verification, Repair) ─────
with col_right:
    # 1. System Status Card
    model_name_disp = "Deterministic Mock" if is_demo else st.session_state.selected_model
    st.markdown(f"""
    <div class="cg-card">
      <div class="cg-card-title">
        <span>⚙️ System Status</span>
        <span class="cg-pill green">All Operational</span>
      </div>
      <div class="cg-status-row">
        <span class="cg-status-lbl"><span>AI Agent Provider</span></span>
        <span class="cg-status-val">{"Offline Mock" if is_demo else "Groq Cloud"}</span>
      </div>
      <div class="cg-status-row">
        <span class="cg-status-lbl"><span>Selected Agent Model</span></span>
        <span class="cg-status-val" style="color:#60a5fa;">{model_name_disp}</span>
      </div>
      <div class="cg-status-row">
        <span class="cg-status-lbl"><span>Hybrid Verifier</span></span>
        <span class="cg-status-val" style="color:#4ade80;">✔ Ready</span>
      </div>
      <div class="cg-status-row">
        <span class="cg-status-lbl"><span>Execution Mode</span></span>
        <span class="cg-status-val" style="color:#c084fc;">{"Demo Mode" if is_demo else "Live LLM"}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. Active Constraints Card
    if resolved_state:
        st.markdown(f"""
        <div class="cg-card">
          <div class="cg-card-title">
            <span>📋 Extracted Constraints</span>
            <span class="cg-pill blue">{len(resolved_state.active)} Active</span>
          </div>
        """, unsafe_allow_html=True)

        for c in resolved_state.active:
            st.markdown(f"""
            <div class="cg-constraint-card">
              <div class="cg-c-header">
                <span class="cg-c-id">{c.id}</span>
                <span class="cg-pill green" style="font-size:0.60rem;">ACTIVE</span>
              </div>
              <div class="cg-c-text">{c.text}</div>
            </div>
            """, unsafe_allow_html=True)

        for c in resolved_state.superseded:
            st.markdown(f"""
            <div class="cg-constraint-card" style="opacity:0.6;">
              <div class="cg-c-header">
                <span class="cg-c-id" style="color:#94a3b8;background:rgba(255,255,255,0.06);">{c.id}</span>
                <span class="cg-pill" style="font-size:0.60rem;">SUPERSEDED</span>
              </div>
              <div class="cg-c-text" style="color:#64748b;">{c.text}</div>
            </div>
            """, unsafe_allow_html=True)

        for c in resolved_state.conflicting:
            st.markdown(f"""
            <div class="cg-constraint-card" style="border-color:rgba(239,68,68,0.30);">
              <div class="cg-c-header">
                <span class="cg-c-id">{c.id}</span>
                <span class="cg-pill red" style="font-size:0.60rem;">CONFLICTING</span>
              </div>
              <div class="cg-c-text" style="color:#f87171;">{c.text}</div>
            </div>
            """, unsafe_allow_html=True)

        with st.expander("🕸️ View Graph Dependency Edges", expanded=False):
            all_edges = graph.get_all_edges()
            if all_edges:
                for src, dst, etype in all_edges:
                    st.write(f"`{src}` ──[{etype.value}]──> `{dst}`")

        st.markdown("</div>", unsafe_allow_html=True)

    # 3. Verification Results Card
    if st.session_state.report:
        rep = st.session_state.report
        status_pass = rep.overall_status == "PASS"
        banner_txt = "✔ VERIFIED (PASS)" if status_pass else "❌ VIOLATIONS DETECTED (FAIL)"
        sub_txt = "All active constraints satisfied!" if status_pass else "Code violates extracted active constraints."

        st.markdown(f"""
        <div class="cg-card">
          <div class="cg-card-title">
            <span>🛡️ Verification Report</span>
            <span class="cg-pill">Grounded Evidence</span>
          </div>
          <div style="background:rgba({'34,197,94' if status_pass else '239,68,68'},0.10);border:1px solid rgba({'34,197,94' if status_pass else '239,68,68'},0.30);border-radius:8px;padding:12px;margin-bottom:10px;">
            <div style="font-size:1.0rem;font-weight:700;color:{'#4ade80' if status_pass else '#f87171'};">{banner_txt}</div>
            <div style="font-size:0.75rem;color:#94a3b8;">{sub_txt}</div>
          </div>
        """, unsafe_allow_html=True)

        for res in rep.results:
            st_val = res.status.value
            st_icon = "✔" if st_val == "SATISFIED" else ("❌" if st_val == "VIOLATED" else "⚠️")
            st_col = "#4ade80" if st_val == "SATISFIED" else ("#f87171" if st_val == "VIOLATED" else "#facc15")
            
            ev_badges = "".join([f' [{e.verifier}]' for e in res.evidences]) or ""

            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:0.78rem;">
              <span style="font-family:'JetBrains Mono',monospace;">{res.constraint_id}{ev_badges}</span>
              <span style="color:{st_col};font-weight:600;">{st_icon} {st_val}</span>
            </div>
            """, unsafe_allow_html=True)

        with st.expander("📊 View Grounded Evidence Dataframe", expanded=False):
            ver_rows = []
            for res in rep.results:
                ver_rows.append({
                    "Constraint ID": res.constraint_id,
                    "Status": res.status.value,
                    "Evidence": " | ".join([f"{e.verifier}: {e.message}" for e in res.evidences])
                })
            st.dataframe(ver_rows)

        st.markdown("</div>", unsafe_allow_html=True)

    # 4. Repair History Card
    rep_count = st.session_state.repair_history.iterations_used if st.session_state.repair_history else 0
    st.markdown(f"""
    <div class="cg-card">
      <div class="cg-card-title">
        <span>🔧 Repair History</span>
        <span class="cg-pill">{rep_count} attempts</span>
      </div>
    """, unsafe_allow_html=True)

    if st.session_state.repair_history:
        rh: RepairHistory = st.session_state.repair_history
        st.write(f"**Iterations**: `{rh.iterations_used} / 2`")
        st.write(f"**Final Verdict**: `{rh.final_report.overall_status}`")
        with st.expander("🔍 View Before & After Code Diff", expanded=False):
            d1, d2 = st.columns(2)
            d1.markdown("**Original Violated Code**")
            d1.code(rh.initial_code, language="python")
            d2.markdown("**Repaired Code**")
            d2.code(rh.final_code, language="python")
    else:
        st.markdown("""
        <div style="text-align:center;padding:16px;color:#64748b;font-size:0.78rem;">
          ⏱️ No repairs yet.<br/>Run verification to see repair history when violations are found.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Bottom Section: System Audit Trail & Activity Log ──────────────────────────
st.markdown("""
<div class="cg-card">
  <div class="cg-card-title">📊 System Audit Trail &amp; Activity Log</div>
""", unsafe_allow_html=True)
log_html = "<br/>".join(st.session_state.cg_activity_log)
st.markdown(f'<div class="cg-activity-box">{log_html}</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="margin-top:20px;padding:12px;border-top:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;color:#64748b;font-size:0.72rem;font-family:'JetBrains Mono',monospace;">
  <span>ConstraintGuard — Track · Resolve · Verify · Repair · Re-Verify</span>
  <span>Model-Agnostic | Evidence-Grounded | Explainable | Built for Safer AI Code Generation</span>
</div>
""", unsafe_allow_html=True)
