"""Evidence Engine for CommitWise.

Collects objective, verifiable git and AST facts:
- Changed files and line diffs
- Added, modified, and removed Python symbols (functions, classes)
- Callers of modified symbols across the repository
- Git blame history for modified lines (suggested reviewers)
- Outdated documentation references

All facts are assigned deterministic IDs (E1, E2, ...) for citation.
Contains zero AI: pure deterministic static analysis and git inspection.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class EvidenceItem:
    """A single verifiable piece of evidence with an ID for citation."""
    id: str
    category: str  # "file_change", "symbol_change", "callers", "blame", "doc_mention"
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceReport:
    """Complete collection of evidence gathered from a repository."""
    repo_path: str
    items: List[EvidenceItem] = field(default_factory=list)
    changed_files: List[Dict[str, Any]] = field(default_factory=list)
    symbols: List[Dict[str, Any]] = field(default_factory=list)
    callers: Dict[str, List[str]] = field(default_factory=dict)
    reviewers: List[Dict[str, Any]] = field(default_factory=list)
    doc_matches: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    raw_diff: str = ""

    def get_item(self, evidence_id: str) -> Optional[EvidenceItem]:
        """Lookup an evidence item by its ID."""
        for item in self.items:
            if item.id == evidence_id:
                return item
        return None

    def all_ids(self) -> Set[str]:
        """Return the set of all evidence IDs."""
        return {item.id for item in self.items}

    def all_symbols(self) -> Set[str]:
        """Return all symbol names tracked in the evidence."""
        return {s["name"] for s in self.symbols if "name" in s}

    def all_changed_files(self) -> Set[str]:
        """Return all changed file paths."""
        return {f["path"] for f in self.changed_files if "path" in f}

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence report to dictionary."""
        return {
            "repo_path": self.repo_path,
            "items": [asdict(item) for item in self.items],
            "changed_files": self.changed_files,
            "symbols": self.symbols,
            "callers": self.callers,
            "reviewers": self.reviewers,
            "doc_matches": self.doc_matches,
            "gaps": self.gaps,
            "raw_diff_summary": f"{len(self.raw_diff.splitlines())} lines of diff",
        }

    def to_prompt_text(self) -> str:
        """Format evidence for LLM prompt with clear IDs to cite."""
        lines = ["### EVIDENCE CATALOG (CITE THESE IDS):"]
        for item in self.items:
            lines.append(f"[{item.id}] ({item.category.upper()}) {item.summary}")
            if item.details:
                for k, v in item.details.items():
                    if v and not isinstance(v, (dict, list)):
                        lines.append(f"    - {k}: {v}")
                    elif isinstance(v, list) and v:
                        lines.append(f"    - {k}: {', '.join(str(x) for x in v[:5])}")

        if self.gaps:
            lines.append("\n### KNOWN GAPS (Cannot be verified from static evidence):")
            for gap in self.gaps:
                lines.append(f"- {gap}")

        return "\n".join(lines)


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Execute a git command safely."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd)] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_git_diff_text(repo_path: Path) -> str:
    """Get the full git diff including staged and unstaged changes."""
    # First try unstaged diff
    _, unstaged, _ = run_git(["diff", "HEAD"], repo_path)
    if not unstaged:
        # If HEAD doesn't exist or diff HEAD failed, try plain diff + staged
        _, d1, _ = run_git(["diff"], repo_path)
        _, d2, _ = run_git(["diff", "--cached"], repo_path)
        unstaged = f"{d1}\n{d2}".strip()
    return unstaged


