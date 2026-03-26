"""
Chaeshin CLI — 한 줄 셋업.

Usage:
    # Claude Code에 연결
    chaeshin setup claude-code

    # OpenClaw Skill로 설치
    chaeshin setup openclaw

    # 저장소 통계
    chaeshin stats

    # 케이스 검색
    chaeshin retrieve "김치찌개 만들어줘"
"""

from chaeshin.cli.main import main

if __name__ == "__main__":
    main()
