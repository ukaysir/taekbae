from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from taekbae.submission import (
    create_submission_zip,
    service_key_from_environment,
    validate_submission_manifest,
)


def _public_report(report: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in report.items() if key != "resolved_files"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the official five-document submission and optionally build its ZIP."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--create-zip", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = validate_submission_manifest(
        manifest,
        base_dir=manifest_path.parent,
        service_key=service_key_from_environment(),
    )

    if args.create_zip:
        if args.output_dir is None:
            parser.error("--output-dir is required with --create-zip")
        zip_path, zip_errors = create_submission_zip(
            report, output_dir=args.output_dir.resolve()
        )
        report["zip_created"] = zip_path is not None
        report["zip_name"] = zip_path.name if zip_path else None
        if zip_errors:
            report["errors"].extend(zip_errors)
            report["status"] = "invalid"
    else:
        report["zip_created"] = False
        report["zip_name"] = None

    public = _public_report(report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
