# Chaeshin (採薪)

> *"Gib einem Agenten einen Plan, er löst eine Aufgabe. Lehre ihn Pläne zu finden, er löst sie alle."*

**Chaeshin** ist ein Case-Based Reasoning (CBR) Framework für LLM Tool Calling. Es speichert erfolgreiche Tool-Ausführungsgraphen, ruft sie bei ähnlichen Problemen ab und passt sie an neue Situationen an.

Der Name stammt von 교자채신(敎子採薪) — *"Gib kein Holz; lehre es zu sammeln."*

[English](../../README.md) | [한국어](../ko/README.md)

---

## Integrationen — Einrichtung in einer Zeile

Beide Plattformen teilen sich `~/.chaeshin/cases.json` — Fälle, die von Claude Code gespeichert wurden, können von OpenClaw wiederverwendet werden und umgekehrt.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Chaeshin Integrationsarchitektur — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Dies registriert einen Chaeshin [MCP](https://modelcontextprotocol.io/) Server bei Claude Code. Vier neue Tools werden verfügbar:

| Tool | Beschreibung |
|------|-------------|
| `chaeshin_retrieve` | Vergangene Fälle durchsuchen — gibt Erfolge + Anti-Pattern-Warnungen zurück |
| `chaeshin_retain` | Ausführungsgraphen speichern (Erfolge und Fehlschläge) |
| `chaeshin_anticipate` | Proaktive Vorschläge basierend auf dem aktuellen Kontext |
| `chaeshin_stats` | Fallspeicher-Statistiken anzeigen |

Bevor eine mehrstufige Aufgabe improvisiert wird, prüft Claude, ob ein ähnliches Muster existiert. Retrieve gibt sowohl erfolgreiche Fälle zum Befolgen **als auch** Warnungen über vergangene Fehlschläge zurück. Nach Abschluss einer Aufgabe wird der Ausführungsgraph gespeichert. Fehlgeschlagene Ausführungen werden ebenfalls mit Fehlergrund gespeichert, damit derselbe Fehler nicht wiederholt wird.

<details>
<summary>Manuelle Einrichtung (wenn die <code>claude</code> CLI nicht verfügbar ist)</summary>

Zu `~/.claude.json` hinzufügen:

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "python",
      "args": ["-m", "chaeshin.integrations.claude_code.mcp_server"]
    }
  }
}
```
</details>

### OpenClaw

```bash
pip install chaeshin && chaeshin setup openclaw
```

Dies installiert eine `SKILL.md` in `~/.openclaw/workspace/skills/chaeshin/`. Ihr OpenClaw-Agent beginnt mit der Nutzung des Tool-Graph-Speichers — er ruft vergangene Muster vor der Ausführung ab und speichert erfolgreiche.

Die Bridge-CLI bietet JSON-basierten Zugriff für das Subprocess-Modell von OpenClaw:

```bash
# Ähnliche Fälle suchen
python -m chaeshin.integrations.openclaw.bridge retrieve "deploy to staging"

# Erfolgreiches Muster speichern
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "deploy to staging" \
    --graph '{"nodes":[...],"edges":[...]}'

# Statistiken anzeigen
python -m chaeshin.integrations.openclaw.bridge stats
```

### Eigenständig (beliebiger Agent)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

# Ähnlichen vergangenen Fall abrufen
results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))

# Den Tool-Graphen des besten Treffers verwenden
if results:
    graph = results[0][0].solution.tool_graph
    # Graph ausführen...
```

