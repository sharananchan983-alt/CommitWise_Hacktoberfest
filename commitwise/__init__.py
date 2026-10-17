"""CommitWise: AI that writes your commit story and shows the proof.

Built for Finite Loop OSS Fest (Hacktoberfest Hack Day) at NMAMIT
for the Best Use of Gemma 4 challenge.
"""

__version__ = "0.1.0"


def __getattr__(name: str):
    if name in ("collect_evidence", "EvidenceReport"):
        from .evidence import collect_evidence, EvidenceReport
        return locals()[name]
    if name in ("verify_claims", "VerificationReport", "inject_false_claim"):
        from .verify import verify_claims, VerificationReport, inject_false_claim
        return locals()[name]
    if name in ("analyze_with_gemma", "analyze_screenshots_with_gemma"):
        from .gemma import analyze_with_gemma, analyze_screenshots_with_gemma
        return locals()[name]
    raise AttributeError(f"module 'commitwise' has no attribute '{name}'")


__all__ = [
    "collect_evidence",
    "EvidenceReport",
    "verify_claims",
    "VerificationReport",
    "inject_false_claim",
    "analyze_with_gemma",
    "analyze_screenshots_with_gemma",
]