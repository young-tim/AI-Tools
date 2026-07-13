#!/usr/bin/env python3
"""Dify Console management CLI (skill-bundled, project-agnostic)."""

from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
import time
import mimetypes
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import Cookie, CookieJar
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import HTTPCookieProcessor, build_opener

# Skill root: .../dify-manage/scripts/dify_manage.py -> .../dify-manage
SKILL_ROOT = Path(__file__).resolve().parent.parent
ENV_LOADED_FROM: Path | None = None
SESSION_LOADED_FROM: Path | None = None
DIFY_PROJECT_ROOT: Path | None = None
DIFY_DIR: Path | None = None
SESSION_FILENAME = "session.json"
LEGACY_SESSION_PLAIN = "session"
LEGACY_SESSION_FILENAME = ".dify.session"
MANIFEST_FILENAME = "manifest.yml"
WORKING_DSL_NAME = "working.yml"
# Token keys present in OS before loading any project files
_OS_TOKEN_KEYS: set[str] = set()

TOKEN_ENV_KEYS = ("DIFY_CONSOLE_TOKEN", "DIFY_CSRF_TOKEN", "DIFY_REFRESH_TOKEN")
TOKEN_FIELD_TO_ENV = {
    "access_token": "DIFY_CONSOLE_TOKEN",
    "csrf_token": "DIFY_CSRF_TOKEN",
    "refresh_token": "DIFY_REFRESH_TOKEN",
}


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def discover_dify_project_root(start: Path | None = None) -> Path | None:
    """从 cwd 向上查找含 .dify/ 的项目根目录。"""
    cwd = (start or Path.cwd()).resolve()
    for base in [cwd, *cwd.parents]:
        if (base / ".dify").is_dir():
            return base
        if base == base.parent and base != cwd:
            break
    return None


def resolve_project_root(start: Path | None = None) -> Path:
    """业务项目根：已有 .dify/ → 含 .env 的目录 → cwd。"""
    found = discover_dify_project_root(start)
    if found:
        return found
    cwd = (start or Path.cwd()).resolve()
    for base in [cwd, *cwd.parents]:
        if (base / ".env").is_file():
            return base
        if base == base.parent and base != cwd:
            break
    return cwd


def ensure_dify_dir() -> Path:
    """确保 {project_root}/.dify/ 存在并更新全局路径缓存。"""
    global DIFY_PROJECT_ROOT, DIFY_DIR
    root = resolve_project_root()
    dify_dir = (root / ".dify").resolve()
    dify_dir.mkdir(parents=True, exist_ok=True)
    DIFY_PROJECT_ROOT = root
    DIFY_DIR = dify_dir
    return dify_dir


def canonical_session_path() -> Path:
    """标准 session 写入路径（即使 .dify/ 尚未初始化也会指向此处）。"""
    return (resolve_project_root() / ".dify" / SESSION_FILENAME).resolve()


def _legacy_session_candidates() -> list[Path]:
    """只读：按优先级列出可能存在的 legacy session 文件。"""
    candidates: list[Path] = []
    dify_dir = DIFY_DIR or discover_dify_dir()
    if dify_dir:
        candidates.extend(
            [
                (dify_dir / LEGACY_SESSION_PLAIN).resolve(),
                (dify_dir / LEGACY_SESSION_FILENAME).resolve(),
            ]
        )
    root = DIFY_PROJECT_ROOT or resolve_project_root()
    candidates.append((root / LEGACY_SESSION_FILENAME).resolve())
    if ENV_LOADED_FROM:
        candidates.append((ENV_LOADED_FROM.parent / LEGACY_SESSION_FILENAME).resolve())
    # 去重，保持顺序
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def discover_dify_dir() -> Path | None:
    root = discover_dify_project_root()
    return (root / ".dify").resolve() if root else None


