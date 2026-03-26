#!/usr/bin/env python3
"""Chaeshin MCP Server — 경량 엔트리포인트.

chaeshin/__init__.py와 structlog의 무거운 import를 건너뛰고
schema + case_store만 직접 로드하여 ~0.1초 이내 기동.

Usage:
    python server_main.py
    또는: claude mcp add chaeshin -- python /path/to/server_main.py
"""
import os
import sys
import types
import logging

# ── 경량 부트스트랩 ──────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(os.path.dirname(_HERE))
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 1) chaeshin/__init__.py 건너뛰기 (GraphExecutor, planner 등 불필요)
_pkg = types.ModuleType("chaeshin")
_pkg.__path__ = [_PKG_DIR]
_pkg.__version__ = "0.1.0"
sys.modules["chaeshin"] = _pkg

# 2) structlog → stdlib logging 대체 (~0.6초 절약)
_fake = types.ModuleType("structlog")
_fake.get_logger = lambda *a, **k: logging.getLogger(a[0] if a else "chaeshin")
sys.modules["structlog"] = _fake

# ── 서버 실행 ────────────────────────────────────────────────

from chaeshin.integrations.claude_code.mcp_server import run_server  # noqa: E402

if __name__ == "__main__":
    run_server()
