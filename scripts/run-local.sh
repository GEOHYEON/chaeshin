#!/usr/bin/env bash
# run-local.sh — chaeshin 로컬 실행
#
# chaeshin 은 MCP 서버 (stdio) + 옵션 ReAct 데모로 구성. HTTP 포트 없음.
# 기본: MCP 서버 stdio 모드. 인자로 "demo" 주면 ReAct 라이브 데모 실행.
#
#   ./scripts/run-local.sh         # MCP 서버 (Claude Code 등이 접속)
#   ./scripts/run-local.sh demo    # ReAct 데모

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f .env ]]; then
  echo "📝 .env 로드" >&2
  set -a; source .env; set +a
fi

MODE="${1:-serve}"

if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv 미설치. macOS: brew install uv" >&2
  exit 1
fi

echo "🔧 uv sync..." >&2
uv sync >&2

case "$MODE" in
  serve)
    echo "" >&2
    cat >&2 <<EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 🧠  chaeshin  (MCP server, stdio)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tools        chaeshin_anticipate / retain / retrieve / stats
  Transport    stdio (Claude Code 의 MCP 설정에 이 스크립트 등록)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
    exec uv run chaeshin serve
    ;;
  demo)
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
      echo "❌ demo 모드에는 OPENAI_API_KEY 필요" >&2
      exit 1
    fi
    echo "🎬 ReAct demo 실행..." >&2
    exec uv run chaeshin demo react
    ;;
  *)
    echo "❌ 알 수 없는 모드: $MODE (serve|demo)" >&2
    exit 1
    ;;
esac
