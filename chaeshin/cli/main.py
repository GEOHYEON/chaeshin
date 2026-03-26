"""
Chaeshin CLI — 플랫폼 연동 셋업 + 저장소 관리.

한 줄 셋업:
    chaeshin setup claude-code     # Claude Code MCP 서버 등록
    chaeshin setup openclaw        # OpenClaw Skill 설치
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


# ── 경로 ──
CHAESHIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.expanduser(os.getenv("CHAESHIN_STORE_DIR", "~/.chaeshin"))
STORE_FILE = os.path.join(STORE_DIR, "cases.json")


def _print(msg: str):
    print(f"  {msg}")


def _ok(msg: str):
    print(f"  ✅ {msg}")


def _err(msg: str):
    print(f"  ❌ {msg}")


def _info(msg: str):
    print(f"  ℹ️  {msg}")


# ═══════════════════════════════════════════════════════════════════════
# setup claude-code
# ═══════════════════════════════════════════════════════════════════════

def setup_claude_code(args):
    """Claude Code MCP 서버 등록."""
    print("\n🔌 Chaeshin → Claude Code 연결\n")

    mcp_module = "chaeshin.integrations.claude_code.mcp_server"
    python_path = sys.executable

    # claude mcp add 명령어 실행
    cmd = [
        "claude", "mcp", "add", "chaeshin",
        "--scope", args.scope,
        "--", python_path, "-m", mcp_module,
    ]

    _info(f"실행: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            _ok("Claude Code에 Chaeshin MCP 서버가 등록되었습니다!")
            _print("")
            _print("이제 Claude Code에서 다음 도구를 사용할 수 있습니다:")
            _print("  • chaeshin_retrieve  — 유사 케이스 검색")
            _print("  • chaeshin_retain    — 성공 패턴 저장")
            _print("  • chaeshin_anticipate — 선제 제안")
            _print("  • chaeshin_stats     — 저장소 통계")
            _print("")
            _print(f"저장소 위치: {STORE_DIR}")
        else:
            _err(f"claude 명령어 실패: {result.stderr.strip()}")
            _print("")
            _print("수동으로 등록하려면:")
            _manual_claude_code(python_path, mcp_module, args.scope)
    except FileNotFoundError:
        _err("'claude' 명령어를 찾을 수 없습니다.")
        _print("")
        _print("Claude Code가 설치되어 있지 않거나 PATH에 없습니다.")
        _print("수동으로 등록하려면:")
        _manual_claude_code(python_path, mcp_module, args.scope)
    except subprocess.TimeoutExpired:
        _err("타임아웃")
        _manual_claude_code(python_path, mcp_module, args.scope)


def _manual_claude_code(python_path: str, mcp_module: str, scope: str):
    """수동 등록 가이드."""
    if scope == "user":
        config_path = os.path.expanduser("~/.claude.json")
    else:
        config_path = ".claude.json"

    config_snippet = {
        "mcpServers": {
            "chaeshin": {
                "command": python_path,
                "args": ["-m", mcp_module],
            }
        }
    }

    _print(f"\n{config_path} 에 다음을 추가하세요:\n")
    _print(json.dumps(config_snippet, indent=2))
    _print("")


# ═══════════════════════════════════════════════════════════════════════
# setup openclaw
# ═══════════════════════════════════════════════════════════════════════

def setup_openclaw(args):
    """OpenClaw Skill 설치."""
    print("\n🦞 Chaeshin → OpenClaw 연결\n")

    # OpenClaw 워크스페이스 찾기
    openclaw_skills = os.path.expanduser(
        args.path or "~/.openclaw/workspace/skills"
    )

    if not os.path.exists(os.path.dirname(openclaw_skills)):
        _err(f"OpenClaw 디렉토리를 찾을 수 없습니다: {os.path.dirname(openclaw_skills)}")
        _print("OpenClaw가 설치되어 있나요?")
        _print("")
        _print("수동 설치:")
        _print(f"  mkdir -p {openclaw_skills}/chaeshin")
        _print(f"  cp {CHAESHIN_DIR}/integrations/openclaw/SKILL.md {openclaw_skills}/chaeshin/")
        return

    target = os.path.join(openclaw_skills, "chaeshin")
    source = os.path.join(CHAESHIN_DIR, "integrations", "openclaw")

    os.makedirs(target, exist_ok=True)

    # SKILL.md 복사
    src_skill = os.path.join(source, "SKILL.md")
    dst_skill = os.path.join(target, "SKILL.md")
    shutil.copy2(src_skill, dst_skill)
    _ok(f"SKILL.md → {dst_skill}")

    _print("")
    _ok("OpenClaw에 Chaeshin Skill이 설치되었습니다!")
    _print("")
    _print("OpenClaw가 다음 실행부터 Chaeshin 메모리를 사용합니다.")
    _print("")
    _print("브리지 명령어:")
    _print(f"  python -m chaeshin.integrations.openclaw.bridge retrieve \"쿼리\"")
    _print(f"  python -m chaeshin.integrations.openclaw.bridge retain --request \"요청\" --graph '{{...}}'")
    _print(f"  python -m chaeshin.integrations.openclaw.bridge stats")
    _print("")
    _print(f"저장소 위치: {STORE_DIR}")


# ═══════════════════════════════════════════════════════════════════════
# stats / retrieve
# ═══════════════════════════════════════════════════════════════════════

def cmd_stats(args):
    """저장소 통계."""
    from chaeshin.integrations.openclaw.bridge import cmd_stats as _stats

    class FakeArgs:
        pass

    _stats(FakeArgs())


def cmd_retrieve(args):
    """케이스 검색."""
    from chaeshin.integrations.openclaw.bridge import cmd_retrieve as _retrieve

    class FakeArgs:
        query = args.query
        category = args.category or ""
        keywords = args.keywords or ""
        top_k = args.top_k

    _retrieve(FakeArgs())


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="chaeshin",
        description="Chaeshin — CBR Memory for AI Agents",
    )
    sub = parser.add_subparsers(dest="command")

    # setup
    p_setup = sub.add_parser("setup", help="플랫폼 연동 셋업")
    setup_sub = p_setup.add_subparsers(dest="platform")

    p_cc = setup_sub.add_parser("claude-code", help="Claude Code MCP 서버 등록")
    p_cc.add_argument("--scope", choices=["user", "project"], default="user", help="등록 범위")
    p_cc.set_defaults(func=setup_claude_code)

    p_oc = setup_sub.add_parser("openclaw", help="OpenClaw Skill 설치")
    p_oc.add_argument("--path", default=None, help="OpenClaw skills 디렉토리")
    p_oc.set_defaults(func=setup_openclaw)

    # stats
    p_stats = sub.add_parser("stats", help="저장소 통계")
    p_stats.set_defaults(func=cmd_stats)

    # retrieve
    p_ret = sub.add_parser("retrieve", help="케이스 검색")
    p_ret.add_argument("query", help="검색 쿼리")
    p_ret.add_argument("--category", default="")
    p_ret.add_argument("--keywords", default="")
    p_ret.add_argument("--top-k", type=int, default=3)
    p_ret.set_defaults(func=cmd_retrieve)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "setup" and not getattr(args, "platform", None):
        p_setup.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
