"""Gemma 4 API integration via the Gemini API (google-genai).

Supports:
- Text-based commit story, impact evaluation, and doc suggestions
- Multimodal visual comparison of before/after screenshots
- Robust JSON extraction with error resilience
- Realistic offline fallback mode for local testing without an API key
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from .evidence import EvidenceReport
from .prompts import (
    COMMIT_AND_IMPACT_SYSTEM_PROMPT,
    SCREENSHOT_ANALYSIS_SYSTEM_PROMPT,
    format_commit_analysis_prompt,
    format_screenshot_prompt,
)

load_dotenv()

DEFAULT_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")


def get_api_key(override_key: Optional[str] = None) -> Optional[str]:
    """Retrieve Gemini API key from parameter or environment."""
    if override_key and override_key.strip():
        return override_key.strip()
    return os.getenv("GEMINI_API_KEY", "").strip() or None


def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extract and parse JSON object from LLM response text."""
    text = raw_text.strip()

    # Match ```json ... ``` or ``` ... ```
    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_block:
        text = json_block.group(1).strip()
    else:
        # Match from first '{' to last '}'
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        # Fallback simple repair attempt for trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(cleaned)


def generate_mock_analysis(evidence: EvidenceReport) -> Dict[str, Any]:
    """Generate a realistic, evidence-accurate analysis when offline or without API key."""
    # Find changed python symbols
    sym_names = [s["name"] for s in evidence.symbols]
    first_sym = sym_names[0] if sym_names else "codebase"
    changed_files = [f["path"] for f in evidence.changed_files]
    first_file = changed_files[0] if changed_files else "src/app.py"

    # Match evidence IDs
    file_eids = [i.id for i in evidence.items if i.category == "file_change"]
    sym_eids = [i.id for i in evidence.items if i.category == "symbol_change"]
    call_eids = [i.id for i in evidence.items if i.category == "callers"]
    blame_eids = [i.id for i in evidence.items if i.category == "blame"]
    doc_eids = [i.id for i in evidence.items if i.category == "doc_mention"]

    # Build valid impact claims citing real IDs
    impact_summary = []
    if sym_eids:
        impact_summary.append({
            "claim": f"Modified symbol '{first_sym}' in {first_file}",
            "evidence_ids": [sym_eids[0]],
            "risk": "medium" if call_eids else "low",
            "rationale": f"Direct modification to {first_sym}; callers need verification.",
        })

    if call_eids:
        callers_for_sym = evidence.callers.get(first_sym, [])
        call_desc = f"called by {len(callers_for_sym)} files" if callers_for_sym else "0 callers detected"
        impact_summary.append({
            "claim": f"Downstream impact on consumers of '{first_sym}' ({call_desc})",
            "evidence_ids": [call_eids[0]],
            "risk": "medium" if callers_for_sym else "low",
            "rationale": "Caller graph analysis indicates downstream touchpoints.",
        })

    if file_eids:
        impact_summary.append({
            "claim": f"Changes staged in {len(changed_files)} file(s) across the repository",
            "evidence_ids": [file_eids[0]],
            "risk": "low",
            "rationale": "Standard file updates; diff footprint inspected.",
        })

    doc_updates = []
    if doc_eids and evidence.doc_matches:
        first_doc = evidence.doc_matches[0]
        doc_updates.append({
            "doc_file": first_doc["doc_file"],
            "evidence_ids": [doc_eids[0]],
            "suggested_change": f"Update references to '{first_doc['term']}' on line {first_doc['line']} to reflect latest signature.",
        })

    suggested_reviewers = []
    if blame_eids and evidence.reviewers:
        top_rev = evidence.reviewers[0]
        suggested_reviewers.append({
            "name": top_rev["name"],
            "evidence_ids": [blame_eids[0]],
            "reason": f"Authored {top_rev['percentage']}% of previously committed lines in modified hunks.",
        })

    return {
        "commit_message": {
            "type": "feat" if any(s.get("change_type") == "added" for s in evidence.symbols) else "refactor",
            "scope": os.path.basename(os.path.dirname(first_file)) or "core",
            "subject": f"update {first_sym} implementation and callers",
            "body": (
                f"Updates {first_sym} to align with recent changes. "
                f"Modifies {', '.join(changed_files[:3])} and validates callers across the repository."
            ),
        },
        "impact_summary": impact_summary,
        "doc_updates": doc_updates,
        "suggested_reviewers": suggested_reviewers,
        "gaps": evidence.gaps or [
            "Dynamic invocations and untyped calls cannot be confirmed statically."
        ],
        "is_mock": True,
    }


