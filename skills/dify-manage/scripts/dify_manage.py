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
                resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Login failed ({exc.code}): {exc.read().decode()}") from exc

        if not self.cookie_value("access_token"):
            raise SystemExit("Login OK but access_token cookie missing")
        path = self.persist_session("login")
        print(f"Session saved to {path}", file=sys.stderr)
        return path

    def refresh(self) -> Path:
        refresh_cookie = self._find_cookie("refresh_token")
        refresh_val = refresh_cookie.value if refresh_cookie else os.environ.get("DIFY_REFRESH_TOKEN", "")
        if not refresh_val:
            raise SystemExit("No refresh_token; run login or set DIFY_REFRESH_TOKEN")
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
                resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Refresh failed ({exc.code}): {exc.read().decode()}") from exc
        path = self.persist_session("refresh")
        print(f"Session saved to {path}", file=sys.stderr)
        return path

    def ensure_session(self) -> None:
        token = self.cookie_value("access_token") or os.environ.get("DIFY_CONSOLE_TOKEN", "")
        if not token:
            email = os.environ.get("DIFY_EMAIL", "")
            password = os.environ.get("DIFY_PASSWORD", "")
            if email and password:
                self.login(email, password)
                return
            raise SystemExit(
                "No console session. Options:\n"
                "  - login (DIFY_EMAIL + DIFY_PASSWORD in .env)\n"
                "  - Put tokens in .dify/session.json (login/refresh creates it)\n"
                "  - Put DIFY_CONSOLE_TOKEN + DIFY_CSRF_TOKEN in .env (SSO/manual)"
            )

        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = int(payload.get("exp", 0))
            if exp and time.time() > exp - 300:
                if self.cookie_value("refresh_token") or os.environ.get("DIFY_REFRESH_TOKEN"):
                    self.refresh()
                    return
        except Exception:
            status, body = self.request("GET", "/console/api/apps?page=1&limit=1")
            if status == 401:
                if os.environ.get("DIFY_REFRESH_TOKEN") or self.cookie_value("refresh_token"):
                    self.refresh()
                elif os.environ.get("DIFY_EMAIL") and os.environ.get("DIFY_PASSWORD"):
                    self.login(os.environ["DIFY_EMAIL"], os.environ["DIFY_PASSWORD"])
                else:
                    raise SystemExit(f"Session invalid ({status}): {body}") from None


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


def cmd_import(args: argparse.Namespace) -> None:
    create = getattr(args, "create", False)
    session = DifySession(require_console_url())
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


def cmd_publish(args: argparse.Namespace) -> None:
    session = DifySession(require_console_url())
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

    args.file = deploy_file
    cmd_import(args)
    cmd_publish(args)

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
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
