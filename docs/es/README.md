# Chaeshin (채신) 採薪

**Agentes LLM que recuerdan lo que funcionó.** En lugar de improvisar llamadas a herramientas cada vez, Chaeshin almacena patrones de ejecución exitosos y los reutiliza — así tu agente mejora con cada tarea.

<p align="center">
  <img src="../../assets/comparison.svg" alt="LLM simple vs Chaeshin — el mismo error vs patrón aprendido" width="820"/>
</p>

[English](../../README.md) | [한국어](../ko/README.md) | [中文](../zh/README.md) | [日本語](../ja/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md)

---

## El Problema

La mayoría de los agentes LLM **improvisan** llamadas a herramientas sobre la marcha o siguen pipelines **codificados**:

- **Improvisado** (estilo ReAct): Se salta pasos, orden incorrecto, repite los mismos errores.
- **Codificado**: Cada nuevo escenario requiere cambios de código. No escala.

## La Solución

Chaeshin recuerda lo que funcionó. Cuando llega una solicitud similar, recupera un grafo de ejecución de herramientas probado, lo adapta, lo ejecuta y guarda el resultado. Esto es [Razonamiento Basado en Casos](https://es.wikipedia.org/wiki/Razonamiento_basado_en_casos): **Recuperar → Reutilizar → Revisar → Retener.**

Los fallos también se guardan — así el mismo error nunca se repite.

```
Día 1:    El agente improvisa todo desde cero
Día 7:    20 casos guardados — los patrones comunes se reutilizan
Día 30:   100+ casos — el agente rara vez improvisa, sigue patrones probados
```

---

## Inicio Rápido

### 1. Instalar

```bash
pip install chaeshin
```

### 2. Conectar a tu agente

```bash
chaeshin setup claude-code       # Claude Code (MCP + auto-aprendizaje)
chaeshin setup claude-desktop    # Claude Desktop
chaeshin setup openclaw          # OpenClaw
```

Eso es todo. Claude ahora automáticamente:
- **Antes** de tareas de múltiples pasos → recupera patrones anteriores
- **Después** de completar tareas → guarda el grafo de ejecución
- **En caso de fallo** → guarda el patrón fallido para no repetirlo

<details>
<summary>Otros métodos de instalación</summary>

Con [uv](https://docs.astral.sh/uv/) (recomendado):

```bash
uv pip install chaeshin
```

Con `uvx` (sin instalación global):

```bash
uvx chaeshin setup claude-code --uvx
```

Configuración manual de MCP (añadir a `~/.claude.json`):

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
<summary>Uso como biblioteca independiente (cualquier agente)</summary>

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```
</details>

### 3. Probar la demo

```bash
git clone https://github.com/GEOHYEON/chaeshin.git && cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent   # no se necesita clave API
```

<details>
<summary>Demo LLM + VectorDB (OpenAI + ChromaDB)</summary>

```bash
cp .env.example .env         # añade tu OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```
</details>

<details>
<summary>Demo con interfaz web (Gradio)</summary>

```bash
cp .env.example .env
uv run python -m examples.cooking.app
```
</details>

Consulta la [Guía de Inicio Rápido](../quickstart.md) para un recorrido completo.

---

## Cómo Funciona

### Grafo de Herramientas

Las llamadas a herramientas se estructuran como un **grafo** — no una simple lista. Los nodos son invocaciones de herramientas; las aristas definen el orden y las condiciones. Se admiten ciclos (ej., "probar → muy soso → cocinar más → probar de nuevo").

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Grafo de Herramientas — nodos, aristas, condiciones, ciclos" width="720"/>
</p>

### Grafo Inmutable + Contexto Mutable

El grafo nunca cambia durante la ejecución. Solo se actualiza el **contexto de ejecución** (cursor, estados de los nodos, salidas). Si ocurre algo inesperado y ninguna arista coincide, el LLM modifica el grafo mediante un **diff** mínimo — no una regeneración completa.

### Cuando Algo Sale Mal

La ejecución real no siempre sigue el plan. Chaeshin maneja esto mediante **replanificación basada en diffs**:

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Replanificación — llamada telefónica, alerta de alergia, ingrediente faltante" width="780"/>
</p>

---

## Ejemplo Completo — Preparar una Mesa para Cenar

Un recorrido completo: "Prepara la cena para 3, el niño tiene alergia al camarón." Muestra cada paso — recuperar, descomponer en capas, cocción en paralelo, ciclos de prueba de sabor y escalamiento de fallos.

<p align="center">
  <img src="../../assets/dinner-table-success.svg" alt="Éxito — Recuperar → Descomponer → Ejecutar → Retener" width="820"/>
</p>

<p align="center">
  <img src="../../assets/dinner-table-failure.svg" alt="Fallo — Escalamiento de L1 → L2 → Usuario → Recuperación" width="820"/>
</p>

Escenario completo con explicaciones paso a paso:
[English](../../examples/dinner-table/scenario_en.md) ·
[한국어](../../examples/dinner-table/scenario_ko.md) ·
[日本語](../../examples/dinner-table/scenario_ja.md) ·
[中文](../../examples/dinner-table/scenario_zh.md)

---

## Integraciones

Todas las plataformas comparten `~/.chaeshin/cases.json` — los casos guardados en Claude Code funcionan en OpenClaw y viceversa.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Arquitectura de Integración — Claude Code y OpenClaw" width="820"/>
</p>

| Plataforma | Comando | Qué hace |
|------------|---------|----------|
| Claude Code | `chaeshin setup claude-code` | Servidor MCP + reglas de auto-aprendizaje (`CLAUDE.md`) |
| Claude Desktop | `chaeshin setup claude-desktop` | Edita automáticamente `claude_desktop_config.json` |
| OpenClaw | `chaeshin setup openclaw` | Instala `SKILL.md` en el workspace |

Tres herramientas quedan disponibles después de la configuración:

| Herramienta | Descripción |
|-------------|-------------|
| `chaeshin_retrieve` | Busca casos anteriores — devuelve éxitos y fallos por separado |
| `chaeshin_retain` | Guarda grafos de ejecución (éxitos y fallos) |
| `chaeshin_stats` | Muestra estadísticas del almacén de casos |

---

## Monitor — Editor Visual de Grafos

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Editor Visual de Grafos" width="720"/>
</p>

Un editor web de grafos de herramientas construido con Next.js y React Flow. Arrastra y suelta nodos, dibuja aristas, establece condiciones, importa/exporta casos desde `~/.chaeshin/cases.json`.

```bash
cd chaeshin-monitor && pnpm install && pnpm dev
```

---

## Arquitectura

<p align="center">
  <img src="../../assets/architecture.svg" alt="Arquitectura de Chaeshin" width="600"/>
</p>

<details>
<summary>Estructura del proyecto</summary>

```
chaeshin/
├── schema.py               # Tipos de datos principales (Case, ToolGraph, GraphNode, GraphEdge)
├── case_store.py           # Ciclo CBR 4R: recuperar, reutilizar, revisar, retener
├── graph_executor.py       # Ejecutor de grafos de herramientas (paralelo, ciclos, condiciones)
├── planner.py              # Creación / adaptación / replanificación de grafos con LLM (basado en diffs)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
├── integrations/
│   ├── claude_code/        # Servidor MCP (FastMCP) + plantilla de auto-aprendizaje CLAUDE.md
│   ├── openclaw/           # SKILL.md + CLI puente
│   ├── openai.py           # Adaptador LLM + embeddings
│   ├── chroma.py           # Almacén de casos vectorial ChromaDB
│   └── chaebi.py           # Sincronización con marketplace Chaebi
└── agents/                 # v2: Orchestrator, Decomposer, Executor, Reflection
chaeshin-monitor/           # Interfaz web Next.js
examples/cooking/           # Agente demo (estofado de kimchi, estofado de doenjang, escenarios de recuperación)
examples/dinner-table/      # Recorrido completo (4 idiomas)
```
</details>

## Requisitos

- Python 3.10+
- Sin dependencias requeridas para uso básico
- Opcionales: `openai` (adaptador LLM), `chromadb` (almacén vectorial), `httpx` (marketplace Chaebi)

## Trabajo Relacionado

Chaeshin se inspira en ideas de:

- [CBR for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — Encuesta sobre integración CBR + LLM
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — Agente de ciencia de datos basado en CBR
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Biblioteca de habilidades con aprendizaje basado en experiencia
- [GAP (2025)](https://arxiv.org/html/2510.25320v1) — Ejecución paralela de herramientas mediante grafos
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Reparación jerárquica de planes

**¿Qué lo diferencia?** Grafos de herramientas almacenados como casos CBR, grafos generales con ciclos (no solo DAGs), modificación basada en diffs en lugar de regeneración completa, y ejecución híbrida donde el código maneja el flujo normal mientras el LLM solo interviene en excepciones.

## Licencia

MIT — ver [LICENSE](../../LICENSE)

---

*敎子採薪 — No des leña; enseña a recogerla.*
