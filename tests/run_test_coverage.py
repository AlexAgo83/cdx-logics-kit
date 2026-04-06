#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run kit unit tests with coverage reporting.")
    parser.add_argument(
        "--xml",
        default="coverage/coverage.xml",
        help="Write a Cobertura-style XML report to this path. Pass an empty string to skip.",
    )
    parser.add_argument(
        "--html-dir",
        default="",
        help="Optionally write an HTML report to this directory.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero when total line coverage drops below this percentage.",
    )
    return parser.parse_args()


def load_coverage():
    try:
        import coverage
    except ImportError as exc:  # pragma: no cover - dependency bootstrap path
        raise SystemExit(
            "Missing Python dependency 'coverage'. Install it with `python -m pip install coverage` before running coverage."
        ) from exc
    return coverage


def main() -> int:
    args = parse_args()
    coverage = load_coverage()

    repo_root = Path(__file__).resolve().parents[1]
    tests_root = repo_root / "tests"
    xml_path = (repo_root / args.xml).resolve() if args.xml else None
    html_dir = (repo_root / args.html_dir).resolve() if args.html_dir else None

    cov = coverage.Coverage(
        branch=True,
        source=[str(repo_root)],
        omit=[
            "*/tests/*",
            "*/__pycache__/*",
            "*/.pytest_cache/*",
            "*/coverage/*",
            "*/changelogs/*",
            "*/logics/.cache/*",
        ],
    )

    cov.start()
    suite = unittest.defaultTestLoader.discover(str(tests_root), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    cov.stop()
    cov.save()

    print("\nCoverage summary")
    total = cov.report(show_missing=True, skip_covered=True)

    if xml_path is not None:
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        cov.xml_report(outfile=str(xml_path))
        print(f"Coverage XML written to {xml_path}")

    if html_dir is not None:
        html_dir.mkdir(parents=True, exist_ok=True)
        cov.html_report(directory=str(html_dir))
        print(f"Coverage HTML written to {html_dir}")

    if not result.wasSuccessful():
        return 1
    if args.fail_under is not None and total < args.fail_under:
        print(f"Coverage {total:.2f}% is below fail-under threshold {args.fail_under:.2f}%")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
