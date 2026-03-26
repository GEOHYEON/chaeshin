# Chaeshin (採薪)

> *"Donnez un plan à un agent, il résout une tâche. Apprenez-lui à chercher des plans, il les résout tous."*

**Chaeshin** est un framework de Case-Based Reasoning (CBR) pour l'appel d'outils LLM. Il stocke les graphes d'exécution d'outils réussis, les récupère pour des problèmes similaires et les adapte à de nouvelles situations.

敎子採薪 — *Ne donne pas du bois; enseigne comment le ramasser.*

[English](../../README.md) | [한국어](../ko/README.md)

---

## Intégrations — Configuration en une ligne

Les deux plateformes partagent `~/.chaeshin/cases.json` — les cas enregistrés par Claude Code peuvent être réutilisés par OpenClaw, et inversement.

<p align="center">
  <img src="../../assets/integrations.svg" alt="Architecture d'intégration Chaeshin — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Cela enregistre un serveur [MCP](https://modelcontextprotocol.io/) Chaeshin avec Claude Code. Quatre nouveaux outils deviennent disponibles :

| Outil | Description |
|-------|-------------|
| `chaeshin_retrieve` | Recherche de cas passés — retourne les succès + avertissements d'anti-patterns |
| `chaeshin_retain` | Sauvegarde des graphes d'exécution (succès et échecs) |
| `chaeshin_anticipate` | Suggestions proactives basées sur le contexte actuel |
| `chaeshin_stats` | Statistiques du magasin de cas |

Avant d'improviser une tâche à étapes multiples, Claude vérifie si un pattern similaire existe. La récupération retourne à la fois les cas réussis à suivre **et** les avertissements sur les échecs passés à éviter. Après avoir terminé une tâche, il sauvegarde le graphe d'exécution. Les exécutions échouées sont également sauvegardées avec la raison de l'erreur afin de ne pas répéter la même erreur.

<details>
<summary>Configuration manuelle (si la CLI <code>claude</code> n'est pas disponible)</summary>

Ajoutez à `~/.claude.json` :

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

Cela installe un `SKILL.md` dans `~/.openclaw/workspace/skills/chaeshin/`. Votre agent OpenClaw commence à utiliser la mémoire de graphes d'outils — récupérant les patterns passés avant l'exécution et conservant ceux qui réussissent.

La CLI bridge fournit un accès JSON pour le modèle subprocess d'OpenClaw :

```bash
# Rechercher des cas similaires
python -m chaeshin.integrations.openclaw.bridge retrieve "deploy to staging"

# Sauvegarder un pattern réussi
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "deploy to staging" \
    --graph '{"nodes":[...],"edges":[...]}'

# Voir les statistiques
python -m chaeshin.integrations.openclaw.bridge stats
```

### Utilisation autonome (tout agent)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

# Récupérer un cas passé similaire
results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))

# Utiliser le graphe d'outils du meilleur résultat
if results:
    graph = results[0][0].solution.tool_graph
    # exécuter le graphe...
```

### Structure du projet

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # Serveur MCP (protocole stdio)
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + CLI bridge (subprocess)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # Adaptateur LLM + embedding
│   └── chroma.py           # Magasin de cas VectorDB
├── schema.py               # Types de données principaux
├── case_store.py            # CBR récupérer / retenir
├── graph_executor.py        # Moteur d'exécution du graphe d'outils
└── planner.py               # Création / adaptation / re-planification de graphes par LLM
```

---

## Pourquoi Chaeshin ?

La plupart des agents LLM soit improvisent les appels d'outils à la volée (style ReAct), soit suivent des pipelines rigides codés en dur par les développeurs. Les deux approches ont des limites :

- **Improvisé** : Le LLM peut sauter des étapes, appeler les outils dans le mauvais ordre ou répéter des erreurs déjà commises.
- **Codé en dur** : Chaque nouveau scénario nécessite des modifications de code. Ne passe pas à l'échelle.

Chaeshin adopte une approche différente : **se souvenir de ce qui a fonctionné et le réutiliser.**

