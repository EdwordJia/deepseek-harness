#!/usr/bin/env python3
"""文书批量 API 客户端和本地审计器。

该脚本只负责可重复的编排和检查，不直接修改 docx。需要修正时应修正
case_data/人工表后重新生成，避免把结构化错误藏在文书 XML 中。
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import json
import mimetypes
import os
import re
import sys
import time
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://qmjkuymwasqg.sealoshzh.site"
DOWNLOAD_TERMINAL = {"completed", "completed_with_errors", "failed"}
WAIT_TERMINAL = DOWNLOAD_TERMINAL | {"preview_ready", "preview_failed"}
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "order_id": ("订单号", "订单编号", "案件编号", "租机订单号", "租赁合同订单的编号", "租赁订单编号", "租赁合同订单号", "order_id", "orderid"),
    "name": ("被告姓名", "姓名", "承租方", "客户姓名", "案件系统姓名（有重复）", "name", "defendant_name"),
    "id_number": ("身份证号", "身份证号码", "证件号码", "id_number"),
    "court": ("管辖法院", "法院", "受诉法院", "court"),
    "total_rent": ("总租金", "租金总额", "合同金额", "合同金额（含买断价、已抵扣首期款优惠）", "total_rent"),
    "remaining_principal": ("剩余本金", "剩余本金（含买断价，已扣除押金）", "剩余租金", "remaining_principal"),
    "paid_rent": ("已付租金", "已还租金", "已还租金（含押金）", "已付金额", "已支付租金", "paid_rent"),
    "buyout_price": ("买断价", "到期买断价", "购买价", "buyout_price"),
    "penalty_amount": ("违约金金额", "逾期违约金", "逾期费用", "违约金", "penalty_amount"),
}
AMOUNT_FIELDS = {"total_rent", "remaining_principal", "paid_rent", "buyout_price", "penalty_amount"}
ID_FIELDS = {"id_number"}


def _base_url() -> str:
    return os.getenv("DOCUMENT_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = os.getenv("DOCUMENT_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_url(path: str) -> str:
    raw = urljoin(_base_url(), path.lstrip("/"))
    parts = urlsplit(raw)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe="/%:@"),
        quote(parts.query, safe="=&%/:?@"),
        parts.fragment,
    ))


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = _headers()
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(_api_url(path), data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=float(os.getenv("DOCUMENT_API_TIMEOUT", "60"))) as response:
            raw = response.read()
    except Exception as exc:  # pragma: no cover - network errors are environment-specific
        raise RuntimeError(f"API 请求失败 {method} {path}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"API 返回不是 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"API 返回结构异常: {path}")
    return value


def _download(url: str, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url if url.startswith("http") else _api_url(url), headers=_headers())
    digest = hashlib.sha256()
    size = 0
    try:
        with urlopen(request, timeout=float(os.getenv("DOCUMENT_API_TIMEOUT", "120"))) as response:
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    except Exception as exc:  # pragma: no cover - network errors are environment-specific
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"下载失败 {url}: {exc}") from exc
    return {"url": url, "path": str(destination), "bytes": size, "sha256": digest.hexdigest()}


def _wait(batch_id: str, interval: float, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    latest: dict[str, Any] = {}
    while True:
        latest = _request_json("GET", f"/api/v1/workflows/document-generation/batch/{batch_id}")
        print(json.dumps({
            "batch_id": batch_id,
            "status": latest.get("status"),
            "progress": latest.get("progress"),
            "total_cases": latest.get("total_cases"),
            "completed_cases": latest.get("completed_cases"),
            "needs_review_cases": latest.get("needs_review_cases"),
            "failed_cases": latest.get("failed_cases"),
        }, ensure_ascii=False), flush=True)
        if latest.get("status") in WAIT_TERMINAL:
            return latest
        if time.monotonic() - started >= timeout:
            raise TimeoutError(f"批次等待超时: {batch_id}")
        time.sleep(interval)


def _start(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {
        "root_dir": args.root_dir,
        "strict": args.strict,
        "quick_draft_if_ai_unavailable": args.quick_draft_if_ai_unavailable,
        "preview_mode": args.preview_mode,
    }
    if args.output_dir:
        payload["output_dir"] = args.output_dir
    if args.max_cases is not None:
        payload["max_cases"] = args.max_cases
    result = _request_json("POST", "/api/v1/workflows/document-generation/batch/start", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.wait:
        result = _wait(result["batch_id"], args.interval, args.timeout)
        if args.download_dir:
            _download_batch(result, Path(args.download_dir))
    return 0


def _selected_upload_files(root: Path, case_name: str | None) -> list[Path]:
    files = [path for path in root.rglob("*") if path.is_file()]
    if not case_name:
        return sorted(files)
    shared_names = {"原告材料", "甲方材料", "plaintiff", "plaintiff_materials"}
    selected: list[Path] = []
    for path in files:
        relative = path.relative_to(root)
        parts = set(relative.parts)
        if len(relative.parts) == 1 or case_name in parts or parts & shared_names:
            selected.append(path)
    if not any(case_name in path.relative_to(root).parts for path in selected):
        raise RuntimeError(f"指定案件目录不存在或没有文件: {case_name}")
    return sorted(selected)


def _upload_local_batch(root: Path, case_name: str | None, client_batch_id: str | None) -> dict[str, Any]:
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise RuntimeError("上传本地资料需要 requests，请在 DSH Python 环境安装 requests") from exc
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"资料根目录不存在: {root}")
    paths = _selected_upload_files(root, case_name)
    if not paths:
        raise RuntimeError(f"资料目录没有可上传文件: {root}")
    data: list[tuple[str, str]] = []
    if client_batch_id:
        data.append(("client_batch_id", client_batch_id))
    with ExitStack() as stack:
        files: list[tuple[str, tuple[str, Any, str]]] = []
        for path in paths:
            relative = (Path(root.name) / path.relative_to(root)).as_posix()
            data.append(("relative_paths", relative))
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            files.append(("files", (path.name, stack.enter_context(path.open("rb")), content_type)))
        try:
            response = requests.post(
                _api_url("/api/v1/uploads/oss/local-batches"),
                data=data,
                files=files,
                headers={key: value for key, value in _headers().items() if key != "Accept"},
                timeout=float(os.getenv("DOCUMENT_UPLOAD_TIMEOUT", "600")),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"本地资料上传失败: {exc}") from exc
    if not response.ok:
        detail = response.text[:2000]
        raise RuntimeError(f"本地资料上传失败 HTTP {response.status_code}: {detail}")
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("上传接口返回不是 JSON") from exc
    if not isinstance(result, dict) or not result.get("materialized_root"):
        raise RuntimeError(f"上传接口未返回 materialized_root: {result}")
    return result


def _upload_start(args: argparse.Namespace) -> int:
    upload = _upload_local_batch(Path(args.root_dir), args.case, args.client_batch_id)
    print(json.dumps({"upload": upload}, ensure_ascii=False, indent=2))
    payload: dict[str, Any] = {
        "root_dir": upload["materialized_root"],
        "strict": args.strict,
        "quick_draft_if_ai_unavailable": args.quick_draft_if_ai_unavailable,
        "preview_mode": args.preview_mode,
    }
    if args.max_cases is not None:
        payload["max_cases"] = args.max_cases
    result = _request_json("POST", "/api/v1/workflows/document-generation/batch/start", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.wait:
        result = _wait(result["batch_id"], args.interval, args.timeout)
        if args.download_dir:
            artifacts = _download_batch(result, Path(args.download_dir))
            metadata_path = Path(args.download_dir) / f"{result['batch_id']}.upload.json"
            metadata_path.write_text(json.dumps(upload, ensure_ascii=False, indent=2), encoding="utf-8")
            artifacts["upload_metadata"] = str(metadata_path)
    return 0


def _download_batch(status: dict[str, Any], destination: Path) -> dict[str, Any]:
    batch_id = str(status["batch_id"])
    destination.mkdir(parents=True, exist_ok=True)
    artifact: dict[str, Any] = {"batch_id": batch_id}
    download_url = status.get("download_url") or f"/api/v1/workflows/document-generation/batch/{batch_id}/download"
    artifact["zip"] = _download(_api_url(str(download_url)), destination / f"{batch_id}.zip")
    case_info = status.get("case_info_excel")
    if isinstance(case_info, dict) and case_info.get("url"):
        artifact["case_info_excel"] = _download(
            _api_url(str(case_info["url"])), destination / (str(case_info.get("filename") or f"{batch_id}-案件信息表.xlsx"))
        )
    (destination / f"{batch_id}.status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return artifact


def _status(args: argparse.Namespace) -> int:
    result = _wait(args.batch_id, args.interval, args.timeout) if args.wait else _request_json(
        "GET", f"/api/v1/workflows/document-generation/batch/{args.batch_id}"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.download_dir and result.get("status") in DOWNLOAD_TERMINAL:
        _download_batch(result, Path(args.download_dir))
    return 0


def _preview_data(args: argparse.Namespace) -> int:
    result = _request_json("GET", f"/api/v1/workflows/document-generation/batch/{args.batch_id}/preview-case-data")
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _regenerate_preview(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.overrides_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("覆盖 JSON 必须是对象")
    known = {"override_clauses", "override_fields", "case_data_overrides"}
    if not known.intersection(payload):
        payload = {"case_data_overrides": payload}
    result = _request_json(
        "POST",
        f"/api/v1/workflows/document-generation/batch/{args.batch_id}/regenerate-preview",
        payload,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.wait:
        result = _wait(args.batch_id, args.interval, args.timeout)
    return 0


def _confirm_preview(args: argparse.Namespace) -> int:
    result = _request_json(
        "POST", f"/api/v1/workflows/document-generation/batch/{args.batch_id}/confirm-preview", {}
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.wait:
        result = _wait(args.batch_id, args.interval, args.timeout)
    if args.download_dir and result.get("status") in DOWNLOAD_TERMINAL:
        _download_batch(result, Path(args.download_dir))
    return 0


def _normal_header(value: Any) -> str:
    return re.sub(r"[\s_\-（）()：:{}]+", "", str(value or "")).lower()


def _field_from_header(value: Any) -> str | None:
    normalized = _normal_header(value)
    for field, aliases in FIELD_ALIASES.items():
        if normalized in {_normal_header(alias) for alias in aliases}:
            return field
    return None


def _load_xlsx(source: Path | bytes) -> list[dict[str, Any]]:
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise RuntimeError("审计 XLSX 需要 openpyxl，请在 DSH Python 环境安装 openpyxl") from exc
    workbook = openpyxl.load_workbook(io.BytesIO(source) if isinstance(source, bytes) else source, data_only=True, read_only=True)
    rows: list[dict[str, Any]] = []
    for sheet in workbook.worksheets:
        values = list(sheet.iter_rows(values_only=True))
        header_index = next((index for index, row in enumerate(values[:12]) if any(_field_from_header(cell) for cell in row)), None)
        if header_index is None:
            continue
        fields = [_field_from_header(cell) for cell in values[header_index]]
        for row in values[header_index + 1 :]:
            record = {field: cell for field, cell in zip(fields, row) if field}
            if any(value not in (None, "") for value in record.values()):
                rows.append(record)
    return rows


def _iter_xlsx_from_zip(archive: zipfile.ZipFile) -> Iterable[tuple[str, bytes]]:
    for info in archive.infolist():
        if info.filename.lower().endswith((".xlsx", ".xlsm")):
            yield info.filename, archive.read(info)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace(",", "")
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def _equal(left: Any, right: Any, field: str) -> bool:
    left_text, right_text = _clean(left), _clean(right)
    if field in AMOUNT_FIELDS:
        try:
            return Decimal(left_text or "0").quantize(Decimal("0.01")) == Decimal(right_text or "0").quantize(Decimal("0.01"))
        except InvalidOperation:
            pass
    return left_text.casefold() == right_text.casefold()


def _mask(value: Any, field: str) -> str:
    text = _clean(value)
    if field == "id_number" and len(text) >= 8:
        return text[:4] + "*" * (len(text) - 8) + text[-4:]
    return text


def _compare_rows(generated: list[dict[str, Any]], authority: list[dict[str, Any]], source: str) -> dict[str, Any]:
    order_pattern = re.compile(r"(?:SH|ME|SA)\d{10,}", re.IGNORECASE)
    use_order_id = any(order_pattern.fullmatch(_clean(row.get("order_id"))) for row in authority)
    key_field = "order_id" if use_order_id else "name"
    def valid_key(row: dict[str, Any]) -> str:
        key = _clean(row.get(key_field))
        if key_field == "order_id":
            return key if order_pattern.fullmatch(key) else ""
        if not key or key in {"姓名", "被告姓名", "承租方", "客户姓名"}:
            return ""
        if "一般为" in key or "承租物品方" in key:
            return ""
        return key
    generated_by_id = {valid_key(row): row for row in generated if valid_key(row)}
    authority_by_id = {valid_key(row): row for row in authority if valid_key(row)}
    differences: list[dict[str, Any]] = []
    for order_id in sorted(set(generated_by_id) | set(authority_by_id)):
        if order_id not in generated_by_id:
            differences.append({"severity": "review", "source": source, key_field: order_id, "kind": "scope_exclusion"})
            continue
        if order_id not in authority_by_id:
            differences.append({"severity": "review", "source": source, key_field: order_id, "kind": "missing_authority"})
            continue
        left, right = generated_by_id[order_id], authority_by_id[order_id]
        for field in set(left) & set(right) - {"order_id"}:
            if not _equal(left.get(field), right.get(field), field):
                differences.append({
                    "severity": "blocker" if field in AMOUNT_FIELDS or field in {"name", "id_number", "court"} else "review",
                    "source": source,
                    key_field: order_id,
                    "field": field,
                    "generated": _mask(left.get(field), field),
                    "authority": _mask(right.get(field), field),
                })
    return {"generated_count": len(generated_by_id), "authority_count": len(authority_by_id), "differences": differences}


def _docx_findings(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for info in archive.infolist():
        if not info.filename.lower().endswith(".docx"):
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(archive.read(info))) as docx:
                xml = docx.read("word/document.xml").decode("utf-8", errors="replace")
                if "{{" in xml or "}}" in xml:
                    findings.append({"severity": "blocker", "file": info.filename, "kind": "unresolved_token"})
                text = re.sub(r"<[^>]+>", "", xml)
                zero_matches = list(re.finditer(r"(?<![\d.])0(?:\.0+)?(?![\d.])\s*元", text))
                for match in zero_matches:
                    context = text[max(0, match.start() - 45) : match.end() + 20]
                    if "保证金" in context or "免押" in context:
                        findings.append({"severity": "review", "file": info.filename, "kind": "zero_deposit_amount", "context": context})
                    else:
                        findings.append({"severity": "blocker", "file": info.filename, "kind": "zero_claim_amount", "context": context})
                if "起诉状" in info.filename:
                    has_seal = "SEAL_PLACEHOLDER" in xml
                    has_legal = "LEGAL_SEAL_PLACEHOLDER" in xml
                    if not has_seal:
                        findings.append({"severity": "blocker", "file": info.filename, "kind": "missing_seal_anchor"})
                    if not has_legal:
                        findings.append({"severity": "blocker", "file": info.filename, "kind": "missing_legal_seal_anchor"})
        except (KeyError, zipfile.BadZipFile) as exc:
            findings.append({"severity": "blocker", "file": info.filename, "kind": "invalid_docx", "detail": str(exc)})
    return findings


def _audit(args: argparse.Namespace) -> int:
    archive_path = Path(args.zip)
    if not archive_path.is_file():
        raise RuntimeError(f"ZIP 不存在: {archive_path}")
    report: dict[str, Any] = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "api_base_url": _base_url().rstrip("/"),
        "zip": {"path": str(archive_path), "bytes": archive_path.stat().st_size, "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest()},
        "findings": [],
        "comparisons": {},
    }
    status_path = Path(args.status) if args.status else archive_path.with_suffix(".status.json")
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            report["batch"] = {
                key: status.get(key)
                for key in (
                    "batch_id", "status", "root_dir", "total_cases", "generated_cases",
                    "completed_cases", "needs_review_cases", "failed_cases", "cases",
                )
                if key in status
            }
            report["status_file"] = str(status_path)
        except (OSError, json.JSONDecodeError) as exc:
            report["findings"].append({"severity": "review", "kind": "invalid_status_json", "detail": str(exc)})
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        report["zip"]["entries"] = len(names)
        report["documents"] = {"docx": sum(name.lower().endswith(".docx") for name in names), "xlsx": sum(name.lower().endswith(".xlsx") for name in names)}
        report["findings"].extend(_docx_findings(archive))
        generated_rows: list[dict[str, Any]] = []
        xlsx_names: list[str] = []
        for name, data in _iter_xlsx_from_zip(archive):
            xlsx_names.append(name)
            generated_rows.extend(_load_xlsx(data))
        if args.human_table:
            authority_rows = _load_xlsx(Path(args.human_table))
            report["comparisons"]["human_table"] = _compare_rows(generated_rows, authority_rows, "human_table")
        if args.amount_table:
            amount_rows = _load_xlsx(Path(args.amount_table))
            report["comparisons"]["amount_table"] = _compare_rows(generated_rows, amount_rows, "amount_table")
        report["xlsx_entries"] = xlsx_names
    all_differences = [item for value in report["comparisons"].values() for item in value["differences"]]
    scope_exclusions = [item for item in all_differences if item.get("kind") == "scope_exclusion"]
    report["summary"] = {
        "blockers": sum(item.get("severity") == "blocker" for item in report["findings"] + all_differences),
        "review_items": sum(
            item.get("severity") == "review" and item.get("kind") != "scope_exclusion"
            for item in report["findings"] + all_differences
        ),
        "scope_exclusions": len(scope_exclusions),
        "documents": report["documents"],
    }
    output = Path(args.report) if args.report else archive_path.with_name(f"{archive_path.stem}.qa-report.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 2 if report["summary"]["blockers"] else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="文书批量生成、下载和 QA 审计")
    sub = parser.add_subparsers(dest="command", required=True)
    upload_start = sub.add_parser("upload-start", help="上传本机资料到服务端后启动批次")
    upload_start.add_argument("--root-dir", required=True)
    upload_start.add_argument("--case", help="只上传指定案件；仍会包含共享原告材料和根目录文件")
    upload_start.add_argument("--client-batch-id")
    upload_start.add_argument("--max-cases", type=int)
    upload_start.add_argument("--strict", action="store_true")
    upload_start.add_argument("--quick-draft-if-ai-unavailable", action="store_true")
    upload_start.add_argument("--preview-mode", action="store_true")
    upload_start.add_argument("--wait", action="store_true")
    upload_start.add_argument("--download-dir")
    upload_start.add_argument("--interval", type=float, default=10)
    upload_start.add_argument("--timeout", type=float, default=3600)
    upload_start.set_defaults(func=_upload_start)
    start = sub.add_parser("start")
    start.add_argument("--root-dir", required=True)
    start.add_argument("--output-dir")
    start.add_argument("--max-cases", type=int)
    start.add_argument("--strict", action="store_true")
    start.add_argument("--quick-draft-if-ai-unavailable", action="store_true")
    start.add_argument("--preview-mode", action="store_true")
    start.add_argument("--wait", action="store_true")
    start.add_argument("--download-dir")
    start.add_argument("--interval", type=float, default=10)
    start.add_argument("--timeout", type=float, default=3600)
    start.set_defaults(func=_start)
    status = sub.add_parser("status")
    status.add_argument("batch_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--download-dir")
    status.add_argument("--interval", type=float, default=10)
    status.add_argument("--timeout", type=float, default=3600)
    status.set_defaults(func=_status)
    preview_data = sub.add_parser("preview-data", help="下载预览批次首案 case_data")
    preview_data.add_argument("batch_id")
    preview_data.add_argument("--output")
    preview_data.set_defaults(func=_preview_data)
    regenerate = sub.add_parser("regenerate-preview", help="应用人工覆盖并重新生成预览首案")
    regenerate.add_argument("batch_id")
    regenerate.add_argument("--overrides-json", required=True)
    regenerate.add_argument("--wait", action="store_true")
    regenerate.add_argument("--interval", type=float, default=10)
    regenerate.add_argument("--timeout", type=float, default=1800)
    regenerate.set_defaults(func=_regenerate_preview)
    confirm = sub.add_parser("confirm-preview", help="确认预览并完成批次")
    confirm.add_argument("batch_id")
    confirm.add_argument("--wait", action="store_true")
    confirm.add_argument("--download-dir")
    confirm.add_argument("--interval", type=float, default=10)
    confirm.add_argument("--timeout", type=float, default=1800)
    confirm.set_defaults(func=_confirm_preview)
    download = sub.add_parser("download")
    download.add_argument("batch_id")
    download.add_argument("--output-dir", required=True)
    download.set_defaults(func=lambda args: _download_batch(_request_json("GET", f"/api/v1/workflows/document-generation/batch/{args.batch_id}"), Path(args.output_dir)) and 0)
    audit = sub.add_parser("audit")
    audit.add_argument("--zip", required=True)
    audit.add_argument("--human-table")
    audit.add_argument("--amount-table")
    audit.add_argument("--status", help="批次状态 JSON；默认读取 ZIP 同目录的 .status.json")
    audit.add_argument("--report")
    audit.set_defaults(func=_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (RuntimeError, TimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
