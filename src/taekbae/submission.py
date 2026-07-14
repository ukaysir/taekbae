from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping


MAX_ZIP_BYTES = 50_000_000
HWP_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
TEAM_NAME_PATTERN = re.compile(r"^[0-9A-Za-z가-힣 _-]{1,30}$")

FILE_SPECS: dict[str, dict[str, object]] = {
    "application": {
        "archive_stem": "1. 참가신청서",
        "suffixes": {".pdf", ".hwp"},
    },
    "proposal_hwp": {"archive_name": "2. 제안서.hwp", "suffixes": {".hwp"}},
    "proposal_pdf": {"archive_name": "2. 제안서.pdf", "suffixes": {".pdf"}},
    "analysis_hwp": {
        "archive_name": "3. 분석 과정 보고서.hwp",
        "suffixes": {".hwp"},
    },
    "analysis_pdf": {
        "archive_name": "3. 분석 과정 보고서.pdf",
        "suffixes": {".pdf"},
    },
    "consent_pledge_pdf": {
        "archive_name": "4. 개인정보 수집·이용·제공 동의서 및 참가서약서.pdf",
        "suffixes": {".pdf"},
    },
    "reviewer_draw_pdf": {
        "archive_name": "5. 심사위원 추첨표.pdf",
        "suffixes": {".pdf"},
    },
}

REQUIRED_CONFIRMATIONS = (
    "participant_eligibility_confirmed",
    "latest_notice_checked",
    "organizer_rights_clause_clarified",
    "originality_and_source_rights_confirmed",
    "hwp_pdf_content_matched",
    "all_required_signatures_present",
    "exactly_seven_draw_numbers_marked",
)

FORBIDDEN_TEXT = {
    "draft_mark": "DRAFT",
    "participant_placeholder": "[사용자 입력 필요]",
    "local_windows_path": "C:\\Users\\",
    "browser_file_url": "file:///",
    "credential_assignment": "DATA_GO_KR_SERVICE_KEY=",
}


def _archive_name(role: str, suffix: str) -> str:
    spec = FILE_SPECS[role]
    fixed = spec.get("archive_name")
    if fixed:
        return str(fixed)
    return f"{spec['archive_stem']}{suffix}"


def _resolve_file(base_dir: Path, raw_path: object) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _pdf_details(path: Path) -> tuple[int | None, str, str | None]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return None, "", "encrypted PDF"
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return len(reader.pages), text, None
    except Exception as exc:  # pragma: no cover - exact parser errors vary
        return None, "", f"unreadable PDF: {type(exc).__name__}"


