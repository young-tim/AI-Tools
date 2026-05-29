# Dify CLI / API 速查

基址：Console `{DIFY_CONSOLE_URL}/console/api`；Service `{DIFY_BASE_URL}`（建议 https）。

## 项目命令

| 命令 | 说明 |
|------|------|
| `init` | 创建 `.dify/` 骨架 |
| `ping` / `session` / `login` / `refresh` | 连接与认证 |
| `apps` | 列出应用 |
| `pull --app-id <id>` | 拉远程 DSL；`--sync-working` 覆盖 working |
| `export -o <path>` | 导出；省略 `-o` 等同 pull |
| `dsl status` / `diff` / `refresh` / `reset` / `prune` | DSL 状态与维护 |
| `deploy [--app-id] [file]` | import + publish；默认 working.yml |
| `cache download\|list\|clean` | 外链缓存（MD5 去重） |
| `files upload <path-or-url> --api-key` | 上传得 `upload_file_id` |
| `run` / `chat --api-key` | 运行；`--input` `--file` `--file-url` `--fixtures` |
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
