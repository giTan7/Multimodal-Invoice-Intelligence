"""
Streamlit UI  --  presentation layer ONLY.

This file never sees an API key. It only talks to our FastAPI backend (BACKEND_URL):
    GET  /prompts/versions   -> fills the version dropdown
    POST /extract            -> uploads the document + chosen version, returns the result

Run (from the project root):   streamlit run app/frontend/streamlit_app.py
"""
import html
import io
import json
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import requests
import streamlit as st
from dotenv import load_dotenv

from grading import score  # app/frontend/grading.py (Streamlit puts this folder on the import path)

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")                      # only BACKEND_URL is used here; secrets stay in the backend
BACKEND_URL = (os.getenv("BACKEND_URL") or "http://localhost:8000").rstrip("/")
SAMPLES_DIR = ROOT / "samples"

FIELDS = [
    ("invoice_number", "Invoice number"),
    ("vendor_name", "Vendor name"),
    ("gstin", "GSTIN"),
    ("invoice_date", "Invoice date"),
    ("total_amount", "Total amount"),
]
FIELD_KEYS = [k for k, _ in FIELDS]

# (label, file, what it tests)
SAMPLES = [
    ("Clean invoice (PNG)", "invoice_clean.png",
     "Two GSTINs and three dates on one page. Tests seller vs buyer and invoice date vs due date."),
    ("Scanned invoice (JPG)", "invoice_scanned.jpg",
     "Tilted, noisy scan. The date is 03/10/2026 (3 October) and there are CGST/SGST lines."),
    ("Invoice PDF (2 pages)", "invoice_native.pdf",
     "Page 2 holds bank details and a PAN that must not be mistaken for a GSTIN."),
    ("Billing export (CSV)", "invoice_export.csv",
     "Tabular text, no image. The total is in the INVOICE TOTAL row, not in a line item."),
    ("Retail bill (PNG)", "retail_bill.png",
     "No GSTIN printed, a 2-digit year, and an FSSAI licence number that looks like an ID."),
]

GRADE_MARK = {"ok": ("✓", "g-ok"), "format": ("≈", "g-format"), "wrong": ("✗", "g-wrong"), "missing": ("✗", "g-wrong")}
STATUS_BADGE = {"ok": ("Clean JSON", "ok"), "off_schema": ("Wrong keys", "warn"), "not_json": ("Plain text", "bad")}

st.set_page_config(page_title="Multimodal Invoice Intelligence", page_icon="🧾", layout="wide")

# ----------------------------------------------------------------------------
# Styling. Ink + paper, one turmeric accent. Display: Bricolage Grotesque.
# Body: Figtree. Extracted values: JetBrains Mono (they are data, so they look like data).
# ----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Figtree:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap');

:root{
  --ink:#1B2340; --ink-soft:#4A5273; --paper:#F3F5FA; --card:#FFFFFF;
  --line:#DDE2EE; --turmeric:#E9A21B; --turmeric-ink:#7A5200;
  --ok:#1F8A5B; --ok-bg:#E6F5ED; --fmt:#8A5A00; --fmt-bg:#FFF1CC; --err:#B3261E; --err-bg:#FBE7E5;
}
html, body, [data-testid="stAppViewContainer"]{ background:var(--paper); }
[data-testid="stAppViewContainer"], .stMarkdown, label, p, li{ font-family:'Figtree',sans-serif; color:var(--ink); }
[data-testid="stHeader"]{ background:transparent; }
#MainMenu, footer, [data-testid="stToolbar"]{ visibility:hidden; }
.block-container{ max-width:1180px; padding-top:1.6rem; padding-bottom:4rem; }

