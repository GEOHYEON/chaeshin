"""
Chaeshin CLI — 플랫폼 연동 셋업 + 저장소 관리.

한 줄 셋업:
    chaeshin setup claude-code      # Claude Code MCP 등록 + CLAUDE.md 자동학습 (한 번에!)
    chaeshin setup claude-desktop   # Claude Desktop config 자동 수정
    chaeshin setup openclaw         # OpenClaw Skill 설치
    chaeshin setup auto-learn       # CLAUDE.md 자동학습 규칙만 별도 설치
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

def _install_auto_learn(target_dir: str):
    """CLAUDE.md 자동학습 규칙 설치 (내부 헬퍼)."""
    target_file = os.path.join(target_dir, "CLAUDE.md")

    source_file = os.path.join(
        CHAESHIN_DIR, "integrations", "claude_code", "CLAUDE.md"
    )

    if not os.path.exists(source_file):
        _err(f"CLAUDE.md 템플릿을 찾을 수 없습니다: {source_file}")
        return False

    if os.path.exists(target_file):
        with open(target_file, "r", encoding="utf-8") as f:
            existing = f.read()

        if "chaeshin" in existing.lower() or "chaeshin_retrieve" in existing:
            _info("이미 Chaeshin 규칙이 CLAUDE.md에 포함되어 있습니다.")
            return True

        with open(source_file, "r", encoding="utf-8") as f:
            chaeshin_rules = f.read()

        with open(target_file, "a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(chaeshin_rules)

        _ok(f"기존 CLAUDE.md에 Chaeshin 규칙을 추가했습니다")
    else:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(source_file, target_file)
        _ok(f"CLAUDE.md 생성 완료")

    _print(f"  위치: {target_file}")
    return True


def _detect_uvx() -> bool:
    """uvx(uv tool run)로 실행 중인지 감지."""
    # uvx는 임시 venv를 만드므로 경로에 uv/tool 패턴이 포함됨
    exe = sys.executable
    return "uv" in exe and ("tool" in exe or ".cache" in exe)


def _find_uv() -> str | None:
    """시스템에서 uv 실행 파일 경로를 찾는다."""
    result = shutil.which("uv")
    if result:
        return result
    # 흔한 설치 경로
    for candidate in [
        os.path.expanduser("~/.cargo/bin/uv"),
        os.path.expanduser("~/.local/bin/uv"),
        "/usr/local/bin/uv",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def setup_claude_code(args):
    """Claude Code MCP 서버 등록 + 자동학습 규칙 설치."""
    print("\n🔌 Chaeshin → Claude Code 연결\n")

    # uvx 환경 감지 → uvx chaeshin-mcp 방식 사용
    if args.no_uvx:
        use_uvx = False
    else:
        use_uvx = args.uvx or _detect_uvx()

    if use_uvx:
        uv_path = _find_uv()
        if not uv_path:
            _err("uv를 찾을 수 없습니다. --no-uvx로 직접 실행 모드를 사용하세요.")
            return

        # uvx chaeshin-mcp = uv tool run chaeshin-mcp
        mcp_cmd = [uv_path, "tool", "run", "chaeshin-mcp"]
        _info("uvx 모드: uv tool run chaeshin-mcp")
    else:
        mcp_module = "chaeshin.integrations.claude_code.mcp_server"
        python_path = sys.executable
        mcp_cmd = [python_path, "-m", mcp_module]

    # claude mcp add 명령어 실행
    cmd = [
        "claude", "mcp", "add", "chaeshin",
        "--scope", args.scope,
    ]

    # --openai-key → 환경변수로 전달
    if args.openai_key:
        cmd += ["-e", f"OPENAI_API_KEY={args.openai_key}"]
        _info("OPENAI_API_KEY가 설정됩니다 (벡터 임베딩 활성화)")

    cmd += ["--"] + mcp_cmd

    _info(f"실행: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            _ok("Claude Code에 Chaeshin MCP 서버가 등록되었습니다!")
            _print("")
            _print("이제 Claude Code에서 다음 도구를 사용할 수 있습니다:")
            _print("  • chaeshin_retrieve  — 유사 케이스 검색 (성공/실패/대기 분리)")
            _print("  • chaeshin_retain    — 실행 그래프 저장 (pending 으로)")
            _print("  • chaeshin_revise    — 이 레이어 그래프 교체 + 다운스트림 cascade")
            _print("  • chaeshin_update    — 메타/outcome 부분 수정 (그래프 외)")
            _print("  • chaeshin_delete    — 케이스 삭제")
            _print("  • chaeshin_verdict   — 사용자 성공/실패 판정 기록")
            _print("  • chaeshin_feedback  — 자연어 피드백 기록")
            _print("  • chaeshin_decompose — 호스트 AI용 재귀 분해 컨텍스트")
            _print("  • chaeshin_stats     — 저장소 통계")
            _print("")
            _print(f"저장소 위치: {STORE_DIR}")
        else:
            _err(f"claude 명령어 실패: {result.stderr.strip()}")
            _print("")
            _print("수동으로 등록하려면:")
            _manual_claude_code(mcp_cmd, args.scope)
    except FileNotFoundError:
        _err("'claude' 명령어를 찾을 수 없습니다.")
        _print("")
        _print("Claude Code가 설치되어 있지 않거나 PATH에 없습니다.")
        _print("수동으로 등록하려면:")
        _manual_claude_code(mcp_cmd, args.scope)
    except subprocess.TimeoutExpired:
        _err("타임아웃")
        _manual_claude_code(mcp_cmd, args.scope)

    # Auto-Learn: CLAUDE.md 자동학습 규칙도 함께 설치
    if not args.no_auto_learn:
        print("\n🧠 Auto-Learn 규칙 설치\n")
        target_dir = os.path.abspath(args.auto_learn_path or ".")
        _install_auto_learn(target_dir)
        _print("")
        _print("Claude Code가 이 프로젝트에서:")
        _print("  • 멀티스텝 작업 전에 자동으로 과거 패턴을 검색합니다")
        _print("  • 작업 완료 후 실행 그래프를 자동으로 저장합니다")
        _print("  • 실패 패턴도 기록하여 같은 실수를 반복하지 않습니다")
        _print("")
    else:
        _print("")
        _info("Auto-Learn 규칙 설치를 건너뛰었습니다 (--no-auto-learn)")
        _print("나중에 설치하려면: chaeshin setup auto-learn")
        _print("")


def _manual_claude_code(mcp_cmd: list[str], scope: str):
    """수동 등록 가이드."""
    if scope == "user":
        config_path = os.path.expanduser("~/.claude.json")
    else:
        config_path = ".claude.json"

    config_snippet = {
        "mcpServers": {
            "chaeshin": {
                "command": mcp_cmd[0],
                "args": mcp_cmd[1:],
            }
        }
    }

    _print(f"\n{config_path} 에 다음을 추가하세요:\n")
    _print(json.dumps(config_snippet, indent=2))
    _print("")


# ═══════════════════════════════════════════════════════════════════════
# setup claude-desktop
# ═══════════════════════════════════════════════════════════════════════

def _get_desktop_config_path() -> str:
    """Claude Desktop config 경로 (OS별)."""
    import platform
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Claude/claude_desktop_config.json"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Claude", "claude_desktop_config.json")
    else:  # Linux
        return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def setup_claude_desktop(args):
    """Claude Desktop config에 Chaeshin MCP 서버 등록."""
    print("\n🖥️  Chaeshin → Claude Desktop 연결\n")

    config_path = _get_desktop_config_path()

    # uv 경로 찾기
    uv_path = _find_uv()
    if not uv_path:
        _err("uv를 찾을 수 없습니다. uv를 먼저 설치해주세요.")
        _print("https://docs.astral.sh/uv/getting-started/installation/")
        return

    # chaeshin 프로젝트 경로 (--directory용)
    chaeshin_project = os.path.dirname(CHAESHIN_DIR)

    # MCP 서버 설정
    server_config = {
        "command": uv_path,
        "args": [
            "--directory", chaeshin_project,
            "run", "chaeshin-mcp",
        ],
    }

    # --openai-key가 있으면 env 추가
    if args.openai_key:
        server_config["env"] = {
            "OPENAI_API_KEY": args.openai_key,
        }
        _info("OPENAI_API_KEY가 설정됩니다 (벡터 임베딩 활성화)")

    # 기존 config 읽기
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            _info("기존 config 파일을 읽을 수 없어 새로 생성합니다.")

    # mcpServers에 chaeshin 추가 (기존 서버 보존)
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["chaeshin"] = server_config

    # config 저장
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    _ok(f"Claude Desktop config 업데이트 완료!")
    _print(f"  위치: {config_path}")
    _print("")
    _print("Claude Desktop을 재시작하면 Chaeshin 도구를 사용할 수 있습니다.")
    _print("  (macOS: Cmd+Q → 재실행)")
    _print("")
    _print(f"저장소 위치: {STORE_DIR}")
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
# setup auto-learn
# ═══════════════════════════════════════════════════════════════════════

def setup_auto_learn(args):
    """CLAUDE.md 자동학습 규칙을 프로젝트에 설치 (독립 명령)."""
    print("\n🧠 Chaeshin Auto-Learn 셋업\n")

    target_dir = os.path.abspath(args.path or ".")
    if _install_auto_learn(target_dir):
        _print("")
        _print("이제 Claude Code가 이 프로젝트에서:")
        _print("  • 멀티스텝 작업 전에 자동으로 과거 패턴을 검색합니다")
        _print("  • 작업 완료 후 실행 그래프를 자동으로 저장합니다")
        _print("  • 실패 패턴도 기록하여 같은 실수를 반복하지 않습니다")
        _print("")


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

    p_cc = setup_sub.add_parser("claude-code", help="Claude Code MCP 서버 등록 + 자동학습")
    p_cc.add_argument("--scope", choices=["user", "project"], default="user", help="등록 범위")
    p_cc.add_argument("--uvx", action="store_true", help="uvx(uv tool run) 모드 강제 사용")
    p_cc.add_argument("--no-uvx", action="store_true", dest="no_uvx", help="uvx 자동감지 무시, python -m 직접 실행")
    p_cc.add_argument("--openai-key", default=None, help="OpenAI API 키 (벡터 임베딩용)")
    p_cc.add_argument("--no-auto-learn", action="store_true", help="CLAUDE.md 자동학습 규칙 설치 건너뛰기")
    p_cc.add_argument("--auto-learn-path", default=None, help="CLAUDE.md를 생성할 디렉토리 (기본: 현재 디렉토리)")
    p_cc.set_defaults(func=setup_claude_code)

    p_cd = setup_sub.add_parser("claude-desktop", help="Claude Desktop config 자동 수정")
    p_cd.add_argument("--openai-key", default=None, help="OpenAI API 키 (벡터 임베딩용)")
    p_cd.set_defaults(func=setup_claude_desktop)

    p_oc = setup_sub.add_parser("openclaw", help="OpenClaw Skill 설치")
    p_oc.add_argument("--path", default=None, help="OpenClaw skills 디렉토리")
    p_oc.set_defaults(func=setup_openclaw)

    p_al = setup_sub.add_parser("auto-learn", help="CLAUDE.md 자동학습 규칙 설치")
    p_al.add_argument("--path", default=None, help="CLAUDE.md를 생성할 디렉토리 (기본: 현재 디렉토리)")
    p_al.set_defaults(func=setup_auto_learn)

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

    # seed (cold-start bootstrapping)
    from chaeshin.cli import seed_cmd
    seed_cmd.add_subparser(sub)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "setup" and not getattr(args, "platform", None):
        p_setup.print_help()
        sys.exit(0)

    if args.command == "seed" and not getattr(args, "seed_command", None):
        seed_parser = sub.choices.get("seed")
        if seed_parser is not None:
            seed_parser.print_help()
            sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