### Projektstruktur

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # MCP-Server (stdio-Protokoll)
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + Bridge-CLI (Subprocess)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # LLM + Embedding-Adapter
│   └── chroma.py           # VectorDB-Fallspeicher
├── schema.py               # Kern-Datentypen
├── case_store.py            # CBR Abrufen / Speichern
├── graph_executor.py        # Tool-Graph-Runner
└── planner.py               # LLM-basierte Graph-Erstellung / Anpassung / Replanning
```

---

## Warum Chaeshin?

Die meisten LLM-Agenten improvisieren Tool-Aufrufe spontan (ReAct-Stil) oder folgen starren, von Entwicklern fest codierten Pipelines. Beide Ansätze haben Grenzen:

- **Improvisiert**: Das LLM könnte Schritte überspringen, Tools in der falschen Reihenfolge aufrufen oder frühere Fehler wiederholen.
- **Fest codiert**: Jedes neue Szenario erfordert Code-Änderungen. Skaliert nicht.

Chaeshin verfolgt einen anderen Ansatz: **Erinnere dich, was funktioniert hat, und verwende es wieder.**

Wenn eine Anfrage eingeht, sucht Chaeshin nach einem ähnlichen vergangenen Fall, holt den funktionierenden Tool-Ausführungsgraphen heraus, passt ihn bei Bedarf an, führt ihn aus und — bei Erfolg — speichert ihn für zukünftige Verwendung. Dies ist der klassische [Case-Based Reasoning](https://de.wikipedia.org/wiki/Fallbasiertes_Schlie%C3%9Fen)-Zyklus: **Abrufen → Wiederverwenden → Überarbeiten → Behalten**.

## Einfaches LLM vs Chaeshin

<p align="center">
  <img src="../../assets/comparison.svg" alt="Einfaches LLM vs Chaeshin — Käsetoast-Vergleich" width="820"/>
</p>

## Kernkonzepte

### Tool Graph

Tool-Aufrufe werden als **Graph** strukturiert (nicht nur ein DAG — Schleifen werden unterstützt).

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Tool-Graph-Beispiel — Kimchi-Eintopf" width="720"/>
</p>

### CBR Case

Jeder Fall ist ein Tupel aus `(problem, solution, outcome, metadata)`:

```python
Case(
    problem_features=ProblemFeatures(
        request="Make kimchi stew",
        category="stew",
        keywords=["kimchi", "stew", "pork"],
    ),
    solution=Solution(
        tool_graph=ToolGraph(nodes=[...], edges=[...])
    ),
    outcome=Outcome(success=True, user_satisfaction=0.90),
    metadata=CaseMetadata(used_count=25, avg_satisfaction=0.88),
)
```

### Unveränderlicher Graph + Veränderlicher Kontext

Der Tool Graph selbst ändert sich während der Ausführung nie. Nur der **Ausführungskontext** (Cursorposition, Knotenstatus, Ausgaben) wird aktualisiert. Wenn etwas Unerwartetes passiert und keine passende Kante existiert, wird das LLM gebeten, den Graphen per Diff zu modifizieren — Knoten und Kanten hinzuzufügen oder zu entfernen.

### Was passiert, wenn etwas schiefgeht?

Reale Ausführungen folgen nicht immer dem Plan. Chaeshin behandelt dies durch **diff-basiertes Replanning** — das LLM greift nur ein, wenn keine passende Kante existiert:

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Replanning-Szenarien — Telefonanruf, Allergie, fehlende Zutat" width="780"/>
</p>

Die zentrale Erkenntnis: Der Graph bleibt während der normalen Ausführung unveränderlich. Nur wenn eine Ausnahme **keine passende Kante** hat, greift das LLM ein, um den Graphen mit einem minimalen Diff zu modifizieren — keine vollständige Neugenerierung.

## Installation

```bash
pip install chaeshin
```

Oder mit [uv](https://docs.astral.sh/uv/):

```bash
uv pip install chaeshin
```

Aus dem Quellcode:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # empfohlen
# oder: pip install -e ".[dev]"
```

## Schnellstart

**Regelbasiertes Demo** (kein API-Schlüssel erforderlich):

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**LLM + VectorDB Demo** (OpenAI + ChromaDB):

```bash
cp .env.example .env         # OPENAI_API_KEY eintragen
uv run python -m examples.cooking.chef_agent_llm
```

Dies führt den vollständigen CBR-Zyklus mit echter LLM-gesteuerter Graph-Erstellung, vektorbasiertem Fallabruf und diff-basiertem Replanning aus.

**Web-UI Demo** (Gradio):

```bash
cp .env.example .env         # OPENAI_API_KEY eintragen
uv run python -m examples.cooking.app
```

Öffnet eine Browser-Oberfläche, in der Sie eine beliebige Kochanfrage eingeben und die CBR-Pipeline Schritt für Schritt verfolgen können.

Siehe den [Schnellstart-Leitfaden](../quickstart.md) für eine schrittweise Anleitung.

## Architektur

<p align="center">
  <img src="../../assets/architecture.svg" alt="Chaeshin Architektur" width="600"/>
</p>

## Verwandte Arbeiten

Chaeshin baut auf Ideen aus folgenden Arbeiten auf:

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM Integrations-Survey
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR-basierter Data-Science-Agent
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Skill-Bibliothek mit erfahrungsbasiertem Lernen
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — Parallele Tool-Ausführung über Graphen
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Hierarchische Planreparatur

**Was ist anders?** Chaeshin kombiniert Tool-Graph-Speicherung als CBR-Fälle, allgemeine Graphen mit Schleifen (nicht nur DAGs), diff-basierte Graph-Modifikation statt vollständiger Neugenerierung und hybride Ausführung, bei der Code den normalen Ablauf behandelt, während das LLM nur bei Ausnahmen eingreift.

## Lizenz

MIT License — siehe [LICENSE](../../LICENSE)

---

*敎子採薪 — Gib kein Holz; lehre es zu sammeln.*
