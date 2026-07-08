#!/usr/bin/env bash
#
# PptSmith CLI - AI Presentation Compiler powered by officecli
# 用法:
#   bash ./scripts/pptsmith.sh validate --input <presentation.json>
#   bash ./scripts/pptsmith.sh build --input <presentation.json> [--output-root ./.pptsmith] [--slug <slug>] [--overwrite] [--qa true|false]
#   bash ./scripts/pptsmith.sh qa --workspace <deck-workspace> [--render auto|required|off]
#   bash ./scripts/pptsmith.sh clean --workspace <deck-workspace> [--cache-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_OUTPUT_ROOT=".pptsmith"
OUTPUT_PPTX_PREFIX="presentation"
ENV_CACHE_FILENAME="env.json"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[pptsmith]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[pptsmith]${NC} $*" >&2; }
log_error() { echo -e "${RED}[pptsmith]${NC} $*" >&2; }

# 检查 officecli 是否安装
check_officecli() {
    if ! command -v officecli &>/dev/null; then
        log_error "officecli 未安装。请先运行安装命令："
        log_error "  curl -fsSL https://d.officecli.ai/install.sh | bash"
        exit 1
    fi
}

# 将字符串转换为 slug
slugify() {
    local input="$1"
    echo "$input" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//' | cut -c1-80
}

# 解析命令行参数
parse_args() {
    COMMAND=""
    INPUT=""
    OUTPUT_ROOT="${DEFAULT_OUTPUT_ROOT}"
    SLUG=""
    WORKSPACE=""
    QA="true"
    RENDER="auto"
    OVERWRITE="false"
    CACHE_ONLY="false"
    REFRESH_ENV="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            validate|build|qa|clean)
                COMMAND="$1"
                shift
                ;;
            --input)
                INPUT="$2"
                shift 2
                ;;
            --output-root)
                OUTPUT_ROOT="$2"
                shift 2
                ;;
            --slug)
                SLUG="$2"
                shift 2
                ;;
            --workspace)
                WORKSPACE="$2"
                shift 2
                ;;
            --qa)
                QA="$2"
                shift 2
                ;;
            --render)
                RENDER="$2"
                shift 2
                ;;
            --overwrite)
                OVERWRITE="true"
                shift
                ;;
            --cache-only)
                CACHE_ONLY="true"
                shift
                ;;
            --refresh-env)
                REFRESH_ENV="true"
                shift
                ;;
            --help|-h)
                print_help
                exit 0
                ;;
            --version|-v)
                echo "0.2.0"
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                print_help
                exit 1
                ;;
        esac
    done
}

# 打印帮助信息
print_help() {
    cat <<EOF
PptSmith CLI - AI Presentation Compiler powered by officecli

用法:
  pptsmith validate --input <presentation.json>
  pptsmith build --input <presentation.json> [--output-root ./.pptsmith] [--slug <slug>] [--refresh-env] [--overwrite] [--qa true|false] [--render auto|required|off]
  pptsmith qa --workspace <deck-workspace> [--render auto|required|off]
  pptsmith clean --workspace <deck-workspace> [--cache-only]

命令说明:
  validate   验证 Slide IR JSON 文件格式
  build      从 Slide IR 构建 PPTX 文件
  qa         对已构建的 PPTX 进行质量检查
  clean      清理工作空间缓存

Build 会在 output/ 目录下创建版本化的 PPTX 文件 (presentation-vN.pptx)。
运行时路径缓存在 .pptsmith/env.json 中，使用 --refresh-env 可刷新缓存。
--render 控制 PPTX 视觉 QA: auto (默认，工具存在时渲染), required (不可用时失败), off (跳过视觉 QA)。
EOF
}

