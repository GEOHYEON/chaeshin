# Chaeshin (채신) 採薪

**Des agents LLM qui retiennent ce qui a fonctionné.** Au lieu d'improviser des appels d'outils à chaque fois, Chaeshin stocke les patterns d'exécution réussis et les réutilise — votre agent s'améliore à chaque tâche.

<p align="center">
  <img src="../../assets/comparison.svg" alt="LLM classique vs Chaeshin — la même erreur vs un pattern appris" width="820"/>
</p>

[English](../../README.md) | [한국어](../ko/README.md) | [中文](../zh/README.md) | [日本語](../ja/README.md) | [Español](../es/README.md) | [Deutsch](../de/README.md)

---

## Le problème

La plupart des agents LLM soit **improvisent** les appels d'outils à la volée, soit suivent des **pipelines codés en dur** :

- **Improvisé** (style ReAct) : Saute des étapes, mauvais ordre, répète les mêmes erreurs.
- **Codé en dur** : Chaque nouveau scénario nécessite des modifications de code. Ne passe pas à l'échelle.

## La solution

Chaeshin retient ce qui a fonctionné. Lorsqu'une requête similaire arrive, il récupère un graphe d'exécution d'outils éprouvé, l'adapte, l'exécute et sauvegarde le résultat. C'est le [Raisonnement à partir de cas](https://fr.wikipedia.org/wiki/Raisonnement_%C3%A0_partir_de_cas) : **Récupérer → Réutiliser → Réviser → Retenir.**

Les échecs sont aussi sauvegardés — la même erreur ne se reproduit jamais deux fois.

```
Jour 1 :   L'agent improvise tout depuis zéro
Jour 7 :   20 cas sauvegardés — les patterns courants sont réutilisés
Jour 30 :  100+ cas — l'agent improvise rarement, suit des patterns éprouvés
```

---

## Démarrage rapide

### 1. Installation

```bash
pip install chaeshin
```

### 2. Connectez à votre agent

```bash
chaeshin setup claude-code       # Claude Code (MCP + auto-apprentissage)
chaeshin setup claude-desktop    # Claude Desktop
chaeshin setup openclaw          # OpenClaw
```

C'est tout. Claude désormais automatiquement :
- **Avant** les tâches à étapes multiples → récupère les patterns passés
- **Après** l'achèvement d'une tâche → sauvegarde le graphe d'exécution
- **En cas d'échec** → sauvegarde le pattern échoué pour qu'il ne se reproduise jamais

<details>
<summary>Autres méthodes d'installation</summary>

Avec [uv](https://docs.astral.sh/uv/) (recommandé) :

```bash
uv pip install chaeshin
```

Avec `uvx` (sans installation globale) :

```bash
uvx chaeshin setup claude-code --uvx
```

Configuration MCP manuelle (ajoutez à `~/.claude.json`) :

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
<summary>Utilisation en bibliothèque autonome (tout agent)</summary>

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```
</details>

### 3. Essayez la démo

```bash
git clone https://github.com/GEOHYEON/chaeshin.git && cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent   # aucune clé API nécessaire
```

<details>
<summary>Démo LLM + VectorDB (OpenAI + ChromaDB)</summary>

```bash
cp .env.example .env         # ajoutez votre OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```
</details>

<details>
<summary>Démo Web UI (Gradio)</summary>

```bash
cp .env.example .env
uv run python -m examples.cooking.app
```
</details>

Consultez le [Guide de démarrage rapide](../quickstart.md) pour une présentation pas à pas.

---

## Comment ça fonctionne

### Graphe d'outils

Les appels d'outils sont structurés sous forme de **graphe** — pas une simple liste. Les nœuds sont des invocations d'outils ; les arêtes définissent l'ordre et les conditions. Les boucles sont supportées (ex. : « goûter → trop fade → cuire davantage → goûter à nouveau »).

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Graphe d'outils — nœuds, arêtes, conditions, boucles" width="720"/>
</p>

### Graphe immuable + Contexte mutable

Le graphe ne change jamais pendant l'exécution. Seul le **contexte d'exécution** (curseur, états des nœuds, sorties) est mis à jour. Si quelque chose d'inattendu se produit et qu'aucune arête ne correspond, le LLM modifie le graphe via un **diff** minimal — pas une régénération complète.

### Quand les choses tournent mal

L'exécution en conditions réelles ne suit pas toujours le plan. Chaeshin gère cela par la **re-planification basée sur les diffs** :

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Re-planification — appel téléphonique, alerte allergie, ingrédient manquant" width="780"/>
</p>

---

## Exemple complet — Dresser une table pour le dîner

Un parcours complet : « Préparer le dîner pour 3 personnes, un enfant est allergique aux crevettes. » Montre chaque étape — récupération, décomposition en couches, cuisson en parallèle, boucles de vérification du goût et escalade en cas d'échec.

<p align="center">
  <img src="../../assets/dinner-table-success.svg" alt="Succès — Récupérer → Décomposer → Exécuter → Retenir" width="820"/>
</p>

<p align="center">
  <img src="../../assets/dinner-table-failure.svg" alt="Échec — Escalade de L1 → L2 → Utilisateur → Récupération" width="820"/>
</p>

Scénario complet avec explications étape par étape :
[English](../../examples/dinner-table/scenario_en.md) ·
[한국어](../../examples/dinner-table/scenario_ko.md) ·
[日本語](../../examples/dinner-table/scenario_ja.md) ·
[中文](../../examples/dinner-table/scenario_zh.md)

---

## Intégrations

Toutes les plateformes partagent `~/.chaeshin/cases.json` — les cas sauvegardés dans Claude Code fonctionnent dans OpenClaw et inversement.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Architecture d'intégration — Claude Code & OpenClaw" width="820"/>
</p>

| Plateforme | Commande | Ce que ça fait |
|------------|----------|----------------|
| Claude Code | `chaeshin setup claude-code` | Serveur MCP + règles d'auto-apprentissage (`CLAUDE.md`) |
| Claude Desktop | `chaeshin setup claude-desktop` | Modification automatique de `claude_desktop_config.json` |
| OpenClaw | `chaeshin setup openclaw` | Installe `SKILL.md` dans l'espace de travail |

Trois outils deviennent disponibles après la configuration :

| Outil | Description |
|-------|-------------|
| `chaeshin_retrieve` | Recherche de cas passés — retourne les succès et échecs séparément |
| `chaeshin_retain` | Sauvegarde des graphes d'exécution (succès et échecs) |
| `chaeshin_stats` | Statistiques du magasin de cas |

---

## Monitor — Éditeur visuel de graphes

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Éditeur visuel de graphes" width="720"/>
</p>

Un éditeur web de graphes d'outils construit avec Next.js et React Flow. Glissez-déposez des nœuds, tracez des arêtes, définissez des conditions, importez/exportez des cas depuis `~/.chaeshin/cases.json`.

```bash
cd chaeshin-monitor && pnpm install && pnpm dev
```

---

## Architecture

<p align="center">
  <img src="../../assets/architecture.svg" alt="Architecture Chaeshin" width="600"/>
</p>

<details>
<summary>Structure du projet</summary>

```
chaeshin/
├── schema.py               # Types de données principaux (Case, ToolGraph, GraphNode, GraphEdge)
├── case_store.py           # Cycle CBR 4R : récupérer, réutiliser, réviser, retenir
├── graph_executor.py       # Moteur d'exécution du graphe d'outils (parallèle, boucles, conditions)
├── planner.py              # Création / adaptation / re-planification de graphes par LLM (basé sur les diffs)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
├── integrations/
│   ├── claude_code/        # Serveur MCP (FastMCP) + modèle d'auto-apprentissage CLAUDE.md
│   ├── openclaw/           # SKILL.md + CLI bridge
│   ├── openai.py           # Adaptateur LLM + embedding
│   ├── chroma.py           # Magasin de cas vectoriel ChromaDB
│   └── chaebi.py           # Synchronisation avec le marketplace Chaebi
└── agents/                 # v2 : Orchestrateur, Décomposeur, Exécuteur, Réflexion
chaeshin-monitor/           # Interface web Next.js
examples/cooking/           # Agent de démo (kimchi stew, doenjang stew, scénarios de récupération)
examples/dinner-table/      # Parcours complet (4 langues)
```
</details>

## Prérequis

- Python 3.10+
- Aucune dépendance requise pour l'utilisation de base
- Optionnel : `openai` (adaptateur LLM), `chromadb` (magasin vectoriel), `httpx` (marketplace Chaebi)

## Travaux connexes

Chaeshin s'inspire de travaux tels que :

- [CBR for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — Enquête sur l'intégration CBR + LLM
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — Agent de data science basé sur le CBR
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Bibliothèque de compétences avec apprentissage par expérience
- [GAP (2025)](https://arxiv.org/html/2510.25320v1) — Exécution parallèle d'outils via des graphes
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Réparation de plans hiérarchiques

**En quoi est-ce différent ?** Les graphes d'outils sont stockés en tant que cas CBR, avec des graphes généraux supportant les boucles (pas seulement des DAGs), une modification par diff au lieu d'une régénération complète, et une exécution hybride où le code gère le flux normal tandis que le LLM n'intervient que sur les exceptions.

## Licence

MIT — voir [LICENSE](../../LICENSE)

---

*敎子採薪 — Ne donne pas du bois ; enseigne comment le ramasser.*
