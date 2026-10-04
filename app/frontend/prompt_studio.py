"""
Prompt Studio  --  the second page of the app (presentation only, like the Invoice Extractor).

    WRITE a prompt -> TEST it (nothing saved) -> SAVE as the next version -> SET ACTIVE -> ROLLBACK anytime

All Langfuse work happens in the backend (/studio/... routes). This page only shows it.
  * Testing compares your unsaved draft with saved versions (v1, v2, v3 by default) on one sample.
  * "Active" = the version carrying Langfuse's "production" label. Setting another version active
    moves that label; no version is ever deleted.
"""
import html
import mimetypes
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

PROMPT_KEY = "studio_prompt"     # the editor text
NAME_KEY = "studio_name"         # the human-readable prompt name


def _esc(x) -> str:
    return html.escape(str(x))


def _call(method, url, timeout=30, **kwargs):
    """One backend call. Returns (ok, json_or_error_text). Never raises."""
    try:
        r = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.ConnectionError:
        return False, "Can't reach the backend. Is it running?"
    except requests.Timeout:
        return False, "The backend took too long to answer."
    if r.status_code == 200:
        return True, r.json()
    try:
        detail = r.json().get("detail")
    except ValueError:
        detail = None
    return False, str(detail or r.text or f"HTTP {r.status_code}")


@st.cache_data(ttl=20, show_spinner=False)
def fetch_studio(backend_url: str):
    return _call("GET", f"{backend_url}/studio/versions", timeout=60)


def _load_into_editor(by_num: dict) -> None:
    """Button callback: copy a saved version's system prompt into the editor."""
    picked = st.session_state.get("studio_start_from")
    if picked in by_num:
        st.session_state[PROMPT_KEY] = by_num[picked]["system_prompt"]


def _test_draft(ctx, filename, data, prompt, model_label):
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return _call("POST", f"{ctx.backend_url}/studio/test", timeout=120,
                 files={"file": (filename, data, mime)},
                 data={"system_prompt": prompt, "model_label": model_label, "user_id": ctx.user_id})