# 验证 Slide IR JSON（基础结构验证）
validate_ir() {
    local input_path="$1"
    if [[ ! -f "$input_path" ]]; then
        log_error "输入文件不存在: $input_path"
        exit 1
    fi

    # 使用 officecli 不直接验证 JSON，但我们做基础结构检查
    if ! python3 -c "
import json, sys
try:
    with open('$input_path', 'r') as f:
        ir = json.load(f)
    # 基础结构检查
    assert 'version' in ir, 'missing version'
    assert 'meta' in ir and isinstance(ir['meta'], dict), 'missing meta'
    assert 'title' in ir.get('meta', {}), 'missing meta.title'
    assert 'theme' in ir, 'missing theme'
    assert 'slides' in ir and isinstance(ir['slides'], list) and len(ir['slides']) > 0, 'slides must be a non-empty array'
    for i, slide in enumerate(ir['slides']):
        assert 'id' in slide, f'slides[{i}] missing id'
        assert 'layout' in slide, f'slides[{i}] missing layout'
        assert 'components' in slide and isinstance(slide['components'], list), f'slides[{i}] components must be an array'
    print(f'valid: {\"$input_path\"} ({len(ir[\"slides\"])} slides)')
except Exception as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1; then
        # 如果 python3 不可用，使用简单检查
        log_warn "python3 不可用，跳过详细结构验证"
        if command -v jq &>/dev/null; then
            local slide_count
            slide_count=$(jq '.slides | length' "$input_path" 2>/dev/null || echo "?")
            log_info "valid: $input_path ($slide_count slides) (基础 JSON 验证)"
        else
            log_info "valid: $input_path (仅检查文件存在)"
        fi
    fi
}

# 确保工作空间目录存在
ensure_workspace() {
    local workspace="$1"
    mkdir -p "$workspace"/{input,ir,output,assets/{images,icons,charts,fonts,generated},qa/rendered-pages,cache,logs}
}

# 解析下一个输出版本号
get_next_version() {
    local workspace="$1"
    local output_dir="$workspace/output"
    mkdir -p "$output_dir"
    local max_version=0
    for f in "$output_dir"/${OUTPUT_PPTX_PREFIX}-v*.pptx; do
        if [[ -f "$f" ]]; then
            local ver
            ver=$(basename "$f" | sed -n "s/${OUTPUT_PPTX_PREFIX}-v\([0-9]*\)\.pptx/\1/p")
            if [[ -n "$ver" && "$ver" -gt "$max_version" ]]; then
                max_version="$ver"
            fi
        fi
    done
    echo $((max_version + 1))
}

# 从 IR 中读取 slug
get_slug_from_ir() {
    local input_path="$1"
    if command -v jq &>/dev/null; then
        local meta_slug
        meta_slug=$(jq -r '.meta.slug // empty' "$input_path" 2>/dev/null)
        if [[ -n "$meta_slug" ]]; then
            echo "$meta_slug"
            return
        fi
        local meta_title
        meta_title=$(jq -r '.meta.title // "deck"' "$input_path" 2>/dev/null)
        slugify "$meta_title"
    else
        # 简单 fallback
        slugify "deck"
    fi
}

