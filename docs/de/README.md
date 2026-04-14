# Chaeshin (채신) 採薪

**LLM-Agenten, die sich merken, was funktioniert hat.** Statt jedes Mal Tool-Aufrufe zu improvisieren, speichert Chaeshin erfolgreiche Ausführungsmuster und verwendet sie wieder — so wird Ihr Agent mit jeder Aufgabe besser.

<p align="center">
  <img src="../../assets/comparison.svg" alt="Einfaches LLM vs Chaeshin — derselbe Fehler vs gelerntes Muster" width="820"/>
</p>

[English](../../README.md) | [한국어](../ko/README.md) | [中文](../zh/README.md) | [日本語](../ja/README.md) | [Español](../es/README.md) | [Français](../fr/README.md)

---

## Das Problem

Die meisten LLM-Agenten **improvisieren** Tool-Aufrufe spontan oder folgen **fest codierten** Pipelines:

- **Improvisiert** (ReAct-Stil): Überspringt Schritte, falsche Reihenfolge, wiederholt dieselben Fehler.
- **Fest codiert**: Jedes neue Szenario erfordert Code-Änderungen. Skaliert nicht.

## Die Lösung

Chaeshin merkt sich, was funktioniert hat. Wenn eine ähnliche Anfrage eingeht, ruft es einen bewährten Tool-Ausführungsgraphen ab, passt ihn an, führt ihn aus und speichert das Ergebnis. Das ist [Case-Based Reasoning](https://de.wikipedia.org/wiki/Fallbasiertes_Schlie%C3%9Fen): **Abrufen → Wiederverwenden → Überarbeiten → Behalten.**

Fehlschläge werden ebenfalls gespeichert — so passiert derselbe Fehler nie zweimal.

```
Tag 1:   Agent improvisiert alles von Grund auf
Tag 7:   20 Fälle gespeichert — häufige Muster werden wiederverwendet
Tag 30:  100+ Fälle — Agent improvisiert selten, folgt bewährten Mustern
```

---

## Schnellstart

### 1. Installation

```bash
pip install chaeshin
```

### 2. Mit Ihrem Agenten verbinden

```bash
chaeshin setup claude-code       # Claude Code (MCP + automatisches Lernen)
chaeshin setup claude-desktop    # Claude Desktop
chaeshin setup openclaw          # OpenClaw
```

Das war's. Claude macht jetzt automatisch:
- **Vor** mehrstufigen Aufgaben → ruft vergangene Muster ab
- **Nach** Abschluss von Aufgaben → speichert den Ausführungsgraphen
- **Bei Fehlern** → speichert das fehlgeschlagene Muster, damit es nie wiederholt wird

<details>
<summary>Andere Installationsmethoden</summary>

Mit [uv](https://docs.astral.sh/uv/) (empfohlen):

```bash
uv pip install chaeshin
```

Mit `uvx` (ohne globale Installation):

```bash
uvx chaeshin setup claude-code --uvx
```

Manuelle MCP-Einrichtung (zu `~/.claude.json` hinzufügen):

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "uv",
      "args": ["tool", "run", "chaeshin-mcp"]
    }
  }
}
```
</details>

<details>
<summary>Als eigenständige Bibliothek verwenden (beliebiger Agent)</summary>

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```
</details>

### 3. Demo ausprobieren

```bash
git clone https://github.com/GEOHYEON/chaeshin.git && cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent   # kein API-Schlüssel erforderlich
```

<details>
<summary>LLM + VectorDB Demo (OpenAI + ChromaDB)</summary>

```bash
cp .env.example .env         # OPENAI_API_KEY eintragen
uv run python -m examples.cooking.chef_agent_llm
```
</details>

<details>
<summary>Web-UI Demo (Gradio)</summary>

```bash
cp .env.example .env
uv run python -m examples.cooking.app
```
</details>

Siehe den [Schnellstart-Leitfaden](../quickstart.md) für eine vollständige Anleitung.

---

## So funktioniert es

### Tool Graph

