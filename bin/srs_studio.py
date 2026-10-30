#!/usr/bin/env python3
"""
srs_studio.py - Framework & CLI tai su dung de hien thi, chinh sua truc quan (WYSIWYG + Flow Canvas)
va xuat ban tai lieu SRS Markdown sang WebView cho bat ky du an nao.

Cac lenh ho tro:
  1. srs-studio init [docs_dir] --title "Ten Du An" --domain "company.com"
  2. srs-studio serve [docs_dir] --port 4321 --title "Ten Du An"
  3. srs-studio build [docs_dir] --out-dir ./dist --title "Ten Du An"
  4. srs-studio publish [docs_dir] --worker-url https://... --title "Ten Du An"
  5. srs-studio pull [docs_dir] --worker-url https://...
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_TEMPLATE = PACKAGE_ROOT / "templates" / "srs_gitbook_app.html"
FALLBACK_TEMPLATE = Path.home() / ".agents" / "scripts" / "templates" / "srs_gitbook_app.html"
DEFAULT_WORKER_URL = os.environ.get(
    "SPEC_STUDIO_WORKER_URL",
    "https://srs-webview-studio-demo.phamhung-plane-ai.workers.dev",
)
CLI_SHARED_KEY = os.environ.get("SRS_STUDIO_CLI_KEY", "srs-studio-cli")


def sanitize_punctuation(text: str) -> str:
    return (
        str(text or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u00b7", "-")
    )


def resolve_docs_dir(raw_path: str) -> Path:
    p = Path(raw_path).resolve()
    if (p / "docs" / "SUMMARY.md").is_file() or ((p / "docs").is_dir() and not (p / "SUMMARY.md").is_file()):
        return p / "docs"
    return p


def load_project_config(docs_dir: Path, args) -> dict:
    candidates = [
        docs_dir / "srs-studio.config.json",
        docs_dir.parent / "srs-studio.config.json",
    ]
    cfg = {
        "title": "SRS Docs Studio",
        "breadcrumbRoot": "Tài liệu SRS",
        "allowedDomain": "*",
        "authRequired": False,
        "workerUrl": DEFAULT_WORKER_URL,
        "defaultDocPath": "",
        "defaultSectionIndex": 0,
    }
    for c in candidates:
        if c.is_file():
            try:
                loaded = json.loads(c.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg.update(loaded)
                break
            except Exception:
                pass

    if getattr(args, "title", None):
        cfg["title"] = args.title
        cfg["breadcrumbRoot"] = args.title
    if getattr(args, "domain", None) is not None:
        cfg["allowedDomain"] = args.domain
    if getattr(args, "worker_url", None):
        cfg["workerUrl"] = args.worker_url
    if getattr(args, "no_auth", False):
        cfg["authRequired"] = False
    return cfg


def extract_markdown_heading(md_file: Path) -> str:
    try:
        for line in md_file.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^#\s+(.+)$", line.strip())
            if m:
                return sanitize_punctuation(m.group(1).strip())
    except Exception:
        pass
    return md_file.stem.replace("-", " ").replace("_", " ").title()


def auto_generate_summary_md(docs_dir: Path, title: str) -> Path:
    """Tu dong quet thu muc Markdown va sinh file SUMMARY.md neu du an chua co."""
    summary_path = docs_dir / "SUMMARY.md"
    md_files = sorted(
        p for p in docs_dir.rglob("*.md")
        if p.name.lower() != "summary.md" and not any(part.startswith(".") for part in p.relative_to(docs_dir).parts)
    )
    lines = [f"# Table of contents - {sanitize_punctuation(title)}", ""]

    root_files = [p for p in md_files if len(p.relative_to(docs_dir).parts) == 1]
    if root_files:
        lines.append("## I. Tổng quan")
        lines.append("")
        for rf in root_files:
            rel = rf.relative_to(docs_dir).as_posix()
            lines.append(f"* [{extract_markdown_heading(rf)}]({rel})")
        lines.append("")

    grouped = {}
    for p in md_files:
        parts = p.relative_to(docs_dir).parts
        if len(parts) <= 1:
            continue
        top = parts[0]
        grouped.setdefault(top, []).append(p)

    for sec_idx, (top_folder, files) in enumerate(sorted(grouped.items()), 1):
        sec_title = top_folder.replace("-", " ").replace("_", " ").title()
        lines.append(f"## {sec_idx}. {sec_title}")
        lines.append("")

        by_parent = {}
        for f in files:
            rel_parts = f.relative_to(docs_dir).parts
            parent_key = "/".join(rel_parts[:-1])
            by_parent.setdefault(parent_key, []).append(f)

        for parent_key, pfiles in sorted(by_parent.items()):
            if len(pfiles) == 1:
                f = pfiles[0]
                rel = f.relative_to(docs_dir).as_posix()
                lines.append(f"* [{extract_markdown_heading(f)}]({rel})")
            else:
                primary = next((x for x in pfiles if x.name in ("brd.md", "index.md", "README.md")), pfiles[0])
                primary_rel = primary.relative_to(docs_dir).as_posix()
                folder_label = parent_key.split("/")[-1]
                lines.append(f"* [{folder_label} - {extract_markdown_heading(primary)}]({primary_rel})")
                for child in pfiles:
                    crel = child.relative_to(docs_dir).as_posix()
                    lines.append(f"  * [{child.stem.upper()} - {extract_markdown_heading(child)}]({crel})")
        lines.append("")

    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return summary_path


def parse_summary_md(summary_path: Path, title: str = "SRS Documentation") -> dict:
    text = summary_path.read_text(encoding="utf-8")
    sections = []
    current_section = {
        "id": "overview",
        "title": "Tổng quan & Từ điển",
        "items": [],
    }
    sections.append(current_section)
    last_top_item = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            sec_title = sanitize_punctuation(line[3:].strip())
            sec_id = f"sec-{len(sections)}"
            current_section = {
                "id": sec_id,
                "title": sec_title,
                "items": [],
            }
            sections.append(current_section)
            last_top_item = None
            continue

        m_top = re.match(r"^\*\s+\[([^\]]+)\]\(([^)]+)\)", line)
        if m_top:
            item = {
                "title": sanitize_punctuation(m_top.group(1).strip()),
                "path": m_top.group(2).strip(),
                "children": [],
            }
            current_section["items"].append(item);
            last_top_item = item
            continue

        m_child = re.match(r"^\s+\*\s+\[([^\]]+)\]\(([^)]+)\)", line)
        if m_child and last_top_item is not None:
            last_top_item["children"].append({
                "title": sanitize_punctuation(m_child.group(1).strip()),
                "path": m_child.group(2).strip(),
            })

    sections = [s for s in sections if s["items"]]
    return {
        "title": title,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": sections,
        "sections": sections,
    }


def collect_manifest_paths(manifest: dict) -> list:
    paths = []
    seen = set()
    for sec in manifest.get("sections", []):
        for item in sec.get("items", []):
            p = item.get("path")
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
            for child in item.get("children", []):
                cp = child.get("path")
                if cp and cp not in seen:
                    seen.add(cp)
                    paths.append(cp)
    return paths


def collect_docs_bundle(docs_dir: Path, title: str) -> tuple:
    summary_path = docs_dir / "SUMMARY.md"
    if not summary_path.is_file():
        summary_path = auto_generate_summary_md(docs_dir, title)
    manifest = parse_summary_md(summary_path, title=title)
    rel_paths = collect_manifest_paths(manifest)
    docs_map = {}
    for rel_path in rel_paths:
        fpath = docs_dir / rel_path
        if fpath.is_file():
            docs_map[rel_path] = fpath.read_text(encoding="utf-8", errors="replace")
    manifest["total_files"] = len(docs_map)
    return manifest, docs_map


def render_studio_html(studio_config: dict, worker_url: str = "") -> str:
    tpl_path = PACKAGE_TEMPLATE if PACKAGE_TEMPLATE.is_file() else FALLBACK_TEMPLATE
    tpl = tpl_path.read_text(encoding="utf-8")
    config_json = json.dumps(studio_config, ensure_ascii=False)
    html = tpl.replace("/*__SRS_STUDIO_CONFIG_INJECT__*/ {}", config_json)
    html = html.replace("__WORKER_API_BASE__", worker_url.rstrip("/"))
    return html


def cmd_init(args) -> int:
    docs_dir = resolve_docs_dir(args.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    title = args.title or docs_dir.parent.name.replace("-", " ").title() + " SRS Docs"
    domain = args.domain if args.domain is not None else "*"

    summary_path = docs_dir / "SUMMARY.md"
    if not summary_path.is_file():
        auto_generate_summary_md(docs_dir, title)
        print(f"[+] Da tu dong quet va tao muc luc: {summary_path}")

    config_path = docs_dir.parent / "srs-studio.config.json"
    config_data = {
        "title": title,
        "breadcrumbRoot": f"Tài liệu {title}",
        "allowedDomain": domain,
        "authRequired": bool(domain and domain != "*"),
        "workerUrl": DEFAULT_WORKER_URL,
        "defaultDocPath": "",
        "defaultSectionIndex": 0,
    }
    config_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[+] Da khoi tao cau hinh SRS WebView Studio tai: {config_path}")
    return 0


def cmd_build(args) -> int:
    docs_dir = resolve_docs_dir(args.docs_dir)
    if not docs_dir.is_dir():
        print(f"[ERROR] Khong tim thay thu muc tai lieu: {docs_dir}", file=sys.stderr)
        return 1

    cfg = load_project_config(docs_dir, args)
    manifest, docs_map = collect_docs_bundle(docs_dir, cfg["title"])

    first_doc = next(iter(docs_map.keys()), "_index.md")
    studio_config = {
        "title": cfg["title"],
        "breadcrumbRoot": cfg.get("breadcrumbRoot") or cfg["title"],
        "allowedDomain": cfg.get("allowedDomain", "*"),
        "authRequired": False,
        "localUserLabel": "Static WebView",
        "apiBaseUrl": "",
        "defaultDocPath": cfg.get("defaultDocPath") or first_doc,
        "defaultSectionIndex": cfg.get("defaultSectionIndex", 0),
        "embeddedManifest": manifest,
        "embeddedDocs": docs_map,
    }

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    index_html = render_studio_html(studio_config, worker_url="")
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[+] Da dong goi Static WebView Bundle ({len(docs_map)} trang Markdown):")
    print(f"    File WebView doc lap: {out_dir / 'index.html'}")
    print(f"    Manifest:             {out_dir / 'manifest.json'}")
    return 0


def cmd_serve(args) -> int:
    docs_dir = resolve_docs_dir(args.docs_dir)
    if not docs_dir.is_dir():
        print(f"[ERROR] Khong tim thay thu muc tai lieu: {docs_dir}", file=sys.stderr)
        return 1

    cfg = load_project_config(docs_dir, args)
    port = int(args.port)
    host = args.host or "127.0.0.1"
    base_url = f"http://{host}:{port}"

    class StudioRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *log_args):
            pass

        def _send_json(self, status: int, data: dict):
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _send_html(self, status: int, html_text: str):
            raw = html_text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            route = parsed.path.rstrip("/") or "/"

            if route in ("/", "/book"):
                manifest, docs_map = collect_docs_bundle(docs_dir, cfg["title"])
                first_doc = next(iter(docs_map.keys()), "_index.md")
                studio_cfg = {
                    "title": cfg["title"],
                    "breadcrumbRoot": cfg.get("breadcrumbRoot") or cfg["title"],
                    "allowedDomain": cfg.get("allowedDomain", "*"),
                    "authRequired": False,
                    "localUserLabel": "Local Disk Sync",
                    "apiBaseUrl": base_url,
                    "defaultDocPath": cfg.get("defaultDocPath") or first_doc,
                    "defaultSectionIndex": cfg.get("defaultSectionIndex", 0),
                }
                self._send_html(200, render_studio_html(studio_cfg, worker_url=base_url))
                return

            if route == "/api/auth/me":
                self._send_json(200, {"authenticated": True, "email": "local@studio.dev"})
                return

            if route == "/api/srs-book/manifest":
                manifest, _ = collect_docs_bundle(docs_dir, cfg["title"])
                self._send_json(200, {"ok": True, "manifest": manifest, "comments": []})
                return

            if route == "/api/srs-book/doc":
                qs = urllib.parse.parse_qs(parsed.query)
                rel_path = (qs.get("path") or [""])[0].lstrip("/")
                target = (docs_dir / rel_path).resolve()
                if not str(target).startswith(str(docs_dir)) or not target.is_file():
                    self._send_json(404, {"ok": False, "error": f"Không tìm thấy file: {rel_path}"})
                    return
                content = target.read_text(encoding="utf-8", errors="replace")
                self._send_json(200, {"ok": True, "path": rel_path, "content": content})
                return

            if route == "/api/srs-book/history":
                qs = urllib.parse.parse_qs(parsed.query)
                rel_path = (qs.get("path") or ["_index.md"])[0].lstrip("/")
                hist_dir = docs_dir.parent / ".srs-history"
                hist_file = hist_dir / f"{rel_path.replace('/', '__')}.json"
                audit_file = hist_dir / "audit-log.json"
                versions = []
                if hist_file.is_file():
                    try:
                        versions = json.loads(hist_file.read_text(encoding="utf-8"))
                    except Exception:
                        versions = []
                target = (docs_dir / rel_path).resolve()
                if not versions and str(target).startswith(str(docs_dir)) and target.is_file():
                    cur_text = target.read_text(encoding="utf-8", errors="replace")
                    versions = [{
                        "id": "v1",
                        "version": 1,
                        "doc_path": rel_path,
                        "author": "local@studio.dev",
                        "author_name": "Bản gốc khởi tạo",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "action": "init",
                        "summary": "Bản gốc khởi tạo",
                        "added_lines": len(cur_text.splitlines()),
                        "removed_lines": 0,
                        "content": cur_text,
                    }]
                audit_log = []
                if audit_file.is_file():
                    try:
                        audit_log = json.loads(audit_file.read_text(encoding="utf-8"))
                    except Exception:
                        audit_log = []
                self._send_json(200, {"ok": True, "path": rel_path, "versions": versions, "audit_log": audit_log})
                return

            self._send_json(404, {"ok": False, "error": "Not found"})

        def do_PUT(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.rstrip("/") == "/api/srs-book/doc":
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                rel_path = str(body.get("path") or "").lstrip("/")
                content = str(body.get("content") or "")
                summary = str(body.get("summary") or "Cập nhật nội dung tài liệu").strip()
                action = str(body.get("action") or "edit").strip()
                target = (docs_dir / rel_path).resolve()
                if not rel_path or not str(target).startswith(str(docs_dir)):
                    self._send_json(400, {"ok": False, "error": "Đường dẫn không hợp lệ"})
                    return
                prev_text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
                hist_dir = docs_dir.parent / ".srs-history"
                hist_dir.mkdir(parents=True, exist_ok=True)
                hist_file = hist_dir / f"{rel_path.replace('/', '__')}.json"
                audit_file = hist_dir / "audit-log.json"
                versions = []
                if hist_file.is_file():
                    try:
                        versions = json.loads(hist_file.read_text(encoding="utf-8"))
                    except Exception:
                        versions = []
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if not versions and prev_text:
                    versions.append({
                        "id": "v1",
                        "version": 1,
                        "doc_path": rel_path,
                        "author": "local@studio.dev",
                        "author_name": "Bản gốc khởi tạo",
                        "timestamp": now_iso,
                        "action": "init",
                        "summary": "Bản gốc trước khi chỉnh sửa",
                        "added_lines": len(prev_text.splitlines()),
                        "removed_lines": 0,
                        "content": prev_text,
                    })
                prev_set = set(prev_text.splitlines())
                next_set = set(content.splitlines())
                added = sum(1 for l in content.splitlines() if l not in prev_set)
                removed = sum(1 for l in prev_text.splitlines() if l not in next_set)
                next_ver = len(versions) + 1
                new_ver = {
                    "id": f"v{next_ver}",
                    "version": next_ver,
                    "doc_path": rel_path,
                    "author": "local@studio.dev",
                    "author_name": "Local Disk Sync",
                    "timestamp": now_iso,
                    "action": action,
                    "summary": summary,
                    "added_lines": added,
                    "removed_lines": removed,
                    "content": content,
                }
                versions.append(new_ver)
                hist_file.write_text(json.dumps(versions, indent=2, ensure_ascii=False), encoding="utf-8")
                audit_log = []
                if audit_file.is_file():
                    try:
                        audit_log = json.loads(audit_file.read_text(encoding="utf-8"))
                    except Exception:
                        audit_log = []
                audit_log.insert(0, {
                    "id": f"audit-{int(datetime.now().timestamp() * 1000)}",
                    "version_id": new_ver["id"],
                    "version": new_ver["version"],
                    "doc_path": rel_path,
                    "author": new_ver["author"],
                    "author_name": new_ver["author_name"],
                    "timestamp": now_iso,
                    "action": action,
                    "summary": summary,
                    "added_lines": added,
                    "removed_lines": removed,
                })
                audit_file.write_text(json.dumps(audit_log[:200], indent=2, ensure_ascii=False), encoding="utf-8")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                self._send_json(200, {"ok": True, "path": rel_path, "saved_to": str(target), "version": new_ver, "versions_count": len(versions)})
                return
            self._send_json(404, {"ok": False, "error": "Not found"})

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.rstrip("/") == "/api/srs-book/revert":
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                rel_path = str(body.get("path") or "").lstrip("/")
                ver_id = str(body.get("version_id") or "").strip()
                hist_dir = docs_dir.parent / ".srs-history"
                hist_file = hist_dir / f"{rel_path.replace('/', '__')}.json"
                audit_file = hist_dir / "audit-log.json"
                if not hist_file.is_file():
                    self._send_json(404, {"ok": False, "error": "Chưa có lịch sử phiên bản"})
                    return
                versions = json.loads(hist_file.read_text(encoding="utf-8"))
                target_ver = next((v for v in versions if v.get("id") == ver_id or str(v.get("version")) == ver_id), None)
                if not target_ver:
                    self._send_json(404, {"ok": False, "error": f"Không tìm thấy phiên bản {ver_id}"})
                    return
                restored = str(target_ver.get("content") or "")
                target = (docs_dir / rel_path).resolve()
                prev_text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
                prev_set = set(prev_text.splitlines())
                next_set = set(restored.splitlines())
                added = sum(1 for l in restored.splitlines() if l not in prev_set)
                removed = sum(1 for l in prev_text.splitlines() if l not in next_set)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                next_ver = len(versions) + 1
                summary = f"Khôi phục về phiên bản {target_ver['id']} ({target_ver.get('author', '')})"
                new_ver = {
                    "id": f"v{next_ver}",
                    "version": next_ver,
                    "doc_path": rel_path,
                    "author": "local@studio.dev",
                    "author_name": "Local Disk Sync",
                    "timestamp": now_iso,
                    "action": "revert",
                    "reverted_from": target_ver["id"],
                    "summary": summary,
                    "added_lines": added,
                    "removed_lines": removed,
                    "content": restored,
                }
                versions.append(new_ver)
                hist_file.write_text(json.dumps(versions, indent=2, ensure_ascii=False), encoding="utf-8")
                audit_log = []
                if audit_file.is_file():
                    try:
                        audit_log = json.loads(audit_file.read_text(encoding="utf-8"))
                    except Exception:
                        audit_log = []
                audit_log.insert(0, {
                    "id": f"audit-{int(datetime.now().timestamp() * 1000)}",
                    "version_id": new_ver["id"],
                    "version": new_ver["version"],
                    "doc_path": rel_path,
                    "author": new_ver["author"],
                    "author_name": new_ver["author_name"],
                    "timestamp": now_iso,
                    "action": "revert",
                    "reverted_from": target_ver["id"],
                    "summary": summary,
                    "added_lines": added,
                    "removed_lines": removed,
                })
                audit_file.write_text(json.dumps(audit_log[:200], indent=2, ensure_ascii=False), encoding="utf-8")
                target.write_text(restored, encoding="utf-8")
                self._send_json(200, {"ok": True, "path": rel_path, "reverted_to": target_ver["id"], "content": restored, "version": new_ver, "versions": versions, "audit_log": audit_log})
                return
            self._send_json(404, {"ok": False, "error": "Not found"})

    server = ThreadingHTTPServer((host, port), StudioRequestHandler)
    print(f"[+] SRS WebView Studio dang chay tai: {base_url}/book")
    print(f"    Thu muc tai lieu: {docs_dir}")
    print("    Moi chinh sua WYSIWYG va Flow Canvas se luu truc tiep vao file .md tren o dia.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Da dung may chu SRS WebView Studio.")
    return 0


def upload_srs_batch(worker_url: str, payload_dict: dict) -> dict:
    url = f"{worker_url.rstrip('/')}/api/srs-book/batch"
    data = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Spec-CLI-Key": CLI_SHARED_KEY,
            "User-Agent": "Mozilla/5.0 srs-webview-studio/1.0",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_publish(args) -> int:
    docs_dir = resolve_docs_dir(args.docs_dir)
    if not docs_dir.is_dir():
        print(f"[ERROR] Khong tim thay thu muc tai lieu: {docs_dir}", file=sys.stderr)
        return 1

    cfg = load_project_config(docs_dir, args)
    worker_url = cfg["workerUrl"].rstrip("/")
    manifest, docs_map = collect_docs_bundle(docs_dir, cfg["title"])
    first_doc = next(iter(docs_map.keys()), "_index.md")

    studio_cfg = {
        "title": cfg["title"],
        "breadcrumbRoot": cfg.get("breadcrumbRoot") or cfg["title"],
        "allowedDomain": cfg.get("allowedDomain", "*"),
        "authRequired": cfg.get("authRequired", True),
        "apiBaseUrl": worker_url,
        "defaultDocPath": cfg.get("defaultDocPath") or first_doc,
        "defaultSectionIndex": cfg.get("defaultSectionIndex", 1),
    }
    html_content = render_studio_html(studio_cfg, worker_url=worker_url)

    print(f"[*] Dang xuat ban {len(docs_map)} trang Markdown tu {docs_dir} len {worker_url}...")
    upload_srs_batch(
        worker_url,
        {
            "html": html_content,
            "manifest": manifest,
            "docs": {},
        },
    )

    batches = []
    cur_batch = {}
    cur_bytes = 0
    for k, v in docs_map.items():
        v_bytes = len(v.encode("utf-8"))
        if cur_batch and (len(cur_batch) >= 20 or cur_bytes + v_bytes > 600_000):
            batches.append(cur_batch)
            cur_batch = {}
            cur_bytes = 0
        cur_batch[k] = v
        cur_bytes += v_bytes
    if cur_batch:
        batches.append(cur_batch)

    def send_chunk(chunk_dict: dict) -> int:
        for attempt in range(3):
            try:
                res = upload_srs_batch(worker_url, {"files": chunk_dict})
                return int(res.get("written", len(chunk_dict)))
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        return 0

    uploaded = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(send_chunk, b) for b in batches]
        for idx, fut in enumerate(as_completed(futures), 1):
            uploaded += fut.result()
            if idx % 10 == 0 or idx == len(batches):
                print(f"    -> Da tai len {uploaded}/{len(docs_map)} trang ({idx}/{len(batches)} lo)...")

    print(f"[+] Hoan tat xuat ban! Link WebView: {worker_url}/book")
    return 0


def cmd_pull(args) -> int:
    docs_dir = resolve_docs_dir(args.docs_dir)
    cfg = load_project_config(docs_dir, args)
    base_url = cfg["workerUrl"].rstrip("/")

    req = urllib.request.Request(
        f"{base_url}/api/srs-book/manifest",
        headers={
            "Accept": "application/json",
            "X-Spec-CLI-Key": CLI_SHARED_KEY,
            "User-Agent": "Mozilla/5.0 srs-webview-studio/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    edited_paths = data.get("edited_paths", []) or []
    pulled_count = 0
    for rel_path in edited_paths:
        q = urllib.parse.urlencode({"path": rel_path})
        doc_req = urllib.request.Request(
            f"{base_url}/api/srs-book/doc?{q}",
            headers={
                "Accept": "application/json",
                "X-Spec-CLI-Key": CLI_SHARED_KEY,
                "User-Agent": "Mozilla/5.0 srs-webview-studio/1.0",
            },
            method="GET",
        )
        with urllib.request.urlopen(doc_req, timeout=20) as dresp:
            djson = json.loads(dresp.read().decode("utf-8"))
            content = djson.get("content")
            if content is not None:
                target_file = (docs_dir / rel_path).resolve()
                if str(target_file).startswith(str(docs_dir)):
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(content, encoding="utf-8")
                    pulled_count += 1

    print(f"[+] Da keo {pulled_count} trang da chinh sua ve {docs_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="srs-studio",
        description="SRS Markdown-to-WebView Studio CLI & Builder cho moi du an.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Khoi tao srs-studio.config.json va SUMMARY.md cho du an")
    p_init.add_argument("docs_dir", nargs="?", default=".", help="Duong dan thu muc docs hoac repo")
    p_init.add_argument("--title", default=None, help="Tieu de hien thi tren WebView")
    p_init.add_argument("--domain", default="*", help="Ten mien Google OAuth cho phep (hoac * de mo)")

    p_serve = sub.add_parser("serve", help="Chay may chu WebView local va luu truc tiep vao file .md")
    p_serve.add_argument("docs_dir", nargs="?", default=".", help="Duong dan thu muc docs hoac repo")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host lang nghe")
    p_serve.add_argument("--port", type=int, default=4321, help="Cong HTTP local (mac dinh: 4321)")
    p_serve.add_argument("--title", default=None, help="Tieu de hien thi tren WebView")

    p_build = sub.add_parser("build", help="Dong goi thanh bundle HTML tinh doc lap (dist/index.html)")
    p_build.add_argument("docs_dir", nargs="?", default=".", help="Duong dan thu muc docs hoac repo")
    p_build.add_argument("-o", "--out-dir", default="./dist-srs-webview", help="Thu muc xuat ban tinh")
    p_build.add_argument("--title", default=None, help="Tieu de hien thi tren WebView")

    p_pub = sub.add_parser("publish", help="Xuat ban thu muc Markdown len Cloudflare Worker/R2")
    p_pub.add_argument("docs_dir", nargs="?", default=".", help="Duong dan thu muc docs hoac repo")
    p_pub.add_argument("--worker-url", default=None, help="URL cua Cloudflare Worker")
    p_pub.add_argument("--title", default=None, help="Tieu de hien thi tren WebView")
    p_pub.add_argument("--domain", default=None, help="Ten mien Google OAuth")
    p_pub.add_argument("--no-auth", action="store_true", help="Tat cong dang nhap Google OAuth")

    p_pull = sub.add_parser("pull", help="Keo cac file Markdown da sua tren WebView Cloud ve may")
    p_pull.add_argument("docs_dir", nargs="?", default=".", help="Duong dan thu muc docs hoac repo")
    p_pull.add_argument("--worker-url", default=None, help="URL cua Cloudflare Worker")

    args = parser.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "serve":
        return cmd_serve(args)
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "publish":
        return cmd_publish(args)
    if args.cmd == "pull":
        return cmd_pull(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
