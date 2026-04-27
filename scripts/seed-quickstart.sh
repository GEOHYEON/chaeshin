#!/usr/bin/env bash
# seed-quickstart.sh — Chaeshin Seed Bootstrapping 워크플로우 시작
#
# 새 도메인을 시작할 때 main chaeshin.db 가 비어있으면 retrieve 가 cold-start.
# 이 스크립트는 다음을 한 번에 해준다:
#   1) 환경 점검 (uv / node / npm / OPENAI_API_KEY)
#   2) Python 의존성 sync
#   3) monitor 의 node_modules 설치 (없으면)
#   4) chaeshin-monitor dev server 띄움 → http://localhost:3060/seed
#
# 사용법
#   ./scripts/seed-quickstart.sh
#   PORT=3070 ./scripts/seed-quickstart.sh        # 포트 변경
#   CHAESHIN_SEED_DB_PATH=./tmp/seed.db ./scripts/seed-quickstart.sh
#
# 그 다음 브라우저에서 /seed 진입 → "Generate" 버튼 → 생성 → 검토 → "Promote".
# CLI 가 더 빠르면:
#   uv run chaeshin seed generate --topic "..." --tools Read,Edit,Bash --count 5
#   uv run chaeshin seed list
#   uv run chaeshin seed promote --all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PORT="${PORT:-3060}"
MONITOR_DIR="$PROJECT_ROOT/chaeshin-monitor"
TOOLS_PATH="${CHAESHIN_TOOLS_PATH:-$HOME/.chaeshin/tools.json}"
SEED_DB_PATH="${CHAESHIN_SEED_DB_PATH:-$HOME/.chaeshin/seed.db}"
MAIN_DB_PATH="${CHAESHIN_DB_PATH:-$HOME/.chaeshin/chaeshin.db}"

if [[ -f .env ]]; then
  echo "📝 .env 로드" >&2
  set -a; source .env; set +a
fi

# ── 환경 점검 ──────────────────────────────────────────────────────

missing=()
command -v uv   >/dev/null 2>&1 || missing+=("uv")
command -v node >/dev/null 2>&1 || missing+=("node")
command -v npm  >/dev/null 2>&1 || missing+=("npm")
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "❌ 미설치 도구: ${missing[*]}" >&2
  echo "   uv:   curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "   node: https://nodejs.org/ (20+ 권장)" >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  cat >&2 <<'EOF'
⚠️  OPENAI_API_KEY 미설정.
   Generate 버튼 / `chaeshin seed generate` 는 LLM + 임베딩이 필요해서
   API 키 없이는 실패한다. 다음 중 하나로 설정 후 재실행:
     export OPENAI_API_KEY=sk-...
     또는 .env 파일에 OPENAI_API_KEY=sk-... 추가
   monitor UI 자체는 키 없이도 띄울 수 있고 import/promote/편집 은 가능.
EOF
fi

if [[ ! -f "$TOOLS_PATH" ]]; then
  cat >&2 <<EOF
⚠️  도구 레지스트리 없음: $TOOLS_PATH
   Generate 다이얼로그의 "도구 allowlist" 가 빈 상태로 시작.
   /api/tools/import 로 Claude Code 도구를 가져오거나, monitor 에서
   도구 관리 다이얼로그로 추가하세요.
EOF
fi

# ── Python deps ────────────────────────────────────────────────────
echo "🔧 uv sync (Python deps)…" >&2
uv sync --extra dev >&2

# ── Monitor deps ───────────────────────────────────────────────────
if [[ ! -d "$MONITOR_DIR/node_modules" ]]; then
  echo "📦 monitor npm install (최초 1회)…" >&2
  (cd "$MONITOR_DIR" && npm install >&2)
fi

# ── 안내 ───────────────────────────────────────────────────────────
cat >&2 <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 🌱  Chaeshin Seed Bootstrapping
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Monitor      http://localhost:${PORT}/seed
  Seed DB      ${SEED_DB_PATH}
  Main DB      ${MAIN_DB_PATH}
  Tools        ${TOOLS_PATH}

  흐름:
    1) /seed 진입 → "Generate" 누르고 topic + 도구 + count 입력
    2) 생성된 카드들 검토 → 수정/삭제/그래프 편집
    3) 체크박스로 선택 → "Promote" → main DB 로 새 id 발급 + 마커 부착
    4) Ctrl-C 로 종료

  CLI 단축키 (다른 터미널):
    uv run chaeshin seed list
    uv run chaeshin seed export /tmp/seeds.json
    uv run chaeshin seed promote --all
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF

# ── Monitor dev server (foreground) ───────────────────────────────
cd "$MONITOR_DIR"
export CHAESHIN_SEED_DB_PATH="$SEED_DB_PATH"
export CHAESHIN_DB_PATH="$MAIN_DB_PATH"
export CHAESHIN_PROJECT_DIR="$PROJECT_ROOT"   # /api/seed/generate 가 spawn 시 cwd 로 사용
exec npx next dev -p "$PORT"