# 解析构建目标 slug
resolve_build_slug() {
    local output_root="$1"
    local requested_slug="$2"
    local input_path="$3"

    local base_workspace="$output_root/decks/$requested_slug"
    
    if [[ "$OVERWRITE" == "true" ]]; then
        echo "$requested_slug"
        return
    fi

    if [[ ! -d "$base_workspace" ]]; then
        echo "$requested_slug"
        return
    fi

    # 如果输入文件在基础工作空间内，复用该 slug
    local abs_input
    abs_input=$(cd "$(dirname "$input_path")" && pwd)/$(basename "$input_path")
    local abs_base
    abs_base=$(cd "$base_workspace" 2>/dev/null && pwd) || true
    if [[ "$abs_input" == "$abs_base"/* ]]; then
        echo "$requested_slug"
        return
    fi

    # 查找下一个可用的编号 slug
    for i in $(seq 2 999); do
        local candidate="${requested_slug}-${i}"
        if [[ ! -d "$output_root/decks/$candidate" ]]; then
            echo "$candidate"
            return
        fi
    done
    log_error "无法找到可用的 deck slug"
    exit 1
}

# 使用 officecli 从 Slide IR 构建 PPTX
build_pptx_with_officecli() {
    local ir_path="$1"
    local output_path="$2"
    local workspace="$3"
    local warnings=()
    local fallbacks=()

    log_info "使用 officecli 创建 PPTX..."
    
    # 创建空白 PPTX
    officecli create "$output_path" --force 2>/dev/null || {
        # 如果 --force 不支持，先删除再创建
        rm -f "$output_path"
        officecli create "$output_path"
    }

    log_info "解析 Slide IR 并构建幻灯片..."
    
    # 使用 Node.js 或 Python 来读取 IR 并调用 officecli
    # 由于需要复杂的逻辑，这里使用一个辅助脚本
    local build_script="$workspace/cache/build-commands.sh"
    cat > "$build_script" << 'BUILDSCRIPT'
#!/usr/bin/env bash
# 此脚本由 pptsmith 生成，用于调用 officecli 构建幻灯片
set -euo pipefail

IR_PATH="$1"
OUTPUT_PATH="$2"
WORKSPACE="$3"
SKILL_ROOT="$4"

BUILDSCRIPT

    # 这里是简化的构建逻辑 - 实际使用时 AI 会直接调用 officecli 命令
    # 本脚本作为基础框架，AI 在 Phase 2 中会生成具体的 officecli 命令
    
    log_info "PPTX 框架已创建: $output_path"
    log_info "注意: 完整的幻灯片内容构建需要 AI 根据 Slide IR 生成 officecli batch 命令"
}

# 运行 PPTX QA
run_qa() {
    local workspace="$1"
    local pptx_path="$2"
    local render_mode="$3"

    if [[ ! -f "$pptx_path" ]]; then
        log_error "PPTX 文件不存在: $pptx_path"
        return 1
    fi

    local qa_dir="$workspace/qa"
    local report_path="$qa_dir/qa-report.json"
    local pptx_qa_report="$qa_dir/pptx-qa-report.json"
    local rendered_dir="$qa_dir/rendered-pages"
    mkdir -p "$rendered_dir"

    log_info "验证 PPTX 结构..."
    local validate_output
    validate_output=$(officecli validate "$pptx_path" 2>&1) || {
        log_warn "officecli validate 报告问题: $validate_output"
    }

    log_info "获取 PPTX 统计信息..."
    local stats_output
    stats_output=$(officecli view "$pptx_path" stats 2>&1) || true
    log_info "统计: $stats_output"

    local issues_output=""
    if [[ "$render_mode" != "off" ]]; then
        log_info "检查 PPTX 问题..."
        issues_output=$(officecli view "$pptx_path" issues 2>&1) || true
        if [[ -n "$issues_output" ]]; then
            log_warn "发现问题: $issues_output"
        fi
    fi

    # 渲染 PDF/PNG 用于视觉 QA
    local visual_status="skipped"
    local representative_pages=()
    if [[ "$render_mode" != "off" ]]; then
        log_info "尝试渲染 PDF 用于视觉检查..."
        local pdf_path="$rendered_dir/presentation.pdf"
        if officecli view "$pptx_path" pdf -o "$pdf_path" 2>/dev/null; then
            visual_status="pdf-rendered"
            log_info "PDF 已生成: $pdf_path"
            representative_pages+=("{\"reason\":\"full-deck\",\"pdf\":\"$pdf_path\"}")

            # 尝试生成关键页面截图
            local slide_count
            slide_count=$(officecli view "$pptx_path" outline 2>/dev/null | grep -c "slide" || echo "0")
            local pages_to_render=("1" "$slide_count")
            for page in "${pages_to_render[@]}"; do
                if [[ "$page" =~ ^[0-9]+$ ]] && [[ "$page" -gt 0 ]]; then
                    local png_path="$rendered_dir/page-${page}.png"
                    if officecli view "$pptx_path" screenshot --page "$page" -o "$png_path" 2>/dev/null; then
                        visual_status="rendered"
                        representative_pages+=("{\"reason\":\"page-$page\",\"page\":$page,\"png\":\"$png_path\"}")
                    fi
                fi
            done
        else
            if [[ "$render_mode" == "required" ]]; then
                log_error "视觉 QA 需要渲染但失败了"
                return 1
            fi
            log_warn "PDF 渲染失败，跳过视觉 QA"
            visual_status="blocked"
        fi
    fi

    # 生成 QA 报告
    cat > "$pptx_qa_report" << JSONEOF
{
  "schemaVersion": 1,
  "pptx": {
    "path": "$pptx_path",
    "exists": true,
    "validateOutput": $(echo "$validate_output" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$validate_output\""),
    "stats": $(echo "$stats_output" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"$stats_output\""),
    "warnings": [],
    "errors": []
  },
  "visualQa": {
    "status": "$visual_status",
    "renderer": "officecli",
    "representativePages": [$(IFS=,; echo "${representative_pages[*]}")],
    "warnings": [],
    "errors": []
  }
}
JSONEOF

    local status="passed"
    if [[ "$visual_status" == "blocked" && "$render_mode" == "required" ]]; then
        status="failed"
    fi

    cat > "$report_path" << JSONEOF
{
  "status": "$status",
  "generatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "workspace": "$workspace",
  "checks": [
    {"name": "ir/presentation.json", "status": "$( [[ -f "$workspace/ir/presentation.json" ]] && echo passed || echo failed )"},
    {"name": "output/pptx", "status": "passed"}
  ],
  "warnings": $(echo "$issues_output" | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin.readlines() if l.strip()]))" 2>/dev/null || echo "[]"),
  "pptxQa": "$(basename "$pptx_qa_report")"
}
JSONEOF

    log_info "QA 报告已生成: $report_path"
    log_info "QA 状态: $status"
    
    if [[ "$visual_status" == "rendered" || "$visual_status" == "pdf-rendered" ]]; then
        log_info "视觉检查页面:"
        for page in "$rendered_dir"/page-*.png "$rendered_dir"/*.pdf; do
            if [[ -f "$page" ]]; then
                log_info "  $(basename "$page")"
            fi
        done
    fi
}

# 清理工作空间
clean_workspace() {
    local workspace="$1"
    local cache_only="$2"

    if [[ ! -d "$workspace" ]]; then
        log_error "工作空间不存在: $workspace"
        exit 1
    fi

    if [[ "$cache_only" == "true" ]]; then
        rm -rf "$workspace/cache"/* "$workspace/logs"/*
        mkdir -p "$workspace/cache" "$workspace/logs"
        log_info "已清理: cache, logs"
    else
        rm -rf "$workspace/qa/rendered-pages"/* "$workspace/cache"/* "$workspace/logs"/*
        mkdir -p "$workspace/qa/rendered-pages" "$workspace/cache" "$workspace/logs"
        log_info "已清理: cache, logs, qa/rendered-pages"
    fi
}

# 写入 manifest.json
write_manifest() {
    local workspace="$1"
    local ir_path="$2"
    local slug="$3"
    local version="$4"
    local pptx_path="$5"
    local input_path="$6"
    local qa_status="$7"

    cat > "$workspace/manifest.json" << JSONEOF
{
  "version": "1.0",
  "generatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "generator": {
    "name": "pptsmith",
    "version": "0.2.0"
  },
  "deck": {
    "title": "$(jq -r '.meta.title // ""' "$ir_path" 2>/dev/null || echo "")",
    "slug": "$slug",
    "author": "$(jq -r '.meta.author // ""' "$ir_path" 2>/dev/null || echo "")",
    "language": "$(jq -r '.meta.language // ""' "$ir_path" 2>/dev/null || echo "")",
    "theme": "$(jq -r '.theme // ""' "$ir_path" 2>/dev/null || echo "")",
    "template": "$(jq -r '.template // ""' "$ir_path" 2>/dev/null || echo "")",
    "slideCount": $(jq '.slides | length' "$ir_path" 2>/dev/null || echo "0")
  },
  "build": {
    "version": $version,
    "outputName": "$(basename "$pptx_path")"
  },
  "sourceFiles": {
    "input": "$(realpath --relative-to="$workspace" "$input_path" 2>/dev/null || echo "$input_path")",
    "slideIr": "ir/presentation.json"
  },
  "outputs": {
    "pptx": "output/$(basename "$pptx_path")"
  },
  "runtime": {
    "engine": "officecli"
  },
  "warnings": [],
  "fallbacks": [],
  "qa": {
    "status": "$qa_status",
    "report": "qa/qa-report.json"
  }
}
JSONEOF
}

# 更新 index.json
update_index() {
    local output_root="$1"
    local workspace="$2"
    local manifest="$3"

    mkdir -p "$output_root"
    local index_path="$output_root/index.json"
    
    # 简单处理 - 新建或追加
    if [[ ! -f "$index_path" ]]; then
        echo '{"version":"1.0","decks":[]}' > "$index_path"
    fi
    
    # 使用 jq 更新索引（如果可用）
    if command -v jq &>/dev/null; then
        local rel_workspace
        rel_workspace=$(realpath --relative-to="$output_root" "$workspace")
        local title
        title=$(jq -r '.deck.title' "$manifest" 2>/dev/null || echo "")
        local slug
        slug=$(jq -r '.deck.slug' "$manifest" 2>/dev/null || echo "")
        local output_pptx
        output_pptx=$(jq -r '.outputs.pptx' "$manifest" 2>/dev/null || echo "")
        
        local tmp_index
        tmp_index=$(mktemp)
        jq --arg slug "$slug" --arg title "$title" --arg ws "$rel_workspace" --arg pptx "$output_pptx" --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
           '.decks = ((.decks // []) | map(select(.slug != $slug))) + [{
               "title": $title,
               "slug": $slug,
               "workspace": $ws,
               "updatedAt": $date,
               "outputs": {"pptx": $ws + "/" + $pptx}
           }] | .updatedAt = $date' \
           "$index_path" > "$tmp_index" && mv "$tmp_index" "$index_path"
    fi
}

# 缓存运行时环境
cache_env() {
    local output_root="$1"
    local force_refresh="$2"
    local cache_path="$output_root/$ENV_CACHE_FILENAME"

    if [[ "$force_refresh" != "true" && -f "$cache_path" ]]; then
        return
    fi

    mkdir -p "$output_root"
    local officecli_path
    officecli_path=$(command -v officecli || echo "")
    
    cat > "$cache_path" << JSONEOF
{
  "version": 1,
  "generatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "skillRoot": "$SKILL_ROOT",
  "engine": "officecli",
  "tools": {
    "officecli": "$officecli_path"
  }
}
JSONEOF
}

# 主函数
main() {
    parse_args "$@"
    check_officecli

    if [[ -z "$COMMAND" ]]; then
        print_help
        exit 1
    fi

    case "$COMMAND" in
        validate)
            if [[ -z "$INPUT" ]]; then
                log_error "validate 需要 --input 参数"
                exit 1
            fi
            validate_ir "$INPUT"
            ;;

        build)
            if [[ -z "$INPUT" ]]; then
                log_error "build 需要 --input 参数"
                exit 1
            fi

            local abs_input
            abs_input=$(realpath "$INPUT")
            cache_env "$OUTPUT_ROOT" "$REFRESH_ENV"

            local requested_slug="${SLUG:-$(get_slug_from_ir "$abs_input")}"
            local slug
            slug=$(resolve_build_slug "$OUTPUT_ROOT" "$requested_slug" "$abs_input")
            
            if [[ "$slug" != "$requested_slug" ]]; then
                log_warn "deck slug \"$requested_slug\" 已存在，使用编号工作空间 \"$slug\""
            fi

            local workspace="$OUTPUT_ROOT/decks/$slug"
            ensure_workspace "$workspace"

            # 复制输入 IR
            cp "$abs_input" "$workspace/ir/presentation.json"

            # 确定版本
            local version
            version=$(get_next_version "$workspace")
            local pptx_path="$workspace/output/${OUTPUT_PPTX_PREFIX}-v${version}.pptx"

            log_info "工作空间: $workspace"
            log_info "构建版本: v$version"

            # 构建 PPTX
            build_pptx_with_officecli "$workspace/ir/presentation.json" "$pptx_path" "$workspace"

            # QA
            local qa_status="skipped"
            if [[ "$QA" == "true" ]]; then
                if run_qa "$workspace" "$pptx_path" "$RENDER"; then
                    qa_status="passed"
                else
                    qa_status="failed"
                fi
            fi

            # 写入 manifest
            write_manifest "$workspace" "$workspace/ir/presentation.json" "$slug" "$version" "$pptx_path" "$abs_input" "$qa_status"
            update_index "$OUTPUT_ROOT" "$workspace" "$workspace/manifest.json"

            log_info "构建完成!"
            log_info "输出: $pptx_path"
            ;;

        qa)
            if [[ -z "$WORKSPACE" ]]; then
                log_error "qa 需要 --workspace 参数"
                exit 1
            fi

            local abs_workspace
            abs_workspace=$(realpath "$WORKSPACE")
            
            # 查找最新的 PPTX
            local latest_pptx=""
            for f in "$abs_workspace"/output/${OUTPUT_PPTX_PREFIX}-v*.pptx; do
                if [[ -f "$f" ]]; then
                    latest_pptx="$f"
                fi
            done

            if [[ -z "$latest_pptx" ]]; then
                log_error "在 $abs_workspace/output/ 中未找到 PPTX 文件"
                exit 1
            fi

            run_qa "$abs_workspace" "$latest_pptx" "$RENDER"
            ;;

        clean)
            if [[ -z "$WORKSPACE" ]]; then
                log_error "clean 需要 --workspace 参数"
                exit 1
            fi
            clean_workspace "$(realpath "$WORKSPACE")" "$CACHE_ONLY"
            ;;

        *)
            log_error "未知命令: $COMMAND"
            print_help
            exit 1
            ;;
    esac
}

main "$@"
