# Chaeshin (채신) 採薪

> *"Dale un plan a un agente y resolverá una tarea. Enséñale a buscar planes y los resolverá todos."*

**Chaeshin** es un framework de Razonamiento Basado en Casos (CBR) para llamadas a herramientas de LLM. Almacena grafos de ejecución de herramientas exitosos, los recupera para problemas similares y los adapta a nuevas situaciones.

El nombre proviene de 교자채신(敎子採薪) — *"No des leña; enseña a recogerla."*

[English](../../README.md) | [한국어](../ko/README.md)

---

## Integraciones — Configuración en una línea

Ambas plataformas comparten `~/.chaeshin/cases.json` — los casos guardados por Claude Code pueden ser reutilizados por OpenClaw, y viceversa.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Arquitectura de Integración de Chaeshin — Claude Code y OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Esto registra un servidor [MCP](https://modelcontextprotocol.io/) de Chaeshin con Claude Code. Cuatro nuevas herramientas estarán disponibles:

| Herramienta | Descripción |
|-------------|-------------|
| `chaeshin_retrieve` | Busca casos anteriores — devuelve éxitos + advertencias de anti-patrones |
| `chaeshin_retain` | Guarda grafos de ejecución (éxitos y fallos) |
| `chaeshin_anticipate` | Obtiene sugerencias proactivas basadas en el contexto actual |
| `chaeshin_stats` | Muestra estadísticas del almacén de casos |

Antes de improvisar una tarea de múltiples pasos, Claude verifica si existe un patrón similar. Retrieve devuelve tanto casos exitosos a seguir **como** advertencias sobre fallos pasados a evitar. Después de completar una tarea, guarda el grafo de ejecución. Las ejecuciones fallidas también se guardan con la razón del error para no repetir el mismo error.

<details>
<summary>Configuración manual (si la CLI de <code>claude</code> no está disponible)</summary>

Añadir a `~/.claude.json`:

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

Esto instala un `SKILL.md` en `~/.openclaw/workspace/skills/chaeshin/`. Tu agente OpenClaw comenzará a usar la memoria de grafos de herramientas — recuperando patrones anteriores antes de ejecutar, y reteniendo los exitosos.

La CLI puente proporciona acceso basado en JSON para el modelo de subproceso de OpenClaw:

```bash
# Buscar casos similares
python -m chaeshin.integrations.openclaw.bridge retrieve "deploy to staging"

# Guardar un patrón exitoso
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "deploy to staging" \
    --graph '{"nodes":[...],"edges":[...]}'

# Ver estadísticas
python -m chaeshin.integrations.openclaw.bridge stats
```

### Independiente (cualquier agente)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

# Recuperar un caso pasado similar
results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))

# Usar el grafo de herramientas de la mejor coincidencia
if results:
    graph = results[0][0].solution.tool_graph
    # ejecutar grafo...
```

### Estructura del Proyecto

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # Servidor MCP (protocolo stdio)
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + CLI puente (subproceso)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # Adaptador LLM + embeddings
│   └── chroma.py           # Almacén de casos VectorDB
├── schema.py               # Tipos de datos principales
├── case_store.py            # CBR recuperar / retener
├── graph_executor.py        # Ejecutor de grafos de herramientas
└── planner.py               # Creación / adaptación / replanificación de grafos con LLM
```

---

## ¿Por qué Chaeshin?

La mayoría de los agentes LLM improvisan llamadas a herramientas sobre la marcha (estilo ReAct) o siguen pipelines rígidos codificados por desarrolladores. Ambos enfoques tienen limitaciones:

- **Improvisado**: El LLM puede saltarse pasos, llamar herramientas en el orden incorrecto o repetir errores que ya cometió.
- **Codificado**: Cada nuevo escenario requiere cambios de código. No escala.

Chaeshin adopta un enfoque diferente: **recordar lo que funcionó y reutilizarlo.**