def validate_submission_manifest(
    manifest: Mapping[str, Any],
    *,
    base_dir: Path,
    service_key: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    file_results: list[dict[str, Any]] = []

    team_name = str(manifest.get("team_name", "")).strip()
    team_name_valid = bool(TEAM_NAME_PATTERN.fullmatch(team_name)) and "입력" not in team_name
    if not team_name_valid:
        errors.append("team_name must be 1-30 safe Korean/ASCII characters")

    confirmations = manifest.get("confirmations")
    if not isinstance(confirmations, Mapping):
        confirmations = {}
    for name in REQUIRED_CONFIRMATIONS:
        if confirmations.get(name) is not True:
            errors.append(f"confirmation missing: {name}")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, Mapping):
        raw_files = {}

    resolved: dict[str, Path] = {}
    secret_bytes = service_key.encode("utf-8") if service_key else None
    secret_hits = 0

    for role, spec in FILE_SPECS.items():
        raw_path = raw_files.get(role)
        result: dict[str, Any] = {"role": role, "status": "invalid"}
        if not raw_path:
            errors.append(f"file missing from manifest: {role}")
            file_results.append(result)
            continue
        path = _resolve_file(base_dir, raw_path)
        result["input_name"] = path.name
        if not path.is_file():
            errors.append(f"file not found: {role}")
            file_results.append(result)
            continue

        suffix = path.suffix.lower()
        allowed_suffixes = set(spec["suffixes"])
        if suffix not in allowed_suffixes:
            errors.append(f"invalid extension for {role}: {suffix}")
            file_results.append(result)
            continue

        raw = path.read_bytes()
        if suffix == ".pdf" and not raw.startswith(b"%PDF-"):
            errors.append(f"invalid PDF signature: {role}")
        if suffix == ".hwp" and not raw.startswith(HWP_MAGIC):
            errors.append(f"invalid HWP signature: {role}")

        role_secret_hits = 0
        if secret_bytes:
            role_secret_hits = raw.count(secret_bytes)
            secret_hits += role_secret_hits
            if role_secret_hits:
                errors.append(f"credential value found in file: {role}")

        page_count: int | None = None
        extracted_text = ""
        if suffix == ".pdf":
            page_count, extracted_text, pdf_error = _pdf_details(path)
            if pdf_error:
                errors.append(f"{role}: {pdf_error}")
            if role == "proposal_pdf" and page_count is not None and not 1 <= page_count <= 10:
                errors.append(f"proposal PDF must be 1-10 pages, got {page_count}")
            if role == "analysis_pdf" and page_count is not None and not 3 <= page_count <= 5:
                warnings.append(f"analysis PDF is outside recommended 3-5 pages: {page_count}")
            for label, forbidden in FORBIDDEN_TEXT.items():
                if forbidden in extracted_text:
                    errors.append(f"forbidden text in {role}: {label}")

        archive_name = _archive_name(role, suffix)
        result.update(
            {
                "status": "checked",
                "bytes": len(raw),
                "suffix": suffix,
                "archive_name": archive_name,
                "pages": page_count,
                "credential_hits": role_secret_hits,
            }
        )
        resolved[role] = path
        file_results.append(result)

    archive_names = [
        result.get("archive_name") for result in file_results if result.get("archive_name")
    ]
    if len(archive_names) != len(set(archive_names)):
        errors.append("duplicate archive names")

    return {
        "status": "valid" if not errors else "invalid",
        "team_name": team_name if team_name_valid else None,
        "expected_zip_name": f"[공모전_{team_name}].zip" if team_name_valid else None,
        "files": file_results,
        "resolved_files": resolved,
        "confirmations_required": list(REQUIRED_CONFIRMATIONS),
        "credential_present": bool(service_key),
        "credential_hits": secret_hits,
        "warnings": warnings,
        "errors": errors,
    }


def create_submission_zip(
    validation: Mapping[str, Any],
    *,
    output_dir: Path,
) -> tuple[Path | None, list[str]]:
    errors = list(validation.get("errors", []))
    if validation.get("status") != "valid" or errors:
        return None, errors or ["submission validation did not pass"]

    zip_name = str(validation["expected_zip_name"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (output_dir / zip_name).resolve()
    resolved_files = validation["resolved_files"]
    file_results = validation["files"]

    with tempfile.NamedTemporaryFile(
        prefix="submission-", suffix=".zip", dir=output_dir, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for result in file_results:
                role = str(result["role"])
                archive.write(resolved_files[role], arcname=str(result["archive_name"]))
        size = temporary.stat().st_size
        if size >= MAX_ZIP_BYTES:
            return None, [f"ZIP must be below 50,000,000 bytes, got {size}"]
        with zipfile.ZipFile(temporary, "r") as archive:
            bad_member = archive.testzip()
            if bad_member:
                return None, [f"ZIP CRC failed: {bad_member}"]
            if len(archive.namelist()) != len(FILE_SPECS):
                return None, ["ZIP member count mismatch"]
        temporary.replace(output_path)
        return output_path, []
    finally:
        if temporary.exists():
            temporary.unlink()


def service_key_from_environment() -> str | None:
    value = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not value and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = str(winreg.QueryValueEx(key, "DATA_GO_KR_SERVICE_KEY")[0]).strip()
        except (FileNotFoundError, OSError):
            value = ""
    return value or None