def analyze_with_gemma(
    evidence: EvidenceReport,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    user_intent: str = "",
) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """Analyze repository evidence using Gemma 4 via Gemini API.

    Returns:
        (analysis_dict, is_mock, error_message)
    """
    key = get_api_key(api_key)
    model = model_name or DEFAULT_MODEL

    # If no key is provided, use high-fidelity mock
    if not key:
        return generate_mock_analysis(evidence), True, "No GEMINI_API_KEY provided; using offline simulation."

    evidence_text = evidence.to_prompt_text()
    user_prompt = format_commit_analysis_prompt(evidence_text, user_intent)

    # 1. Try official google-genai SDK with retry
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        last_err = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=COMMIT_AND_IMPACT_SYSTEM_PROMPT,
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    parsed = clean_json_response(response.text)
                    parsed["is_mock"] = False
                    return parsed, False, None
            except Exception as e:
                last_err = e
                time.sleep(1.0 * (attempt + 1))

        if last_err:
            return generate_mock_analysis(evidence), True, f"Gemini API error ({last_err}); using offline fallback."
    except ImportError:
        pass

    # 2. Try legacy google.generativeai
    try:
        import google.generativeai as genai_legacy

        genai_legacy.configure(api_key=key)
        gen_model = genai_legacy.GenerativeModel(
            model_name=model,
            system_instruction=COMMIT_AND_IMPACT_SYSTEM_PROMPT,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )
        resp = gen_model.generate_content(user_prompt)
        if resp.text:
            parsed = clean_json_response(resp.text)
            parsed["is_mock"] = False
            return parsed, False, None
    except ImportError:
        pass
    except Exception as e:
        return generate_mock_analysis(evidence), True, f"Gemini API error ({e}); using offline fallback."

    # If neither SDK is installed
    return generate_mock_analysis(evidence), True, "google-genai package not installed; using offline simulation."


def generate_mock_screenshot_analysis(changed_ui_files: List[str]) -> Dict[str, Any]:
    """Generate realistic visual comparison analysis when offline."""
    first_ui = changed_ui_files[0] if changed_ui_files else "ui/login.py"
    return {
        "visual_changes": [
            {
                "element": "Primary Action Button",
                "before_state": "Flat gray rectangular button with basic sans-serif text",
                "after_state": "Rounded vibrant blue button with subtle drop shadow and white bold text",
                "linked_code_file": first_ui,
                "significance": "functional",
            },
            {
                "element": "Header Navigation Bar",
                "before_state": "Default 48px height with plain border",
                "after_state": "Streamlined 56px height with improved contrast and status badge",
                "linked_code_file": first_ui,
                "significance": "cosmetic",
            },
        ],
        "overall_summary": "Substantial UI polish improving visual hierarchy, touch targets, and brand contrast.",
        "code_linkage_explanation": f"Styling updates in {first_ui} correspond directly to the updated button geometry and color tokens.",
        "potential_regressions": [
            "Ensure button text maintains WCAG AA contrast ratio in both dark and light modes."
        ],
        "is_mock": True,
    }


def analyze_screenshots_with_gemma(
    before_image: Any,
    after_image: Any,
    changed_ui_files: List[str],
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """Compare before and after screenshots using Gemma 4 multimodal capabilities.

    Returns:
        (analysis_dict, is_mock, error_message)
    """
    key = get_api_key(api_key)
    model = model_name or DEFAULT_MODEL

    if not key:
        return generate_mock_screenshot_analysis(changed_ui_files), True, "No GEMINI_API_KEY provided; using offline visual mock."

    user_prompt = format_screenshot_prompt(changed_ui_files)

    # Try google-genai with retry
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        last_v_err = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        user_prompt,
                        "BEFORE SCREENSHOT:",
                        before_image,
                        "AFTER SCREENSHOT:",
                        after_image,
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=SCREENSHOT_ANALYSIS_SYSTEM_PROMPT,
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    parsed = clean_json_response(response.text)
                    parsed["is_mock"] = False
                    return parsed, False, None
            except Exception as e:
                last_v_err = e
                time.sleep(1.0 * (attempt + 1))

        if last_v_err:
            return generate_mock_screenshot_analysis(changed_ui_files), True, f"Vision API error ({last_v_err}); using offline fallback."
    except ImportError:
        pass

    # Try legacy google.generativeai
    try:
        import google.generativeai as genai_legacy

        genai_legacy.configure(api_key=key)
        gen_model = genai_legacy.GenerativeModel(
            model_name=model,
            system_instruction=SCREENSHOT_ANALYSIS_SYSTEM_PROMPT,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )
        resp = gen_model.generate_content([
            user_prompt,
            "BEFORE SCREENSHOT:",
            before_image,
            "AFTER SCREENSHOT:",
            after_image,
        ])
        if resp.text:
            parsed = clean_json_response(resp.text)
            parsed["is_mock"] = False
            return parsed, False, None
    except ImportError:
        pass
    except Exception as e:
        return generate_mock_screenshot_analysis(changed_ui_files), True, f"Vision API error ({e}); using offline fallback."

    return generate_mock_screenshot_analysis(changed_ui_files), True, "google-genai package not installed; using offline visual mock."