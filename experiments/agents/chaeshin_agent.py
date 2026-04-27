"""Chaeshin agents — full + 3 ablation variants.

Variants (matching Table 3 of the paper):
- ChaeshinFullAgent  : recursive + tri-state + cascade
- ChaeshinNoCascade  : recursive + tri-state, no orphan detection
- ChaeshinNoPending  : recursive, binary outcome (agent self-judges)
- ChaeshinNoRecursion: depth=0 only (flat case bank)

Each agent maintains a CaseStore *across tasks* within the same instance
(per-seed), so the runner is expected to keep one Chaeshin agent
instance per (variant, benchmark, seed) tuple. This isolates the
cumulative-memory effect.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from chaeshin.case_store import CaseStore
from chaeshin.event_log import EventLog
from chaeshin.schema import (
    Case, CaseMetadata, GraphEdge, GraphNode, Outcome,
    ProblemFeatures, Solution, ToolGraph,
)
from chaeshin.storage.sqlite_backend import SQLiteBackend

from experiments.agents.base import Agent, RunRecord, StepRecord
from experiments.agents._react_core import react_loop
from experiments.benchmarks.base import ToolSpec


# ─────────────────────────────────────────────────────────────────────
# Shared chaeshin tool wrappers exposed to the LLM
# ─────────────────────────────────────────────────────────────────────


@dataclass
class _ChaeshinConfig:
    """Per-variant flags."""
    enable_recursion: bool = True
    enable_pending: bool = True
    enable_cascade: bool = True
    name: str = "chaeshin_full"


def _make_chaeshin_tools(
    store: CaseStore,
    events: EventLog,
    cfg: _ChaeshinConfig,
    state: Dict[str, Any],
) -> List[ToolSpec]:
    """Returns retrieve/retain/(revise)/(verdict) tools, shaped by ablation flags."""

    def _retrieve(args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get("query", "")
        if not query:
            return {"error": "query required"}
        kw = args.get("keywords", "")
        kw_list = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
        probe = ProblemFeatures(request=query, category=args.get("category", ""), keywords=kw_list)
        result = store.retrieve_with_warnings(probe, top_k=int(args.get("top_k", 3)))
        # Compact view
        def _brief(c, s):
            return {
                "case_id": c.metadata.case_id,
                "sim": round(float(s), 4),
                "request": c.problem_features.request,
                "layer": c.metadata.layer,
                "graph": [n.tool for n in c.solution.tool_graph.nodes][:8],
            }
        payload = {
            "successes": [_brief(c, s) for c, s in result["cases"]],
            "warnings": [_brief(c, s) for c, s in result["warnings"]],
            "total_in_store": len(store.cases),
        }
        if cfg.enable_pending:
            payload["pending"] = [_brief(c, s) for c, s in result.get("pending", [])]
        events.record("retrieve", {"query": query, "n": len(payload["successes"])})
        state["n_retrieves"] += 1
        if payload["successes"] or payload["warnings"]:
            state["retrieve_hits"] += 1
        return payload

    def _retain(args: Dict[str, Any]) -> Dict[str, Any]:
        request = args.get("request", "")
        graph_dict = args.get("graph") or {"nodes": [], "edges": []}
        nodes = [
            GraphNode(id=n.get("id", f"n{i}"), tool=n.get("tool", "?"),
                      params_hint=n.get("params_hint", {}), note=n.get("note", ""))
            for i, n in enumerate(graph_dict.get("nodes", []))
        ]
        edges = [
            GraphEdge(from_node=e.get("from_node", e.get("from", "")),
                      to_node=e.get("to_node", e.get("to")),
                      condition=e.get("condition"))
            for e in graph_dict.get("edges", [])
        ]
        layer = args.get("layer", "L1")
        depth = int(args.get("depth", 0))
        parent = args.get("parent_case_id", "") if cfg.enable_recursion else ""
        parent_node = args.get("parent_node_id", "") if cfg.enable_recursion else ""
        # Pending-vs-binary outcome
        if cfg.enable_pending:
            outcome = Outcome(status="pending")
        else:
            # Agent self-judges (matches Voyager/DS-Agent default)
            inferred_success = bool(args.get("self_success", True))
            outcome = Outcome(
                status="success" if inferred_success else "failure",
                success=inferred_success,
            )
        case = Case(
            problem_features=ProblemFeatures(
                request=request,
                category=args.get("category", ""),
                keywords=[k.strip() for k in args.get("keywords", "").split(",") if k.strip()],
            ),
            solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
            outcome=outcome,
            metadata=CaseMetadata(
                source=cfg.name,
                layer=layer,
                depth=depth if cfg.enable_recursion else 0,
                parent_case_id=parent,
                parent_node_id=parent_node,
            ),
        )
        cid = store.retain(case)
        if parent and cfg.enable_recursion:
            store.link_parent_child(parent, cid, parent_node)
        events.record("retain", {"layer": layer, "parent": parent}, case_ids=[cid])
        state["n_retains"] += 1
        return {"case_id": cid, "outcome_status": outcome.status}

    def _revise(args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id", "")
        nodes = args.get("nodes") or []
        edges = args.get("edges") or []
        result = store.revise_graph(
            case_id, nodes=nodes, edges=edges,
            cascade=cfg.enable_cascade,
            reason=args.get("reason", ""),
        )
        if result is None:
            return {"error": f"case not found: {case_id}"}
        events.record("revise", {
            "added": result["added_nodes"],
            "removed": result["removed_nodes"],
            "orphaned": result["orphaned_children"],
        }, case_ids=[case_id])
        # Stale-reference detection: in the no-cascade variant we mark any
        # child whose parent_node_id was in `removed` as a stale-ref event.
        if not cfg.enable_cascade and result["removed_nodes"]:
            stale_count = 0
            for child in store.cases:
                if (child.metadata.parent_case_id == case_id
                        and child.metadata.parent_node_id in result["removed_nodes"]):
                    stale_count += 1
            if stale_count:
                state["stale_refs"] += stale_count
        return result

    def _verdict(args: Dict[str, Any]) -> Dict[str, Any]:
        # Only meaningful when pending is enabled.
        if not cfg.enable_pending:
            return {"error": "verdict disabled in this variant"}
        case_id = args.get("case_id", "")
        status = args.get("status", "")
        if status not in ("success", "failure"):
            return {"error": "status must be success or failure"}
        case = store.set_verdict(case_id, status, args.get("note", ""))
        if case is None:
            return {"error": f"case not found: {case_id}"}
        events.record("verdict", {"status": status}, case_ids=[case_id])
        state["n_verdicts"] += 1
        return {"case_id": case_id, "outcome_status": status}

    tools = [
        ToolSpec(
            name="chaeshin_retrieve",
            description="Search past cases. Returns successes/warnings"
                        + ("/pending" if cfg.enable_pending else "")
                        + " lists. Call FIRST for any non-trivial task.",
            example_input='{"query": "...", "keywords": "k1,k2", "top_k": 3}',
            fn=_retrieve,
        ),
        ToolSpec(
            name="chaeshin_retain",
            description=(
                "Save the executed graph. " +
                ("Stored as 'pending' until verdict." if cfg.enable_pending
                 else "Pass self_success=true|false to commit outcome immediately.") +
                (" Use parent_case_id+parent_node_id to chain layers."
                 if cfg.enable_recursion else " Flat: no parent linkage.")
            ),
            example_input=('{"request":"...", "category":"...", "keywords":"...", '
                           '"layer":"L1", "depth":0, "graph":{"nodes":[...], "edges":[...]}}'),
            fn=_retain,
        ),
    ]
    if cfg.enable_recursion:
        tools.append(ToolSpec(
            name="chaeshin_revise",
            description=(
                "Replace this layer's graph and " +
                ("cascade to orphan children." if cfg.enable_cascade
                 else "leave child cases untouched (cascade disabled).")
            ),
            example_input='{"case_id":"<id>", "nodes":[...], "edges":[...], "reason":"..."}',
            fn=_revise,
        ))
    if cfg.enable_pending:
        tools.append(ToolSpec(
            name="chaeshin_verdict",
            description="Record user's success/failure verdict on a pending case.",
            example_input='{"case_id":"<id>", "status":"success", "note":"..."}',
            fn=_verdict,
        ))
    return tools


# ─────────────────────────────────────────────────────────────────────
# Agent class
# ─────────────────────────────────────────────────────────────────────


class _ChaeshinBase(Agent):
    """Shared logic; subclasses just override `_cfg`."""

    _cfg: _ChaeshinConfig

    def __init__(self):
        # Per-agent-instance ephemeral DB. Persists across tasks within this
        # instance (= one seed × one variant × one benchmark).
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "chaeshin.db"
        self._backend = SQLiteBackend(self._db_path)
        self._events = EventLog(self._backend, session_id=self._cfg.name)
        self._store = CaseStore(backend=self._backend, auto_load=False)

    def __del__(self):
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def case_count(self) -> int:
        return len(self._store.cases)

    def status_distribution(self) -> Dict[str, int]:
        d: Dict[str, int] = {}
        for c in self._store.cases:
            d[c.outcome.status] = d.get(c.outcome.status, 0) + 1
        return d

    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        # State accumulator for this trial — captures chaeshin-specific metrics.
        state = {
            "n_retrieves": 0, "retrieve_hits": 0,
            "n_retains": 0, "n_verdicts": 0, "stale_refs": 0,
        }
        chaeshin_tools = _make_chaeshin_tools(self._store, self._events, self._cfg, state)

        instructions = (
            "Before any non-trivial task, call chaeshin_retrieve. "
            "After completing, call chaeshin_retain with the graph you "
            "actually executed."
        )
        if self._cfg.enable_recursion:
            instructions += (
                " For composite tasks, chain retains via parent_case_id "
                "from outer layer to leaf."
            )
        if self._cfg.enable_pending:
            instructions += (
                " Stored cases are pending until a user verdict; do NOT "
                "call chaeshin_verdict yourself unless the user explicitly "
                "judges the result."
            )

        steps, final, tokens, latency = await react_loop(
            env,
            adapter,
            role_hint=(
                "You are an agent with persistent memory (Chaeshin) "
                "augmenting your tool calling."
            ),
            extra_tools=chaeshin_tools,
            extra_instructions=instructions,
            max_steps=max_steps,
        )
        outcome = env.outcome()

        return RunRecord(
            agent_name=self._cfg.name,
            benchmark_name="",
            task_id="",
            seed=0,
            steps=steps,
            final_answer=final,
            success=outcome.success,
            failure_reason="" if outcome.success else outcome.reason,
            tokens_used=tokens,
            latency_seconds=latency,
            extras={
                "n_retrieves": state["n_retrieves"],
                "retrieve_hits": state["retrieve_hits"],
                "n_retains": state["n_retains"],
                "n_verdicts": state["n_verdicts"],
                "stale_refs": state["stale_refs"],
                "case_bank_size_after": self.case_count(),
                "status_distribution_after": self.status_distribution(),
                "variant": self._cfg.name,
            },
        )


# ─────────────────────────────────────────────────────────────────────
# Concrete variants
# ─────────────────────────────────────────────────────────────────────


class ChaeshinFullAgent(_ChaeshinBase):
    name = "chaeshin_full"
    def __init__(self):
        self._cfg = _ChaeshinConfig(
            enable_recursion=True, enable_pending=True, enable_cascade=True,
            name="chaeshin_full",
        )
        super().__init__()


class ChaeshinNoCascadeAgent(_ChaeshinBase):
    name = "chaeshin_no_cascade"
    def __init__(self):
        self._cfg = _ChaeshinConfig(
            enable_recursion=True, enable_pending=True, enable_cascade=False,
            name="chaeshin_no_cascade",
        )
        super().__init__()


class ChaeshinNoPendingAgent(_ChaeshinBase):
    name = "chaeshin_no_pending"
    def __init__(self):
        self._cfg = _ChaeshinConfig(
            enable_recursion=True, enable_pending=False, enable_cascade=True,
            name="chaeshin_no_pending",
        )
        super().__init__()


class ChaeshinNoRecursionAgent(_ChaeshinBase):
    name = "chaeshin_no_recursion"
    def __init__(self):
        self._cfg = _ChaeshinConfig(
            enable_recursion=False, enable_pending=True, enable_cascade=False,
            name="chaeshin_no_recursion",
        )
        super().__init__()
