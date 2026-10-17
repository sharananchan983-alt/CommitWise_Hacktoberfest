"""CommitWise - Streamlit UI.

AI that writes your commit story and shows the proof.
Built for the Finite Loop OSS Fest (Hacktoberfest Hack Day) at NMAMIT
for the Best Use of Gemma 4 challenge.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from PIL import Image

from commitwise.evidence import collect_evidence, EvidenceReport
from commitwise.gemma import (
    analyze_with_gemma,
    analyze_screenshots_with_gemma,
    get_api_key,
)
from commitwise.verify import verify_claims, inject_false_claim

st.set_page_config(
    page_title="CommitWise - Verifiable Commit Story",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------------------
# Custom CSS Styling
# ------------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #475569;
        margin-bottom: 1.2rem;
    }
    .badge-bar {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
    }
    .custom-badge {
        background-color: #EEF2F6;
        color: #1E293B;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid #CBD5E1;
    }
    .badge-gemma {
        background-color: #E0F2FE;
        color: #0369A1;
        border-color: #BAE6FD;
    }
    .badge-verify {
        background-color: #DCFCE7;
        color: #15803D;
        border-color: #BBF7D0;
    }
    .eid-pill {
        display: inline-block;
        background-color: #F1F5F9;
        color: #0F172A;
        border: 1px solid #94A3B8;
        border-radius: 4px;
        padding: 0.1rem 0.35rem;
        font-family: monospace;
        font-size: 0.82rem;
        font-weight: 700;
        margin-right: 0.3rem;
    }
    .claim-card {
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
        border-left: 5px solid;
    }
    .risk-high {
        background-color: #FEF2F2;
        border-color: #EF4444;
    }
    .risk-medium {
        background-color: #FFFBEB;
        border-color: #F59E0B;
    }
    .risk-low {
        background-color: #F0FDF4;
        border-color: #10B981;
    }
    .flagged-card {
        background-color: #FFF1F2;
        border: 1px solid #F43F5E;
        border-left: 6px solid #E11D48;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    .verified-card {
        background-color: #F0FDF4;
        border: 1px solid #86EFAC;
        border-left: 6px solid #16A34A;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Sidebar Configuration
# ------------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://raw.githubusercontent.com/google/gemma_pytorch/main/docs/gemma_logo.png"
        if False
        else "https://api.iconify.design/lucide:shield-check.svg?color=%2316a34a&width=48",
        width=48,
    )
    st.title("CommitWise")
    st.caption("Verifiable Commit Story & Honesty Engine")

    st.markdown("---")
    st.subheader("Repository Target")

    default_repo = "demo_repo" if Path("demo_repo").exists() else "."
    repo_input = st.text_input(
        "Git Repository Path",
        value=default_repo,
        help="Local directory path containing the git repository to analyze.",
    )

    if st.button("⚡ Build / Reset Demo Repo", help="Runs scripts/make_demo_repo.sh"):
        with st.spinner("Building realistic demo repository with 2 authors and pending diff..."):
            res = subprocess.run(
                ["bash", "scripts/make_demo_repo.sh", "demo_repo"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                st.success("Created demo_repo successfully!")
                st.rerun()
            else:
                st.error(f"Error building demo repo: {res.stderr}")

    st.markdown("---")
    st.subheader("Model & Credentials")

    env_key = os.getenv("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "Gemini API Key",
        value=env_key,
        type="password",
        help="Google Gemini API key for accessing Gemma 4.",
    )

    model_options = [
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it",
        "gemma-2-27b-it",
        "gemma-2-9b-it",
        "gemini-2.5-flash",
    ]
    env_model = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
    model_choice = st.selectbox(
        "Gemma Model ID",
        options=model_options,
        index=0 if env_model not in model_options else model_options.index(env_model),
        help="The Gemma 4 model accessed via Gemini API.",
    )

    if api_key_input:
        st.markdown("🟢 **API Key Configured** (Live Gemma 4)")
    else:
        st.markdown("⚪ **Offline Simulation Mode** (No key required for demo)")

    st.markdown("---")
    st.subheader("Demo Experiments")
    inject_falsehood = st.checkbox(
        "Demo: inject a false claim",
        value=False,
        help=(
            "Simulates an LLM hallucination with an unknown citation [E99], phantom file, "
            "and phantom function to watch the non-AI honesty verification engine catch and flag it."
        ),
    )

    optional_intent = st.text_area(
        "Optional: Author Intent",
        placeholder="e.g., Adding mandatory role-based check for security compliance.",
        help="Optional guidance to give Gemma additional context.",
    )

    analyze_button = st.button("🔍 Analyze My Changes", type="primary", use_container_width=True)

# ------------------------------------------------------------------------------
# App Header
# ------------------------------------------------------------------------------
st.markdown('<div class="main-header">CommitWise</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">AI that writes your commit story and shows the proof.</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="badge-bar">
        <span class="custom-badge badge-gemma">⚡ Gemma 4 Powered</span>
        <span class="custom-badge badge-verify">🛡️ Zero-AI Honesty Verifier</span>
        <span class="custom-badge">🏛️ Finite Loop OSS Fest (NMAMIT)</span>
        <span class="custom-badge">👁️ Multimodal UI Diff</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Session State Management
# ------------------------------------------------------------------------------
if "evidence" not in st.session_state:
    st.session_state.evidence = None
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "verification" not in st.session_state:
    st.session_state.verification = None
if "is_mock" not in st.session_state:
    st.session_state.is_mock = False

# Auto-run if first time and demo_repo exists
if st.session_state.evidence is None and Path(repo_input).exists():
    with st.spinner("Collecting git facts & AST evidence..."):
        ev = collect_evidence(repo_input)
        st.session_state.evidence = ev
        # Generate initial analysis
        an, is_m, _ = analyze_with_gemma(
            evidence=ev,
            api_key=api_key_input,
            model_name=model_choice,
            user_intent=optional_intent,
        )
        if inject_falsehood:
            an = inject_false_claim(an)
        st.session_state.analysis = an
        st.session_state.is_mock = is_m
        st.session_state.verification = verify_claims(an, ev)

# Re-run when analyze button is pressed or settings change
if analyze_button:
    with st.spinner("Collecting ground-truth git facts (no AI)..."):
        ev = collect_evidence(repo_input)
        st.session_state.evidence = ev

    with st.spinner("Generating commit story & impact with Gemma 4..."):
        an, is_m, err = analyze_with_gemma(
            evidence=ev,
            api_key=api_key_input,
            model_name=model_choice,
            user_intent=optional_intent,
        )
        if inject_falsehood:
            an = inject_false_claim(an)
        st.session_state.analysis = an
        st.session_state.is_mock = is_m

    with st.spinner("Running deterministic honesty checks (no AI)..."):
        st.session_state.verification = verify_claims(an, ev)

    st.success("Analysis and honesty verification complete!")

evidence: Optional[EvidenceReport] = st.session_state.evidence
analysis: Optional[Dict[str, Any]] = st.session_state.analysis
verification = st.session_state.verification
is_mock_run = st.session_state.is_mock

if not evidence or not analysis or not verification:
    st.info("👈 Enter a git repository path in the sidebar and click **Analyze My Changes** to start.")
    st.stop()

# ------------------------------------------------------------------------------
# Summary KPI Metrics
# ------------------------------------------------------------------------------
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric("Files Changed", len(evidence.changed_files))
with kpi2:
    st.metric("AST Symbols", len(evidence.symbols))
with kpi3:
    st.metric("Callers Traced", sum(len(c) for c in evidence.callers.values()))
with kpi4:
    st.metric("Evidence Items", len(evidence.items))
with kpi5:
    score = verification.honesty_score
    st.metric("Honesty Score", f"{score}%", delta="Verified" if verification.passed else "-Flagged")

# ------------------------------------------------------------------------------
# Main Application Tabs
# ------------------------------------------------------------------------------
tab_story, tab_verify, tab_evidence, tab_vision = st.tabs([
    "📝 Commit Story & Impact (Gemma 4)",
    "🛡️ Honesty Verification (No AI)",
    "🔍 Evidence Inspector (Raw Git Facts)",
    "🖼️ Multimodal UI Changes (Vision)",
])

# ------------------------------------------------------------------------------
# TAB 1: Commit Story & Impact
# ------------------------------------------------------------------------------
with tab_story:
    if is_mock_run:
        st.info("ℹ️ Running in **Offline Simulation Mode** (no Gemini API key detected). Evidence and AST analysis are 100% real.")

    # 1. Commit Message Section
    st.markdown("### 🏷️ Conventional Commit Message")
    cm = analysis.get("commit_message", {})
    scope_str = f"({cm.get('scope')})" if cm.get("scope") else ""
    subject_line = f"{cm.get('type', 'chore')}{scope_str}: {cm.get('subject', 'update files')}"

    c_box, c_copy = st.columns([4, 1])
    with c_box:
        st.code(f"{subject_line}\n\n{cm.get('body', '')}", language="gitcommit")
    with c_copy:
        st.caption("Quick Subject")
        st.code(subject_line, language="text")

    st.markdown("---")

    # 2. Impact Summary & Risk Matrix
    st.markdown("### 💥 Impact Summary & Risk Analysis")
    st.caption("Every claim below cites verifiable evidence IDs gathered from git and code analysis.")

    impact_items = analysis.get("impact_summary", [])
    if impact_items:
        for idx, imp in enumerate(impact_items):
            risk = imp.get("risk", "low").lower()
            risk_class = f"risk-{risk}"
            risk_badge = {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}.get(risk, "⚪ UNKNOWN")

            eids = imp.get("evidence_ids", [])
            pills = "".join(f'<span class="eid-pill">{eid}</span>' for eid in eids)

            st.markdown(
                f"""
                <div class="claim-card {risk_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <strong>{imp.get('claim')}</strong>
                        <span style="font-weight: 700; font-size: 0.85rem;">{risk_badge}</span>
                    </div>
                    <div style="font-size: 0.9rem; color: #334155; margin-bottom: 0.4rem;">
                        <strong>Rationale:</strong> {imp.get('rationale')}
                    </div>
                    <div style="font-size: 0.82rem; color: #64748B;">
                        <strong>Citing Evidence:</strong> {pills or '<em>None</em>'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.write("No impact claims reported.")

    st.markdown("---")

    # 3. Suggested Docs & Reviewers
    col_docs, col_revs = st.columns(2)

    with col_docs:
        st.markdown("### 📚 Outdated Documentation Fixes")
        docs_list = analysis.get("doc_updates", [])
        if docs_list:
            for d in docs_list:
                eids = d.get("evidence_ids", [])
                pills = "".join(f'<span class="eid-pill">{eid}</span>' for eid in eids)
                st.markdown(
                    f"""
                    <div style="padding: 0.8rem; border: 1px solid #E2E8F0; border-radius: 6px; margin-bottom: 0.6rem; background: #F8FAFC;">
                        <div style="font-weight: 600; color: #0284C7;">📄 {d.get('doc_file')}</div>
                        <div style="font-size: 0.88rem; margin-top: 0.2rem;">{d.get('suggested_change')}</div>
                        <div style="margin-top: 0.4rem;">{pills}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No documentation updates required by this change.")

    with col_revs:
        st.markdown("### 👥 Suggested Reviewers (`git blame`)")
        revs_list = analysis.get("suggested_reviewers", [])
        if revs_list:
            for r in revs_list:
                eids = r.get("evidence_ids", [])
                pills = "".join(f'<span class="eid-pill">{eid}</span>' for eid in eids)
                st.markdown(
                    f"""
                    <div style="padding: 0.8rem; border: 1px solid #E2E8F0; border-radius: 6px; margin-bottom: 0.6rem; background: #F8FAFC;">
                        <div style="font-weight: 600; color: #1E293B;">👤 {r.get('name')}</div>
                        <div style="font-size: 0.88rem; margin-top: 0.2rem;">{r.get('reason')}</div>
                        <div style="margin-top: 0.4rem;">{pills}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No prior author history found for modified lines.")

    # 4. What Gemma Doesn't Know (Gaps)
    st.markdown("---")
    st.markdown("### ⚠️ What Gemma Does Not Know (Gaps & Limitations)")
    st.caption("CommitWise is designed to report uncertainty instead of guessing.")
    gaps = analysis.get("gaps", [])
    if gaps:
        for g in gaps:
            st.warning(f"• {g}")
    else:
        st.success("No critical analysis gaps detected.")

# ------------------------------------------------------------------------------
# TAB 2: Honesty Verification (No AI)
# ------------------------------------------------------------------------------
with tab_verify:
    st.markdown("### 🛡️ Non-AI Honesty Verification Engine")
    st.caption(
        "Verifies every claim made by the LLM against ground-truth evidence. "
        "Any claim with missing citations, unknown IDs, phantom files, or phantom functions is flagged."
    )

    if verification.passed:
        st.success(f"✅ **VERIFICATION PASSED (100% Honesty Score)**: {verification.summary}")
    else:
        st.error(
            f"🚨 **UNSUPPORTED CLAIMS FLAGGED**: Caught {verification.flagged_count} hallucinated "
            f"or unsupported claim(s). Honesty score: {verification.honesty_score}%."
        )

    # Flagged Claims Section
    if verification.flagged_claims:
        st.markdown("#### 🚨 Flagged / Hallucinated Claims")
        for f in verification.flagged_claims:
            eids = f.evidence_ids
            pills = "".join(f'<span class="eid-pill">{eid}</span>' for eid in eids)
            violations_html = "".join(f"<li style='color: #B91C1C; font-weight: 600;'>{v}</li>" for v in f.violations)
            st.markdown(
                f"""
                <div class="flagged-card">
                    <div style="font-weight: 700; font-size: 1rem; color: #991B1B;">
                        ❌ {f.claim_text}
                    </div>
                    <div style="margin-top: 0.4rem; font-size: 0.85rem;">
                        <strong>Cited IDs:</strong> {pills or '<em>None cited</em>'}
                    </div>
                    <div style="margin-top: 0.5rem;">
                        <ul style="margin: 0; padding-left: 1.2rem;">
                            {violations_html}
                        </ul>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Verified Claims Section
    st.markdown("#### ✅ Verified Claims (Supported by Evidence)")
    for v in verification.verified_claims:
        eids = v.evidence_ids
        pills = "".join(f'<span class="eid-pill">{eid}</span>' for eid in eids)
        supporting_html = "".join(f"<li>{s}</li>" for s in v.supporting_evidence)
        st.markdown(
            f"""
            <div class="verified-card">
                <div style="font-weight: 600; color: #166534;">
                    ✔ {v.claim_text}
                </div>
                <div style="margin-top: 0.3rem;">
                    {pills}
                </div>
                <div style="margin-top: 0.4rem; font-size: 0.85rem; color: #374151;">
                    <ul style="margin: 0; padding-left: 1.2rem;">
                        {supporting_html}
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("#### 🔎 Interactive Evidence Citation Explorer")
    id_list = sorted(list(evidence.all_ids()), key=lambda x: int(x[1:]) if x[1:].isdigit() else 999)
    selected_id = st.selectbox("Inspect specific Evidence ID:", id_list)
    if selected_id:
        item = evidence.get_item(selected_id)
        if item:
            st.json({
                "id": item.id,
                "category": item.category,
                "summary": item.summary,
                "details": item.details,
            })

# ------------------------------------------------------------------------------
# TAB 3: Evidence Inspector (Raw Git Facts)
# ------------------------------------------------------------------------------
with tab_evidence:
    st.markdown("### 🗄️ Ground-Truth Evidence Catalog")
    st.caption("Extracted deterministically via git diff, git blame, and Python AST.")

    # 1. Changed Files
    st.markdown("#### 1. Changed Files")
    if evidence.changed_files:
        st.dataframe(
            [
                {
                    "File": f["path"],
                    "Status": f["status"].upper(),
                    "Additions": f"+{f['additions']}",
                    "Deletions": f"-{f['deletions']}",
                    "Hunks": len(f.get("hunk_ranges", [])),
                }
                for f in evidence.changed_files
            ],
            use_container_width=True,
        )
    else:
        st.write("No changed files found.")

    # 2. Python AST Symbols
    st.markdown("#### 2. AST Symbols (Functions & Classes)")
    if evidence.symbols:
        st.dataframe(
            [
                {
                    "Symbol": s["name"],
                    "Kind": s["kind"],
                    "File": s["file"],
                    "Change": s["change_type"].upper(),
                    "Signature Changed": s.get("signature_changed", False),
                    "Lines": f"{s.get('lines', ('?', '?'))[0]}-{s.get('lines', ('?', '?'))[1]}",
                }
                for s in evidence.symbols
            ],
            use_container_width=True,
        )
    else:
        st.write("No Python symbols added, modified, or removed.")

    # 3. Callers Graph
    st.markdown("#### 3. Downstream Callers Graph")
    if evidence.callers:
        call_rows = []
        for sym, calls in evidence.callers.items():
            call_rows.append({
                "Symbol": sym,
                "Caller Count": len(calls),
                "Callers": ", ".join(calls) if calls else "None detected",
            })
        st.dataframe(call_rows, use_container_width=True)
    else:
        st.write("No callers to inspect.")

    # 4. Git Blame History
    st.markdown("#### 4. Git Blame Author Distribution")
    if evidence.reviewers:
        st.dataframe(
            [
                {
                    "Author": r["name"],
                    "Lines Authored": r["lines_authored"],
                    "Share": f"{r['percentage']}%",
                    "Files": ", ".join(r["files"]),
                }
                for r in evidence.reviewers
            ],
            use_container_width=True,
        )
    else:
        st.write("No blame history available for modified lines.")

    # 5. Raw Git Diff
    st.markdown("#### 5. Unified Git Diff")
    if evidence.raw_diff:
        st.code(evidence.raw_diff, language="diff")
    else:
        st.info("Git diff is empty (all changes may be untracked or clean).")

# ------------------------------------------------------------------------------
# TAB 4: Multimodal UI Changes (Vision)
# ------------------------------------------------------------------------------
with tab_vision:
    st.markdown("### 🖼️ Gemma 4 Multimodal Visual UI Comparison")
    st.caption("Upload before and after screenshots of your UI to have Gemma 4 describe visual changes and link them to modified code files.")

    # Auto-load demo screenshots if available in demo_repo
    demo_before_path = Path(repo_input) / "screenshots" / "before.png"
    demo_after_path = Path(repo_input) / "screenshots" / "after.png"

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.subheader("1. Before Screenshot")
        up_before = st.file_uploader("Upload Before Image", type=["png", "jpg", "jpeg"], key="up_b")
        before_img = None
        if up_before:
            before_img = Image.open(up_before)
        elif demo_before_path.exists():
            before_img = Image.open(demo_before_path)
            st.caption(f"Loaded demo screenshot: `{demo_before_path}`")

        if before_img:
            st.image(before_img, caption="Before State", use_container_width=True)

    with col_up2:
        st.subheader("2. After Screenshot")
        up_after = st.file_uploader("Upload After Image", type=["png", "jpg", "jpeg"], key="up_a")
        after_img = None
        if up_after:
            after_img = Image.open(up_after)
        elif demo_after_path.exists():
            after_img = Image.open(demo_after_path)
            st.caption(f"Loaded demo screenshot: `{demo_after_path}`")

        if after_img:
            st.image(after_img, caption="After State", use_container_width=True)

    ui_files_input = st.text_input(
        "Changed UI Code Files",
        value="ui/login.py",
        help="Comma-separated list of UI files modified in this commit.",
    )

    if st.button("🎨 Analyze Visual Changes with Gemma 4 Vision", type="primary"):
        if before_img is None or after_img is None:
            st.warning("Please provide both Before and After screenshots.")
        else:
            with st.spinner("Analyzing UI transformation with Gemma 4 Vision..."):
                ui_file_list = [f.strip() for f in ui_files_input.split(",") if f.strip()]
                vision_analysis, v_mock, v_err = analyze_screenshots_with_gemma(
                    before_image=before_img,
                    after_image=after_img,
                    changed_ui_files=ui_file_list,
                    api_key=api_key_input,
                    model_name=model_choice,
                )

                if v_mock:
                    st.info("ℹ️ Running in **Visual Simulation Mode** (no Gemini API key provided).")

                st.markdown("#### 🌟 Overall Visual Summary")
                st.write(vision_analysis.get("overall_summary", "No summary provided."))

                st.markdown("#### 🔗 UI Code Linkage")
                st.write(vision_analysis.get("code_linkage_explanation", "No linkage provided."))

                st.markdown("#### 🔍 Element-by-Element Diff")
                v_changes = vision_analysis.get("visual_changes", [])
                if v_changes:
                    st.dataframe(
                        [
                            {
                                "Element": c.get("element"),
                                "Before State": c.get("before_state"),
                                "After State": c.get("after_state"),
                                "Linked File": c.get("linked_code_file"),
                                "Significance": c.get("significance", "cosmetic").upper(),
                            }
                            for c in v_changes
                        ],
                        use_container_width=True,
                    )

                regressions = vision_analysis.get("potential_regressions", [])
                if regressions:
                    st.markdown("#### ⚠️ Visual Bug & Regression Check")
                    for reg in regressions:
                        st.warning(f"• {reg}")