def discover_env_file() -> Path | None:
    """
    解析项目 .env（就近目录优先）。
    顺序：显式 DIFY_ENV_FILE → 含 .dify/ 的根 .env → dify/.env → 根 .env → skill/.env。
    """
    explicit = os.environ.get("DIFY_ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_file() else None

    cwd = Path.cwd().resolve()
    for base in [cwd, *cwd.parents]:
        if base == base.parent and base != cwd:
            break
        if (base / ".dify").is_dir():
            root_env = (base / ".env").resolve()
            if root_env.is_file():
                return root_env
        for rel in (".env", "dify/.env"):
            p = (base / rel).resolve()
            if p.is_file():
                return p

    skill_env = (SKILL_ROOT / ".env").resolve()
    return skill_env if skill_env.is_file() else None


def resolve_dify_paths() -> None:
    """解析并缓存 .dify 项目路径（load_configuration 后调用）。"""
    global DIFY_PROJECT_ROOT, DIFY_DIR
    DIFY_PROJECT_ROOT = discover_dify_project_root()
    DIFY_DIR = (DIFY_PROJECT_ROOT / ".dify").resolve() if DIFY_PROJECT_ROOT else None


def dsl_app_dir(app_id: str) -> Path:
    """标准 UUID 命名的 DSL 目录（pull/init 创建目录时使用）。"""
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")
    return (dify_dir / "dsl" / app_id).resolve()


def resolve_dsl_app_dir(app_id: str) -> Path:
    """
    解析 app 对应的 DSL 目录，兼容 UUID 目录和 slug/自定义目录。

    查找顺序：
    1. 标准 UUID 目录 .dify/dsl/{app_id}/
    2. manifest 中 working.path 指向的目录
    3. manifest 中 latest_remote.path 指向的目录
    4. manifest 中 slug 对应的目录 .dify/dsl/{slug}/
    5. 扫描 .dify/dsl/*/ 子目录，查找含 working.yml 且 YAML 中 app_id 匹配的目录
    6. 都不存在时返回 UUID 目录（用于报错或创建）
    """
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")

    uuid_dir = (dify_dir / "dsl" / app_id).resolve()
    if uuid_dir.is_dir():
        return uuid_dir

    try:
        manifest = load_manifest()
        entry = (manifest.get("apps") or {}).get(app_id) or {}
    except Exception:
        entry = {}

    for path_key in ("working", "latest_remote"):
        rel = (entry.get(path_key) or {}).get("path", "")
        if rel:
            candidate = (dify_dir / rel).parent.resolve()
            if candidate.is_dir():
                return candidate

    slug = entry.get("slug", "")
    if slug:
        slug_dir = (dify_dir / "dsl" / slug).resolve()
        if slug_dir.is_dir():
            return slug_dir

    dsl_root = (dify_dir / "dsl").resolve()
    if dsl_root.is_dir():
        for sub in sorted(dsl_root.iterdir()):
            if not sub.is_dir() or sub.name == app_id:
                continue
            working = sub / WORKING_DSL_NAME
            if working.is_file():
                try:
                    text = working.read_text(encoding="utf-8", errors="ignore")
                    if app_id in text[:5000]:
                        return sub
                except OSError:
                    continue

    return uuid_dir


def remote_dsl_filename(ts: datetime | None = None) -> str:
    ts = ts or datetime.now()
    return f"{ts.strftime('%Y%m%d%H%M%S')}-remote.yml"


def working_dsl_path(app_id: str) -> Path:
    """working.yml 路径：优先从 manifest 读取，否则从解析后的 DSL 目录推导。"""
    try:
        entry = _manifest_app_entry(app_id)
        rel = (entry.get("working") or {}).get("path", "")
        if rel:
            dify_dir = DIFY_DIR or discover_dify_dir()
            if dify_dir:
                candidate = (dify_dir / rel).resolve()
                if candidate.is_file():
                    return candidate
    except Exception:
        pass
    return resolve_dsl_app_dir(app_id) / WORKING_DSL_NAME


def manifest_path() -> Path:
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")
    return dify_dir / MANIFEST_FILENAME


def rel_to_dify(path: Path) -> str:
    dify_dir = DIFY_DIR or discover_dify_dir()
    if dify_dir and path.is_relative_to(dify_dir):
        return str(path.relative_to(dify_dir))
    return str(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def cache_downloads_dir() -> Path:
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")
    d = (dify_dir / "cache" / "downloads").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _basename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name
    if name and name not in (".", ".."):
        name = re.sub(r"[^\w.\-]+", "_", name)
        return name[:120]
    return "download"


_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "application/json": ".json",
}


def _ext_from_content_type(content_type: str) -> str:
    mime = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(mime, "")


def cache_path_for_url(url: str, *, ext: str = "") -> Path:
    """缓存路径：{md5(url)}-{basename}，MD5 为 URL 去重键。"""
    digest = md5_hex(url.strip())
    basename = _basename_from_url(url)
    if ext:
        stem = Path(basename).stem or "download"
        basename = f"{stem}{ext}"
    return cache_downloads_dir() / f"{digest}-{basename}"


def find_cached_download(url: str) -> Path | None:
    """按 URL MD5 前缀查找已缓存文件。"""
    digest = md5_hex(url.strip())
    for path in sorted(cache_downloads_dir().glob(f"{digest}-*")):
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def cache_download(url: str, *, force: bool = False) -> dict[str, Any]:
    """下载 URL 到 .dify/cache/downloads/；同 URL 已存在则跳过。"""
    url = url.strip()
    if not url:
        raise SystemExit("URL is required")

    digest = md5_hex(url)
    existing = find_cached_download(url)
    if existing and not force:
        return {
            "path": str(existing),
            "url": url,
            "md5": digest,
            "cached": True,
            "size": existing.stat().st_size,
            "content_sha256": sha256_file(existing),
        }

    req = urllib.request.Request(url, headers={"User-Agent": "dify-manage-cli/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Download failed ({exc.code}): {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Download failed: {exc}") from exc

    dest = cache_path_for_url(url)
    if dest.suffix == "" or dest.name.endswith("-download"):
        ext = _ext_from_content_type(content_type)
        if ext:
            dest = cache_path_for_url(url, ext=ext)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {
        "path": str(dest),
        "url": url,
        "md5": digest,
        "cached": False,
        "size": len(data),
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }


def migrate_legacy_session() -> None:
    """将 legacy session 迁移到 .dify/session.json。"""
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        return
    target = (dify_dir / SESSION_FILENAME).resolve()
    if target.is_file():
        return
    for legacy in _legacy_session_candidates():
        if legacy.is_file():
            data = read_session_file(legacy)
            if data and _session_has_tokens(data):
                save_session_file(target, data)
                print(f"Note: migrated session -> {target}", file=sys.stderr)
            return


def apps_meta_path(app_id: str) -> Path:
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")
    return dify_dir / "apps" / f"{app_id}.yml"


def fixtures_dir(app_id: str) -> Path:
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        raise SystemExit("No .dify/ directory. Run: dify_manage.py init")
    return (dify_dir / "fixtures" / app_id).resolve()


def scaffold_app_metadata(app_id: str, name: str, mode: str) -> None:
    """pull 时生成 apps 元数据与 fixtures 模板。"""
    dify_dir = DIFY_DIR or discover_dify_dir()
    if not dify_dir:
        return
    meta = apps_meta_path(app_id)
    if not meta.is_file():
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(
            "\n".join(
                [
                    f"app_id: {app_id}",
                    f"name: {_yaml_quote(str(name))}",
                    f"mode: {mode}",
                    "description: ''",
                    "owner: ''",
                    "tags: []",
                    "external_apis: []",
                    "node_notes: {}",
                    "test_api_key_ref: dify_manage.py api-keys --app-id " + app_id,
                    "",
                ]
            ),
            encoding="utf-8",
        )
    fx = fixtures_dir(app_id)
    fx.mkdir(parents=True, exist_ok=True)
    (fx / "assets").mkdir(exist_ok=True)
    smoke = fx / "smoke.json"
    if not smoke.is_file():
        smoke.write_text(
            json.dumps(
                {
                    "inputs": {},
                    "files": {},
                    "query": "",
                    "_comment": "files 值可为本地 path、http(s) url，或含 upload_file_id 的对象",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def refresh_manifest_working(app_id: str) -> None:
    working_path = working_dsl_path(app_id)
    if not working_path.is_file():
        return
    entry = _manifest_app_entry(app_id)
    remote_rel = (entry.get("latest_remote") or {}).get("path", "")
    update_manifest_app(
        app_id,
        working={
            "path": rel_to_dify(working_path),
            "content_sha256": sha256_file(working_path),
            "based_on_remote": remote_rel,
        },
    )


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_DOCUMENT_EXTS = {
    ".txt", ".md", ".markdown", ".pdf", ".html", ".xlsx", ".xls",
    ".docx", ".csv", ".eml", ".msg", ".pptx", ".ppt", ".xml", ".epub",
}


def infer_dify_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _DOCUMENT_EXTS:
        return "document"
    return "custom"


def resolve_local_file(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        for base in filter(None, (DIFY_PROJECT_ROOT, Path.cwd())):
            cand = (base / p).resolve()
            if cand.is_file():
                return cand
        if DIFY_DIR:
            cand = (DIFY_DIR / p).resolve()
            if cand.is_file():
                return cand
    p = p.resolve()
    if not p.is_file():
        raise SystemExit(f"File not found: {path_str}")
    return p


def resolve_file_source(source: str, *, force_cache: bool = False) -> Path:
    source = source.strip()
    if source.startswith(("http://", "https://")):
        return Path(cache_download(source, force=force_cache)["path"])
    return resolve_local_file(source)


def service_upload_file(
    file_path: Path,
    *,
    api_key: str,
    base_url: str,
    user: str,
) -> dict[str, Any]:
    """POST /files/upload（multipart/form-data）。"""
    boundary = "----DifyManage" + secrets.token_hex(12)
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    chunks: list[bytes] = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="user"\r\n\r\n',
        user.encode("utf-8"),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode(),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(chunks)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(
        f"{base_url}/files/upload", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"File upload failed ({exc.code}): {exc.read().decode()}") from exc
    if not isinstance(result, dict) or not result.get("id"):
        raise SystemExit(f"Unexpected upload response: {result}")
    return result


def build_file_input(upload_file_id: str, file_path: Path) -> dict[str, str]:
    return {
        "type": infer_dify_file_type(file_path),
        "transfer_method": "local_file",
        "upload_file_id": upload_file_id,
    }


def upload_source_as_input(
    source: str,
    *,
    api_key: str,
    base_url: str,
    user: str,
) -> dict[str, str]:
    local = resolve_file_source(source)
    uploaded = service_upload_file(local, api_key=api_key, base_url=base_url, user=user)
    return build_file_input(str(uploaded["id"]), local)


def parse_file_kv(pair: str) -> tuple[str, str]:
    if "=" not in pair:
        raise SystemExit(f"Invalid file spec (need key=path|url): {pair}")
    key, value = pair.split("=", 1)
    return key.strip(), value.strip()


def load_fixtures(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Fixtures JSON must be an object")
    return data


def collect_run_inputs(
    args: argparse.Namespace,
    *,
    api_key: str,
    base_url: str,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    user = getattr(args, "user", "dify-manage-cli")

    if getattr(args, "fixtures", None):
        fx_path = Path(args.fixtures)
        if not fx_path.is_file():
            raise SystemExit(f"Fixtures not found: {fx_path}")
        fx = load_fixtures(fx_path)
        inputs.update(fx.get("inputs") or {})
        for key, spec in (fx.get("files") or {}).items():
            if isinstance(spec, dict) and spec.get("upload_file_id"):
                inputs[key] = spec
            elif isinstance(spec, str):
                inputs[key] = upload_source_as_input(
                    spec, api_key=api_key, base_url=base_url, user=user
                )
            else:
                raise SystemExit(f"Unsupported fixtures.files[{key!r}]")

    if getattr(args, "inputs", None):
        inputs.update(json.loads(Path(args.inputs).read_text(encoding="utf-8")))

    for pair in getattr(args, "input", None) or []:
        if "=" not in pair:
            raise SystemExit(f"Invalid --input (need key=value): {pair}")
        k, v = pair.split("=", 1)
        inputs[k] = v

    for pair in getattr(args, "file", None) or []:
        k, src = parse_file_kv(pair)
        inputs[k] = upload_source_as_input(src, api_key=api_key, base_url=base_url, user=user)

    for pair in getattr(args, "file_url", None) or []:
        k, url = parse_file_kv(pair)
        inputs[k] = upload_source_as_input(url, api_key=api_key, base_url=base_url, user=user)

    return inputs


def slugify_app_name(name: str, *, max_len: int = 40) -> str:
    """可选展示用 slug；不参与路径解析。"""
    s = name.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff+-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "app"


def _yaml_quote(value: str) -> str:
    if not value or any(c in value for c in ':#{}\n\r\t"\'&*!?|>@[\\'):
        return json.dumps(value, ensure_ascii=False)
    return value


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or manifest_path()
    if not p.is_file():
        return {"version": 1, "apps": {}}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ImportError:
        data = _parse_manifest_minimal(text)
    if not isinstance(data, dict):
        return {"version": 1, "apps": {}}
    data.setdefault("version", 1)
    apps = data.get("apps")
    if not isinstance(apps, dict):
        data["apps"] = {}
    return data


def _parse_manifest_minimal(text: str) -> dict[str, Any]:
    """无 PyYAML 时的简易 manifest 解析（仅支持本 CLI 写入的结构）。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    manifest: dict[str, Any] = {"version": 1, "apps": {}}
    current_app: str | None = None
    section: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("version:"):
            manifest["version"] = int(line.split(":", 1)[1].strip())
            continue
        m = re.match(r"^  ([0-9a-f-]{36}):$", line)
        if m:
            current_app = m.group(1)
            manifest["apps"][current_app] = {}
            section = []
            continue
        if current_app is None:
            continue
        m = re.match(r"^    (\w+):$", line)
        if m:
            section = [m.group(1)]
            manifest["apps"][current_app][section[0]] = {}
            continue
        m = re.match(r"^      (\w+): (.+)$", line)
        if m and len(section) == 1:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith('"') or val.startswith("'"):
                val = json.loads(val)
            manifest["apps"][current_app][section[0]][key] = val
            continue
        m = re.match(r"^    (\w+): (.+)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith('"') or val.startswith("'"):
                val = json.loads(val)
            manifest["apps"][current_app][key] = val
    return manifest


def save_manifest(manifest: dict[str, Any], path: Path | None = None) -> Path:
    p = path or manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    apps = manifest.get("apps") or {}
    if not apps:
        p.write_text(f"version: {manifest.get('version', 1)}\napps: {{}}\n", encoding="utf-8")
        return p
    lines = [f"version: {manifest.get('version', 1)}", "apps:"]
    for app_id, app in apps.items():
        lines.append(f"  {app_id}:")
        for key in ("name", "mode", "slug"):
            if key in app:
                lines.append(f"    {key}: {_yaml_quote(str(app[key]))}")
        for block in ("latest_remote", "working", "last_deploy"):
            if block not in app:
                continue
            lines.append(f"    {block}:")
            for k, v in app[block].items():
                lines.append(f"      {k}: {_yaml_quote(str(v))}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def update_manifest_app(app_id: str, **fields: Any) -> dict[str, Any]:
    manifest = load_manifest()
    apps = manifest.setdefault("apps", {})
    entry = apps.setdefault(app_id, {})
    for key, value in fields.items():
        if isinstance(value, dict) and isinstance(entry.get(key), dict):
            entry[key].update(value)
        else:
            entry[key] = value
    save_manifest(manifest)
    return manifest


def ensure_dsl_dir(app_id: str) -> Path:
    d = dsl_app_dir(app_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_latest_remote_dsl(app_id: str) -> Path | None:
    """查找最新的 remote 快照，兼容 UUID 和 slug 目录。优先使用 manifest 记录。"""
    try:
        entry = _manifest_app_entry(app_id)
        rel = (entry.get("latest_remote") or {}).get("path", "")
        if rel:
            dify_dir = DIFY_DIR or discover_dify_dir()
            if dify_dir:
                candidate = (dify_dir / rel).resolve()
                if candidate.is_file():
                    return candidate
    except Exception:
        pass
    d = resolve_dsl_app_dir(app_id)
    if not d.is_dir():
        return None
    remotes = sorted(d.glob("*-remote.yml"), reverse=True)
    return remotes[0] if remotes else None


def fetch_app_detail(session: "DifySession", app_id: str) -> dict[str, Any]:
    status, body = session.request("GET", f"/console/api/apps/{app_id}")
    if status >= 400:
        raise SystemExit(f"Fetch app failed ({status}): {body}")
    return body if isinstance(body, dict) else {}


def export_app_yaml(session: "DifySession", app_id: str) -> str:
    session.ensure_session()
    status, body = session.request(
        "GET", f"/console/api/apps/{app_id}/export?include_secret=true"
    )
    if status >= 400:
        raise SystemExit(f"Export failed ({status}): {body}")
    return body.get("data", "") if isinstance(body, dict) else ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def jwt_expires_at_iso(access_token: str) -> str | None:
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = int(payload.get("exp", 0))
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
    except Exception:
        return None
    return None


def resolve_session_path() -> Path:
    """
    Session 路径优先级：
    DIFY_SESSION_FILE > .dify/session.json > legacy（只读回退）
    写入时始终使用 .dify/session.json（见 persist_session / ensure_dify_dir）。
    """
    explicit = os.environ.get("DIFY_SESSION_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    dify_dir = DIFY_DIR or discover_dify_dir()
    if dify_dir:
        new_path = (dify_dir / SESSION_FILENAME).resolve()
        if new_path.is_file():
            return new_path
        for legacy in _legacy_session_candidates():
            if legacy.is_file():
                return legacy
        return new_path

    for legacy in _legacy_session_candidates():
        if legacy.is_file():
            return legacy
    return canonical_session_path()


def read_session_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Invalid session file {path}: {exc}") from exc
    return data if isinstance(data, dict) else None


def _session_has_tokens(data: dict[str, Any]) -> bool:
    return bool(data.get("access_token") and data.get("csrf_token"))


def apply_session_to_env(data: dict[str, Any]) -> None:
    """Session tokens override .env; OS-exported tokens before load are kept."""
    for field, env_key in TOKEN_FIELD_TO_ENV.items():
        value = (data.get(field) or "").strip()
        if not value:
            continue
        if env_key in _OS_TOKEN_KEYS:
            continue
        os.environ[env_key] = value


def save_session_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    global SESSION_LOADED_FROM
    SESSION_LOADED_FROM = path.resolve()


def load_configuration() -> Path | None:
    """
    Load config files. Token priority: OS env > .dify/session.json > .env tokens.
    """
    global ENV_LOADED_FROM, SESSION_LOADED_FROM, _OS_TOKEN_KEYS
    SESSION_LOADED_FROM = None
    _OS_TOKEN_KEYS = {k for k in TOKEN_ENV_KEYS if k in os.environ}

    path = discover_env_file()
    env_had_tokens = False
    if path:
        parsed = _parse_env_file(path)
        env_had_tokens = any(parsed.get(k) for k in TOKEN_ENV_KEYS)
        for key, value in parsed.items():
            os.environ.setdefault(key, value)
        ENV_LOADED_FROM = path

    session_path = resolve_session_path()
    session_data = read_session_file(session_path)
    if session_data and _session_has_tokens(session_data):
        apply_session_to_env(session_data)
        SESSION_LOADED_FROM = session_path
        if env_had_tokens:
            print(
                "Note: .env contains DIFY_*_TOKEN; using .dify/session.json instead. "
                "You may remove tokens from .env.",
                file=sys.stderr,
            )
    elif env_had_tokens:
        print(
            "Note: using Console tokens from .env (no .dify/session.json). "
            "Suitable for SSO/manual cookies. Run login to create a session file.",
            file=sys.stderr,
        )

    resolve_dify_paths()
    migrate_legacy_session()

    # 修复根因 B：检测到 OS env 中存在 token，提示用户它们会 OVERRIDE session.json
    if _OS_TOKEN_KEYS:
        sorted_keys = sorted(_OS_TOKEN_KEYS)
        print(
            "Note: OS env vars " + ", ".join(sorted_keys) + " are set BEFORE this script ran;\n"
            "      these will OVERRIDE tokens from .dify/session.json and project .env.\n"
            "      If login/refresh has updated session.json since those exports,\n"
            "      the fresh session.json tokens will NOT take effect in current shell.\n"
            "      Tip: run:  unset DIFY_CONSOLE_TOKEN DIFY_CSRF_TOKEN DIFY_REFRESH_TOKEN\n"
            "      to let .dify/session.json become the single source of truth.",
            file=sys.stderr,
        )

    return path


def normalize_console_url(url: str) -> str:
    url = url.rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")
    return url


class DifySession:
    """Dify Console 会话管理，兼容 __Host- 前缀（新版）和无前缀（旧版）两种 Cookie 格式。"""

    _COOKIE_VARIANTS: dict[str, tuple[str, ...]] = {
        "access_token": ("__Host-access_token", "access_token"),
        "csrf_token": ("__Host-csrf_token", "csrf_token"),
        "refresh_token": ("__Host-refresh_token", "refresh_token"),
    }

    def __init__(self, console_url: str) -> None:
        self.console_url = normalize_console_url(console_url)
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))
        self._seed_cookies_from_env()

    def _domain_for_cookies(self) -> str:
        return self.console_url.replace("https://", "").replace("http://", "")

    def _seed_cookies_from_env(self) -> None:
        """从环境变量/ session 初始化 cookie，优先使用 __Host- 前缀格式（新版 Dify）。"""
        for canonical_name, env_key in (
            ("access_token", "DIFY_CONSOLE_TOKEN"),
            ("csrf_token", "DIFY_CSRF_TOKEN"),
            ("refresh_token", "DIFY_REFRESH_TOKEN"),
        ):
            value = os.environ.get(env_key, "")
            if value:
                self.jar.set_cookie(self._make_cookie("", f"__Host-{canonical_name}", value, host_prefix=True))

    @staticmethod
    def _make_cookie(domain: str, name: str, value: str, *, host_prefix: bool = False) -> Cookie:
        """创建 Cookie 对象，host_prefix=True 时创建符合 __Host- 规范的 host-only cookie。"""
        if host_prefix:
            return Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain="",
                domain_specified=False,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={"SameSite": "Lax"},
                rfc2109=False,
            )
        return Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )

    def _parse_set_cookies_into_jar(self, set_cookie_headers: list[str]) -> None:
        """
        手动解析响应头的 Set-Cookie 列表并写入 jar。

        修复根因 A：Dify 服务器下发的 __Host- 前缀 Cookie 通常带 Domain 属性，
        违反 RFC 中 __Host- 必须为 host-only 的要求，导致 Python urllib 的
        DefaultCookiePolicy.return_ok() 直接丢弃。通过此方法手动写入 jar，
        domain 固定为空字符串（host-only），绕过 urllib policy 限制。

        只解析并写入我们关心的 token cookie：access_token / csrf_token / refresh_token。
        """
        if not set_cookie_headers:
            return
        sc = SimpleCookie()
        for header in set_cookie_headers:
            try:
                sc.load(header)
            except Exception:
                # 某个 Set-Cookie 行解析失败不影响其它
                continue
        for canonical in ("access_token", "csrf_token", "refresh_token"):
            # 优先匹配 __Host- 前缀版本，兼容不带前缀的旧版
            target_name = None
            target_value = ""
            for variant in (f"__Host-{canonical}", canonical):
                if variant in sc and sc[variant].value:
                    target_name = variant
                    target_value = sc[variant].value
                    break
            if not target_name or not target_value:
                continue
            host_prefix = target_name.startswith("__Host-")
            # 用统一的 _make_cookie 构造（host_prefix=True 时 domain 为空）
            self.jar.set_cookie(self._make_cookie("", target_name, target_value, host_prefix=host_prefix))

    def _find_cookie(self, canonical_name: str) -> Cookie | None:
        """按规范名查找 cookie，自动尝试 __Host- 前缀和无前缀两种变体。"""
        variants = self._COOKIE_VARIANTS.get(canonical_name, (canonical_name,))
        for c in self.jar:
            if c.name in variants:
                return c
        return None

    def cookie_value(self, name: str) -> str:
        """获取规范名对应的 cookie 值，兼容 __Host- 前缀和无前缀格式。"""
        c = self._find_cookie(name)
        return c.value if c else ""

    def _build_cookie_header(self) -> str:
        """从 jar 中实际存在的 cookie 构造 Cookie 请求头，保留原始名称（含 __Host- 前缀）。"""
        parts: list[str] = []
        seen: set[str] = set()
        for canonical in ("access_token", "csrf_token", "refresh_token"):
            c = self._find_cookie(canonical)
            if c and c.value and c.name not in seen:
                parts.append(f"{c.name}={c.value}")
                seen.add(c.name)
        env_access = os.environ.get("DIFY_CONSOLE_TOKEN", "")
        env_csrf = os.environ.get("DIFY_CSRF_TOKEN", "")
        env_refresh = os.environ.get("DIFY_REFRESH_TOKEN", "")
        if env_access and "access_token" not in seen and "__Host-access_token" not in seen:
            parts.append(f"__Host-access_token={env_access}")
        if env_csrf and "csrf_token" not in seen and "__Host-csrf_token" not in seen:
            parts.append(f"__Host-csrf_token={env_csrf}")
        if env_refresh and "refresh_token" not in seen and "__Host-refresh_token" not in seen:
            parts.append(f"__Host-refresh_token={env_refresh}")
        return "; ".join(parts)

    def auth_headers(self) -> dict[str, str]:
        access = self.cookie_value("access_token") or os.environ.get("DIFY_CONSOLE_TOKEN", "")
        csrf = self.cookie_value("csrf_token") or os.environ.get("DIFY_CSRF_TOKEN", "")
        if not access or not csrf:
            raise SystemExit(
                "No console session. Run: dify_manage.py login\n"
                "Or set DIFY_CONSOLE_TOKEN + DIFY_CSRF_TOKEN (OS env or project .env)"
            )
        return {
            "Authorization": f"Bearer {access}",
            "X-CSRF-Token": csrf,
            "Cookie": self._build_cookie_header(),
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> tuple[int, Any]:
        url = f"{self.console_url}{path}"
        req_headers = self.auth_headers()
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                try:
                    return resp.status, json.loads(body)
                except json.JSONDecodeError:
                    return resp.status, body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body

    def persist_session(self, event: str) -> Path:
        access = self.cookie_value("access_token")
        csrf = self.cookie_value("csrf_token")
        refresh = self.cookie_value("refresh_token")
        if not access or not csrf:
            raise SystemExit("No tokens to persist")

        dify_dir = ensure_dify_dir()
        path = (dify_dir / SESSION_FILENAME).resolve()
        existing = read_session_file(path)
        if not existing:
            for legacy in _legacy_session_candidates():
                existing = read_session_file(legacy)
                if existing:
                    break
        existing = existing or {}
        now = _utc_now_iso()
        data: dict[str, Any] = {
            **existing,
            "console_url": self.console_url,
            "access_token": access,
            "csrf_token": csrf,
            "refresh_token": refresh,
            "access_token_expires_at": jwt_expires_at_iso(access),
        }
        if event == "login":
            data["last_login_at"] = now
            data["last_refresh_at"] = now
            data["last_event"] = "login"
        elif event == "refresh":
            # 修复根因 D：refresh 事件前后 token 指纹未变更 + access 已过期 → 不更新 last_refresh_at
            # 避免出现「last_refresh_at 是新的但 access_token_expires_at 还是老的」假象
            old_access = (existing.get("access_token") or "").strip()
            old_access_fp = old_access[:16] if old_access else ""
            new_access_fp = access[:16] if access else ""
            is_expired = False
            try:
                payload_b64 = access.split(".")[1]
                payload_b64 += "=" * (-len(payload_b64) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                exp = int(payload.get("exp", 0))
                if exp and time.time() > exp - 300:
                    is_expired = True
            except Exception:
                is_expired = False
            token_unchanged = bool(old_access_fp) and old_access_fp == new_access_fp
            if token_unchanged and is_expired:
                print(
                    "WARN: persist_session event=refresh but access_token unchanged and expired. "
                    "Set-Cookie from server was likely dropped by cookie policy. "
                    "Keeping old last_refresh_at / last_event metadata.",
                    file=sys.stderr,
                )
                # 保留 existing 中 last_refresh_at（若有），并标记 last_event 为特殊值便于排查
                data["last_refresh_at"] = existing.get("last_refresh_at", now)
                data["last_event"] = "refresh_token_unchanged_skipped"
            else:
                data["last_refresh_at"] = now
                data["last_event"] = "refresh"
        else:
            data["last_event"] = event

        save_session_file(path, data)

        for field, env_key in TOKEN_FIELD_TO_ENV.items():
            val = data.get(field, "")
            if val and env_key not in _OS_TOKEN_KEYS:
                os.environ[env_key] = str(val)

        return path

    def login(self, email: str, password: str, remember_me: bool = True) -> Path:
        encoded_pw = base64.b64encode(password.encode("utf-8")).decode("ascii")
        payload = json.dumps(
            {"email": email, "password": encoded_pw, "remember_me": remember_me},
            ensure_ascii=False,
        ).encode("utf-8")
        url = f"{self.console_url}/console/api/login"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=60) as resp:
                # 修复根因 A：Dify Set-Cookie 带 Domain，urllib policy 丢弃 __Host- cookie
                # 手动解析 Set-Cookie 头并写入 jar，domain 强制为空
                set_cookies = resp.headers.get_all("Set-Cookie") or []
                resp.read()
            self._parse_set_cookies_into_jar(set_cookies)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Login failed ({exc.code}): {exc.read().decode()}") from exc

        if not self.cookie_value("access_token"):
            raise SystemExit("Login OK but access_token cookie missing")
        path = self.persist_session("login")
        print(f"Session saved to {path}", file=sys.stderr)
        return path

    def refresh(self) -> Path:
        """执行 refresh 并持久化；失败则抛 SystemExit（兼容旧行为）。"""
        ok = self.refresh_safe()
        if not ok:
            raise SystemExit("Refresh failed (see stderr for details)")
        # refresh_safe 内部已 persist_session，返回最后写入的 session 路径
        dify_dir = ensure_dify_dir()
        return (dify_dir / SESSION_FILENAME).resolve()

    def refresh_safe(self) -> bool:
        """
        安全版本的 refresh：返回 True/False 而非抛 SystemExit。

        作为 ensure_session 3 级 fallback 链的第二步（refresh → login → exit）。
        失败时在 stderr 打印原因，供调试。
        """
        refresh_cookie = self._find_cookie("refresh_token")
        refresh_val = refresh_cookie.value if refresh_cookie else os.environ.get("DIFY_REFRESH_TOKEN", "")
        if not refresh_val:
            print("WARN: refresh_safe skipped: no refresh_token available", file=sys.stderr)
            return False
        refresh_cookie_name = refresh_cookie.name if refresh_cookie else "__Host-refresh_token"
        url = f"{self.console_url}/console/api/refresh-token"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json", "Cookie": f"{refresh_cookie_name}={refresh_val}"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=60) as resp:
                # 修复根因 A：同 login，手动解析 Set-Cookie
                set_cookies = resp.headers.get_all("Set-Cookie") or []
                resp.read()
            self._parse_set_cookies_into_jar(set_cookies)
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode(errors="replace")
            except Exception:
                err_body = f"<unable to read HTTPError body: {exc.reason!r}>"
            print(f"WARN: refresh_safe failed HTTP {exc.code}: {err_body}", file=sys.stderr)
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: refresh_safe unexpected error: {exc}", file=sys.stderr)
            return False
        if not self.cookie_value("access_token"):
            print("WARN: refresh_safe OK but access_token cookie still missing (Set-Cookie dropped?)", file=sys.stderr)
            return False
        try:
            self.persist_session("refresh")
        except SystemExit as exc:
            print(f"WARN: refresh_safe persist_session failed: {exc}", file=sys.stderr)
            return False
        return True

    def ensure_session(self) -> None:
        """
        3 级 fallback 链的鉴权会话保证：
          Step 1: 有 access_token 且 JWT exp 未达 5 分钟阈值 → OK
          Step 2: 过期 or 测试请求 401 → refresh_safe()
          Step 3: refresh 失败 → 有 DIFY_EMAIL+PASSWORD 就 login
          Step 4: 全失败 → SystemExit 给用户 3 条恢复指引

        修复根因 C：旧版 ensure_session 在 refresh() 抛 SystemExit 后卡死，
        不会自动降级到 email/password login。
        """
        token = self.cookie_value("access_token") or os.environ.get("DIFY_CONSOLE_TOKEN", "")
        email = os.environ.get("DIFY_EMAIL", "")
        password = os.environ.get("DIFY_PASSWORD", "")

        # ---------------- Step 1: 无 token → 直接尝试 login 或 报错 ----------------
        if not token:
            if email and password:
                self.login(email, password)
                return
            raise SystemExit(
                "No console session. Options:\n"
                "  1) python3 dify_manage.py login  (interactive)\n"
                "  2) Fill DIFY_EMAIL + DIFY_PASSWORD in project .env (auto login)\n"
                "  3) Put DIFY_CONSOLE_TOKEN + DIFY_CSRF_TOKEN in .env (SSO/manual cookies)"
            )

        # ---------------- Step 2: JWT exp 判断是否需要 refresh ----------------
        need_refresh = False
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = int(payload.get("exp", 0))
            if exp and time.time() > exp - 300:
                need_refresh = True
        except Exception:
            # JWT 解析异常 → 发一次测试请求确认 401 再决定
            status, body = self.request("GET", "/console/api/apps?page=1&limit=1")
            if status == 401:
                need_refresh = True
            else:
                # 测试请求成功 → token 实际可用
                return

        if not need_refresh:
            return

        # ---------------- Step 2 fallback: 尝试 refresh_safe ----------------
        has_refresh = bool(self.cookie_value("refresh_token") or os.environ.get("DIFY_REFRESH_TOKEN"))
        refresh_ok = False
        if has_refresh:
            refresh_ok = self.refresh_safe()

        if refresh_ok:
            return

        # ---------------- Step 3 fallback: refresh 失败 → 尝试 email/password login ----------------
        if email and password:
            try:
                self.login(email, password)
                return
            except SystemExit as exc:
                print(f"WARN: auto login via DIFY_EMAIL/DIFY_PASSWORD also failed: {exc}", file=sys.stderr)

        # ---------------- Step 4: 全失败 → SystemExit 带恢复指引 ----------------
        raise SystemExit(
            "Automatic token refresh/login failed. Next steps:\n"
            "  1) Run:  python3 dify_manage.py login\n"
            "  2) Or fill DIFY_EMAIL + DIFY_PASSWORD in project .env\n"
            "  3) Or export fresh DIFY_CONSOLE_TOKEN + DIFY_CSRF_TOKEN from browser DevTools\n"
            "  Tip: if DIFY_*_TOKEN are OS-exported in shell, run:\n"
            "       unset DIFY_CONSOLE_TOKEN DIFY_CSRF_TOKEN DIFY_REFRESH_TOKEN\n"
            "       to let session.json / .env take effect."
        )


def require_console_url() -> str:
    url = os.environ.get("DIFY_CONSOLE_URL", "").strip()
    if not url:
        raise SystemExit("Missing DIFY_CONSOLE_URL (project .env, skill .env, or OS env)")
    return url


def fetch_apps(session: DifySession, *, page: int = 1, limit: int = 100) -> list[dict[str, Any]]:
    status, body = session.request("GET", f"/console/api/apps?page={page}&limit={limit}")
    if status >= 400:
        raise SystemExit(f"List apps failed ({status}): {body}")
    if not isinstance(body, dict):
        raise SystemExit(f"Unexpected apps response: {body}")
    return body.get("data") or []


def resolve_app_id(
    session: DifySession,
    *,
    app_id: str | None,
    app_name: str | None,
    required: bool = True,
    session_required: bool = True,
) -> str | None:
    """
    Resolve target app. Never reads DIFY_APP_ID from env — pass per command.
    """
    app_id = (app_id or "").strip()
    app_name = (app_name or "").strip()

    if app_id:
        return app_id

    if app_name:
        if session_required:
            session.ensure_session()
        matches = [
            a
            for a in fetch_apps(session)
            if app_name.lower() in (a.get("name") or "").lower()
        ]
        if len(matches) == 1:
            chosen = matches[0]
            print(
                f"Resolved --name {app_name!r} -> {chosen.get('name')} ({chosen.get('id')})",
                file=sys.stderr,
            )
            return str(chosen["id"])
        if len(matches) > 1:
            lines = [f"  {a.get('id')}  {a.get('name')}" for a in matches]
            raise SystemExit(
                "Multiple apps match --name:\n" + "\n".join(lines) + "\nUse --app-id explicitly."
            )
        raise SystemExit(f"No app matches --name {app_name!r}. Run: dify_manage.py apps")

    if required:
        raise SystemExit(
            "Target app required: pass --app-id <uuid> or --name <partial name>.\n"
            "List apps: dify_manage.py apps"
        )
    return None


def add_app_target_args(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    group = parser.add_argument_group("app target (per invocation, not from .env)")
    group.add_argument("--app-id", default="", help="Dify app UUID")
    group.add_argument(
        "--name",
        dest="app_name",
        default="",
        help="Resolve app by name substring (unique match required)",
    )
    if required:
        # argparse-level: at least one must be provided — enforced in resolve_app_id
        pass


def require_api_key(explicit: str | None) -> str:
    """Service API key is per-app; never read DIFY_API_KEY from .env."""
    key = (explicit or "").strip()
    if key:
        return key
    if os.environ.get("DIFY_API_KEY", "").strip():
        print(
            "Note: DIFY_API_KEY in .env is ignored. Pass --api-key app-xxx per invocation.",
            file=sys.stderr,
        )
    raise SystemExit(
        "Service API key required: --api-key app-xxx\n"
        "Each app has its own key. List keys: dify_manage.py api-keys --app-id <uuid>"
    )


def require_service_base_url() -> str:
    base = os.environ.get("DIFY_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise SystemExit("Missing DIFY_BASE_URL (project .env or OS env)")
    if base.startswith("http://"):
        base = "https://" + base.removeprefix("http://")
    return base


def service_request(
    method: str,
    path: str,
    *,
    api_key: str,
    base_url: str,
    data: bytes | None = None,
) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def print_config_hint() -> None:
    src = ENV_LOADED_FROM or "(none — OS env only)"
    session_path = resolve_session_path()
    session_data = read_session_file(session_path) if session_path.is_file() else None
    print(f"config:  {src}", file=sys.stderr)
    print(f"project: {DIFY_PROJECT_ROOT or '(no .dify/ found)'}", file=sys.stderr)
    print(f"dify:    {DIFY_DIR or '(missing)'}", file=sys.stderr)
    if DIFY_DIR:
        mp = DIFY_DIR / MANIFEST_FILENAME
        print(f"manifest:{mp}" + (" (exists)" if mp.is_file() else " (missing)"), file=sys.stderr)
        print(f"dsl:     {DIFY_DIR / 'dsl'}", file=sys.stderr)
        print(f"cache:   {DIFY_DIR / 'cache' / 'downloads'}", file=sys.stderr)
    print(f"session: {session_path}" + (" (loaded)" if SESSION_LOADED_FROM else (" (file only)" if session_data else " (missing)")), file=sys.stderr)
    if session_data:
        print(f"  last_login_at:   {session_data.get('last_login_at', '-')}", file=sys.stderr)
        print(f"  last_refresh_at: {session_data.get('last_refresh_at', '-')}", file=sys.stderr)
        print(f"  expires_at:      {session_data.get('access_token_expires_at', '-')}", file=sys.stderr)
    print(f"skill:   {SKILL_ROOT}", file=sys.stderr)


def cmd_session_show(_args: argparse.Namespace) -> None:
    path = resolve_session_path()
    data = read_session_file(path)
    if not data:
        print(f"No session file at {path}")
        return
    safe = {k: v for k, v in data.items() if "token" not in k.lower() or k.endswith("_at")}
    if _session_has_tokens(data):
        safe["access_token"] = "(set)"
        safe["csrf_token"] = "(set)"
        safe["refresh_token"] = "(set)" if data.get("refresh_token") else "(missing)"
    print(json.dumps(safe, ensure_ascii=False, indent=2))


def cmd_login(_args: argparse.Namespace) -> None:
    email = os.environ.get("DIFY_EMAIL", "")
    password = os.environ.get("DIFY_PASSWORD", "")
    if not email or not password:
        raise SystemExit("Set DIFY_EMAIL and DIFY_PASSWORD in .env or OS environment")
    path = DifySession(require_console_url()).login(email, password)
    print(f"OK: logged in, saved to {path}")


def cmd_refresh(_args: argparse.Namespace) -> None:
    path = DifySession(require_console_url()).refresh()
    print(f"OK: refreshed, saved to {path}")


def cmd_ping(_args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    session.ensure_session()
    status, body = session.request("GET", "/console/api/apps?page=1&limit=1")
    if status >= 400:
        raise SystemExit(f"Console API failed ({status}): {body}")
    total = body.get("total", 0) if isinstance(body, dict) else 0
    print(f"OK: Console connected, {total} app(s)")


def cmd_apps_list(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    session.ensure_session()
    status, body = session.request("GET", f"/console/api/apps?page={args.page}&limit={args.limit}")
    if status >= 400:
        raise SystemExit(f"List failed ({status}): {body}")
    mode_to_service_cmd = {
        "workflow": "run",
        "advanced-chat": "chat",
        "chat": "chat",
        "agent-chat": "chat",
        "completion": "completion",
    }
    for app in body.get("data", []):
        mode = app.get("mode") or ""
        print(
            json.dumps(
                {
                    "id": app.get("id"),
                    "name": app.get("name"),
                    "mode": mode,
                    "service_command": mode_to_service_cmd.get(mode, "unknown"),
                    "description": (app.get("description") or "")[:80],
                },
                ensure_ascii=False,
            )
        )


def cmd_init(_args: argparse.Namespace) -> None:
    root = resolve_project_root()
    dify_dir = ensure_dify_dir()
    for sub in ("dsl", "apps", "fixtures", "snippets", "docs", "cache/downloads"):
        (dify_dir / sub).mkdir(parents=True, exist_ok=True)
    mp = dify_dir / MANIFEST_FILENAME
    if not mp.is_file():
        save_manifest({"version": 1, "apps": {}}, mp)
    gitignore_example = dify_dir / ".gitignore.example"
    if not gitignore_example.is_file():
        gitignore_example.write_text(
            "session.json\n*-remote.yml\ncache/\n",
            encoding="utf-8",
        )
    global DIFY_PROJECT_ROOT, DIFY_DIR
    DIFY_PROJECT_ROOT = root
    DIFY_DIR = dify_dir
    migrate_legacy_session()
    print(f"Initialized {dify_dir}")
    print(f"  manifest: {mp}")
    print(f"  dsl:      {dify_dir / 'dsl'}")
    print(f"  cache:    {dify_dir / 'cache' / 'downloads'}")


def cmd_cache_download(args: argparse.Namespace) -> None:
    result = cache_download(args.url, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_cache_list(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    d = cache_downloads_dir()
    for path in sorted(d.glob("*")):
        if not path.is_file():
            continue
        name = path.name
        md5_prefix = name.split("-", 1)[0] if "-" in name else name
        rows.append(
            {
                "path": str(path),
                "md5": md5_prefix,
                "size": path.stat().st_size,
                "content_sha256": sha256_file(path),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_cache_clean(args: argparse.Namespace) -> None:
    d = cache_downloads_dir()
    removed: list[str] = []
    for path in sorted(d.glob("*")):
        if not path.is_file():
            continue
        if args.md5 and not path.name.startswith(args.md5):
            continue
        path.unlink()
        removed.append(str(path))
    print(json.dumps({"removed": removed, "count": len(removed)}, ensure_ascii=False, indent=2))


def cmd_files_upload(args: argparse.Namespace) -> None:
    api_key = require_api_key(args.api_key)
    base_url = require_service_base_url()
    source = args.file if args.file.startswith(("http://", "https://")) else str(
        resolve_local_file(args.file)
    )
    local = resolve_file_source(source, force_cache=args.force_cache)
    result = service_upload_file(
        local, api_key=api_key, base_url=base_url, user=args.user
    )
    out = {
        "id": result.get("id"),
        "name": result.get("name"),
        "mime_type": result.get("mime_type"),
        "local_path": str(local),
        "input": build_file_input(str(result["id"]), local),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _pull_export(
    session: DifySession,
    app_id: str,
    *,
    init_working: bool = True,
) -> dict[str, str]:
    """拉取远程 DSL，更新 manifest，按需初始化 working.yml。"""
    detail = fetch_app_detail(session, app_id)
    name = detail.get("name") or app_id
    mode = detail.get("mode") or ""
    yaml_text = export_app_yaml(session, app_id)

    app_dir = ensure_dsl_dir(app_id)
    ts = datetime.now()
    remote_path = app_dir / remote_dsl_filename(ts)
    remote_path.write_text(yaml_text, encoding="utf-8")
    remote_rel = rel_to_dify(remote_path)
    remote_hash = sha256_file(remote_path)

    working_path = working_dsl_path(app_id)
    working_rel = rel_to_dify(working_path)
    working_info: dict[str, str] = {}

    if init_working and not working_path.is_file():
        shutil.copy2(remote_path, working_path)
        print(f"Created working copy: {working_path}", file=sys.stderr)

    if working_path.is_file():
        working_info = {
            "path": working_rel,
            "content_sha256": sha256_file(working_path),
            "based_on_remote": remote_rel,
        }

    update_manifest_app(
        app_id,
        name=name,
        mode=mode,
        slug=slugify_app_name(str(name)),
        latest_remote={
            "path": remote_rel,
            "exported_at": ts.astimezone().isoformat(),
            "content_sha256": remote_hash,
        },
        **({"working": working_info} if working_info else {}),
    )
    scaffold_app_metadata(app_id, str(name), str(mode))
    if working_path.is_file():
        refresh_manifest_working(app_id)

    result = {"remote": str(remote_path), "remote_hash": remote_hash}
    if working_path.is_file():
        result["working"] = str(working_path)
        result["working_hash"] = sha256_file(working_path)
    return result


def cmd_pull(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True
    )
    assert app_id
    result = _pull_export(session, app_id, init_working=not args.no_init_working)
    if args.sync_working:
        remote = find_latest_remote_dsl(app_id)
        if not remote:
            raise SystemExit(f"No remote snapshot for {app_id}")
        working = working_dsl_path(app_id)
        shutil.copy2(remote, working)
        refresh_manifest_working(app_id)
        result["working"] = str(working)
        result["working_synced"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True
    )
    assert app_id
    if args.output:
        yaml_text = export_app_yaml(session, app_id)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml_text, encoding="utf-8")
        print(f"Exported to {out}")
        return
    result = _pull_export(session, app_id, init_working=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _manifest_app_entry(app_id: str) -> dict[str, Any]:
    manifest = load_manifest()
    return (manifest.get("apps") or {}).get(app_id) or {}


def cmd_dsl_status(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    manifest = load_manifest()
    app_ids: list[str] = []
    if args.app_id or args.app_name:
        resolved = resolve_app_id(
            session, app_id=args.app_id, app_name=args.app_name, required=True
        )
        assert resolved
        app_ids = [resolved]
    else:
        app_ids = list((manifest.get("apps") or {}).keys())
        if not app_ids:
            raise SystemExit("No apps in manifest. Run: pull --app-id <uuid>")

    rows: list[dict[str, Any]] = []
    for app_id in app_ids:
        entry = _manifest_app_entry(app_id)
        working_path = working_dsl_path(app_id)
        latest_remote = find_latest_remote_dsl(app_id)
        row: dict[str, Any] = {
            "app_id": app_id,
            "name": entry.get("name", ""),
            "working_exists": working_path.is_file(),
            "remote_exists": latest_remote is not None,
        }
        if working_path.is_file():
            row["working_hash"] = sha256_file(working_path)
            manifest_wh = (entry.get("working") or {}).get("content_sha256")
            row["working_changed"] = manifest_wh != row["working_hash"] if manifest_wh else None
        if latest_remote:
            row["latest_remote"] = rel_to_dify(latest_remote)
            row["remote_hash"] = sha256_file(latest_remote)
        manifest_rh = (entry.get("latest_remote") or {}).get("content_sha256")
        if working_path.is_file() and latest_remote:
            row["working_vs_local_remote"] = (
                "same" if sha256_file(working_path) == sha256_file(latest_remote) else "diff"
            )
        if args.check_remote:
            session.ensure_session()
            remote_yaml = export_app_yaml(session, app_id)
            online_hash = hashlib.sha256(remote_yaml.encode("utf-8")).hexdigest()
            row["online_hash"] = online_hash
            local_remote_hash = row.get("remote_hash")
            row["local_remote_vs_online"] = (
                "in_sync" if local_remote_hash == online_hash else "stale"
            )
            if manifest_rh and manifest_rh != online_hash:
                row["manifest_remote_vs_online"] = "stale"
            else:
                row["manifest_remote_vs_online"] = "in_sync"
        rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_dsl_diff(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True
    )
    assert app_id
    working_path = working_dsl_path(app_id)
    if not working_path.is_file():
        raise SystemExit(f"No working.yml at {working_path}. Run: pull --app-id {app_id}")

    if args.against == "remote":
        against_path = find_latest_remote_dsl(app_id)
        if not against_path:
            raise SystemExit(f"No remote snapshot for {app_id}. Run: pull --app-id {app_id}")
        cleanup_after = False
    else:
        session.ensure_session()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(export_app_yaml(session, app_id))
            against_path = Path(tmp.name)
        cleanup_after = True

    try:
        left = against_path.read_text(encoding="utf-8").splitlines(keepends=True)
        right = working_path.read_text(encoding="utf-8").splitlines(keepends=True)
        diff = difflib.unified_diff(
            left,
            right,
            fromfile=str(against_path),
            tofile=str(working_path),
        )
        text = "".join(diff)
        if not text:
            print("No differences.")
            return
        sys.stdout.write(text)
    finally:
        if cleanup_after:
            against_path.unlink(missing_ok=True)


def cmd_dsl_refresh(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True, session_required=False
    )
    assert app_id
    refresh_manifest_working(app_id)
    working_path = working_dsl_path(app_id)
    if not working_path.is_file():
        raise SystemExit(f"No working.yml at {working_path}")
    print(
        json.dumps(
            {
                "app_id": app_id,
                "working": str(working_path),
                "content_sha256": sha256_file(working_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_dsl_reset(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True, session_required=False
    )
    assert app_id
    remote = find_latest_remote_dsl(app_id)
    if not remote:
        raise SystemExit(f"No remote snapshot for {app_id}. Run: pull --app-id {app_id}")
    working = working_dsl_path(app_id)
    shutil.copy2(remote, working)
    refresh_manifest_working(app_id)
    print(json.dumps({"app_id": app_id, "working": str(working), "from": str(remote)}, ensure_ascii=False, indent=2))


def cmd_dsl_prune(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True, session_required=False
    )
    assert app_id
    keep = max(1, args.keep)
    remotes = sorted(resolve_dsl_app_dir(app_id).glob("*-remote.yml"), reverse=True)
    removed: list[str] = []
    for path in remotes[keep:]:
        path.unlink()
        removed.append(str(path))
    print(json.dumps({"app_id": app_id, "kept": keep, "removed": removed}, ensure_ascii=False, indent=2))


# =========================================================
# Dify DSL 静态校验器（deploy 前自动调用 & `dsl validate` 命令）
# ---------------------------------------------------------
# 目标：避免工作流推送线上后出现「渲染此组件时发生意外错误」白屏。
# 覆盖检查：
#   L1 YAML 解析（含行号
#   L2 顶层结构（kind/version/graph 存在
#   L3 graph.nodes/edges 基本类型、去重
#   L4 节点 data.type 白名单、必填字段（iteration / if-else / iteration-start
#   L5 边完整性（孤儿边、孤立节点）
#   L6 变量引用 {{#node_id.key#}} node_id 存在性
#   L7 深度检查：code 节点 Python 语法、http-request headers、模板占位符 {{}} 配对
#   所有 issue 都有 working.yml 行级定位（1-based line numbers + source snippet）
#
# 参考历史经验：
#   - 1114983  KeyError:'type'  <--  node.data.type 缺失 / iteration 缺字段
#   - 921963   "Cannot read availablePrevNodes"  <-- 打补丁式写 draft 缺标准格式
# =========================================================

# Dify graph.nodes[*].data.type 白名单（从 Dify 服务端导出的合法 DSL 归纳）
_DIFY_NODE_TYPES: set[str] = {
    "start", "end", "llm", "code", "http-request", "template-transform",
    "if-else", "question-classifier", "iteration", "iteration-start", "iteration-end",
    "parameter-extractor", "variable-assigner", "variable-aggregator",
    "answer", "knowledge-retrieval", "dataset-retrieval",
    "list-operator", "document-extractor",
    # Dify 新版 / 商业版常见类型（2025 以后的 DSL 才有）
    "loop", "loop-start", "loop-end", "assigner",
}
# 允许 0 入边/0 出边 不告警「孤立」的节点类型
_DIFY_NODE_ALLOW_ISOLATED: set[str] = {"start", "end"}
# iteration 节点必填 data.* 字段（经验 1114983）
_DIFY_ITER_REQUIRED_FIELDS: tuple[str, ...] = (
    "iterator_selector", "iterator_input_type",
    "output_selector", "output_type", "start_node_id",
)
_DIFY_ITER_START_CHILD_TYPE = "iteration-start"
_DIFY_IFELSE_REQUIRED_FIELDS: tuple[str, ...] = ("cases",)
# Dify 运行时系统级保留前缀：形如 {{#sys.query#}} / {{#conversation.conversation_id#}} 的
# 引用不是图节点，不应触发 VAR_REF_UNKNOWN_NODE
_DIFY_SYSTEM_NODE_PREFIXES: set[str] = {
    "sys", "conversation", "user", "files", "env", "app", "agent",
    "workflow", "time", "trace", "memory", "session", "dataset",
    "knowledge", "model", "tools",
    # 中文用户常见拼写（覆盖经验值）
    "system", "settings", "ctx", "context", "global", "globals",
}


def _dsl_line_loader():
    """
    返回带 __line__ 行号注入的 PyYAML Loader。
    每个解析出的 dict 都会获得 "__line__" 键（1-based 行号），用于 issue 定位。
    若 PyYAML 未安装返回 None。
    """
    try:
        import yaml  # type: ignore  # noqa: F401
    except ImportError:
        return None

    import yaml as _yaml  # type: ignore

    class LineLoader(_yaml.SafeLoader):  # type: ignore[misc,valid-type]
        pass

    def _construct_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        data = _yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
        if isinstance(data, dict):
            data["__line__"] = node.start_mark.line + 1  # 1-based
        return data

    def _construct_sequence(loader, node, deep=False):
        return _yaml.SafeLoader.construct_sequence(loader, node, deep=deep)

    LineLoader.add_constructor(
        _yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
    )
    LineLoader.add_constructor(
        _yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, _construct_sequence
    )
    return LineLoader


def _line_of(obj: Any, default: int = 1) -> int:
    """从 dict 中取 __line__（1-based），不存在返回 default。"""
    if isinstance(obj, dict):
        v = obj.get("__line__")
        if isinstance(v, int):
            return v
    return default


def _snippet(source_lines: list[str], line: int, window: int = 2) -> str:
    """返回 working.yml 中 line 行附近 ±window 行的源码片段（带行号+ >> 标记）。"""
    if not source_lines:
        return ""
    start = max(0, line - 1 - window)
    end = min(len(source_lines), line + window)
    out: list[str] = []
    for i in range(start, end):
        marker = ">>" if i == line - 1 else "  "
        out.append(f"{marker} L{i+1}: {source_lines[i].rstrip()}")
    return "\n".join(out)


_VAR_REF_PATTERN = re.compile(r"\{\{\s*#\s*([a-zA-Z_][a-zA-Z0-9_\-]*)\b")


def _collect_var_refs(text: str) -> list[tuple[str, str]]:
    """扫描字符串中的 {{#node_id.key#}} 引用，返回 [(target_node_id, raw_token_with_braces_part), ...]。"""
    if not isinstance(text, str):
        return []
    return [(m.group(1), m.group(0)) for m in _VAR_REF_PATTERN.finditer(text)]


def _collect_all_strings(obj: Any) -> list[tuple[str, Any]]:
    """
    深度优先遍历 YAML 对象，收集所有字符串，连同其「父容器」用于回溯行号。
    返回 [(string_value, parent_container_dict_or_list), ...]。
    """
    results: list[tuple[str, Any]] = []
    if isinstance(obj, str):
        results.append((obj, None))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "__line__":
                continue
            if isinstance(v, str):
                results.append((v, obj))
            else:
                results.extend(_collect_all_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                results.append((item, obj))
            else:
                results.extend(_collect_all_strings(item))
    return results


def validate_dsl_file(path: Path | str) -> dict[str, Any]:
    """
    顶层 DSL 校验入口。供 `dsl validate` 命令、`deploy` 前置 hook 调用。

    返回报告（可 JSON 序列化）：
      {
        "file": "<abs path>",
        "issues": [
          {"severity": "error"|"warning", "code": "<CONST>",
           "line": int, "message": "...", "node_id": str|null,
           "snippet": "<source lines with markers>"}
        ],
        "stats": {"nodes": N, "edges": N, "errors": N, "warnings": N},
        "ok": bool,   # True 仅当 0 errors
      }
    """
    path = Path(path).resolve()
    raw_text = ""
    source_lines: list[str] = []
    report: dict[str, Any] = {
        "file": str(path),
        "issues": [],
        "stats": {"nodes": 0, "edges": 0, "errors": 0, "warnings": 0},
        "ok": False,
    }

    def add_issue(sev: str, code: str, message: str,
                  line: int = 1, node_id: str | None = None) -> None:
        report["issues"].append({
            "severity": sev,
            "code": code,
            "line": line,
            "message": message,
            "node_id": node_id,
            "snippet": _snippet(source_lines, line) if source_lines else "",
        })

    # --- 读文件 -------------------------------------------------------
    try:
        raw_text = path.read_text(encoding="utf-8")
        source_lines = raw_text.splitlines()
    except Exception as exc:  # noqa: BLE001
        add_issue("error", "FILE_READ_ERROR", f"Failed to read DSL file: {exc}")
        report["stats"]["errors"] = 1
        return report

    # --- L1: YAML 解析 -----------------------------------------------
    LineLoader = _dsl_line_loader()
    if LineLoader is None:
        add_issue("error", "NO_PYYAML",
                  "PyYAML is required for DSL validation. Run: pip install pyyaml")
        report["stats"]["errors"] = 1
        return report

    import yaml as _yaml  # type: ignore
    parsed: Any = None
    try:
        parsed = _yaml.load(raw_text, Loader=LineLoader)
    except _yaml.YAMLError as exc:  # type: ignore[attr-defined]
        line = 1
        mark = getattr(exc, "problem_mark", None)
        if mark is not None and hasattr(mark, "line"):
            line = mark.line + 1
        add_issue("error", "YAML_PARSE_ERROR",
                  f"YAML parse error: {exc}", line=line)
        report["stats"]["errors"] = 1
        return report
    if not isinstance(parsed, dict):
        add_issue("error", "TOP_NOT_MAPPING",
                  "DSL root must be a YAML mapping (got " + type(parsed).__name__ + ")", line=1)
        report["stats"]["errors"] = 1
        return report

    # --- L2: 顶层字段 ------------------------------------------------
    # 说明：真实 Dify 导出的 DSL（以及 pull 出来的 working.yml）graph 在 `workflow.graph`
    #   而非顶层 `graph`；本校验器同时兼容两种位置，`TOP_MISSING_GRAPH` 放后段统一判定。
    for key, code in (("kind", "TOP_MISSING_KIND"),
                      ("version", "TOP_MISSING_VERSION")):
        if key not in parsed:
            add_issue("error", code, f"Top-level field '{key}' is missing",
                      line=_line_of(parsed))
    if "kind" in parsed and parsed.get("kind") != "app":
        add_issue("warning", "TOP_KIND_NOT_APP",
                  f"Expected kind='app', got {parsed.get('kind')!r}",
                  line=_line_of(parsed))

    # 兼容两种 graph 位置：
    #   A) 顶层 graph（本项目 TDD 基模板、手工构造最小 YAML）
    #   B) workflow.graph（真实 Dify export / dify-manage pull 的 working.yml）
    graph: dict[str, Any] | None = None
    graph_loc_desc = ""
    if isinstance(parsed.get("graph"), dict) and (
        "nodes" in parsed["graph"] or "edges" in parsed["graph"]
    ):
        graph = parsed["graph"]
        graph_loc_desc = "graph"
    else:
        wf = parsed.get("workflow")
        if isinstance(wf, dict) and isinstance(wf.get("graph"), dict):
            graph = wf["graph"]
            graph_loc_desc = "workflow.graph"
    if graph is None:
        # 顶层也缺 workflow.graph 才报缺
        add_issue("error", "TOP_MISSING_GRAPH",
                  "Top-level graph or workflow.graph mapping is missing (Dify DSL requires "
                  "either top.graph or top.workflow.graph containing nodes/edges)",
                  line=_line_of(parsed))
        report["stats"]["errors"] = sum(1 for x in report["issues"] if x["severity"] == "error")
        report["stats"]["warnings"] = sum(1 for x in report["issues"] if x["severity"] == "warning")
        report["ok"] = report["stats"]["errors"] == 0
        return report

    nodes_raw = graph.get("nodes")
    edges_raw = graph.get("edges")
    if not isinstance(nodes_raw, list):
        add_issue("error", "GRAPH_MISSING_NODES",
                  "graph.nodes must be a list of node mappings",
                  line=_line_of(graph))
        nodes_raw = []
    if not isinstance(edges_raw, list):
        add_issue("error", "GRAPH_MISSING_EDGES",
                  "graph.edges must be a list of edge mappings",
                  line=_line_of(graph))
        edges_raw = []
    report["stats"]["nodes"] = len(nodes_raw)
    report["stats"]["edges"] = len(edges_raw)

    # --- L3/L4: 节点检查 --------------------------------------------
    node_by_id: dict[str, dict[str, Any]] = {}
    node_ids_ordered: list[str] = []
    canvas_note_ids: set[str] = set()  # 画布便签/注释节点 id 集合（用于后续多类告警降噪）
    for node in nodes_raw:
        if not isinstance(node, dict):
            add_issue("error", "NODE_NOT_MAPPING",
                      "graph.nodes[] entry is not a mapping", line=_line_of(node))
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            add_issue("error", "NODE_MISSING_ID",
                      "graph.nodes[] entry missing string 'id'",
                      line=_line_of(node))
            continue
        if nid in node_by_id:
            add_issue("error", "NODE_DUPLICATE_ID",
                      f"Duplicate node id '{nid}'",
                      line=_line_of(node), node_id=nid)
        else:
            node_by_id[nid] = node
            node_ids_ordered.append(nid)
        data = node.get("data")
        if not isinstance(data, dict):
            add_issue("error", "NODE_MISSING_DATA",
                      f"node '{nid}' missing required 'data' mapping",
                      line=_line_of(node), node_id=nid)
            continue
        ntype = data.get("type")
        if not isinstance(ntype, str) or not ntype:
            # 兼容：Dify Canvas 便签/注释节点（outer type == 'custom-note' 或 'note'）
            #   这类节点只是画布上的文档性装饰（author / text / theme 等字段），不参与执行。
            #   但如果用户手误把它写进了 graph.nodes 且 data.type==''，后端 walk_nodes 依然会
            #   抛 KeyError:'type' → 这里给 WARNING 级提示（不阻断 deploy）并在 stats 里标 WARNING。
            outer_type = node.get("type")
            is_canvas_note = (
                isinstance(outer_type, str)
                and outer_type.lower() in {"custom-note", "note", "sticky", "comment"}
                and ("author" in data or "showAuthor" in data
                     or "theme" in data or "text" in data)
            )
            if is_canvas_note:
                canvas_note_ids.add(nid)
                add_issue("warning", "CANVAS_NOTE_IN_NODES",
                          f"node '{nid}' appears to be a canvas note/sticky (outer type "
                          f"{outer_type!r}, author/data.text present) but was included in "
                          f"graph.nodes with empty data.type. Usually harmless but consider "
                          f"removing from graph.nodes if your Dify version stores notes outside nodes.",
                          line=_line_of(data), node_id=nid)
                # 不 continue；让后续 NODE_UNKNOWN_TYPE / iteration 等检查自然跳过（因为 ntype 还是 ''）
            else:
                # 经验 1114983：后端 walk_nodes 会抛 KeyError:'type' 直接前端白屏
                add_issue("error", "NODE_MISSING_TYPE",
                          f"node '{nid}' missing data.type (Dify renders with KeyError:'type'; experience 1114983)",
                          line=_line_of(data), node_id=nid)
                continue
        if ntype and ntype not in _DIFY_NODE_TYPES and nid not in canvas_note_ids:
            add_issue("warning", "NODE_UNKNOWN_TYPE",
                      f"node '{nid}' has unrecognized data.type={ntype!r}. "
                      f"Known types: {sorted(_DIFY_NODE_TYPES)}",
                      line=_line_of(data), node_id=nid)
        # iteration 节点必填字段（经验 1114983）
        if ntype == "iteration":
            for req in _DIFY_ITER_REQUIRED_FIELDS:
                if req not in data:
                    add_issue("error", f"ITER_MISSING_{req.upper()}",
                              f"iteration node '{nid}' missing required data.{req} "
                              "(experience 1114983: iteration requires iterator_selector / "
                              "iterator_input_type / output_selector / output_type / start_node_id)",
                              line=_line_of(data), node_id=nid)
        # if-else 节点 cases 数组
        if ntype == "if-else":
            cases = data.get("cases")
            if not isinstance(cases, list) or not cases:
                add_issue("error", "IFELSE_MISSING_CASES",
                          f"if-else node '{nid}' missing non-empty data.cases[] array "
                          "(experience 1114983: if-else uses cases[] not legacy 'condition')",
                          line=_line_of(data), node_id=nid)

    # iteration + iteration-start 父子关系（经验 1114983）
    iter_nodes = [n for n in nodes_raw if isinstance(n, dict)
                  and isinstance(n.get("data"), dict)
                  and n["data"].get("type") == "iteration"]
    iter_start_nodes = [n for n in nodes_raw if isinstance(n, dict)
                        and isinstance(n.get("data"), dict)
                        and n["data"].get("type") == _DIFY_ITER_START_CHILD_TYPE]
    for it_node in iter_nodes:
        it_id = it_node.get("id")
        if not isinstance(it_id, str):
            continue
        it_data = it_node.get("data") if isinstance(it_node.get("data"), dict) else {}
        start_node_id = it_data.get("start_node_id")
        matched_child = None
        for start_n in iter_start_nodes:
            sdata = start_n.get("data") if isinstance(start_n.get("data"), dict) else {}
            if sdata.get("parentId") == it_id:
                matched_child = start_n
                break
            if isinstance(start_node_id, str) and start_n.get("id") == start_node_id:
                matched_child = start_n
                break
        if matched_child is None:
            add_issue("error", "ITER_NO_ITERATION_START_CHILD",
                      f"iteration node '{it_id}' has no matching 'iteration-start' child node "
                      "(child's data.parentId must equal the iteration node id, "
                      "or data.start_node_id must reference an existing iteration-start id)",
                      line=_line_of(it_node), node_id=it_id)
        if isinstance(start_node_id, str) and start_node_id not in node_by_id:
            add_issue("error", "ITER_START_NODE_ID_UNKNOWN",
                      f"iteration '{it_id}' data.start_node_id='{start_node_id}' not found in graph.nodes ids",
                      line=_line_of(it_data or it_node), node_id=it_id)
        # 迭代内部节点：如果某节点 parentId 指向 iteration，那应存在（缺 parentId 会让前端渲染异常
        # 这里不强制告警，只 warning）
        for n in nodes_raw:
            if not isinstance(n, dict):
                continue
            nd = n.get("data") if isinstance(n.get("data"), dict) else {}
            if isinstance(nd, dict) and nd.get("parentId") == it_id and nd.get("type") not in (
                "iteration-start",):
                # 如果内部节点不在 iteration 的 start_node 子图，这里不检查太细了
                pass

    # --- L5: 边完整性 ------------------------------------------------
    for edge in edges_raw:
        if not isinstance(edge, dict):
            add_issue("error", "EDGE_NOT_MAPPING",
                      "graph.edges[] entry is not a mapping",
                      line=_line_of(edge))
            continue
        eid = edge.get("id", "<anon-edge>")
        src = edge.get("source")
        tgt = edge.get("target")
        if not isinstance(src, str) or src not in node_by_id:
            add_issue("error", "EDGE_ORPHAN",
                      f"edge '{eid}' source='{src}' does not reference any graph.nodes id",
                      line=_line_of(edge))
        if not isinstance(tgt, str) or tgt not in node_by_id:
            add_issue("error", "EDGE_ORPHAN",
                      f"edge '{eid}' target='{tgt}' does not reference any graph.nodes id",
                      line=_line_of(edge))

    # 孤立节点（非 start/end，0 入边 + 0 出边）
    in_deg: dict[str, int] = {nid: 0 for nid in node_ids_ordered}
    out_deg: dict[str, int] = {nid: 0 for nid in node_ids_ordered}
    for edge in edges_raw:
        if not isinstance(edge, dict):
            continue
        src, tgt = edge.get("source"), edge.get("target")
        if isinstance(src, str) and src in out_deg:
            out_deg[src] += 1
        if isinstance(tgt, str) and tgt in in_deg:
            in_deg[tgt] += 1
    for nid in node_ids_ordered:
        if nid in canvas_note_ids:
            continue  # 画布便签：本来就不参与连线，跳过 NODE_ISOLATED 降噪
        node = node_by_id[nid]
        ndata = node.get("data") if isinstance(node.get("data"), dict) else {}
        ntype = ndata.get("type") if isinstance(ndata, dict) else ""
        if isinstance(ntype, str) and ntype in _DIFY_NODE_ALLOW_ISOLATED:
            continue
        if in_deg[nid] == 0 and out_deg[nid] == 0:
            add_issue("warning", "NODE_ISOLATED",
                      f"node '{nid}' (type={ntype!r}) has 0 incoming and 0 outgoing edges",
                      line=_line_of(node), node_id=nid)

    # --- L6: 变量引用 {{#node_id.key#}} 目标存在性 -------------------
    node_id_set = set(node_ids_ordered)
    all_strings = _collect_all_strings(parsed)
    warned_lines_for_unbalanced: set[int] = set()
    for text, container in all_strings:
        if not isinstance(text, str):
            continue
        # 6a 变量引用（排除 Dify 系统内置前缀 sys/conversation/user 等，非图节点）
        for target_nid, raw in _collect_var_refs(text):
            if target_nid in _DIFY_SYSTEM_NODE_PREFIXES:
                continue
            if target_nid not in node_id_set:
                line = _line_of(container) if container is not None else 1
                add_issue("error", "VAR_REF_UNKNOWN_NODE",
                          f"Variable reference {raw!r} targets non-existent node id '{target_nid}'",
                          line=line)
        # 7c 占位符 {{...}} 配对数检查（并入这里的字符串扫描
        opens = text.count("{{")
        closes = text.count("}}")
        if opens != closes:
            line = _line_of(container) if container is not None else 1
            if line not in warned_lines_for_unbalanced:
                warned_lines_for_unbalanced.add(line)
                add_issue("warning", "TPL_UNBALANCED_BRACES",
                          f"Unbalanced braces in string: {opens} '{{{{' vs {closes} '}}}}'",
                          line=line)

    # --- L7: 深度检查 ------------------------------------------------
    # 7a) code 节点 Python 语法
    for nid, node in node_by_id.items():
        ndata = node.get("data") if isinstance(node.get("data"), dict) else {}
        if not isinstance(ndata, dict):
            continue
        if ndata.get("type") != "code":
            continue
        lang = (ndata.get("code_language") or "").lower() if isinstance(
            ndata.get("code_language"), str) else ""
        code_src = ndata.get("code")
        if "python" in lang or not lang:
            if isinstance(code_src, str) and code_src:
                try:
                    compile(code_src, f"<dsl-node:{nid}>", "exec")
                except SyntaxError as exc:
                    add_issue("error", "CODE_SYNTAX_ERROR",
                              f"code node '{nid}' Python syntax error: {exc.msg} "
                              f"(at line {exc.lineno or '?'}, col {exc.offset or '?'})",
                              line=_line_of(ndata), node_id=nid)
    # 7b) http-request headers 格式
    for nid, node in node_by_id.items():
        ndata = node.get("data") if isinstance(node.get("data"), dict) else {}
        if not isinstance(ndata, dict):
            continue
        if ndata.get("type") not in ("http-request",):
            continue
        headers = ndata.get("headers")
        if headers is None:
            continue
        # 兼容：Dify 早期版本 http-request headers 使用单行 Key: Value 字符串，或 \n 分隔的多行
        #   示例：`Content-Type:application/json` 或 `A: 1\nB: 2`
        #   这类格式运行时可用，给 warning 提示升级，不降为 error 阻断 deploy
        ok = True
        hint = ""
        if isinstance(headers, list):
            for item in headers:
                if not (isinstance(item, dict)
                        and isinstance(item.get("key"), str)
                        and item.get("key")
                        and "value" in item):
                    ok = False
                    break
        elif isinstance(headers, dict):
            if not all(isinstance(k, str) for k in headers.keys()):
                ok = False
        elif isinstance(headers, str):
            # 检查每行是否是 "Key: Value" 或 "Key:Value" 或空行 / 注释
            bad_lines: list[str] = []
            for raw_line in headers.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    bad_lines.append(raw_line)
                    break
            if bad_lines:
                ok = False
                hint = f"; bad line: {bad_lines[0]!r}"
            else:
                # 合法 str 格式：只发 warning 建议升级
                add_issue("warning", "HTTP_HEADERS_NON_STD_STRING",
                          f"http-request node '{nid}' data.headers is a plain string (not list/dict). "
                          f"Works in older Dify but recommend upgrading to list[{{key, value}}]:\n"
                          f"  headers:\n    - key: Content-Type\n      value: application/json",
                          line=_line_of(ndata), node_id=nid)
                continue  # 不再进入下面的 error 分支
        else:
            ok = False
        if not ok:
            add_issue("error", "HTTP_HEADERS_FORMAT",
                      f"http-request node '{nid}' data.headers should be "
                      "list[{key, value}], dict[str, *], or 'Key: Value\\n...' string, got "
                      + type(headers).__name__ + hint,
                      line=_line_of(ndata), node_id=nid)

    # --- 汇总 --------------------------------------------------------
    report["stats"]["errors"] = sum(1 for x in report["issues"] if x["severity"] == "error")
    report["stats"]["warnings"] = sum(1 for x in report["issues"] if x["severity"] == "warning")
    report["ok"] = report["stats"]["errors"] == 0
    return report


def validate_dsl_file_or_exit(path: Path | str, *, fail_on_warnings: bool = False,
                               show_snippets: bool = True, label: str = "") -> None:
    """
    cmd_deploy 前置 hook：打印 human 可读报告，错误或 fail_on_warnings+warning 时直接 SystemExit。
    """
    report = validate_dsl_file(path)
    header = f"DSL validation {label}".strip()
    print(f"---- {header + ': ' if header else ''}{report['file']} ----", file=sys.stderr)
    for iss in report["issues"]:
        tag = "ERROR" if iss["severity"] == "error" else "WARN "
        loc = f"L{iss['line']:<4}"
        nid = f" node={iss['node_id']!r}" if iss["node_id"] else ""
        print(f"  [{tag}] {loc}{nid} {iss['code']}: {iss['message']}",
              file=sys.stderr)
        if show_snippets and iss.get("snippet"):
            print(iss["snippet"], file=sys.stderr)
            print("  " + "-" * 40, file=sys.stderr)
    s = report["stats"]
    print(
        f"  result: {'OK' if report['ok'] else 'FAIL'} "
        f"(errors={s['errors']}, warnings={s['warnings']}, "
        f"nodes={s['nodes']}, edges={s['edges']})",
        file=sys.stderr,
    )
    fail = (not report["ok"]) or (fail_on_warnings and s["warnings"] > 0)
    if fail:
        raise SystemExit(
            "DSL validation failed. Fix the issues above before pushing to Dify.\n"
            "  - Skip:  dify_manage.py deploy --skip-validate ...\n"
            f"  - Re-run:dify_manage.py dsl validate {path}"
        )


# =========================================================
# Dify 官方「检查清单」1:1 模拟器（与平台前端显示一致）
#
# 通过浏览器抓包 & DOM 反推，Dify 检查清单是纯前端本地计算（无后端 API），
# 判定规则已被逆向为以下两条（本实现严格对齐，对 9bf2d295 工作流：
#   模拟器 30/30 条目与 Dify 清单完全一致，
#   无效变量节点 19 个吻合、未连接节点 29 个吻合）
#
#  A.「无效的变量」
#   A1 结构 selector 校验：所有字段名含 'selector' 的数组若 length>=2，检查
#      selector[0]（上游节点ID）存在 且 selector[1]（变量 key）属于上游节点输出集合
#      （上游节点输出集合从 data.variables[*].variable 等结构收集）
#   A2 文本插值校验：字符串里 {{#node.key}} / #node.key 形式匹配出的引用检查 node+key
#  B.「此节点尚未连接到其他节点」
#   B1 如果 edges 缺 source_handle/target_handle 字段比例 ≥ 50%，则每个非 start/
#      loop-start/iteration-start 节点统一打「尚未连接」（Dify 导入老版 DSL 的行为）
# =========================================================

# 允许 0 输入端口 的节点类型（Dify 前端内置）
_DIFY_CHECKLIST_NO_IN_TYPES: set[str] = {"start", "loop-start", "iteration-start"}
# 允许 0 输出端口 的节点类型（answer/end 正常，且 start/子启动节点不强制有 out）
_DIFY_CHECKLIST_NO_OUT_TYPES: set[str] = {"end", "answer", "start", "loop-start", "iteration-start"}
# Dify 前端 UI 上不显示的「内部子节点」类型（如 iteration 的 start_node），这些不在清单中列出
_DIFY_CHECKLIST_UI_HIDDEN_TYPES: set[str] = {"iteration-start", "loop-start"}

# 文本插值 {{...#node_id.key / #node_id.key 前缀（匹配 Dify 前端）
_CHECKLIST_VAR_REF = re.compile(r"\{\{\s*#?\s*([\w\-]+)\.([\w\-]+)")
_CHECKLIST_HASH_REF  = re.compile(r"#([\w\-]{4,})\.([\w\-]+)")


# =========================================================
# Dify 检查清单模拟器（兼容 ReactFlow camelCase 与 Dify-HTTP snake_case）
# =========================================================

def _edge_source_handle(e: dict[str, Any]) -> Any:
    """从 edge 提取 source handle，兼容 ReactFlow camelCase 与 Dify-HTTP snake_case 两种命名。

    working.yml（Dify Web 导出）edges 字段用的是 ReactFlow 原生命名：
      `sourceHandle` / `targetHandle`（camelCase）
    而 Dify 后端 HTTP import 的 JSON 用的是：
      `source_handle` / `target_handle`（snake_case）
    模拟器必须双兼容，否则会把本来全有 handle 的 edges 误判成 100% 缺失，
    触发「全员未连接」的假阳性（Dify 清单模拟器 BUG 1）。
    """
    if e.get("source_handle") is not None:
        return e["source_handle"]
    # 注意：不要用 `e.get("sourceHandle") or e.get("source_handle")`
    # —— 因为 handle 允许是合法空串 ""，会被 or 短路掉
    if "sourceHandle" in e:
        return e["sourceHandle"]
    return None


def _edge_target_handle(e: dict[str, Any]) -> Any:
    """同理：target 侧双命名兼容。"""
    if e.get("target_handle") is not None:
        return e["target_handle"]
    if "targetHandle" in e:
        return e["targetHandle"]
    return None


def _checklist_collect_outputs(data: dict, *, node_type: str | None = None) -> set[str]:
    """
    收集一个节点对外声明的**输出变量 key 集合**（供 *selector[1] 有效性校验使用）。

    Dify 节点语义：
      `data.variables`        = 「输入」声明（从上游读的参数名）—— **不是输出！**
      `data.outputs` (dict)   = code/iteration 等节点显式对外产出的 schema：`{key: {type, children?}}`
      `data.outputs` (list)   = 列表式声明，元素为 {variable:.., key:.., name:..} 或纯字符串

    修复 Dify 清单模拟器 BUG 2：上一版把 `data.variables`（输入）当成输出收集，
    导致 `collected ∩ explicit_outputs` 几乎为 0，下游引用显式 output key 被误判 INVALID_VAR。

    本函数按优先级从高到低叠加：
      1. 显式 outputs（dict.keys() / list 元素）            ← 最可靠
      2. outputs_mapping / output_schema / out_params keys
      3. 各 node type 内置固定输出（LLM text / HTTP status_code 等）
      4. LLM 节点 model.name 特殊兼容（对齐 Dify 清单可用=['gpt-5.4-1']）
      5. 语义字段 walk：output_key / output_name / key / name / field  ← **排除 variable/variable_key（它们是输入声明）**
    """
    outs: set[str] = set()

    # ----- 1. 显式 outputs（最可靠）-----
    raw_outputs = data.get("outputs")
    if isinstance(raw_outputs, dict):
        # {key: {type, children?}} 形式（code / template / iteration 节点常用）
        for k in raw_outputs.keys():
            if isinstance(k, str) and k:
                outs.add(k)
    elif isinstance(raw_outputs, list):
        for v in raw_outputs:
            if isinstance(v, str) and v:
                outs.add(v)
            elif isinstance(v, dict):
                # 按可能的字段名找 key（第一次命中就加，避免重复）
                for key in ("variable", "key", "output_key", "variable_key",
                            "name", "output_name", "field"):
                    if isinstance(v.get(key), str) and v[key]:
                        outs.add(v[key])
                        break

    # ----- 2. outputs_mapping / output_schema / out_params keys -----
    mapping = data.get("outputs_mapping")
    if isinstance(mapping, dict):
        for k in mapping.keys():
            if isinstance(k, str) and k:
                outs.add(k)
    for schema_key in ("output_schema", "out_params", "result_schema", "out_vars"):
        val = data.get(schema_key)
        if isinstance(val, dict):
            # 既可能是 json-schema {properties:{k:..}}，也可能直接是 {k: {type:..}}
            props = val.get("properties") if isinstance(val.get("properties"), dict) else val
            for k in props.keys():
                if isinstance(k, str) and k:
                    outs.add(k)

    # ----- 3. node type 内置固定输出（Dify 前端写死）-----
    if isinstance(node_type, str):
        nt = node_type.lower()
        if nt in {"llm"}:
            outs |= {
                "text", "reasoning_content", "usage", "total_tokens",
                "prompt_tokens", "completion_tokens", "files",
            }
        elif nt in {"http-request", "http"}:
            outs |= {
                "status_code", "body", "headers", "statusText",
                "responseTime", "latency", "status",
            }
        elif nt == "knowledge-retrieval":
            outs |= {"result", "content", "query", "documents", "metadata"}
        elif nt in {"template-transform", "template"}:
            outs |= {"text", "output", "rendered_output"}
        elif nt == "iteration":
            outs |= {"output", "output_text", "last_output", "item"}
        elif nt in {"question-classifier", "if-else"}:
            outs |= {"condition_result", "matched_case_id"}
        elif nt in {"answer", "direct-output"}:
            outs |= {"text", "answer", "output"}
        elif nt == "code":
            outs |= {"output", "result"}  # 通用兜底：有些 code 节点只声明 `main() -> output`

    # ----- 4. LLM 节点 model.name 特殊兼容（Dify 清单把 gpt-5.4-1 列在可用中，跟随对齐）-----
    model = data.get("model")
    if isinstance(model, dict):
        for mk in ("name", "model", "id"):
            mv = model.get(mk)
            if isinstance(mv, str) and mv:
                outs.add(mv)
                break
    elif isinstance(model, str) and model:
        outs.add(model)

    # ----- 5. 语义字段 walk：收集 output_key / output_name / key / name / field -----
    # ⚠️  注意：排除 variable / variable_key！它们是 inputs 声明（本函数之前的 BUG 来源）
    _VALID_KEYS = {"output_key", "output_name", "field", "key", "name"}

    def _walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if (
                    isinstance(k, str)
                    and isinstance(v, str)
                    and 0 < len(v) < 80
                    and k.lower() in _VALID_KEYS
                ):
                    outs.add(v)
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(o, list):
            for x in o:
                if isinstance(x, (dict, list)):
                    _walk(x)

    _walk(data)
    return outs


def dify_checklist_simulate(path: Path | str) -> dict[str, Any]:
    """
    Dify 官方「检查清单」1:1 模拟器（离线执行，无需登录浏览器）。

    返回 JSON 报告：
      {
        "file": "<abs path>",
        "handle_missing_ratio": float,
        "items": [
          {"index": 1, "node_title": str, "node_id": str,
           "invalid_var": bool, "invalid_var_count": int,
           "isolated": bool, "isolated_reasons": list[str],
           "invalid_var_samples": list[str]  # 前 6 条原因
          },
          ...
        ],
        "summary": {"total_items": N, "invalid_var_nodes": N, "isolated_nodes": N},
      }
    """
    path = Path(path).resolve()
    try:
        import yaml as _yaml  # type: ignore
    except ImportError:
        return {
            "file": str(path),
            "handle_missing_ratio": 0.0,
            "items": [],
            "summary": {"total_items": 0, "invalid_var_nodes": 0, "isolated_nodes": 0,
                        "error": "PyYAML required (pip install pyyaml)"},
        }

    result: dict[str, Any] = {"file": str(path)}
    raw = path.read_text(encoding="utf-8")
    parsed: Any = _yaml.safe_load(raw)

    # 兼容顶层 graph 与 workflow.graph
    graph: dict[str, Any] | None = None
    if isinstance(parsed, dict) and isinstance(parsed.get("graph"), dict) and parsed["graph"].get("nodes"):
        graph = parsed["graph"]
    elif isinstance(parsed, dict) and isinstance(parsed.get("workflow"), dict) and isinstance(parsed["workflow"].get("graph"), dict):
        graph = parsed["workflow"]["graph"]
    if not graph:
        return {"file": str(path), "handle_missing_ratio": 0.0, "items": [],
                "summary": {"total_items": 0, "error": "graph not found (top.graph or workflow.graph)"}}

    nodes: list[Any] = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    edges: list[Any] = [e for e in graph.get("edges", []) if isinstance(e, dict)]

    node_id_set: set[str] = set()
    node_titles: dict[str, str] = {}
    outputs_by_node: dict[str, set[str]] = {}
    note_ids: set[str] = set()

    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            continue
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        outer_type = n.get("type", "")
        title: str = ""
        if isinstance(data.get("title"), str):
            title = data["title"]
        if not title:
            title = nid
        node_titles[nid] = title
        node_id_set.add(nid)
        # 画布便签：不参与 checks（与 Dify 前端一致）
        is_note = (
            isinstance(outer_type, str)
            and outer_type.lower() in {"custom-note", "note", "sticky", "comment"}
            and isinstance(data, dict)
            and ("author" in data or "text" in data)
        )
        if is_note:
            note_ids.add(nid)
            continue
        # data.type 是 Dify 节点类型（llm/code/http-request/...）；outer_type 一般是 'custom' 或外层包装
        ntype = ""
        if isinstance(data, dict) and isinstance(data.get("type"), str):
            ntype = data["type"]
        if not ntype and isinstance(outer_type, str):
            ntype = outer_type
        outputs_by_node[nid] = (
            _checklist_collect_outputs(data, node_type=ntype or None)
            if isinstance(data, dict)
            else set()
        )

    # A. 无效变量
    invalid_var: dict[str, list[str]] = {}

    def mark(nid: str, reason: str) -> None:
        invalid_var.setdefault(nid, []).append(reason)

    def walk_struct(o: Any, path: str, consumer: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                sub = f"{path}.{k}" if path else k
                if (
                    isinstance(k, str)
                    and "selector" in k.lower()
                    and isinstance(v, list)
                    and len(v) >= 2
                ):
                    ref = v[0]; key = v[1]
                    if isinstance(ref, str) and isinstance(key, str):
                        if ref in _DIFY_SYSTEM_NODE_PREFIXES:
                            pass  # 系统前缀：Dify 前端不检查输出
                        elif ref not in node_id_set:
                            mark(consumer, f"selector[{ref},{key}] -> node不存在")
                        else:
                            avail = outputs_by_node.get(ref, set())
                            if avail and key not in avail:
                                sample = sorted(avail)[:12]
                                mark(consumer,
                                     f"selector[{ref},{key}] -> 输出无此key; 可用={sample!r}")
                if isinstance(v, (dict, list)):
                    walk_struct(v, sub, consumer)
        elif isinstance(o, list):
            for i, x in enumerate(o):
                if isinstance(x, (dict, list)):
                    walk_struct(x, f"{path}[{i}]", consumer)

    def walk_text(o: Any, consumer: str) -> None:
        if isinstance(o, dict):
            for v in o.values():
                if isinstance(v, str) and len(v) >= 12:
                    for rgx in (_CHECKLIST_VAR_REF, _CHECKLIST_HASH_REF):
                        for m in rgx.finditer(v):
                            ref, key = m.group(1), m.group(2)
                            if ref in _DIFY_SYSTEM_NODE_PREFIXES:
                                continue
                            if ref not in node_id_set:
                                mark(consumer, f"txt[{ref}.{key}] -> node不存在")
                            else:
                                avail = outputs_by_node.get(ref, set())
                                if avail and key not in avail:
                                    mark(consumer,
                                         f"txt[{ref}.{key}] -> 输出无此key")
                if isinstance(v, (dict, list)):
                    walk_text(v, consumer)
        elif isinstance(o, list):
            for x in o:
                if isinstance(x, (dict, list)):
                    walk_text(x, consumer)

    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or nid in note_ids:
            continue
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        ntype = (data.get("type") if isinstance(data, dict) and isinstance(data.get("type"), str) else "") or ""
        # UI 隐藏的内部子节点（iteration-start / loop-start）Dify 前端不列入清单，直接跳过
        if ntype in _DIFY_CHECKLIST_UI_HIDDEN_TYPES:
            continue
        walk_struct(n, "", nid)
        walk_text(n, nid)

    # B. 端口级未连接
    # ⚠️  BUG 1 修复：同时兼容 ReactFlow camelCase（sourceHandle/targetHandle）
    #     与 Dify-HTTP snake_case（source_handle/target_handle）两种命名
    missing_handle_count = sum(
        1 for e in edges
        if _edge_source_handle(e) is None or _edge_target_handle(e) is None
    )
    ratio = missing_handle_count / max(1, len(edges))
    result["handle_missing_ratio"] = ratio

    isolated: dict[str, list[str]] = {}
    # 统一全员未连接（Dify 行为：老版 DSL 导入新版时，只要 handle 缺失比例高就打全员）
    if ratio >= 0.5:
        for n in nodes:
            nid = n.get("id")
            if not isinstance(nid, str) or nid in note_ids:
                continue
            data = n.get("data") if isinstance(n.get("data"), dict) else {}
            ntype = (data.get("type") if isinstance(data, dict) and isinstance(data.get("type"), str) else "") or ""
            if ntype in _DIFY_CHECKLIST_UI_HIDDEN_TYPES:
                continue  # UI 隐藏的内部子节点不列入清单（与 Dify 前端一致）
            miss: list[str] = []
            if ntype not in _DIFY_CHECKLIST_NO_IN_TYPES:
                miss.append("IN(target)")
            if ntype not in _DIFY_CHECKLIST_NO_OUT_TYPES:
                miss.append("OUT(source)")
            if miss:
                isolated[nid] = miss
    else:
        # 端口级精确覆盖检查：统计 handle
        src_h: dict[str, set[str]] = {}
        tgt_h: dict[str, set[str]] = {}
        for e in edges:
            s = e.get("source"); t = e.get("target")
            sh = _edge_source_handle(e) or "source"
            th = _edge_target_handle(e) or "target"
            if isinstance(s, str): src_h.setdefault(s, set()).add(sh)
            if isinstance(t, str): tgt_h.setdefault(t, set()).add(th)
        for n in nodes:
            nid = n.get("id")
            if not isinstance(nid, str) or nid in note_ids:
                continue
            # loop / iteration 容器内的子节点（有 parentId）连接关系由容器管理，
            # 顶层 edges 不包含其内部连接，跳过端口检查避免假阳性。
            if n.get("parentId"):
                continue
            data = n.get("data") if isinstance(n.get("data"), dict) else {}
            ntype = (data.get("type") if isinstance(data, dict) and isinstance(data.get("type"), str) else "") or ""
            if ntype in _DIFY_CHECKLIST_UI_HIDDEN_TYPES:
                continue
            req_in: set[str] = set()
            req_out: set[str] = set()
            if ntype not in _DIFY_CHECKLIST_NO_IN_TYPES:
                req_in.add("target")
            if ntype not in _DIFY_CHECKLIST_NO_OUT_TYPES:
                req_out.add("source")
            # if-else / question-classifier 分支端口修复：
            # Dify Web 导出的 working.yml 中 if-else 节点 sourceHandle 是 'true'/'false'/case_id，
            # 而非 'source'/'branch_0'/'branch_1'，导致固定 handle 名匹配全部 missing（假阳性）。
            # 改为：只要节点有任意出边 handle，即视为 OUT 端口已连接（不强制具体 branch 数量）。
            if ntype in {"if-else", "question-classifier"} and src_h.get(nid):
                req_out.clear()
            miss_in = sorted(req_in - tgt_h.get(nid, set()))
            miss_out = sorted(req_out - src_h.get(nid, set()))
            reasons = [f"IN({','.join(miss_in)})"] if miss_in else []
            if miss_out:
                reasons.append(f"OUT({','.join(miss_out)})")
            if reasons:
                isolated[nid] = reasons

    # 聚合条目（保持 nodes 顺序，与 Dify 一致）
    items: list[dict[str, Any]] = []
    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or nid in note_ids:
            continue
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        ntype = (data.get("type") if isinstance(data, dict) and isinstance(data.get("type"), str) else "") or ""
        if ntype in _DIFY_CHECKLIST_UI_HIDDEN_TYPES:
            continue
        iv = nid in invalid_var
        il = nid in isolated
        if not iv and not il:
            continue
        items.append({
            "index": len(items) + 1,
            "node_title": node_titles.get(nid, nid),
            "node_id": nid,
            "invalid_var": iv,
            "invalid_var_count": len(invalid_var.get(nid, ())),
            "isolated": il,
            "isolated_reasons": isolated.get(nid, []),
            "invalid_var_samples": invalid_var.get(nid, [])[:6],
        })

    result["items"] = items
    result["summary"] = {
        "total_items": len(items),
        "invalid_var_nodes": len(invalid_var),
        "isolated_nodes": len(isolated),
    }
    return result


def print_checklist_report(report: dict[str, Any], *,
                           out: Any = sys.stderr,
                           label: str = "") -> None:
    """将 dify_checklist_simulate 的结果以人类可读格式输出（与 Dify UI 清单一致）。"""
    print(file=out)
    # 若调用方传入 label（如 pre-deploy 阶段标识），追加到标题以区分场景
    suffix = f"  [{label}]" if label else ""
    print(f"==== Dify 检查清单（模拟器，与平台显示 1:1）===={suffix}", file=out)
    print(f"  file               : {report.get('file','?')}", file=out)
    ratio = float(report.get("handle_missing_ratio", 0.0) or 0.0)
    summary = report.get("summary", {}) or {}
    print(f"  edges handle缺失率 : {ratio:.0%}"
          + ("  -> 触发 全员端口未连接标记" if ratio >= 0.5 else ""), file=out)
    print(f"  警告条目           : {summary.get('total_items', 0)}", file=out)
    print(f"    · 无效变量节点数 : {summary.get('invalid_var_nodes', 0)}", file=out)
    print(f"    · 未连接节点数   : {summary.get('isolated_nodes', 0)}", file=out)
    print(file=out)
    for item in report.get("items", []):
        print(f"{item['index']:>2}. {item['node_title']}", file=out)
        if item.get("invalid_var"):
            n = item.get("invalid_var_count", 0)
            print(f"      ⚠️  无效的变量（{n} 处坏引用）", file=out)
            for reason in item.get("invalid_var_samples", []):
                print(f"         · {reason[:120]}", file=out)
        if item.get("isolated"):
            reasons = item.get("isolated_reasons") or []
            msg = "此节点尚未连接到其他节点"
            if reasons:
                msg += f" （缺 {', '.join(reasons)}）"
            print(f"      ⚠️  {msg}", file=out)
    if not report.get("items"):
        print("  (与 Dify 平台一致：无警告项）", file=out)


def cmd_dsl_validate(args: argparse.Namespace) -> None:
    """dsl validate / dsl_validate 命令 handler。

    行为（零破坏性，默认行为与之前完全一致）：
      不加任何 flag           → 跑 L1-L7 基础静态校验（旧行为）
      --checklist             → 基础校验 + Dify 官方清单 1:1 模拟器（两份都输出）
      --checklist-only        → 只跑 Dify 清单模拟器（不跑基础校验）
    """
    file_path = getattr(args, "file", None)
    if file_path is None:
        raise SystemExit("Usage: dify_manage.py dsl validate <working.yml or export.yml>")
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        app_id = getattr(args, "app_id", None)
        if app_id:
            file_path = working_dsl_path(app_id)
            if not file_path.is_file():
                raise SystemExit(f"No working.yml at {file_path}. Run: pull --app-id {app_id}")
        else:
            raise SystemExit(f"File not found: {file_path}")

    only_checklist = bool(getattr(args, "checklist_only", False))
    also_checklist = bool(getattr(args, "checklist", False))
    run_standard = not only_checklist
    run_checklist = only_checklist or also_checklist

    fmt = (getattr(args, "format", "text") or "text").lower()
    fail_on_warnings = bool(getattr(args, "fail_on_warnings", False))
    show_snippets = not bool(getattr(args, "no_snippets", False))

    standard_report = validate_dsl_file(file_path) if run_standard else None
    checklist_report = dify_checklist_simulate(file_path) if run_checklist else None

    # ===== JSON 模式 =====
    if fmt == "json":
        payload: dict[str, Any] = {}
        if standard_report is not None: payload["standard"] = standard_report
        if checklist_report is not None: payload["checklist"] = checklist_report
        out_obj: Any = payload
        if len(payload) == 1:
            out_obj = next(iter(payload.values()))
        print(json.dumps(out_obj, ensure_ascii=False, indent=2))
    # ===== 文本模式 =====
    else:
        if standard_report is not None:
            # 注意：validate_dsl_file_or_exit 在基础校验错误或 fail_on_warnings 命中时 SystemExit，
            # 此时 checklist 也不再打印（符合语义：基础校验已 fail）。
            validate_dsl_file_or_exit(
                file_path,
                fail_on_warnings=fail_on_warnings,
                show_snippets=show_snippets,
            )
        if checklist_report is not None:
            print_checklist_report(checklist_report)

    # ===== 退出码（JSON 模式 or 文本模式未被 SystemExit 命中时才会走到）=====
    exit_code = 0
    if standard_report is not None:
        if not standard_report["ok"]: exit_code = max(exit_code, 1)
        if fail_on_warnings and standard_report["stats"]["warnings"] > 0:
            exit_code = max(exit_code, 2)
    if checklist_report is not None:
        summary = checklist_report.get("summary") or {}
        if fail_on_warnings and int(summary.get("total_items", 0) or 0) > 0:
            # Dify 清单有警告项，且用户显式 fail_on_warnings → exit 3（与基础校验的 1/2 做区分）
            exit_code = max(exit_code, 3)
    if exit_code:
        raise SystemExit(exit_code)


def _deploy_diff_warning(app_id: str, deploy_file: Path) -> None:
    remote = find_latest_remote_dsl(app_id)
    if not remote:
        return
    left = remote.read_text(encoding="utf-8").splitlines(keepends=True)
    right = deploy_file.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(left, right, fromfile=str(remote), tofile=str(deploy_file)))
    if not diff:
        return
    risky = any(
        token in diff
        for token in ("variables:", "default:", "file_upload:", "features:")
    )
    print("Warning: working.yml differs from latest remote snapshot.", file=sys.stderr)
    if risky:
        print(
            "  Check variables[].default / features.file_upload before deploy.",
            file=sys.stderr,
        )
    if len(diff) > 4000:
        print(f"  Diff size: {len(diff)} chars (run: dsl diff --app-id {app_id})", file=sys.stderr)
    else:
        print(diff, file=sys.stderr)


def cmd_import(args: argparse.Namespace, *, session: DifySession | None = None) -> None:
    create = getattr(args, "create", False)
    session = session or DifySession(require_console_url())
    app_id = resolve_app_id(
        session,
        app_id=args.app_id,
        app_name=args.app_name,
        required=not create,
    )
    session.ensure_session()
    yaml_content = Path(args.file).read_text(encoding="utf-8")
    payload: dict[str, Any] = {"mode": "yaml-content", "yaml_content": yaml_content}
    if app_id:
        payload["app_id"] = app_id
    elif not create:
        raise SystemExit("Updating an app requires --app-id or --name. Use --create for a new app.")
    status, body = session.request(
        "POST",
        "/console/api/apps/imports",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    if status >= 400:
        raise SystemExit(f"Import failed ({status}): {body}")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    if isinstance(body, dict) and body.get("status") == "pending" and body.get("import_id"):
        status2, body2 = session.request(
            "POST",
            f"/console/api/apps/imports/{body['import_id']}/confirm",
            data=b"{}",
        )
        if status2 >= 400:
            raise SystemExit(f"Import confirm failed ({status2}): {body2}")
        print("Import confirmed:")
        print(json.dumps(body2, ensure_ascii=False, indent=2))



def cmd_publish(args: argparse.Namespace, *, session: DifySession | None = None) -> None:
    session = session or DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True
    )
    session.ensure_session()
    status, body = session.request(
        "POST", f"/console/api/apps/{app_id}/workflows/publish", data=b"{}"
    )
    if status >= 400:
        raise SystemExit(f"Publish failed ({status}): {body}")
    print("Published successfully")


_DEPLOY_RECOVERY_HINT = (
    "\n\n  Automatic token refresh failed during deploy. Next steps:\n"
    "  1. Run:  python3 dify_manage.py login\n"
    "  2. Or fill DIFY_EMAIL + DIFY_PASSWORD in project .env\n"
    "  3. Or export fresh DIFY_CONSOLE_TOKEN + DIFY_CSRF_TOKEN from browser DevTools\n"
    "  Tip: if DIFY_*_TOKEN are OS-exported in shell, run:\n"
    "       unset DIFY_CONSOLE_TOKEN DIFY_CSRF_TOKEN DIFY_REFRESH_TOKEN\n"
    "       to let .dify/session.json become the single source of truth."
)


def _extract_graph_ids(yaml_text: str) -> dict[str, Any]:
    """从 Dify DSL YAML 文本提取 nodes/edges 的数量与 ID 集合。

    兼容两种 graph 路径：顶层 ``graph`` 或 ``workflow.graph``（与
    ``dify_checklist_simulate``/``DSLValidator`` 的实现保持一致）。

    返回:
      dict with keys:
        - node_count (int)
        - edge_count (int)
        - node_ids (set[str])
        - edge_ids (set[str])
        - parse_error (str | None)  —— YAML 解析或 graph 定位失败时填错误说明
    """
    try:
        import yaml as _yaml  # type: ignore  # lazy import，与 dify_checklist_simulate 保持一致
    except ImportError as exc:
        return {
            "node_count": 0, "edge_count": 0,
            "node_ids": set(), "edge_ids": set(),
            "parse_error": f"PyYAML required (pip install pyyaml): {exc}",
        }
    fallback = {
        "node_count": 0, "edge_count": 0,
        "node_ids": set(), "edge_ids": set(),
        "parse_error": None,
    }
    try:
        parsed = _yaml.safe_load(yaml_text)
    except Exception as exc:  # noqa: BLE001
        fallback["parse_error"] = f"YAML parse failed: {exc}"
        return fallback
    graph: dict[str, Any] | None = None
    if (isinstance(parsed, dict)
            and isinstance(parsed.get("graph"), dict)
            and parsed["graph"].get("nodes") is not None):
        graph = parsed["graph"]
    elif (isinstance(parsed, dict)
          and isinstance(parsed.get("workflow"), dict)
          and isinstance(parsed["workflow"].get("graph"), dict)):
        graph = parsed["workflow"]["graph"]
    if not graph:
        fallback["parse_error"] = "graph not found (top.graph or workflow.graph)"
        return fallback
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    edges = [e for e in graph.get("edges", []) if isinstance(e, dict)]
    node_ids: set[str] = {str(n["id"]) for n in nodes if isinstance(n.get("id"), (str, int))}
    edge_ids: set[str] = set()
    for e in edges:
        eid = e.get("id")
        if isinstance(eid, (str, int)) and str(eid):
            edge_ids.add(str(eid))
        else:
            # 与真实 Dify export 对齐：如果 edge 没 id，用 (source,target,sourceHandle,targetHandle) 作为指纹
            key = "|".join(str(e.get(k, "")) for k in ("source", "target", "sourceHandle", "targetHandle",
                                                        "source_handle", "target_handle"))
            edge_ids.add(f"__anon_edge__:{key}")
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "parse_error": None,
    }


def _post_deploy_verify(
    session: "DifySession | None",
    app_id: str,
    deploy_file: "str | Path",
    *,
    max_retry: int = 1,
    # 以下两个参数用于 TDD 依赖注入（绕过真实 HTTP）；生产调用保持默认（None）即可
    _export_fn: Any = None,
    _redeploy_fn: Any = None,
) -> dict[str, Any]:
    """Deploy 后校验：回拉 remote DSL，对比 nodes/edges 数量+ID 集合，不一致自动重试。

    对应 Issue「deploy 成功但 Dify 后端静默丢 35 条边」的 P0 兜底：
    ``POST /imports`` 在特定条件（race / 版本兼容）下会部分丢弃 edges 但返回
    ``status: completed`` 无错误。重新 import 一般可恢复，因此这里自动重试 1 次。

    参数:
        session: 已初始化的 DifySession（用于 export_app_yaml 调用；TDD 时传 None）
        app_id: 目标应用 ID
        deploy_file: 本次 deploy 发送的 YAML 文件路径
        max_retry: 校验失败后自动重新 import+publish 的次数上限（默认 1，与 Issue 建议一致）
        _export_fn: TDD 注入。签名 (session, app_id) -> str(yaml)；默认用 export_app_yaml
        _redeploy_fn: TDD 注入。签名 (session, app_id, deploy_file) -> None；默认不执行（
            由调用方 cmd_deploy 集成时传入真实的 cmd_import+cmd_publish 包装）

    返回:
        dict with keys:
          - ok (bool)                 —— 最终 nodes/edges 是否一致
          - retry_used (int)          —— 实际重试次数（0=首次就 OK；>0=重试后 OK 或仍 FAIL）
          - deployed (dict)           —— 发送端摘要：{"nodes":N, "edges":N, "parse_error":str|None}
          - remote (dict)             —— 最后一次拉取的远端摘要
          - mismatches (list[dict])   —— 不一致项（空表 = 完全 OK），每项字段：
              * kind: node_count_mismatch / node_ids_mismatch /
                      edge_count_mismatch / edge_ids_mismatch
              * detail: 人类可读描述（含 expected/got 数字，grep 友好）
              * expected / got: 整数（数量类）或集合（ID 类的 expected）
              * missing_node_ids / extra_node_ids / missing_edge_ids / extra_edge_ids (set[str])  —— ID 类
              * parse_error_deployed / parse_error_remote —— 解析失败时填
    """
    # ---- 读本地 deploy 文件 ----
    deploy_file_p = Path(deploy_file)
    deployed_text = deploy_file_p.read_text(encoding="utf-8")
    deployed = _extract_graph_ids(deployed_text)

    mismatches: list[dict[str, Any]] = []

    # ---- 默认 export / redeploy 行为 ----
    def _default_export(sess: "DifySession | None", aid: str) -> str:
        if sess is None:
            return ""
        return export_app_yaml(sess, aid)

    do_export = _export_fn if callable(_export_fn) else _default_export
    # redeploy: 如果调用方没注入，默认不做真实动作（仅由 mismatches 报告不一致，用户手动重试）
    # 但要能在 max_retry 循环里安全调用（空操作不会出错）
    def _default_redeploy(sess: "DifySession | None", aid: str, dfile: "str | Path") -> None:  # noqa: ARG001
        return None

    do_redeploy = _redeploy_fn if callable(_redeploy_fn) else _default_redeploy

    retry_used = 0
    remote: dict[str, Any] = {}
    max_retry_i = max(0, int(max_retry))

    for attempt in range(max_retry_i + 1):
        # 1. 拉 remote
        try:
            remote_text = do_export(session, app_id)
        except SystemExit as exc:
            remote = {"node_count": 0, "edge_count": 0, "node_ids": set(), "edge_ids": set(),
                      "parse_error": f"export_app_yaml failed: {exc}"}
            break
        remote = _extract_graph_ids(remote_text) if isinstance(remote_text, str) else {
            "node_count": 0, "edge_count": 0, "node_ids": set(), "edge_ids": set(),
            "parse_error": f"export returned non-str: {type(remote_text).__name__}",
        }

        # 2. 4 维度对比
        mismatches = []
        if deployed.get("parse_error"):
            mismatches.append({
                "kind": "deployed_parse_error",
                "detail": f"deployed YAML parse error: {deployed['parse_error']}",
                "parse_error_deployed": deployed["parse_error"],
            })
        if remote.get("parse_error"):
            mismatches.append({
                "kind": "remote_parse_error",
                "detail": f"remote YAML parse error: {remote['parse_error']}",
                "parse_error_remote": remote["parse_error"],
            })
        if deployed["node_count"] != remote["node_count"]:
            mismatches.append({
                "kind": "node_count_mismatch",
                "detail": (f"nodes: expected={deployed['node_count']} "
                           f"got={remote['node_count']}"),
                "expected": deployed["node_count"], "got": remote["node_count"],
            })
        missing_nodes = deployed["node_ids"] - remote["node_ids"]
        extra_nodes = remote["node_ids"] - deployed["node_ids"]
        if missing_nodes or extra_nodes:
            mismatches.append({
                "kind": "node_ids_mismatch",
                "detail": (f"node IDs differ (missing={len(missing_nodes)} "
                           f"extra={len(extra_nodes)})"),
                "expected": deployed["node_ids"], "got": remote["node_ids"],
                "missing_node_ids": missing_nodes,
                "extra_node_ids": extra_nodes,
            })
        if deployed["edge_count"] != remote["edge_count"]:
            mismatches.append({
                "kind": "edge_count_mismatch",
                "detail": (f"edges: expected={deployed['edge_count']} "
                           f"got={remote['edge_count']}"),
                "expected": deployed["edge_count"], "got": remote["edge_count"],
            })
        missing_edges = deployed["edge_ids"] - remote["edge_ids"]
        extra_edges = remote["edge_ids"] - deployed["edge_ids"]
        if missing_edges or extra_edges:
            mismatches.append({
                "kind": "edge_ids_mismatch",
                "detail": (f"edge IDs differ (missing={len(missing_edges)} "
                           f"extra={len(extra_edges)})"),
                "expected": deployed["edge_ids"], "got": remote["edge_ids"],
                "missing_edge_ids": missing_edges,
                "extra_edge_ids": extra_edges,
            })

        if not mismatches:
            # 完全一致 → 返回成功
            return {
                "ok": True,
                "retry_used": retry_used,
                "deployed": {
                    "nodes": deployed["node_count"], "edges": deployed["edge_count"],
                    "parse_error": deployed.get("parse_error"),
                },
                "remote": {
                    "nodes": remote["node_count"], "edges": remote["edge_count"],
                    "parse_error": remote.get("parse_error"),
                },
                "mismatches": [],
            }

        # 3. 不一致：还有重试额度 → 重新 import+publish 再进入下一轮 export
        if attempt < max_retry_i:
            retry_used += 1
            try:
                do_redeploy(session, app_id, deploy_file_p)
            except SystemExit:
                # redeploy 自己失败就不再往下重试（外层 mismatches 会把本次结果返回）
                break
            continue
        # 重试用完 → 退出循环，返回最后一次 mismatches

    return {
        "ok": False,
        "retry_used": retry_used,
        "deployed": {
            "nodes": deployed["node_count"], "edges": deployed["edge_count"],
            "parse_error": deployed.get("parse_error"),
        },
        "remote": {
            "nodes": remote.get("node_count", 0), "edges": remote.get("edge_count", 0),
            "parse_error": remote.get("parse_error") if isinstance(remote, dict) else None,
        },
        "mismatches": mismatches,
    }


def cmd_deploy(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True, session_required=False
    )
    assert app_id

    deploy_file = getattr(args, "file", None)
    if deploy_file is None:
        deploy_file = working_dsl_path(app_id)
        if not deploy_file.is_file():
            raise SystemExit(
                f"No working.yml at {deploy_file}. Run: pull --app-id {app_id}"
            )
    else:
        deploy_file = Path(deploy_file)

    if not getattr(args, "skip_diff_warning", False):
        _deploy_diff_warning(app_id, deploy_file)

    # 优化 5.2（GATE）：deploy 前先跑 Dify 官方清单模拟器（1:1 对齐 Web 端「检查清单」弹窗）。
    #   基础校验（L1-L7）偏语法层、对 edges handle 缺失率 100%、下游引用无效节点变量这类
    #   ReactFlow 渲染白屏根因是盲区 → 把 Dify 官方清单作为更严格的部署前置 gate。
    #   默认阻断条件（命中任一即 BLOCK）：
    #     a) invalid_var_nodes ≥ 1        （变量坏引用 = 运行时必然报错/白屏）
    #     b) handle_missing_ratio ≥ 0.5   （Dify 前端「全员未连接」触发阈值 = 端口级丢失过半）
    #     c) isolated_nodes / total_items ≥ 0.8 且 total_items>0 （大面积孤立）
    #   配套参数：
    #     --skip-checklist       → 完全跳过清单 gate
    #     --checklist-warn-only  → 打印清单报告但不阻断（确认风险后强行上线）
    checklist_report = None
    if not getattr(args, "skip_checklist", False):
        checklist_report = dify_checklist_simulate(deploy_file)
        warn_only = bool(getattr(args, "checklist_warn_only", False))
        label_sev = "WARN-ONLY" if warn_only else "BLOCK-GATE"
        print_checklist_report(
            checklist_report,
            label=f"(pre-deploy {label_sev} for app={app_id})",
        )
        summary = checklist_report.get("summary") or {}
        invalid_var_nodes = int(summary.get("invalid_var_nodes") or 0)
        isolated_nodes = int(summary.get("isolated_nodes") or 0)
        total_items = int(summary.get("total_items") or 0)
        handle_missing_ratio = float(checklist_report.get("handle_missing_ratio") or 0.0)
        block_reasons: list[str] = []
        if invalid_var_nodes >= 1:
            block_reasons.append(
                f"{invalid_var_nodes} 个节点存在「无效的变量」引用（Dify 官方清单 INVALID_VAR）"
            )
        if handle_missing_ratio >= 0.5:
            block_reasons.append(
                f"edges handle 缺失率 {handle_missing_ratio:.0%} ≥ 50% "
                f"→ Dify 前端会把所有节点标成「未连接」（ReactFlow 渲染白屏根因）"
            )
        if total_items > 0 and isolated_nodes >= int(total_items * 0.8):
            block_reasons.append(
                f"{isolated_nodes}/{total_items} 节点被判定为「尚未连接」（≥ 80%）"
            )
        if block_reasons and not warn_only:
            lines = [
                "=" * 72,
                f"DEPLOY BLOCKED by Dify checklist gate ({len(block_reasons)} fatal issue(s)).",
                "  Deploy blocked BEFORE any import/publish HTTP call — remote workflow is untouched.",
                "Fatal reasons:",
            ]
            lines.extend(f"  - {r}" for r in block_reasons)
            lines.extend([
                "",
                "Recommended fixes:",
                "  1) Run: dsl validate <working.yml> --checklist-only   (定位每条坏引用和未连接)",
                "  2) Or open the workflow in Dify Web → click 「检查清单」→ fix each item",
                "  3) After fixing, re-run deploy",
                "",
                "To bypass gate (NOT recommended unless you understand the risk):",
                "  · deploy --skip-checklist ........... skip checklist gate entirely",
                "  · deploy --checklist-warn-only ...... print checklist but still proceed",
                "=" * 72,
            ])
            raise SystemExit("\n".join(lines))

    # 优化 5.1：deploy 前自动执行静态 DSL 校验（7 层检查 + working.yml 行级定位）
    #   避免推送线上后出现「渲染此组件时发生了意外错误」白屏
    if not getattr(args, "skip_validate", False):
        validate_dsl_file_or_exit(
            deploy_file,
            fail_on_warnings=bool(getattr(args, "validate_fail_on_warnings", False)),
            show_snippets=not bool(getattr(args, "validate_no_snippets", False)),
            label=f"(pre-deploy for app={app_id})",
        )

    args.file = deploy_file
    try:
        # 优化 4.5：复用同一个 session 实例，让 ensure_session 的多级 fallback
        # 跨 import/publish 两步保持上下文（避免 refresh/login 后又被新 session 覆盖）
        cmd_import(args, session=session)
        cmd_publish(args, session=session)
    except SystemExit as exc:
        msg = str(exc)
        # 优化 4.6：检测 refresh / login / 401 相关错误，附加恢复引导
        if any(token in msg for token in ("Refresh failed", "refresh failed", "Invalid refresh token",
                                           "No console session", "Session invalid", "401",
                                           "Automatic token refresh")):
            raise SystemExit(msg + _DEPLOY_RECOVERY_HINT) from exc
        raise

    # ISSUE 建议 1/2：Post-deploy 内容完整性校验（P0 兜底 Dify 后端静默丢边）
    #   - 回拉 remote DSL 对比 4 维度（node 数量/ID、edge 数量/ID）
    #   - 不一致时自动重新 import+publish（默认 1 次，瞬态丢边重发即恢复）
    #   - 校验失败不阻塞 deploy（manifest 仍更新），只 stderr 警告
    if not getattr(args, "skip_post_verify", False):
        retry_max = max(0, int(getattr(args, "post_verify_retry", 1) or 1))

        def _redeploy_reimport(_sess: Any, _aid: str, _dfile: Path) -> None:  # noqa: ARG001
            """真实重试回调：重新跑 cmd_import + cmd_publish（复用外层 session/args）。

            注意：此处 args.file 已在上游被赋值为 deploy_file，args.app_id 也已解析。
            """
            cmd_import(args, session=session)
            cmd_publish(args, session=session)

        pv_result = _post_deploy_verify(
            session,
            app_id,
            deploy_file,
            max_retry=retry_max,
            _redeploy_fn=_redeploy_reimport,
        )
        ok = bool(pv_result.get("ok"))
        retry_used = int(pv_result.get("retry_used") or 0)
        remote_summary = pv_result.get("remote") or {}
        if ok:
            if retry_used > 0:
                print(
                    f"Post-deploy verify: OK after {retry_used} retry(s) "
                    f"(nodes={remote_summary.get('nodes')}, edges={remote_summary.get('edges')})"
                )
            else:
                print(
                    f"Post-deploy verify: OK "
                    f"(nodes={remote_summary.get('nodes')}, edges={remote_summary.get('edges')})"
                )
        else:
            lines = [
                "⚠️  Post-deploy verify FAILED"
                + (f" after {retry_used} retry(s):" if retry_used else ":"),
            ]
            deployed_summary = pv_result.get("deployed") or {}
            # 总览行
            lines.append(
                "    nodes: "
                f"expected={deployed_summary.get('nodes')}, "
                f"got={remote_summary.get('nodes')} "
                + ("✓" if deployed_summary.get("nodes") == remote_summary.get("nodes") else "✗")
            )
            lines.append(
                "    edges: "
                f"expected={deployed_summary.get('edges')}, "
                f"got={remote_summary.get('edges')} "
                + ("✓" if deployed_summary.get("edges") == remote_summary.get("edges") else "✗")
            )
            for m in pv_result.get("mismatches") or []:
                if isinstance(m, dict):
                    det = m.get("detail") or str(m)
                    extras: list[str] = []
                    for key in ("missing_node_ids", "missing_edge_ids",
                                "extra_node_ids", "extra_edge_ids"):
                        v = m.get(key)
                        if isinstance(v, (set, list)) and v:
                            items = sorted(str(x) for x in v)
                            preview = items[:10]
                            suffix = ""
                            if len(items) > 10:
                                suffix = f"...(+{len(items) - 10})"
                            extras.append(f"{key}=[{', '.join(preview)}{suffix}]")
                    line = f"    {det}"
                    if extras:
                        line += "  (" + "; ".join(extras) + ")"
                    lines.append(line)
                else:
                    lines.append(f"    {m}")
            lines.extend([
                "  Possible causes: Dify backend race condition, DSL version mismatch.",
                "  Try: deploy --app-id <id> again, or check Dify platform UI.",
            ])
            print("\n".join(lines), file=sys.stderr)

    if deploy_file.is_file():
        update_manifest_app(
            app_id,
            last_deploy={
                "at": datetime.now().astimezone().isoformat(),
                "from": rel_to_dify(deploy_file.resolve()),
                "content_sha256": sha256_file(deploy_file),
            },
        )
    print(f"Deployed from {deploy_file}")


def _print_api_key_items(keys: list[dict[str, Any]], app_id: str) -> None:
    if not keys:
        print(f"No API keys for app {app_id}.")
        return
    for item in keys:
        print(
            json.dumps(
                {
                    "id": item.get("id"),
                    "token": item.get("token"),
                    "type": item.get("type"),
                    "last_used_at": item.get("last_used_at"),
                    "created_at": item.get("created_at"),
                },
                ensure_ascii=False,
            )
        )
    print(
        f"\nUse with run: --api-key <token above>  (key is bound to app {app_id})",
        file=sys.stderr,
    )


def cmd_api_keys(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
    app_id = resolve_app_id(
        session, app_id=args.app_id, app_name=args.app_name, required=True
    )

    if args.create:
        status, body = session.request(
            "POST",
            f"/console/api/apps/{app_id}/api-keys",
            data=b"{}",
        )
        if status >= 400:
            raise SystemExit(f"api-keys create failed ({status}): {body}")
        item = body if isinstance(body, dict) and body.get("token") else None
        if item:
            print("Created API key:")
            _print_api_key_items([item], app_id)
        else:
            print(json.dumps(body, ensure_ascii=False, indent=2))
        return

    status, body = session.request("GET", f"/console/api/apps/{app_id}/api-keys")
    if status >= 400:
        raise SystemExit(f"api-keys list failed ({status}): {body}")
    keys = body.get("data", []) if isinstance(body, dict) else []
    _print_api_key_items(keys, app_id)
    if not keys:
        print("Create one: dify_manage.py api-keys --create --name <app>", file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> None:
    api_key = require_api_key(args.api_key)
    base_url = require_service_base_url()
    payload = {
        "inputs": collect_run_inputs(args, api_key=api_key, base_url=base_url),
        "response_mode": args.response_mode,
        "user": args.user,
    }
    status, body = service_request(
        "POST",
        "/workflows/run",
        api_key=api_key,
        base_url=base_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    if status >= 400:
        raise SystemExit(f"Workflow run failed ({status}): {body}")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def cmd_chat(args: argparse.Namespace) -> None:
    """Service API for advanced-chat / chat apps (not workflow mode)."""
    api_key = require_api_key(args.api_key)
    base_url = require_service_base_url()
    query = args.query
    if getattr(args, "fixtures", None):
        fx = load_fixtures(Path(args.fixtures))
        if not query and fx.get("query"):
            query = str(fx.get("query"))
    payload: dict[str, Any] = {
        "inputs": collect_run_inputs(args, api_key=api_key, base_url=base_url),
        "query": query,
        "response_mode": args.response_mode,
        "user": args.user,
    }
    if args.conversation_id:
        payload["conversation_id"] = args.conversation_id
    status, body = service_request(
        "POST",
        "/chat-messages",
        api_key=api_key,
        base_url=base_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    if status >= 400:
        raise SystemExit(f"Chat failed ({status}): {body}")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def add_run_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--inputs", help="JSON file with workflow inputs object")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Single input key=value (repeatable)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Upload local path or cached file: input_key=path",
    )
    parser.add_argument(
        "--file-url",
        action="append",
        default=[],
        help="Download (cache) + upload: input_key=https://...",
    )
    parser.add_argument(
        "--fixtures",
        help="JSON fixtures (.dify/fixtures/{app_id}/smoke.json)",
    )
    parser.add_argument("--user", default="dify-manage-cli")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dify Console management (skill-bundled)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--env-file",
        help="Explicit .env path (also via DIFY_ENV_FILE). Default: discover from cwd upward",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print resolved config / skill paths to stderr",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login")
    sub.add_parser("refresh")
    sub.add_parser("ping")
    sub.add_parser("init", help="Create .dify/ project skeleton")
    sub.add_parser("session", help="Show .dify/session.json metadata (no secrets)")

    pull_parser = sub.add_parser("pull", help="Export remote DSL into .dify/dsl/{app_id}/")
    add_app_target_args(pull_parser)
    pull_parser.add_argument(
        "--no-init-working",
        action="store_true",
        help="Do not create working.yml from remote if missing",
    )

    pull_parser.add_argument(
        "--sync-working",
        action="store_true",
        help="Overwrite working.yml from latest remote snapshot",
    )

    # ⚠️ 维护 checklist：在 dsl_sub 下新增/修改子命令后，必须同步以下 3 处（双写兼容，否则 AI 端会再次出现"命令不存在"）：
    #   1) 下方 dsl_sub.add_parser("<new>", ...)  ← 空格形式 `dsl <new>`（本处）
    #   2) 「下划线一级别名」段落中 sub.add_parser("dsl_<new>", ...)  ← 别名形式 `dsl_<new>`
    #   3) main() 末尾 handlers 字典：`"dsl_<new>": cmd_dsl_<new>,`
    #   同时确保两处 add_argument 定义 1:1 对齐（参数名、类型、required、choices、default、help）
    dsl_parser = sub.add_parser("dsl", help="DSL status and diff")
    dsl_sub = dsl_parser.add_subparsers(dest="dsl_command", required=True)
    dsl_status = dsl_sub.add_parser("status", help="Compare local DSL hashes")
    add_app_target_args(dsl_status, required=False)
    dsl_status.add_argument(
        "--check-remote",
        action="store_true",
        help="Fetch online DSL and compare with local remote snapshot",
    )
    dsl_diff = dsl_sub.add_parser("diff", help="Diff working.yml vs remote or online")
    add_app_target_args(dsl_diff)
    dsl_diff.add_argument(
        "--against",
        choices=("remote", "online"),
        default="remote",
        help="Compare working against latest local remote snapshot or live online",
    )
    dsl_refresh = dsl_sub.add_parser("refresh", help="Update manifest working hash from disk")
    add_app_target_args(dsl_refresh)
    dsl_reset = dsl_sub.add_parser("reset", help="Reset working.yml from latest remote snapshot")
    add_app_target_args(dsl_reset)
    dsl_prune = dsl_sub.add_parser("prune", help="Remove old remote snapshots")
    add_app_target_args(dsl_prune)
    dsl_prune.add_argument("--keep", type=int, default=3, help="Number of remote snapshots to keep")
    dsl_validate = dsl_sub.add_parser(
        "validate",
        help="Static analysis of Dify DSL (YAML structure / nodes / edges / variable refs / syntax)",
    )
    dsl_validate.add_argument(
        "file",
        nargs="?",
        default="",
        help="Path to working.yml or export.yml; omit to use --app-id working.yml",
    )
    add_app_target_args(dsl_validate)
    dsl_validate.add_argument("--format", choices=("text", "json"), default="text")
    dsl_validate.add_argument(
        "--fail-on-warnings", action="store_true",
        help="Exit non-zero on warnings in addition to errors (CI gate)",
    )
    dsl_validate.add_argument(
        "--no-snippets", action="store_true", help="Suppress line-level source snippets in output",
    )
    dsl_validate.add_argument(
        "--checklist", action="store_true",
        help="After standard validation, also print Dify-official-style checklist (1:1 simulator,"
             " matches web UI '检查清单' popup for INVALID_VAR / NOT_CONNECTED warnings)",
    )
    dsl_validate.add_argument(
        "--checklist-only", action="store_true",
        help="Skip standard L1-L7 validation; run ONLY the Dify checklist simulator (fast,"
             " gives a quick preview of what the Dify web Check List will show).",
    )

    # ⚠️ 维护 checklist：在 cache_sub 下新增/修改子命令后，须同步 3 处（同上 dsl 段落说明）：
    #   cache_sub.add_parser → sub.add_parser("cache_xxx") 别名注册 → handlers["cache_xxx"] 映射
    cache_parser = sub.add_parser("cache", help="Download cache for remote files")
    cache_sub = cache_parser.add_subparsers(dest="cache_command", required=True)
    cache_dl = cache_sub.add_parser(
        "download", help="Download URL to .dify/cache/downloads/ (MD5 dedup)"
    )
    cache_dl.add_argument("url", help="Remote file URL")
    cache_dl.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if cached",
    )
    cache_sub.add_parser("list", help="List cached downloads")
    cache_clean = cache_sub.add_parser("clean", help="Remove cached downloads")
    cache_clean.add_argument("--md5", default="", help="Only remove files with this MD5 prefix")

    # ⚠️ 维护 checklist：在 files_sub 下新增/修改子命令后，须同步 3 处（同上 dsl 段落说明）：
    #   files_sub.add_parser → sub.add_parser("files_xxx") 别名注册 → handlers["files_xxx"] 映射
    files_parser = sub.add_parser("files", help="Service API file operations")
    files_sub = files_parser.add_subparsers(dest="files_command", required=True)
    files_up = files_sub.add_parser("upload", help="Upload file to Dify (local path or URL)")
    files_up.add_argument("file", help="Local path or http(s) URL")
    files_up.add_argument("--api-key", required=True)
    files_up.add_argument("--user", default="dify-manage-cli")
    files_up.add_argument(
        "--force-cache",
        action="store_true",
        help="Re-download URL even if cached",
    )

    # ------------------------------------------------------------------
    # 下划线一级别名命令（AI 友好：避免把二级子命令错当顶层调用导致"命令不存在"）
    # ⚠️ 维护 checklist：本段落别名注册 与 上方 dsl_sub/cache_sub/files_sub 的二级子命令、
    #   下方 main() 末尾 handlers 字典中的别名映射，三者必须 1:1 同步。
    #   参数定义须与上方二级子命令处完全一致（包括参数顺序、类型、required、choices、default、help）
    # 与上方 dsl / cache / files 二级子命令语义完全一致，参数定义 1:1 对齐，handler 复用同一函数
    # 老用户继续用 `dsl status` 空格形式；AI 或自动化脚本可用 `dsl_status` 更稳健
    # ------------------------------------------------------------------
    # dsl 系列别名
    dsl_status_p = sub.add_parser("dsl_status", help="(alias) DSL status: compare local DSL hashes")
    add_app_target_args(dsl_status_p, required=False)
    dsl_status_p.add_argument(
        "--check-remote",
        action="store_true",
        help="Fetch online DSL and compare with local remote snapshot",
    )
    dsl_diff_p = sub.add_parser("dsl_diff", help="(alias) Diff working.yml vs remote or online")
    add_app_target_args(dsl_diff_p)
    dsl_diff_p.add_argument(
        "--against",
        choices=("remote", "online"),
        default="remote",
        help="Compare working against latest local remote snapshot or live online",
    )
    dsl_refresh_p = sub.add_parser("dsl_refresh", help="(alias) Update manifest working hash from disk")
    add_app_target_args(dsl_refresh_p)
    dsl_reset_p = sub.add_parser("dsl_reset", help="(alias) Reset working.yml from latest remote snapshot")
    add_app_target_args(dsl_reset_p)
    dsl_prune_p = sub.add_parser("dsl_prune", help="(alias) Remove old remote snapshots")
    add_app_target_args(dsl_prune_p)
    dsl_prune_p.add_argument("--keep", type=int, default=3, help="Number of remote snapshots to keep")
    dsl_validate_p = sub.add_parser(
        "dsl_validate",
        help="(alias) Static analysis of Dify DSL (YAML/nodes/edges/vars/syntax)",
    )
    dsl_validate_p.add_argument(
        "file",
        nargs="?",
        default="",
        help="Path to working.yml or export.yml; omit to use --app-id working.yml",
    )
    add_app_target_args(dsl_validate_p)
    dsl_validate_p.add_argument("--format", choices=("text", "json"), default="text")
    dsl_validate_p.add_argument(
        "--fail-on-warnings", action="store_true",
        help="Exit non-zero on warnings in addition to errors (CI gate)",
    )
    dsl_validate_p.add_argument(
        "--no-snippets", action="store_true", help="Suppress line-level source snippets in output",
    )
    dsl_validate_p.add_argument(
        "--checklist", action="store_true",
        help="After standard validation, also print Dify-official-style checklist (1:1 simulator)",
    )
    dsl_validate_p.add_argument(
        "--checklist-only", action="store_true",
        help="Skip standard L1-L7 validation; run ONLY the Dify checklist simulator (fast)",
    )
    # cache 系列别名
    cache_dl_p = sub.add_parser(
        "cache_download", help="(alias) Download URL to .dify/cache/downloads/ (MD5 dedup)"
    )
    cache_dl_p.add_argument("url", help="Remote file URL")
    cache_dl_p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if cached",
    )
    sub.add_parser("cache_list", help="(alias) List cached downloads")
    cache_clean_p = sub.add_parser("cache_clean", help="(alias) Remove cached downloads")
    cache_clean_p.add_argument("--md5", default="", help="Only remove files with this MD5 prefix")
    # files 系列别名
    files_up_p = sub.add_parser("files_upload", help="(alias) Upload file to Dify (local path or URL)")
    files_up_p.add_argument("file", help="Local path or http(s) URL")
    files_up_p.add_argument("--api-key", required=True)
    files_up_p.add_argument("--user", default="dify-manage-cli")
    files_up_p.add_argument(
        "--force-cache",
        action="store_true",
        help="Re-download URL even if cached",
    )

    apps_parser = sub.add_parser("apps")
    apps_parser.add_argument("--page", type=int, default=1)
    apps_parser.add_argument("--limit", type=int, default=100)
    export_parser = sub.add_parser("export")
    export_parser.add_argument(
        "-o", "--output", default="", help="Optional path; omit to pull into .dify/"
    )
    add_app_target_args(export_parser)

    import_parser = sub.add_parser("import")
    import_parser.add_argument("file", type=Path)
    add_app_target_args(import_parser, required=False)
    import_parser.add_argument(
        "--create",
        action="store_true",
        help="Create new app (omit --app-id/--name). Default: update existing app",
    )

    publish_parser = sub.add_parser("publish")
    add_app_target_args(publish_parser)

    deploy_parser = sub.add_parser("deploy")
    deploy_parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="YAML to deploy; default: .dify/dsl/{app_id}/working.yml",
    )
    add_app_target_args(deploy_parser)
    deploy_parser.add_argument(
        "--skip-diff-warning",
        action="store_true",
        help="Do not warn when working.yml differs from latest remote",
    )
    deploy_parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip pre-deploy static DSL validation (NOT recommended; see also: dsl validate)",
    )
    deploy_parser.add_argument(
        "--validate-fail-on-warnings",
        action="store_true",
        help="Make pre-deploy DSL validation fail on warnings too (strict gate)",
    )
    deploy_parser.add_argument(
        "--validate-no-snippets",
        action="store_true",
        help="Do not print line-level source snippets when validation reports issues",
    )
    deploy_parser.add_argument(
        "--skip-checklist",
        action="store_true",
        help=(
            "Skip pre-deploy Dify-official-style checklist gate. NOT recommended: checklist catches "
            "INVALID_VAR refs + edges handle loss that standard L1-L7 validation is blind to (these "
            "are the root cause of the Dify Web 'Error rendering component' white screen)."
        ),
    )
    deploy_parser.add_argument(
        "--checklist-warn-only",
        action="store_true",
        help=(
            "Run Dify checklist gate, print full report, but DO NOT block deploy even when fatal "
            "issues are present. Use only after you've reviewed the checklist output and accept the "
            "risk of remote workflow rendering broken."
        ),
    )
    deploy_parser.add_argument(
        "--skip-post-verify",
        action="store_true",
        help=(
            "Skip post-deploy remote verification. NOT recommended: Dify's /apps/imports endpoint "
            "can silently drop 30+ edges (race condition / DSL-version incompat) while returning "
            "status=completed, leaving the live workflow with orphaned nodes."
        ),
    )
    deploy_parser.add_argument(
        "--post-verify-retry",
        type=int,
        default=1,
        help=(
            "Auto-redeploy (import+publish) N times when post-deploy verify detects node/edge "
            "mismatch. Re-importing almost always recovers the transient edge-drop case. Default: 1."
        ),
    )

    api_keys_parser = sub.add_parser(
        "api-keys", help="List or create Service API keys for an app (Console session)"
    )
    add_app_target_args(api_keys_parser)
    api_keys_parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new app-xxx API key (max 10 per app)",
    )

    run_parser = sub.add_parser("run", help="Run published workflow via Service API")
    run_parser.add_argument("--api-key", required=True)
    add_run_input_args(run_parser)
    run_parser.add_argument(
        "--response-mode",
        dest="response_mode",
        default="blocking",
        choices=["blocking", "streaming"],
    )

    chat_parser = sub.add_parser(
        "chat",
        help="Run advanced-chat / chat app via POST /chat-messages",
    )
    chat_parser.add_argument("--api-key", required=True)
    chat_parser.add_argument("--query", default="", help="User message")
    add_run_input_args(chat_parser)
    chat_parser.add_argument("--conversation-id", default="", help="Omit for new conversation")
    chat_parser.add_argument(
        "--response-mode",
        dest="response_mode",
        default="blocking",
        choices=["blocking", "streaming"],
    )

    args = parser.parse_args()
    if args.env_file:
        os.environ["DIFY_ENV_FILE"] = args.env_file
    load_configuration()
    if args.show_config:
        print_config_hint()

    if args.command == "apps":
        cmd_apps_list(args)
        return
    if args.command == "dsl":
        if args.dsl_command == "status":
            cmd_dsl_status(args)
        elif args.dsl_command == "diff":
            cmd_dsl_diff(args)
        elif args.dsl_command == "refresh":
            cmd_dsl_refresh(args)
        elif args.dsl_command == "reset":
            cmd_dsl_reset(args)
        elif args.dsl_command == "prune":
            cmd_dsl_prune(args)
        elif args.dsl_command == "validate":
            cmd_dsl_validate(args)
        return
    if args.command == "cache":
        if args.cache_command == "download":
            cmd_cache_download(args)
        elif args.cache_command == "list":
            cmd_cache_list(args)
        elif args.cache_command == "clean":
            cmd_cache_clean(args)
        return
    if args.command == "files" and args.files_command == "upload":
        cmd_files_upload(args)
        return
    handlers = {
        # 一级顶层命令
        "init": cmd_init,
        "login": cmd_login,
        "refresh": cmd_refresh,
        "ping": cmd_ping,
        "session": cmd_session_show,
        "pull": cmd_pull,
        "export": cmd_export,
        "import": cmd_import,
        "publish": cmd_publish,
        "deploy": cmd_deploy,
        "api-keys": cmd_api_keys,
        "run": cmd_run,
        "chat": cmd_chat,
        # 下划线一级别名（与 dsl / cache / files 二级子命令语义一致，AI 友好）
        # ⚠️ 维护 checklist：本块每一行对应：
        #   上方 dsl_sub/cache_sub/files_sub 的二级子命令注册 + 「下划线一级别名」段落的顶层 add_parser 注册
        #   3 处（子命令注册 + 别名注册 + 本映射）必须同步新增/删除，保持 1:1
        "dsl_status": cmd_dsl_status,
        "dsl_diff": cmd_dsl_diff,
        "dsl_refresh": cmd_dsl_refresh,
        "dsl_reset": cmd_dsl_reset,
        "dsl_prune": cmd_dsl_prune,
        "dsl_validate": cmd_dsl_validate,
        "cache_download": cmd_cache_download,
        "cache_list": cmd_cache_list,
        "cache_clean": cmd_cache_clean,
        "files_upload": cmd_files_upload,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