Lorsqu'une requête arrive, Chaeshin recherche un cas passé similaire, extrait le graphe d'exécution d'outils qui a fonctionné, l'adapte si nécessaire, l'exécute et — en cas de succès — le sauvegarde pour une utilisation future. C'est le cycle classique du [Case-Based Reasoning](https://fr.wikipedia.org/wiki/Raisonnement_%C3%A0_partir_de_cas) : **Récupérer → Réutiliser → Réviser → Retenir**.

## LLM classique vs Chaeshin

<p align="center">
  <img src="../../assets/comparison.svg" alt="LLM classique vs Chaeshin — comparaison du cheese toast" width="820"/>
</p>

## Concepts fondamentaux

### Graphe d'outils

Les appels d'outils sont structurés sous forme de **graphe** (pas seulement un DAG — les boucles sont supportées).

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Exemple de graphe d'outils — Kimchi Stew" width="720"/>
</p>

### Cas CBR

Chaque cas est un tuple `(problem, solution, outcome, metadata)` :

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

### Graphe immuable + Contexte mutable

Le graphe d'outils lui-même ne change jamais pendant l'exécution. Seul le **contexte d'exécution** (position du curseur, états des noeuds, sorties) est mis à jour. Si quelque chose d'inattendu se produit et qu'aucune arête correspondante n'existe, le LLM est invité à modifier le graphe via un diff — en ajoutant ou supprimant des noeuds et des arêtes.

### Que se passe-t-il quand les choses tournent mal ?

L'exécution en conditions réelles ne suit pas toujours le plan. Chaeshin gère cela par la **re-planification basée sur les diffs** — le LLM n'intervient que lorsqu'aucune arête correspondante n'existe :

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="Scénarios de re-planification — Appel téléphonique, Allergie, Ingrédient manquant" width="780"/>
</p>

Le principe clé : le graphe reste immuable pendant l'exécution normale. Ce n'est que lorsqu'une exception **n'a aucune arête correspondante** que le LLM intervient pour modifier le graphe via un diff minimal — pas une régénération complète.

## Installation

```bash
pip install chaeshin
```

Ou avec [uv](https://docs.astral.sh/uv/) :

```bash
uv pip install chaeshin
```

Depuis les sources :

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # recommandé
# ou : pip install -e ".[dev]"
```

## Démarrage rapide

**Démo basée sur les règles** (pas de clé API nécessaire) :

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**Démo LLM + VectorDB** (OpenAI + ChromaDB) :

```bash
cp .env.example .env         # ajoutez votre OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```

Cela exécute le cycle CBR complet avec création de graphes par LLM, récupération de cas par vecteurs et re-planification basée sur les diffs.

**Démo Web UI** (Gradio) :

```bash
cp .env.example .env         # ajoutez votre OPENAI_API_KEY
uv run python -m examples.cooking.app
```

Ouvre une interface web où vous pouvez entrer n'importe quelle requête culinaire et observer le pipeline CBR s'exécuter étape par étape.

Consultez le [Guide de démarrage rapide](../quickstart.md) pour une présentation pas à pas.

## Architecture

<p align="center">
  <img src="../../assets/architecture.svg" alt="Architecture Chaeshin" width="600"/>
</p>

## Travaux connexes

Chaeshin s'inspire de travaux tels que :

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — Enquête sur l'intégration CBR + LLM
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — Agent de data science basé sur le CBR
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Bibliothèque de compétences avec apprentissage par expérience
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — Exécution parallèle d'outils via des graphes
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Réparation de plans hiérarchiques

**En quoi est-ce différent ?** Chaeshin combine le stockage de graphes d'outils en tant que cas CBR, des graphes généraux avec boucles (pas seulement des DAGs), la modification de graphes par diff au lieu d'une régénération complète, et une exécution hybride où le code gère le flux normal tandis que le LLM n'intervient que sur les exceptions.

## Licence

MIT License — voir [LICENSE](../../LICENSE)

---

*敎子採薪 — Ne donne pas du bois; enseigne comment le ramasser.*