/* ---- hero ---- */
.hero{ background:var(--ink); border-radius:18px; padding:34px 38px 30px; margin-bottom:26px; border-bottom:5px solid var(--turmeric); }
.hero h1{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:2.5rem; letter-spacing:-0.02em; color:#fff; margin:0 0 8px 0; line-height:1.05; }
.hero p{ color:#C5CBE3; font-size:1.05rem; margin:0; max-width:680px; }

.sec{ font-family:'Bricolage Grotesque',sans-serif; font-weight:600; font-size:1.25rem; letter-spacing:-0.01em; margin:4px 0 10px; color:var(--ink); }
.hint{ color:var(--ink-soft); font-size:.92rem; margin:2px 0 12px; }
[data-testid="stVerticalBlockBorderWrapper"]{ background:var(--card); border-radius:14px; border-color:var(--line) !important; }
[data-testid="stImage"] img{ max-height:430px; object-fit:contain; border:1px solid var(--line); border-radius:8px; }
[data-testid="stFileUploaderDropzone"]{ background:#F8F9FD; border:2px dashed #B9C1DB; border-radius:12px; }
[data-testid="stFileUploaderDropzone"]:hover{ border-color:var(--turmeric); background:#FFFAEF; }

/* ---- buttons ---- */
button[data-testid="stBaseButton-primary"], .stButton > button[kind="primary"]{
  background:var(--ink); color:#fff; border:0; border-radius:10px; padding:.7rem 1rem; font-family:'Figtree',sans-serif; font-weight:600; font-size:1rem; width:100%; }
button[data-testid="stBaseButton-primary"]:hover, .stButton > button[kind="primary"]:hover{ background:var(--turmeric); color:var(--ink); }
button[data-testid="stBaseButton-primary"]:disabled{ background:#B9C1DB; color:#fff; }
/* button labels are <p> tags, which the global text colour above would otherwise turn ink-on-ink */
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primary"]:disabled p{ color:#fff; }
button[data-testid="stBaseButton-primary"]:hover p{ color:var(--ink); }
button[data-testid="stBaseButton-secondary"] p{ color:var(--ink); }
button[data-testid="stBaseButton-secondary"]{ border-radius:10px; font-weight:600; border-color:#B9C1DB; color:var(--ink); }
button[data-testid="stBaseButton-secondary"]:hover{ border-color:var(--turmeric); color:var(--ink); background:#FFFAEF; }
button:focus-visible{ outline:3px solid var(--turmeric) !important; outline-offset:2px; }

/* ---- the invoice slip ---- */
.slip{ position:relative; background:#fff; border:1px solid var(--line); border-radius:6px 6px 14px 14px; padding:34px 30px 14px; margin-top:12px; box-shadow:0 10px 30px -18px rgba(27,35,64,.45); }
.slip::before{ content:""; position:absolute; top:-1px; left:0; right:0; height:14px; background:radial-gradient(circle at 10px 0, var(--paper) 7px, transparent 7.5px) 0 0 / 20px 14px repeat-x; }
.slip-head{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px; }
.slip-title{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:1.35rem; letter-spacing:-0.01em; }
.slip-sub{ color:var(--ink-soft); font-size:.88rem; margin-top:2px; }
.stamp{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:1.05rem; color:var(--turmeric-ink); border:2.5px solid var(--turmeric); border-radius:10px; padding:5px 14px; transform:rotate(-4deg); background:#FFF6DF; white-space:nowrap; }
.row{ display:flex; justify-content:space-between; align-items:center; gap:14px; padding:15px 0; border-top:1px dashed var(--line); }
.row:first-of-type{ border-top:0; }
.lbl{ color:var(--ink-soft); font-size:.95rem; min-width:120px; }
.val{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:1.1rem; text-align:right; word-break:break-word; flex:1; }
.val.missing{ font-family:'Figtree',sans-serif; font-weight:500; font-style:italic; color:#9AA2BF; }
.row.total{ border-top:2px solid var(--ink); margin-top:4px; }
.row.total .val{ font-size:1.45rem; color:var(--ok); }
.row.total .val.missing{ font-size:1.1rem; color:#9AA2BF; }
.chk{ display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:50%; font-weight:700; font-size:.95rem; flex:none; }
.g-ok{ background:var(--ok-bg); color:var(--ok); } .g-format{ background:var(--fmt-bg); color:var(--fmt); } .g-wrong{ background:var(--err-bg); color:var(--err); }
.legend{ color:var(--ink-soft); font-size:.85rem; margin:10px 2px 0; }
.legend b{ display:inline-block; min-width:20px; text-align:center; border-radius:6px; padding:0 5px; margin-right:3px; }

/* ---- request info ---- */
.meta{ display:flex; justify-content:space-between; gap:12px; padding:9px 0; border-bottom:1px solid #EEF1F8; font-size:.95rem; }
.meta:last-child{ border-bottom:0; }
.meta span:first-child{ color:var(--ink-soft); }
.meta span:last-child{ font-weight:600; text-align:right; }
.pill{ display:inline-block; padding:2px 11px; border-radius:99px; font-weight:600; font-size:.86rem; white-space:nowrap; }
.pill.ok{ background:var(--ok-bg); color:var(--ok); } .pill.warn{ background:var(--fmt-bg); color:var(--fmt); } .pill.bad{ background:var(--err-bg); color:var(--err); }
.note{ background:#FFF6DF; border-left:4px solid var(--turmeric); border-radius:8px; padding:12px 16px; font-size:.95rem; color:#5A3F00; margin:12px 0 4px; }
.note.bad{ background:var(--err-bg); border-left-color:var(--err); color:#6B1A15; }
.pdfcard{ background:#F8F9FD; border:1px solid var(--line); border-radius:12px; padding:22px; text-align:center; }

/* ---- compare matrix ---- */
.cmpwrap{ overflow-x:auto; margin-top:8px; }
table.cmp{ width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid var(--line); border-radius:14px; overflow:hidden; font-size:.95rem; }
table.cmp th{ background:var(--ink); color:#fff; font-family:'Bricolage Grotesque',sans-serif; font-weight:600; padding:12px 14px; text-align:left; }
table.cmp td{ padding:12px 14px; border-top:1px solid #EEF1F8; vertical-align:top; font-family:'JetBrains Mono',monospace; font-weight:600; font-size:.9rem; word-break:break-word; }
table.cmp td.fld{ font-family:'Figtree',sans-serif; font-weight:500; color:var(--ink-soft); white-space:nowrap; }
table.cmp td.exp{ background:#F8F9FD; color:var(--ink); }
table.cmp td.nul{ font-family:'Figtree',sans-serif; font-style:italic; font-weight:500; color:#9AA2BF; }
table.cmp td.g-ok{ background:var(--ok-bg); color:#14573A; } table.cmp td.g-format{ background:var(--fmt-bg); color:var(--fmt); } table.cmp td.g-wrong{ background:var(--err-bg); color:#7A1B16; }
table.cmp td.sum{ font-family:'Figtree',sans-serif; font-weight:600; }
table.cmp td.sm{ font-family:'Figtree',sans-serif; font-weight:500; color:var(--ink-soft); }


/* ---- sidebar navigation + Prompt Studio ---- */
.navtitle{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:1.1rem; letter-spacing:-0.01em; margin:2px 0 12px; color:var(--ink); }
[data-testid="stSidebar"] [role="radiogroup"]{ gap:6px; }
[data-testid="stSidebar"] [role="radiogroup"] label{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:9px 12px; width:100%; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){ border-color:var(--turmeric); background:#FFF6DF; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child{ display:none; }
.vrow{ display:flex; justify-content:space-between; align-items:center; gap:12px; padding:13px 16px; border:1px solid var(--line); border-radius:12px; background:#fff; margin:10px 0 2px; }
.vrow.active{ border:2px solid var(--ok); background:#F2FBF6; }
.vnum{ font-family:'JetBrains Mono',monospace; font-weight:600; }
.vname{ font-weight:600; }
.statusbar{ display:flex; flex-wrap:wrap; gap:8px 22px; align-items:center; background:#fff; border:1px solid var(--line); border-radius:12px; padding:12px 18px; margin:-6px 0 18px; font-size:.95rem; }
.statusbar b{ font-weight:600; }
table.cmp th.draft{ background:var(--turmeric); color:var(--ink); }

@media (prefers-reduced-motion: no-preference){ button{ transition:background .15s ease; } }
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Talking to the backend
# ----------------------------------------------------------------------------
def backend_error(resp: requests.Response) -> str:
    try:
        return resp.json().get("detail") or resp.text
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"


@st.cache_data(ttl=5, show_spinner=False)
def fetch_versions():
    """Returns (versions, prompt_name, error_message, active_version)."""
    try:
        r = requests.get(f"{BACKEND_URL}/prompts/versions", timeout=15)
    except requests.ConnectionError:
        return [], None, (f"Can't reach the backend at {BACKEND_URL}. Start it with: "
                          f"uvicorn app.backend.main:app --reload --port 8000"), None
    except requests.Timeout:
        return [], None, "The backend took too long to answer.", None
    if r.status_code != 200:
        return [], None, backend_error(r), None
    data = r.json()
    return data["versions"], data["prompt_name"], None, data.get("active_version")


@st.cache_data(ttl=30, show_spinner=False)
def fetch_models():
    try:
        return list(requests.get(f"{BACKEND_URL}/health", timeout=10).json().get("models", {}).keys())
    except Exception:
        return ["Claude Haiku 4.5", "Claude Sonnet 4.6"]


@st.cache_data(show_spinner=False)
def load_ground_truth():
    try:
        return json.loads((SAMPLES_DIR / "ground_truth.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def call_extract(name, data, version, model_label, user_id):
    """One extraction request. Returns (ok, payload_or_error_text). Safe to run in a thread."""
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        r = requests.post(f"{BACKEND_URL}/extract", files={"file": (name, data, mime)},
                          data={"prompt_version": version, "model_label": model_label, "user_id": user_id},
                          timeout=120)
    except requests.ConnectionError:
        return False, f"Can't reach the backend at {BACKEND_URL}. Is it running?"
    except requests.Timeout:
        return False, "The extraction took too long. Try again."
    return (True, r.json()) if r.status_code == 200 else (False, backend_error(r))


def esc(x) -> str:
    return html.escape(str(x))


def mark(grade: str) -> str:
    symbol, cls = GRADE_MARK[grade]
    return f'<span class="chk {cls}">{symbol}</span>'


def status_banner(data) -> str:
    """Explains, in plain words, when a prompt version didn't follow the output contract."""
    if data["status"] == "ok":
        return ""
    cls = "note bad" if data["status"] == "not_json" else "note"
    return f'<div class="{cls}"><b>{STATUS_BADGE[data["status"]][0]}.</b> {esc(data["status_message"])}</div>'


def render_compare(runs, exp, active_version=None):
    """
    The side-by-side matrix, shared by the Invoice Extractor and Prompt Studio.
    Each run is {"ok", "payload"} plus either "version" (a saved prompt) or "label"/"draft" (a Studio draft).
    """
    def title(r):
        if r.get("label"):
            return r["label"]
        return f"Prompt v{r['version']}" + (" 🟢" if r["version"] == active_version else "")

    head = "<th>Field</th>" + ("<th>Expected</th>" if exp else "") + "".join(
        f'<th class="{"draft" if r.get("draft") else ""}">{esc(title(r))}</th>' for r in runs)
    body = ""

    # response-status row
    cells = ""
    for r in runs:
        if r["ok"]:
            text, cls = STATUS_BADGE[r["payload"]["status"]]
            cells += f'<td class="sum"><span class="pill {cls}">{text}</span></td>'
        else:
            cells += '<td class="sum"><span class="pill bad">Error</span></td>'
    body += f'<tr><td class="fld">Response</td>{"<td class=exp></td>" if exp else ""}{cells}</tr>'

    # one row per field
    scores = {}
    for i, r in enumerate(runs):
        if r["ok"] and exp:
            scores[i] = score(r["payload"]["fields"], exp, FIELD_KEYS, present=set(r["payload"]["keys_returned"]))
    for key, label in FIELDS:
        row = f'<td class="fld">{label}</td>'
        if exp:
            row += (f'<td class="exp">{esc(exp[key])}</td>' if exp.get(key) else '<td class="exp nul">null</td>')
        for i, r in enumerate(runs):
            if not r["ok"]:
                row += '<td class="nul">–</td>'
                continue
            if key not in r["payload"]["keys_returned"]:      # the model never produced this key
                row += ('<td class="nul">–</td>' if r["payload"]["status"] == "not_json"
                        else '<td class="g-wrong nul">no key</td>')
                continue
            value = r["payload"]["fields"].get(key)
            grade = scores[i]["grades"][key] if exp else None
            cls = (GRADE_MARK[grade][1] if grade else "") + ("" if value else " nul")
            row += f'<td class="{cls.strip()}">{esc(value) if value else "null"}</td>'
        body += f"<tr>{row}</tr>"

    # score + cost rows
    if exp:
        cells = ""
        for i, r in enumerate(runs):
            sc = scores.get(i)
            if sc:
                extra = f" · {sc['format']} format-only" if sc["format"] else ""
                cells += f'<td class="sum">{sc["ok"]}/{sc["total"]} correct{extra}</td>'
            else:
                cells += '<td class="sum">–</td>'
        body += f'<tr><td class="fld"><b>Score</b></td><td class="exp"></td>{cells}</tr>'
    meta_cells = "".join(
        f'<td class="sm">{r["payload"]["info"]["latency_ms"] / 1000:.1f} s · {r["payload"]["info"]["total_tokens"]} tokens</td>'
        if r["ok"] else '<td class="sm">–</td>' for r in runs)
    body += f'<tr><td class="fld">Latency · tokens</td>{"<td class=exp></td>" if exp else ""}{meta_cells}</tr>'

    st.markdown(f'<div class="cmpwrap"><table class="cmp"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
                unsafe_allow_html=True)
    if exp:
        st.markdown('<div class="legend"><b class="g-ok">green</b>correct <b class="g-format">amber</b>right value, wrong format '
                    '<b class="g-wrong">red</b>wrong, invented or missing</div>', unsafe_allow_html=True)

    for r in runs:
        if not r["ok"]:
            st.error(f"{title(r)}: {r['payload']}")
        elif r["payload"]["status"] != "ok":
            with st.expander(f"{title(r)}: what the model actually said", expanded=r["payload"]["status"] == "not_json"):
                st.markdown(status_banner(r["payload"]), unsafe_allow_html=True)
                st.code(r["payload"]["raw_output"], language=None)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------
st.session_state.setdefault("history", [])
st.session_state.setdefault("result", None)
st.session_state.setdefault("compare", None)

with st.sidebar:
    st.markdown('<div class="navtitle">Multimodal Invoice Intelligence</div>', unsafe_allow_html=True)
    page = st.radio("Navigate", ["📄 Invoice Extractor", "🧪 Prompt Studio"], label_visibility="collapsed")
    st.markdown("---")
    st.markdown("### Who's asking")
    user_id = st.text_input("User ID", value="demo_user", help="Attached to every Langfuse trace.")
    st.caption("Each extraction is traced in Langfuse under this user.")
    st.markdown("---")
    st.caption(f"Backend: {BACKEND_URL}")

# ---- second page: Prompt Studio (same app, same styling; the Invoice Extractor below is untouched) ----
if page == "🧪 Prompt Studio":
    import prompt_studio  # app/frontend/prompt_studio.py

    prompt_studio.render(SimpleNamespace(
        backend_url=BACKEND_URL, user_id=(user_id or "demo_user").strip() or "demo_user",
        samples=SAMPLES, samples_dir=SAMPLES_DIR, models=fetch_models(),
        ground_truth=load_ground_truth(), call_extract=call_extract, render_compare=render_compare,
        status_banner=status_banner, esc=esc, refresh_caches=fetch_versions.clear))
    st.stop()

st.markdown(
    """
<div class="hero">
  <h1>Multimodal Invoice Intelligence</h1>
  <p>Images, scans, PDFs and CSV exports go in. Pick a prompt version, or run them all side by side, and see what a better prompt changes.</p>
</div>
""",
    unsafe_allow_html=True,
)

versions, prompt_name, versions_error, active_version = fetch_versions()
models = fetch_models()
ground_truth = load_ground_truth()

left, right = st.columns([1.15, 1], gap="large")

# ---- choose the document -------------------------------------------------------
doc_name, doc_bytes, expected = None, None, None
with left:
    with st.container(border=True):
        st.markdown('<div class="sec">Choose a document</div>', unsafe_allow_html=True)
        source = st.radio("Source", ["Try a sample", "Upload my own"], horizontal=True, label_visibility="collapsed")
        if source == "Try a sample":
            labels = [s[0] for s in SAMPLES]
            choice = st.selectbox("Sample", labels, label_visibility="collapsed")
            _, fname, tests = SAMPLES[labels.index(choice)]
            st.markdown(f'<div class="hint"><b>Tests:</b> {esc(tests)}</div>', unsafe_allow_html=True)
            doc_name, doc_bytes = fname, (SAMPLES_DIR / fname).read_bytes()
            expected = ground_truth.get(fname)
        else:
            up = st.file_uploader("Document", type=["jpg", "jpeg", "png", "pdf", "csv"], label_visibility="collapsed")
            if up is None:
                st.markdown('<div class="hint">JPG, PNG, PDF or CSV, up to 10 MB.</div>', unsafe_allow_html=True)
            else:
                doc_name, doc_bytes = up.name, up.getvalue()

        # preview, by file type
        if doc_name:
            ext = Path(doc_name).suffix.lower()
            if ext in (".png", ".jpg", ".jpeg"):
                st.image(doc_bytes, use_container_width=True)
            elif ext == ".pdf":
                try:
                    st.pdf(doc_bytes, height=430)
                except Exception:
                    st.markdown(f'<div class="pdfcard"><b>{esc(doc_name)}</b><br>PDF · {len(doc_bytes) // 1024} KB</div>',
                                unsafe_allow_html=True)
            elif ext == ".csv":
                try:
                    import pandas as pd
                    st.dataframe(pd.read_csv(io.BytesIO(doc_bytes), dtype=str).fillna(""), hide_index=True, height=300)
                except Exception:
                    st.code(doc_bytes.decode("utf-8", "replace")[:2500], language=None)

with right:
    with st.container(border=True):
        st.markdown('<div class="sec">Choose how to extract</div>', unsafe_allow_html=True)
        if versions_error:
            st.error(versions_error)
        elif not versions:
            st.warning(f"No versions of the prompt '{prompt_name}' exist in Langfuse yet.")
            st.code("python -m app.prompts.seed_prompts --up-to 1", language="bash")
        c1, c2 = st.columns([1.15, 1.25])
        with c1:
            default_index = versions.index(active_version) if active_version in versions else 0
            version = st.selectbox(
                "Prompt version", versions or [None], index=default_index, disabled=not versions,
                key=f"extract_version_{active_version}",     # new active version -> dropdown resets to it
                format_func=lambda v: ("None found" if v is None else
                                       f"Version {v} 🟢" if v == active_version else f"Version {v}"))
        with c2:
            model_label = st.selectbox("Model", models)
        if st.button("↻ Refresh versions", help="Pick up versions you just created in Langfuse"):
            fetch_versions.clear()
            st.rerun()
        st.markdown('<div class="hint">Prompts are loaded from Langfuse when you click, so a new version needs no code change.'
                    + (f'<br>🟢 Active version: <b>v{active_version}</b> (set in Prompt Studio). It is selected by default.'
                       if active_version else '') + '</div>', unsafe_allow_html=True)
        can_run = bool(doc_name) and bool(versions)
        go_one = st.button("Extract with this version", type="primary", disabled=not can_run)
        go_all = st.button(f"Compare all {len(versions)} versions" if versions else "Compare all versions",
                           disabled=not can_run or len(versions) < 2,
                           help="Runs every prompt version on this same document, side by side")

uid = (user_id or "demo_user").strip() or "demo_user"

# ---- run: one version ------------------------------------------------------------
if go_one and can_run:
    with st.spinner(f"Reading {doc_name} with prompt version {version}…"):
        ok, payload = call_extract(doc_name, doc_bytes, version, model_label, uid)
    st.session_state.compare = None
    if ok:
        st.session_state.result = {"data": payload, "filename": doc_name, "expected": expected}
        f, info = payload["fields"], payload["info"]
        st.session_state.history.append({
            "Run": len(st.session_state.history) + 1, "File": doc_name, "Prompt version": info["prompt_version"],
            "Response": STATUS_BADGE[payload["status"]][0],
            **{label: f.get(key) or "—" for key, label in FIELDS},
            "Latency (s)": round(info["latency_ms"] / 1000, 2), "Tokens": info["total_tokens"]})
    else:
        st.session_state.result = None
        st.error(payload)

# ---- run: all versions side by side --------------------------------------------------
if go_all and can_run:
    ordered = sorted(versions)[:6]
    with st.spinner(f"Running {len(ordered)} prompt versions on {doc_name}…"):
        with ThreadPoolExecutor(max_workers=min(4, len(ordered))) as pool:
            futures = {v: pool.submit(call_extract, doc_name, doc_bytes, v, model_label, uid) for v in ordered}
            runs = [{"version": v, "ok": futures[v].result()[0], "payload": futures[v].result()[1]} for v in ordered]
    st.session_state.result = None
    st.session_state.compare = {"filename": doc_name, "expected": expected, "runs": runs}

# ---- show: single result ------------------------------------------------------------
stored = st.session_state.result
if stored:
    data, info, exp = stored["data"], stored["data"]["info"], stored["expected"]
    fields = data["fields"]
    grades = score(fields, exp, FIELD_KEYS, present=set(data["keys_returned"]))["grades"] if exp else None
    res_col, info_col = st.columns([1.15, 1], gap="large")

    with res_col:
        rows = ""
        for key, label in FIELDS:
            value = fields.get(key)
            cls = "row total" if key == "total_amount" else "row"
            val = f'<div class="val">{esc(value)}</div>' if value else '<div class="val missing">Not found</div>'
            rows += f'<div class="{cls}"><div class="lbl">{label}</div>{val}{mark(grades[key]) if grades else ""}</div>'
        legend = ('<div class="legend"><b class="g-ok">✓</b>correct <b class="g-format">≈</b>right value, wrong format '
                  '<b class="g-wrong">✗</b>wrong, invented or missing</div>') if grades else ""
        st.markdown(
            f"""
<div class="slip">
  <div class="slip-head">
    <div><div class="slip-title">Extraction result</div><div class="slip-sub">{esc(stored['filename'])}</div></div>
    <div class="stamp">prompt v{info['prompt_version']}</div>
  </div>
  {rows}
</div>{legend}{status_banner(data)}""",
            unsafe_allow_html=True,
        )
        with st.expander("Raw model output", expanded=data["status"] != "ok"):
            st.code(data["raw_output"], language=None if data["status"] == "not_json" else "json")

    with info_col:
        with st.container(border=True):
            st.markdown('<div class="sec">Request info</div>', unsafe_allow_html=True)
            label_text, pill_cls = STATUS_BADGE[data["status"]]
            traced = bool(info["trace_id"]) and not info["tracing_note"]
            st.markdown(
                f"""
<div class="meta"><span>Response</span><span><span class="pill {pill_cls}">{label_text}</span></span></div>
<div class="meta"><span>Prompt</span><span>{esc(info['prompt_name'])} · version {info['prompt_version']}</span></div>
<div class="meta"><span>Model</span><span>{esc(info['model'])}</span></div>
<div class="meta"><span>Latency</span><span>{info['latency_ms'] / 1000:.2f} s</span></div>
<div class="meta"><span>Tokens</span><span>{info['input_tokens']} in · {info['output_tokens']} out · {info['total_tokens']} total</span></div>
<div class="meta"><span>User</span><span>{esc(info['user_id'])}</span></div>
<div class="meta"><span>Request ID</span><span>{esc(info['request_id'])}</span></div>
<div class="meta"><span>Tracing</span><span><span class="pill {'ok' if traced else 'bad'}">{'Sent to Langfuse' if traced else 'Check Langfuse'}</span></span></div>
""",
                unsafe_allow_html=True,
            )
            if info.get("trace_id"):
                st.caption("Langfuse trace ID")
                st.code(info["trace_id"], language=None)
                if info.get("trace_url"):
                    st.link_button("Open trace in Langfuse", info["trace_url"], use_container_width=True)
                st.caption("Cost is calculated by Langfuse from the token usage. Open the trace to see it.")
            if info.get("tracing_note"):
                st.markdown(f'<div class="note">{esc(info["tracing_note"])} The extraction itself worked.</div>',
                            unsafe_allow_html=True)

# ---- show: compare matrix -------------------------------------------------------------
cmp_state = st.session_state.compare
if cmp_state:
    runs, exp = cmp_state["runs"], cmp_state["expected"]
    st.markdown(f'<div class="sec" style="margin-top:8px">Same document, different prompts</div>'
                f'<div class="hint">{esc(cmp_state["filename"])}: each column is a prompt version, '
                f'each run is traced separately in Langfuse.</div>', unsafe_allow_html=True)

    render_compare(runs, exp, active_version)

# ---- history ----------------------------------------------------------------------------
if st.session_state.history:
    with st.expander(f"All single runs this session ({len(st.session_state.history)})"):
        st.dataframe(st.session_state.history[::-1], hide_index=True, use_container_width=True)
        if st.button("Clear history"):
            st.session_state.history = []
            st.rerun()