Tool-Aufrufe werden als **Graph** strukturiert — nicht als einfache Liste. Knoten sind Tool-Aufrufe; Kanten definieren Reihenfolge und Bedingungen. Schleifen werden unterstützt (z.B. „abschmecken → zu fad → weiterkochen → erneut abschmecken").

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Tool Graph — Knoten, Kanten, Bedingungen, Schleifen" width="720"/>
</p>

### Unveränderlicher Graph + Veränderlicher Kontext

Der Graph ändert sich während der Ausführung nie. Nur der **Ausführungskontext** (Cursor, Knotenstatus, Ausgaben) wird aktualisiert. Wenn etwas Unerwartetes passiert und keine Kante passt, modifiziert das LLM den Graphen über einen minimalen **Diff** — keine vollständige Neugenerierung.

### Wenn etwas schiefgeht

Reale Ausführungen folgen nicht immer dem Plan. Chaeshin behandelt dies durch **diff-basiertes Replanning**:

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Replanning — Telefonanruf, Allergie-Warnung, fehlende Zutat" width="780"/>
</p>

---

## Vollständiges Beispiel — Tisch decken für das Abendessen

Eine komplette Anleitung: „Bereite Abendessen für 3 Personen vor, Kind hat Garnelen-Allergie." Zeigt jeden Schritt — Abrufen, Zerlegung in Ebenen, paralleles Kochen, Abschmeck-Schleifen und Fehler-Eskalation.

<p align="center">
  <img src="../../assets/dinner-table-success.svg" alt="Erfolg — Abrufen → Zerlegen → Ausführen → Behalten" width="820"/>
</p>

<p align="center">
  <img src="../../assets/dinner-table-failure.svg" alt="Fehlschlag — Eskalation von L1 → L2 → Benutzer → Wiederherstellung" width="820"/>
</p>

Vollständiges Szenario mit Schritt-für-Schritt-Erklärungen:
[English](../../examples/dinner-table/scenario_en.md) ·
[한국어](../../examples/dinner-table/scenario_ko.md) ·
[日本語](../../examples/dinner-table/scenario_ja.md) ·
[中文](../../examples/dinner-table/scenario_zh.md)

---

## Integrationen

Alle Plattformen teilen sich `~/.chaeshin/cases.json` — Fälle, die in Claude Code gespeichert wurden, funktionieren in OpenClaw und umgekehrt.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Integrationsarchitektur — Claude Code & OpenClaw" width="820"/>
</p>

| Plattform | Befehl | Was es macht |
|-----------|--------|-------------|
| Claude Code | `chaeshin setup claude-code` | MCP-Server + automatische Lernregeln (`CLAUDE.md`) |
| Claude Desktop | `chaeshin setup claude-desktop` | Bearbeitet automatisch `claude_desktop_config.json` |
| OpenClaw | `chaeshin setup openclaw` | Installiert `SKILL.md` im Arbeitsbereich |

Nach der Einrichtung stehen drei Tools zur Verfügung:

| Tool | Beschreibung |
|------|-------------|
| `chaeshin_retrieve` | Vergangene Fälle durchsuchen — gibt Erfolge und Fehlschläge getrennt zurück |
| `chaeshin_retain` | Ausführungsgraphen speichern (Erfolge und Fehlschläge) |
| `chaeshin_stats` | Fallspeicher-Statistiken anzeigen |

---

## Monitor — Visueller Graph-Editor

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Visueller Graph-Editor" width="720"/>
</p>

Ein webbasierter Tool-Graph-Editor, gebaut mit Next.js und React Flow. Knoten per Drag-and-Drop platzieren, Kanten zeichnen, Bedingungen setzen, Fälle aus `~/.chaeshin/cases.json` importieren/exportieren.

```bash
cd chaeshin-monitor && pnpm install && pnpm dev
```

---

## Architektur

<p align="center">
  <img src="../../assets/architecture.svg" alt="Chaeshin Architektur" width="600"/>
</p>

<details>
<summary>Projektstruktur</summary>

```
chaeshin/
├── schema.py               # Kern-Datentypen (Case, ToolGraph, GraphNode, GraphEdge)
├── case_store.py           # CBR 4R-Zyklus: Abrufen, Wiederverwenden, Überarbeiten, Behalten
├── graph_executor.py       # Tool-Graph-Runner (parallel, Schleifen, Bedingungen)
├── planner.py              # LLM-basierte Graph-Erstellung / Anpassung / Replanning (diff-basiert)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
├── integrations/
│   ├── claude_code/        # MCP-Server (FastMCP) + CLAUDE.md Auto-Lern-Vorlage
│   ├── openclaw/           # SKILL.md + Bridge-CLI
│   ├── openai.py           # LLM + Embedding-Adapter
│   ├── chroma.py           # ChromaDB Vektor-Fallspeicher
│   └── chaebi.py           # Chaebi Marktplatz-Synchronisation
└── agents/                 # v2: Orchestrator, Decomposer, Executor, Reflection
chaeshin-monitor/           # Next.js Web-UI
examples/cooking/           # Demo-Agent (Kimchi-Eintopf, Doenjang-Eintopf, Wiederherstellungsszenarien)
examples/dinner-table/      # Vollständige Anleitung (4 Sprachen)
```
</details>

## Anforderungen

- Python 3.10+
- Keine erforderlichen Abhängigkeiten für die Kernnutzung
- Optional: `openai` (LLM-Adapter), `chromadb` (Vektorspeicher), `httpx` (Chaebi Marktplatz)

## Verwandte Arbeiten

Chaeshin baut auf Ideen aus folgenden Arbeiten auf:

- [CBR for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM Integrations-Survey
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR-basierter Data-Science-Agent
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Skill-Bibliothek mit erfahrungsbasiertem Lernen
- [GAP (2025)](https://arxiv.org/html/2510.25320v1) — Parallele Tool-Ausführung über Graphen
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Hierarchische Planreparatur

**Was ist anders?** Tool-Graphen als CBR-Fälle gespeichert, allgemeine Graphen mit Schleifen (nicht nur DAGs), diff-basierte Modifikation statt vollständiger Neugenerierung und hybride Ausführung, bei der Code den normalen Ablauf behandelt, während das LLM nur bei Ausnahmen eingreift.

## Lizenz

MIT — siehe [LICENSE](../../LICENSE)

---

*敎子採薪 — Gib kein Holz; lehre es zu sammeln.*