def get_changed_files_list(repo_path: Path) -> List[Dict[str, Any]]:
    """Get list of modified, added, deleted, or untracked files."""
    changed: List[Dict[str, Any]] = []
    code, status_out, _ = run_git(["status", "--porcelain"], repo_path)
    if code != 0 or not status_out:
        return changed

    for line in status_out.splitlines():
        if len(line) < 3:
            continue
        status_code = line[:2]
        file_path_str = line[2:].strip().strip('"')

        # Handle renames like "old.py -> new.py"
        if " -> " in file_path_str:
            old_p, new_p = file_path_str.split(" -> ", 1)
            file_path_str = new_p

        abs_path = repo_path / file_path_str

        # Get diff stats for this file
        _, diff_out, _ = run_git(["diff", "HEAD", "--", file_path_str], repo_path)
        if not diff_out:
            _, diff_out, _ = run_git(["diff", "--", file_path_str], repo_path)

        additions = 0
        deletions = 0
        hunk_ranges: List[Tuple[int, int]] = []

        if diff_out:
            for d_line in diff_out.splitlines():
                if d_line.startswith("+") and not d_line.startswith("+++"):
                    additions += 1
                elif d_line.startswith("-") and not d_line.startswith("---"):
                    deletions += 1
                elif d_line.startswith("@@"):
                    # Parse @@ -a,b +c,d @@
                    match = re.search(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", d_line)
                    if match:
                        start = int(match.group(3))
                        count = int(match.group(4)) if match.group(4) else 1
                        hunk_ranges.append((start, start + count))

        status_name = "modified"
        if "?" in status_code:
            status_name = "untracked"
            # For untracked files, additions is total line count
            if abs_path.is_file():
                try:
                    additions = len(abs_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    hunk_ranges.append((1, max(1, additions)))
                except Exception:
                    pass
        elif "A" in status_code:
            status_name = "added"
        elif "D" in status_code:
            status_name = "deleted"

        changed.append({
            "path": file_path_str.replace("\\", "/"),
            "status": status_name,
            "status_code": status_code,
            "additions": additions,
            "deletions": deletions,
            "hunk_ranges": hunk_ranges,
        })

    return changed


def get_head_file_content(repo_path: Path, relative_path: str) -> Optional[str]:
    """Read a file's content as of HEAD from git."""
    code, stdout, _ = run_git(["show", f"HEAD:{relative_path}"], repo_path)
    if code == 0:
        return stdout
    return None


@dataclass
class AstSymbol:
    name: str
    kind: str  # "function", "async_function", "class"
    start_line: int
    end_line: int
    params: List[str]
    docstring: Optional[str] = None


def extract_symbols_from_ast(source_code: str) -> Dict[str, AstSymbol]:
    """Extract functions and classes from Python source code."""
    symbols: Dict[str, AstSymbol] = {}
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = [arg.arg for arg in node.args.args]
            if node.args.vararg:
                params.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                params.append(f"**{node.args.kwarg.arg}")
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            symbols[node.name] = AstSymbol(
                name=node.name,
                kind=kind,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                params=params,
                docstring=ast.get_docstring(node),
            )
        elif isinstance(node, ast.ClassDef):
            symbols[node.name] = AstSymbol(
                name=node.name,
                kind="class",
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                params=[],
                docstring=ast.get_docstring(node),
            )
    return symbols


def analyze_python_symbols(repo_path: Path, file_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compare AST symbols between HEAD and working tree."""
    rel_path = file_info["path"]
    if not rel_path.endswith(".py"):
        return []

    abs_path = repo_path / rel_path
    if not abs_path.is_file() and file_info["status"] != "deleted":
        return []

    new_content = ""
    if abs_path.is_file():
        try:
            new_content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    old_content = get_head_file_content(repo_path, rel_path) or ""

    old_symbols = extract_symbols_from_ast(old_content)
    new_symbols = extract_symbols_from_ast(new_content)

    hunk_ranges = file_info.get("hunk_ranges", [])
    results: List[Dict[str, Any]] = []

    # Check for removed symbols
    for name, sym in old_symbols.items():
        if name not in new_symbols:
            results.append({
                "name": name,
                "file": rel_path,
                "kind": sym.kind,
                "change_type": "removed",
                "old_params": sym.params,
                "summary": f"{sym.kind} '{name}' was removed from {rel_path}",
            })

    # Check for added or modified symbols
    for name, sym in new_symbols.items():
        if name not in old_symbols:
            results.append({
                "name": name,
                "file": rel_path,
                "kind": sym.kind,
                "change_type": "added",
                "params": sym.params,
                "lines": (sym.start_line, sym.end_line),
                "summary": f"new {sym.kind} '{name}({', '.join(sym.params)})' added in {rel_path}:{sym.start_line}",
            })
        else:
            old_sym = old_symbols[name]
            # Check if signature changed
            sig_changed = old_sym.params != sym.params
            # Check if line range overlaps with modified hunk
            overlap = any(
                not (sym.end_line < h_start or sym.start_line > h_end)
                for h_start, h_end in hunk_ranges
            )

            if sig_changed or overlap:
                change_desc = []
                if sig_changed:
                    change_desc.append(
                        f"signature changed from ({', '.join(old_sym.params)}) to ({', '.join(sym.params)})"
                    )
                if overlap:
                    change_desc.append("body lines modified")

                results.append({
                    "name": name,
                    "file": rel_path,
                    "kind": sym.kind,
                    "change_type": "modified",
                    "old_params": old_sym.params,
                    "new_params": sym.params,
                    "signature_changed": sig_changed,
                    "lines": (sym.start_line, sym.end_line),
                    "summary": f"{sym.kind} '{name}' in {rel_path} was modified: {'; '.join(change_desc)}",
                })

    return results


def find_symbol_callers(
    repo_path: Path, symbol_names: Set[str], ignore_dirs: Optional[Set[str]] = None
) -> Tuple[Dict[str, List[str]], List[str]]:
    """Scan all Python files in the repo to find callers of the changed symbols."""
    callers: Dict[str, List[str]] = {name: [] for name in symbol_names}
    gaps: List[str] = []

    if not symbol_names:
        return callers, gaps

    if ignore_dirs is None:
        ignore_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}

    has_dynamic_call = False

    for root, dirs, files in os.walk(repo_path):
        # Exclude ignored dirs
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]

        for fname in files:
            if not fname.endswith(".py"):
                continue

            file_path = Path(root) / fname
            rel_path = file_path.relative_to(repo_path).as_posix()

            try:
                code_text = file_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(code_text)
            except Exception:
                continue

            for node in ast.walk(tree):
                # Detect dynamic invocations
                if isinstance(node, ast.Call):
                    # Check direct function call: func()
                    if isinstance(node.func, ast.Name) and node.func.id in symbol_names:
                        callers[node.func.id].append(f"{rel_path}:{node.lineno}")
                    # Check method or attribute call: obj.func()
                    elif isinstance(node.func, ast.Attribute) and node.func.attr in symbol_names:
                        callers[node.func.attr].append(f"{rel_path}:{node.lineno}")
                    # Check getattr dynamic call
                    elif isinstance(node.func, ast.Name) and node.func.id in {"getattr", "eval", "exec"}:
                        has_dynamic_call = True

    # Deduplicate caller locations
    for name in callers:
        callers[name] = sorted(list(set(callers[name])))

    if has_dynamic_call:
        gaps.append("Dynamic calls (getattr/eval) detected in repository; some runtime callers may not be captured statically.")

    return callers, gaps


def get_blame_authors(
    repo_path: Path, changed_files: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Run git blame on modified lines to find prior authors and recommend reviewers."""
    author_counts: Dict[str, int] = {}
    author_files: Dict[str, Set[str]] = {}

    for f in changed_files:
        rel_path = f["path"]
        hunks = f.get("hunk_ranges", [])
        if not hunks or f["status"] == "added":
            continue

        for start, end in hunks:
            if start >= end:
                continue
            code, stdout, _ = run_git(
                ["blame", "-L", f"{start},{end}", "--line-porcelain", rel_path],
                repo_path,
            )
            if code != 0 or not stdout:
                continue

            for line in stdout.splitlines():
                if line.startswith("author "):
                    author = line[len("author "):].strip()
                    if author and author != "Not Committed Yet":
                        author_counts[author] = author_counts.get(author, 0) + 1
                        author_files.setdefault(author, set()).add(rel_path)

    # Convert to sorted list of recommended reviewers
    reviewers: List[Dict[str, Any]] = []
    total_blamed_lines = sum(author_counts.values()) or 1

    for author, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = round((count / total_blamed_lines) * 100)
        reviewers.append({
            "name": author,
            "lines_authored": count,
            "percentage": percentage,
            "files": sorted(list(author_files.get(author, set()))),
            "summary": f"{author} authored {percentage}% of modified lines in {', '.join(author_files.get(author, set()))}",
        })

    return reviewers


def find_doc_references(
    repo_path: Path, symbol_names: Set[str], changed_files: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Search markdown and documentation files for mentions of changed symbols or files."""
    matches: List[Dict[str, Any]] = []
    doc_extensions = {".md", ".rst", ".txt", ".adoc"}

    terms_to_search = set(symbol_names)
    for f in changed_files:
        # Also search base filename e.g. token.py
        p = Path(f["path"])
        terms_to_search.add(p.name)

    terms_to_search = {t for t in terms_to_search if len(t) > 2}
    if not terms_to_search:
        return matches

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "venv"}]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in doc_extensions:
                continue

            file_path = Path(root) / fname
            rel_path = file_path.relative_to(repo_path).as_posix()

            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                for term in terms_to_search:
                    if term in line:
                        matches.append({
                            "doc_file": rel_path,
                            "line": i,
                            "term": term,
                            "snippet": line.strip()[:120],
                            "summary": f"{rel_path}:{i} references '{term}'",
                        })
                        break  # one match per line is enough

    return matches


def collect_evidence(repo_path_str: str = ".") -> EvidenceReport:
    """Main entrypoint: collects all verifiable facts from the repository."""
    repo_path = Path(repo_path_str).resolve()
    report = EvidenceReport(repo_path=str(repo_path))

    # Verify git repository exists
    code, _, _ = run_git(["rev-parse", "--is-inside-work-tree"], repo_path)
    if code != 0:
        report.gaps.append(f"Directory {repo_path} is not a valid git repository.")
        return report

    # 1. Changed files and diff
    report.raw_diff = get_git_diff_text(repo_path)
    report.changed_files = get_changed_files_list(repo_path)

    # 2. Symbols analysis
    all_symbols: List[Dict[str, Any]] = []
    symbol_names: Set[str] = set()

    for f_info in report.changed_files:
        if f_info["path"].endswith(".py"):
            syms = analyze_python_symbols(repo_path, f_info)
            all_symbols.extend(syms)
            for s in syms:
                symbol_names.add(s["name"])

    report.symbols = all_symbols

    # 3. Callers lookup
    callers, dynamic_gaps = find_symbol_callers(repo_path, symbol_names)
    report.callers = callers
    report.gaps.extend(dynamic_gaps)

    # 4. Git blame & Reviewers
    report.reviewers = get_blame_authors(repo_path, report.changed_files)

    # 5. Outdated documentation search
    report.doc_matches = find_doc_references(repo_path, symbol_names, report.changed_files)

    # 6. Check for non-Python changed files where AST couldn't be parsed
    non_py_files = [f["path"] for f in report.changed_files if not f["path"].endswith(".py")]
    if non_py_files:
        report.gaps.append(
            f"Non-Python files changed ({', '.join(non_py_files[:3])}): AST symbol extraction is limited to Python."
        )

    # 7. Build catalog with deterministic IDs: E1, E2, E3...
    item_idx = 1

    # File change evidence
    for f in report.changed_files:
        evidence_id = f"E{item_idx}"
        item_idx += 1
        summary = f"File {f['path']} ({f['status']}): +{f['additions']} -{f['deletions']} lines"
        report.items.append(EvidenceItem(
            id=evidence_id,
            category="file_change",
            summary=summary,
            details=f,
        ))

    # Symbol changes
    for sym in report.symbols:
        evidence_id = f"E{item_idx}"
        item_idx += 1
        report.items.append(EvidenceItem(
            id=evidence_id,
            category="symbol_change",
            summary=sym["summary"],
            details=sym,
        ))

    # Caller evidence (only for symbols with callers or explicit zero callers)
    for sym_name, call_list in report.callers.items():
        evidence_id = f"E{item_idx}"
        item_idx += 1
        if call_list:
            summary = f"Symbol '{sym_name}' is called by: {', '.join(call_list)}"
        else:
            summary = f"Symbol '{sym_name}' has 0 static callers detected in repository"
        report.items.append(EvidenceItem(
            id=evidence_id,
            category="callers",
            summary=summary,
            details={"symbol": sym_name, "called_by": call_list},
        ))

    # Blame & reviewer evidence
    for reviewer in report.reviewers:
        evidence_id = f"E{item_idx}"
        item_idx += 1
        report.items.append(EvidenceItem(
            id=evidence_id,
            category="blame",
            summary=reviewer["summary"],
            details=reviewer,
        ))

    # Documentation matches
    for doc in report.doc_matches:
        evidence_id = f"E{item_idx}"
        item_idx += 1
        report.items.append(EvidenceItem(
            id=evidence_id,
            category="doc_mention",
            summary=doc["summary"],
            details=doc,
        ))

    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    evidence_report = collect_evidence(target)
    print(json.dumps(evidence_report.to_dict(), indent=2))