def render(ctx) -> None:
    st.markdown(
        """
<div class="hero">
  <h1>Prompt Studio</h1>
  <p>Write a prompt, test it against the saved versions, save it as the next version, and choose which version is live. Rolling back is one click.</p>
</div>""", unsafe_allow_html=True)

    ok, data = fetch_studio(ctx.backend_url)
    if not ok:
        st.error(data)
        return
    versions = data["versions"]                       # newest first
    active, next_v = data["active_version"], data["next_version"]
    by_num = {v["version"]: v for v in versions}
    numbers_desc = [v["version"] for v in versions]
    numbers_asc = sorted(numbers_desc)

    def vlabel(n: int) -> str:
        return f"v{n} — {by_num[n]['name']}"

    # ---- status bar --------------------------------------------------------------------------------
    active_text = (f"🟢 <b>Active:</b> {_esc(vlabel(active))}" if active is not None
                   else "⚪ <b>No version is active yet</b>")
    st.markdown(f'<div class="statusbar"><span>{active_text}</span>'
                f'<span><b>{len(versions)}</b> saved versions</span>'
                f'<span>Next save becomes <b>v{next_v}</b></span></div>', unsafe_allow_html=True)

    # ---- 1. write ---------------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('<div class="sec">Write a prompt</div>', unsafe_allow_html=True)
        st.text_input("Prompt name", key=NAME_KEY, max_chars=100, placeholder="e.g. GST Strict Extraction",
                      help="A human-readable name. The Langfuse prompt itself stays 'invoice-extractor'.")
        c1, c2 = st.columns([3, 1])
        with c1:
            st.selectbox("Start from a saved version (optional)", numbers_desc, format_func=vlabel,
                         key="studio_start_from")
        with c2:
            st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
            st.button("Load into editor", on_click=_load_into_editor, args=(by_num,), use_container_width=True)
        st.text_area("System prompt", key=PROMPT_KEY, height=320,
                     placeholder="You are a precise invoice extraction assistant.\n\nReturn valid JSON with the keys "
                                 "invoice_number, vendor_name, gstin, invoice_date, total_amount. Use null if a field "
                                 "is not visible.")

    # ---- 2. test ------------------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('<div class="sec">Test it on a sample</div>', unsafe_allow_html=True)
        s1, s2 = st.columns([1.4, 1])
        with s1:
            sample_label = st.selectbox("Test sample", [s[0] for s in ctx.samples], key="studio_sample")
        with s2:
            model_label = st.selectbox("Model", ctx.models, key="studio_model")
        default_cmp = [n for n in (1, 2, 3) if n in by_num] or numbers_asc[:3]
        chosen = st.multiselect("Compare your draft against", numbers_asc, default=default_cmp,
                                format_func=vlabel, key="studio_compare")
        min_needed = min(2, len(numbers_asc))
        st.markdown(f'<div class="hint">Your draft and the chosen saved versions run on the same sample, side by side '
                    f'(pick at least {min_needed}). Testing saves nothing to Langfuse, so test as often as you like.</div>',
                    unsafe_allow_html=True)
        rerun_saved = st.checkbox("Re-run the saved versions on every test", key="studio_rerun",
                                  help="Off by default: saved versions never change, so their results are reused "
                                       "for this sample during your session and only your draft runs again.")
        test_clicked = st.button("Test Prompt", type="primary")

    if test_clicked:
        draft_prompt = (st.session_state.get(PROMPT_KEY) or "").strip()
        if not draft_prompt:
            st.warning("Write a system prompt first.")
        elif len(chosen) < min_needed:
            st.warning(f"Pick at least {min_needed} saved versions to compare against.")
        else:
            filename = next(s[1] for s in ctx.samples if s[0] == sample_label)
            file_bytes = (ctx.samples_dir / filename).read_bytes()
            cache = st.session_state.setdefault("studio_cache", {})
            todo = [n for n in sorted(chosen) if rerun_saved or (filename, n, model_label) not in cache]
            with st.spinner(f"Testing your draft against {len(chosen)} saved versions on {filename}…"):
                with ThreadPoolExecutor(max_workers=5) as pool:
                    draft_future = pool.submit(_test_draft, ctx, filename, file_bytes, draft_prompt, model_label)
                    saved_futures = {n: pool.submit(ctx.call_extract, filename, file_bytes, n, model_label, ctx.user_id)
                                     for n in todo}
                    draft_result = draft_future.result()
                    fresh = {n: f.result() for n, f in saved_futures.items()}
            for n, res in fresh.items():
                if res[0]:
                    cache[(filename, n, model_label)] = res            # only successful runs are reused
            saved_runs = []
            for n in sorted(chosen):
                res = fresh.get(n) or cache.get((filename, n, model_label))
                saved_runs.append({"version": n, "ok": res[0], "payload": res[1]})
            st.session_state.studio_test = {
                "filename": filename, "expected": ctx.ground_truth.get(filename),
                "draft": draft_result, "saved": saved_runs, "prompt": draft_prompt,
                "name": (st.session_state.get(NAME_KEY) or "").strip()}

    # ---- test result -----------------------------------------------------------------------------------
    result = st.session_state.get("studio_test")
    if result:
        st.markdown('<div class="sec" style="margin-top:14px">Test result</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="hint">{_esc(result["filename"])}: your unsaved draft (amber) next to saved versions. '
                    f'Each run is traced in Langfuse; the draft is tagged <code>prompt-studio-draft</code>.</div>',
                    unsafe_allow_html=True)
        draft_ok, draft_payload = result["draft"]
        runs = [{"label": "Your draft", "draft": True, "ok": draft_ok, "payload": draft_payload}] + result["saved"]
        ctx.render_compare(runs, result["expected"], active)

        if (st.session_state.get(PROMPT_KEY) or "").strip() != result["prompt"]:
            st.markdown('<div class="note">The editor has changed since this test. Click <b>Test Prompt</b> again to '
                        'test the current text.</div>', unsafe_allow_html=True)

        st.markdown("**JSON output from Claude (your draft)**")
        if draft_ok:
            if draft_payload["status"] != "ok":
                st.markdown(ctx.status_banner(draft_payload), unsafe_allow_html=True)
            st.code(draft_payload["raw_output"], language=None if draft_payload["status"] == "not_json" else "json")
            info = draft_payload["info"]
            st.caption(f"{info['latency_ms'] / 1000:.2f} s · {info['input_tokens']} in / {info['output_tokens']} out tokens"
                       + (f" · trace {info['trace_id']}" if info.get("trace_id") else ""))
        else:
            st.error(draft_payload)

    # ---- 3. save ---------------------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('<div class="sec">Save as a new version</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="hint">This will be saved as <b>v{next_v}</b>. The number is assigned automatically '
                    f'from the versions that exist in Langfuse; you cannot choose it. Saving does not make it active.</div>',
                    unsafe_allow_html=True)
        current = (st.session_state.get(PROMPT_KEY) or "").strip()
        twin = next((v for v in versions if current and v["system_prompt"].strip() == current), None)
        if twin and "studio_flash_save" not in st.session_state:      # no duplicate warning right after saving
            st.warning(f"This text is identical to {vlabel(twin['version'])}. Saving it would create a duplicate.")
        if st.button("Save as New Version", type="primary"):
            name = (st.session_state.get(NAME_KEY) or "").strip()
            if not name:
                st.error("Prompt name is required.")
            elif not current:
                st.error("System prompt is required.")
            else:
                saved_ok, saved = _call("POST", f"{ctx.backend_url}/studio/versions",
                                        json={"name": name, "system_prompt": current})
                if saved_ok:
                    fetch_studio.clear()
                    ctx.refresh_caches()
                    st.session_state["studio_flash_save"] = (
                        f"Saved as v{saved['version']} — {saved['name']}. It is stored but not active yet.")
                    st.rerun()
                else:
                    st.error(saved)
        flash = st.session_state.pop("studio_flash_save", None)
        if flash:
            st.success(flash)

    # ---- 4. version history ----------------------------------------------------------------------------
    st.markdown('<div class="sec" style="margin-top:14px">Version history</div>', unsafe_allow_html=True)
    if active is None:
        st.markdown('<div class="note">No version is marked active yet. Choose one below and click <b>Set Active</b>.</div>',
                    unsafe_allow_html=True)
    for v in versions:
        n = v["version"]
        pill = '<span class="pill ok">🟢 ACTIVE</span>' if v["is_active"] else ""
        st.markdown(f'<div class="vrow {"active" if v["is_active"] else ""}">'
                    f'<div><span class="vnum">v{n}</span> <span class="vname">— {_esc(v["name"])}</span></div>'
                    f'<div>{pill}</div></div>', unsafe_allow_html=True)
        with st.expander(f"View prompt text · v{n}"):
            st.code(v["system_prompt"] or "(empty)", language=None, wrap_lines=True)

    # ---- 5. set active / rollback ------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('<div class="sec">Active version</div>', unsafe_allow_html=True)
        st.markdown('<div class="hint">The active version is what the Invoice Extractor selects by default. '
                    'To roll back, pick an older version and click <b>Set Active</b>. Nothing is ever deleted.</div>',
                    unsafe_allow_html=True)
        default_i = numbers_desc.index(active) if active in numbers_desc else 0
        pick = st.selectbox("Active version", numbers_desc, index=default_i, key=f"studio_active_pick_{active}",
                            format_func=lambda n: vlabel(n) + (" · 🟢 active" if n == active else ""))
        if st.button("Set Active"):
            set_ok, res = _call("PUT", f"{ctx.backend_url}/studio/active", json={"version": pick})
            if set_ok:
                fetch_studio.clear()
                ctx.refresh_caches()
                others = ", ".join(f"v{n}" for n in numbers_desc if n != pick)
                st.session_state["studio_flash_active"] = (
                    f"{vlabel(pick)} is now active. Still stored: {others}." if others else f"{vlabel(pick)} is now active.")
                st.rerun()
            else:
                st.error(res)
        flash = st.session_state.pop("studio_flash_active", None)
        if flash:
            st.success(flash)
