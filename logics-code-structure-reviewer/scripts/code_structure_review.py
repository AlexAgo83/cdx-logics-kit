#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    ".svelte-kit",
    ".turbo",
    ".cache",
    "coverage",
    "target",
    "vendor",
}

CODE_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".rb",
    ".php",
}


@dataclass(frozen=True)
class FileStat:
    path: Path
    bytes_size: int
    lines: int
    ext: str


@dataclass(frozen=True)
class StackGuess:
    primary: str
    signals: list[str]
    confidence: str


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "logics").is_dir():
            return candidate
    # Fall back to git root if present, otherwise cwd.
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return current


def _read_text_best_effort(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError:
            return ""


def _count_lines_fast(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _iter_files(repo_root: Path, include_logics: bool) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        rel_parts = path.relative_to(repo_root).parts
        if not rel_parts:
            continue
        if not include_logics and rel_parts[0] == "logics":
            continue
        if any(part in DEFAULT_IGNORED_DIRS for part in rel_parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _collect_code_stats(repo_root: Path, include_logics: bool) -> list[FileStat]:
    stats: list[FileStat] = []
    for path in _iter_files(repo_root, include_logics=include_logics):
        ext = path.suffix.lower()
        if ext not in CODE_EXTENSIONS:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        lines = _count_lines_fast(path)
        stats.append(FileStat(path=path, bytes_size=size, lines=lines, ext=ext))
    return stats


def _parse_package_json(repo_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    path = repo_root / "package.json"
    if not path.is_file():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    deps = data.get("dependencies") or {}
    dev = data.get("devDependencies") or {}
    if not isinstance(deps, dict):
        deps = {}
    if not isinstance(dev, dict):
        dev = {}
    return deps, dev


def _has_any(repo_root: Path, candidates: list[str]) -> bool:
    return any((repo_root / c).exists() for c in candidates)


def _guess_stack(repo_root: Path, stats: list[FileStat]) -> StackGuess:
    signals: list[str] = []

    deps, dev = _parse_package_json(repo_root)
    all_deps = {**deps, **dev}

    ext_counts: dict[str, int] = {}
    for s in stats:
        ext_counts[s.ext] = ext_counts.get(s.ext, 0) + 1

    def count_ext(*exts: str) -> int:
        return sum(ext_counts.get(e, 0) for e in exts)

    js_ts_score = count_ext(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    py_score = count_ext(".py")
    go_score = count_ext(".go")
    rs_score = count_ext(".rs")
    java_score = count_ext(".java", ".kt")
    cs_score = count_ext(".cs")

    if (repo_root / "package.json").is_file():
        signals.append("Found package.json")
        if "typescript" in all_deps or (repo_root / "tsconfig.json").is_file():
            signals.append("TypeScript present")
        if "react" in all_deps:
            signals.append("React dependency")
        if "next" in all_deps or _has_any(repo_root, ["next.config.js", "next.config.mjs", "next.config.ts"]):
            signals.append("Next.js signals")
        if "vue" in all_deps:
            signals.append("Vue dependency")
        if "svelte" in all_deps:
            signals.append("Svelte dependency")
        if "express" in all_deps:
            signals.append("Express dependency")
        if "nestjs" in all_deps or "@nestjs/core" in all_deps:
            signals.append("NestJS dependency")

    if _has_any(repo_root, ["pyproject.toml", "requirements.txt", "setup.cfg", "setup.py"]):
        signals.append("Python packaging signals")
        text = _read_text_best_effort(repo_root / "pyproject.toml") + "\n" + _read_text_best_effort(repo_root / "requirements.txt")
        for needle, label in [
            ("django", "Django"),
            ("fastapi", "FastAPI"),
            ("flask", "Flask"),
            ("pytest", "pytest"),
        ]:
            if re.search(rf"(?i)\\b{re.escape(needle)}\\b", text):
                signals.append(f"{label} signals")

    if (repo_root / "go.mod").is_file():
        signals.append("Go module (go.mod)")
    if (repo_root / "Cargo.toml").is_file():
        signals.append("Rust crate (Cargo.toml)")
    if _has_any(repo_root, ["pom.xml", "build.gradle", "build.gradle.kts"]):
        signals.append("JVM build files (Maven/Gradle)")
    if any(repo_root.rglob("*.csproj")):
        signals.append(".NET project (*.csproj)")

    # Pick a primary stack based on strongest signals.
    if "Next.js signals" in signals or _has_any(repo_root, ["app", "pages"]):
        return StackGuess(primary="js/ts-nextjs", signals=signals, confidence="medium")
    if "React dependency" in signals:
        return StackGuess(primary="js/ts-react", signals=signals, confidence="medium")
    if "NestJS dependency" in signals:
        return StackGuess(primary="js/ts-nestjs", signals=signals, confidence="medium")
    if "Express dependency" in signals:
        return StackGuess(primary="js/ts-node", signals=signals, confidence="medium")
    if js_ts_score > max(py_score, go_score, rs_score, java_score, cs_score) and js_ts_score > 0:
        return StackGuess(primary="js/ts", signals=signals, confidence="low")
    if py_score > max(js_ts_score, go_score, rs_score, java_score, cs_score) and py_score > 0:
        return StackGuess(primary="python", signals=signals, confidence="low")
    if go_score > max(js_ts_score, py_score, rs_score, java_score, cs_score) and go_score > 0:
        return StackGuess(primary="go", signals=signals, confidence="low")
    if rs_score > max(js_ts_score, py_score, go_score, java_score, cs_score) and rs_score > 0:
        return StackGuess(primary="rust", signals=signals, confidence="low")
    if java_score > max(js_ts_score, py_score, go_score, rs_score, cs_score) and java_score > 0:
        return StackGuess(primary="jvm", signals=signals, confidence="low")
    if cs_score > max(js_ts_score, py_score, go_score, rs_score, java_score) and cs_score > 0:
        return StackGuess(primary="dotnet", signals=signals, confidence="low")

    return StackGuess(primary="unknown", signals=signals, confidence="low")


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _render_recommendations(stack: StackGuess) -> list[str]:
    base = [
        "Prefer smaller files with one responsibility; split very large modules into cohesive units.",
        "Introduce clear folder boundaries (e.g., `src/` + subdomains) and keep entrypoints thin.",
        "Avoid dumping unrelated helpers into `utils/`; prefer domain-scoped helpers next to their usage.",
        "Keep configuration and environment wiring separate from business logic.",
    ]

    if stack.primary == "js/ts-nextjs":
        return base + [
            "Next.js: keep `app/` or `pages/` focused on routing; move reusable UI into `components/` and logic into `lib/` / `services/`.",
            "Next.js: keep server-only code separated (route handlers, server actions) from client components.",
        ]
    if stack.primary == "js/ts-react":
        return base + [
            "React: split large UI files into `components/` and extract non-UI logic into hooks (`use*`) or services.",
            "React: keep container/page components thin; move reusable pieces into feature folders.",
        ]
    if stack.primary in {"js/ts-node", "js/ts-nestjs"}:
        return base + [
            "Node backend: separate transport (routes/controllers) from domain (services/use-cases) and data (repositories).",
            "Node backend: keep validation/schemas close to the boundary (request/DTO layer).",
        ]
    if stack.primary == "python":
        return base + [
            "Python: prefer a `src/` layout for packages when the repo grows; keep CLI/web entrypoints thin.",
            "Python: separate web layer (routers/views) from domain logic and persistence adapters.",
        ]
    if stack.primary == "go":
        return base + [
            "Go: keep packages small and purpose-driven; avoid `util` mega-packages.",
            "Go: place entrypoints in `cmd/<app>/` and keep domain logic in internal packages.",
        ]
    if stack.primary == "rust":
        return base + [
            "Rust: split large modules into smaller `mod` files; keep `lib.rs`/`main.rs` focused on wiring.",
            "Rust: prefer feature modules + clear public APIs; keep internal helpers private.",
        ]
    if stack.primary in {"jvm", "dotnet"}:
        return base + [
            "JVM/.NET: structure by feature/domain rather than by technical layer only; keep controllers thin.",
            "JVM/.NET: keep DTOs, services, and persistence separated with clear boundaries.",
        ]
    return base + [
        "If the stack is still unknown: start with a `src/` folder and create one folder per domain/feature.",
    ]


def _render_report(repo_root: Path, stack: StackGuess, stats: list[FileStat], max_lines: int, top: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append("# Code Structure Review")
    lines.append("")
    lines.append(f"_Generated: {now}_")
    lines.append("")

    lines.append("## Detected stack (heuristic)")
    lines.append("")
    lines.append(f"- Primary guess: `{stack.primary}` (confidence: {stack.confidence})")
    if stack.signals:
        lines.append("- Signals:")
        for s in stack.signals[:20]:
            lines.append(f"  - {s}")
    else:
        lines.append("- Signals: _none_")
    lines.append("")

    if not stats:
        lines.append("## Scan results")
        lines.append("")
        lines.append("_No code files detected (or everything is ignored). If this is intentional (template repo), you're good._")
        lines.append("")
        lines.append("## Recommendations")
        lines.append("")
        for rec in _render_recommendations(stack):
            lines.append(f"- {rec}")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    total_files = len(stats)
    max_file = max(stats, key=lambda s: s.lines)
    lines.append("## Scan results")
    lines.append("")
    lines.append(f"- Code files scanned: {total_files}")
    lines.append(f"- Largest by lines: `{_rel(repo_root, max_file.path)}` ({max_file.lines} lines)")
    lines.append("")

    large = [s for s in stats if s.lines >= max_lines]
    large.sort(key=lambda s: (s.lines, s.bytes_size), reverse=True)

    lines.append(f"## Large files (>= {max_lines} lines)")
    lines.append("")
    if not large:
        lines.append("_None_")
        lines.append("")
    else:
        lines.append("| File | Lines | Size |")
        lines.append("|---|---:|---:|")
        for s in large[:top]:
            lines.append(f"| `{_rel(repo_root, s.path)}` | {s.lines} | {s.bytes_size} |")
        if len(large) > top:
            lines.append(f"\n_And {len(large) - top} more..._")
        lines.append("")

    stats_sorted = sorted(stats, key=lambda s: (s.lines, s.bytes_size), reverse=True)
    lines.append(f"## Top {top} files by lines")
    lines.append("")
    lines.append("| File | Lines | Size |")
    lines.append("|---|---:|---:|")
    for s in stats_sorted[:top]:
        lines.append(f"| `{_rel(repo_root, s.path)}` | {s.lines} | {s.bytes_size} |")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    for rec in _render_recommendations(stack):
        lines.append(f"- {rec}")
    lines.append("")

    lines.append("## Next actions (concrete)")
    lines.append("")
    lines.append("- Pick the top 1–3 largest files and identify natural seams (types/models, IO boundaries, feature sections).")
    lines.append("- Extract one seam at a time into a new module/package; keep the original file as an orchestrator.")
    lines.append("- Add a simple guardrail: fail CI if new files exceed the threshold (once the stack is known).")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate a stack-aware code structure review report.")
    parser.add_argument("--out", help="Write the Markdown report to this path (relative to repo root).")
    parser.add_argument("--max-lines", type=int, default=400)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--include-logics", action="store_true", help="Include `logics/**` in the scan.")
    args = parser.parse_args(argv)

    repo_root = _find_repo_root(Path.cwd())
    stats = _collect_code_stats(repo_root, include_logics=args.include_logics)
    stack = _guess_stack(repo_root, stats)
    report = _render_report(repo_root, stack, stats, max_lines=args.max_lines, top=args.top)

    if not args.out:
        sys.stdout.write(report)
        return 0

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    try:
        printable = out_path.relative_to(repo_root)
    except ValueError:
        printable = out_path
    print(f"Wrote {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

