# Dify CLI / API 速查

基址：Console `{DIFY_CONSOLE_URL}/console/api`；Service `{DIFY_BASE_URL}`（建议 https）。

## 项目命令

> 所有命令均有两种**等价**调用形式：**下划线 `父_子`（AI 调用推荐，不会触发「命令不存在」）** 和 空格 `父 子`（人类终端习惯，完全兼容）。示例：`dsl_status` ≡ `dsl status`、`cache_download` ≡ `cache download`、`files_upload` ≡ `files upload`。其他没有 `父_子` 组合的命令（`init`、`pull`、`deploy` 等）天然只有一级。

| 命令 | 说明 |
|------|------|
| `init` | 创建 `.dify/` 骨架 |
| `ping` / `session` / `login` / `refresh` | 连接与认证 |
| `apps` | 列出应用 |
| `pull --app-id <id>` | 拉远程 DSL；`--sync-working` 覆盖 working |
| `export -o <path>` | 导出；省略 `-o` 等同 pull |
| `dsl_status` / `dsl_diff` / `dsl_refresh` / `dsl_reset` / `dsl_prune` | DSL 状态与维护（等价空格形式：`dsl status / diff / refresh / reset / prune`） |
| `deploy [--app-id] [file]` | import + publish；默认 working.yml |
| `cache_download` / `cache_list` / `cache_clean` | 外链缓存（MD5 去重，等价空格形式：`cache download / list / clean`） |
| `files_upload <path-or-url> --api-key` | 上传得 `upload_file_id`（等价空格形式：`files upload ...`） |
| `run --api-key` / `chat --api-key` | 运行；`--input` `--file` `--file-url` `--fixtures` |
| `api-keys --app-id <id>` | Service API key |

## 文件上传

```http
POST /v1/files/upload
Authorization: Bearer app-xxx
Content-Type: multipart/form-data

file=<binary>
user=<user-id>
```

## fixtures 格式

```json
{
  "inputs": { "style": "modern" },
  "files": {
    "product_image": "fixtures/<app_id>/assets/product.jpg",
    "banner": "https://example.com/a.jpg"
  },
  "query": ""
}
```

## Console API

| 方法 | 路径 |
|------|------|
| GET | `/apps` `/apps/{id}` `/apps/{id}/export?include_secret=true` |
| POST | `/apps/imports` `/apps/imports/{id}/confirm` |
| POST | `/apps/{id}/workflows/publish` |
| GET/POST | `/apps/{id}/api-keys` |

## 错误

| 状态 | 处理 |
|------|------|
| 401 | `refresh` / `login` |
| import pending | confirm |
| BASE_URL http 301 | 用 `https://.../v1` |
