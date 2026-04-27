#!/usr/bin/env bash
# run-seed.sh — chaeshin seed bootstrapping 로컬 실행 (Next.js monitor)
#
# Cold-start 시드 케이스를 LLM 으로 생성 → 검토/수정 → main chaeshin.db 로 promote.
# OPENAI_API_KEY 가 없으면 인자 또는 prompt 로 받음. UI 만 띄우려면 비워서 skip.
#
#   ./scripts/run-seed.sh                # env/.env 에 키 있으면 사용, 없으면 prompt
#   ./scripts/run-seed.sh sk-...         # 인자로 직접 전달
#   PORT=3070 ./scripts/run-seed.sh      # 포트 변경

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f .env ]]; then
  echo "📝 .env 로드"
  set -a; source .env; set +a
fi

PORT="${PORT:-3060}"
HOST="${HOST:-localhost}"
MONITOR_DIR="$PROJECT_ROOT/chaeshin-monitor"
SEED_DB_PATH="${CHAESHIN_SEED_DB_PATH:-$HOME/.chaeshin/seed.db}"
MAIN_DB_PATH="${CHAESHIN_DB_PATH:-$HOME/.chaeshin/chaeshin.db}"
TOOLS_PATH="${CHAESHIN_TOOLS_PATH:-$HOME/.chaeshin/tools.json}"

# ── OPENAI_API_KEY 결정 (env > 인자 > prompt) ───────────────────────
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ $# -ge 1 && -n "${1:-}" ]]; then
    OPENAI_API_KEY="$1"
    export OPENAI_API_KEY
  elif [[ -t 0 ]]; then
    read -rsp "🔑 OPENAI_API_KEY (Enter 로 skip — UI 만 띄움): " OPENAI_API_KEY
    echo
    [[ -n "${OPENAI_API_KEY:-}" ]] && export OPENAI_API_KEY
  fi
fi

# ── 의존성 점검 ────────────────────────────────────────────────────
if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js 미설치"; exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv 미설치 — generate/promote 가 동작 안 함"
  echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "🔧 uv sync..."
uv sync --extra dev

if [[ ! -d "$MONITOR_DIR/node_modules" ]] || [[ "$MONITOR_DIR/package.json" -nt "$MONITOR_DIR/node_modules" ]]; then
  echo "🔧 npm install (monitor)..."
  (cd "$MONITOR_DIR" && npm install)
fi

[[ -f "$TOOLS_PATH" ]] || echo "ℹ️  도구 레지스트리 없음 — Generate 의 도구 allowlist 가 빈 상태"

# ── 실행 ──────────────────────────────────────────────────────────
cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 🌱  chaeshin seed  (cold-start 시드 생성 → 검토 → promote)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  URL          http://$HOST:$PORT/seed
  Seed DB      $SEED_DB_PATH
  Main DB      $MAIN_DB_PATH
  Tools        $TOOLS_PATH
  OpenAI       $([[ -n "${OPENAI_API_KEY:-}" ]] && echo "ON" || echo "OFF (Generate 비활성)")
  Hot reload   ON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  CLI 단축키 (다른 터미널):
    uv run chaeshin seed list
    uv run chaeshin seed export /tmp/seeds.json
    uv run chaeshin seed promote --all

EOF

cd "$MONITOR_DIR"
export CHAESHIN_SEED_DB_PATH="$SEED_DB_PATH"
export CHAESHIN_DB_PATH="$MAIN_DB_PATH"
export CHAESHIN_PROJECT_DIR="$PROJECT_ROOT"
exec npx next dev --port "$PORT" --hostname "$HOST"