Cuando llega una solicitud, Chaeshin busca un caso pasado similar, extrae el grafo de ejecución de herramientas que funcionó, lo adapta si es necesario, lo ejecuta y — si tiene éxito — lo guarda para uso futuro. Este es el ciclo clásico de [Razonamiento Basado en Casos](https://es.wikipedia.org/wiki/Razonamiento_basado_en_casos): **Recuperar → Reutilizar → Revisar → Retener**.

## LLM Simple vs Chaeshin

<p align="center">
  <img src="../../assets/comparison.svg" alt="LLM Simple vs Chaeshin — comparación con tostada de queso" width="820"/>
</p>

## Conceptos Principales

### Grafo de Herramientas

Las llamadas a herramientas se estructuran como un **grafo** (no solo un DAG — se admiten ciclos).

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Ejemplo de Grafo de Herramientas — Estofado de Kimchi" width="720"/>
</p>

### Caso CBR

Cada caso es una tupla de `(problema, solución, resultado, metadatos)`:

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

### Grafo Inmutable + Contexto Mutable

El grafo de herramientas nunca cambia durante la ejecución. Solo se actualiza el **contexto de ejecución** (posición del cursor, estados de los nodos, salidas). Si ocurre algo inesperado y no existe una arista coincidente, se le pide al LLM que modifique el grafo mediante un diff — añadiendo o eliminando nodos y aristas.

### ¿Qué pasa cuando algo sale mal?

La ejecución en el mundo real no siempre sigue el plan. Chaeshin maneja esto mediante **replanificación basada en diffs** — el LLM solo interviene cuando no existe una arista coincidente:

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Escenarios de Replanificación — Llamada telefónica, Alergia, Ingrediente faltante" width="780"/>
</p>

La idea clave: el grafo permanece inmutable durante la ejecución normal. Solo cuando una excepción **no tiene una arista coincidente**, el LLM interviene para modificar el grafo mediante un diff mínimo — no una regeneración completa.

## Instalación

```bash
pip install chaeshin
```

O con [uv](https://docs.astral.sh/uv/):

```bash
uv pip install chaeshin
```

Desde el código fuente:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # recomendado
# o: pip install -e ".[dev]"
```

## Inicio Rápido

**Demo basada en reglas** (no se necesita clave API):

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**Demo LLM + VectorDB** (OpenAI + ChromaDB):

```bash
cp .env.example .env         # añade tu OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```

Esto ejecuta el ciclo CBR completo con creación de grafos impulsada por LLM real, recuperación de casos basada en vectores y replanificación basada en diffs.

**Demo con interfaz web** (Gradio):

```bash
cp .env.example .env         # añade tu OPENAI_API_KEY
uv run python -m examples.cooking.app
```

Abre una interfaz de navegador donde puedes ingresar cualquier solicitud de cocina y observar el pipeline CBR ejecutarse paso a paso.

Consulta la [Guía de Inicio Rápido](../quickstart.md) para un recorrido paso a paso.

## Arquitectura

<p align="center">
  <img src="../../assets/architecture.svg" alt="Arquitectura de Chaeshin" width="600"/>
</p>

## Trabajo Relacionado

Chaeshin se inspira en ideas de:

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — Encuesta sobre integración CBR + LLM
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — Agente de ciencia de datos basado en CBR
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Biblioteca de habilidades con aprendizaje basado en experiencia
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — Ejecución paralela de herramientas mediante grafos
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Reparación jerárquica de planes

**¿Qué lo diferencia?** Chaeshin combina el almacenamiento de grafos de herramientas como casos CBR, grafos generales con ciclos (no solo DAGs), modificación de grafos basada en diffs en lugar de regeneración completa, y ejecución híbrida donde el código maneja el flujo normal mientras el LLM solo interviene en excepciones.

## Licencia

Licencia MIT — ver [LICENSE](../../LICENSE)

---

*敎子採薪 — No des leña; enseña a recogerla.*
