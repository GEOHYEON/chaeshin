# 採薪 (Chaeshin)

> **「エージェントに計画を与えれば一つの課題を解く。計画を探す方法を教えれば全てを解く。」**

**採薪**はLLMツール呼び出し（Tool Calling）のためのCase-Based Reasoning（CBR）フレームワークです。過去に成功したツール実行グラフを保存し、似た問題が来たら取り出して使い、状況に合わせて修正して実行します。

敎子採薪 — *薪を与えるな、薪の集め方を教えよ。*

[English](../../README.md) | [한국어](../ko/README.md)

---

## 連携 — ワンラインセットアップ

両プラットフォームとも `~/.chaeshin/cases.json` を共有します — Claude Codeで蓄積したケースをOpenClawで使うことができ、その逆も可能です。

<p align="center">
  <img src="../../assets/integrations.svg" alt="採薪 連携構造 — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Chaeshin [MCP](https://modelcontextprotocol.io/) サーバーがClaude Codeに登録されます。4つのツールが追加されます：

| ツール | 説明 |
|--------|------|
| `chaeshin_retrieve` | 類似ケース検索 — 成功ケース + アンチパターン警告 |
| `chaeshin_retain` | 実行グラフ保存（成功/失敗の両方） |
| `chaeshin_anticipate` | プロアクティブ提案 — 現在のコンテキストに基づく先行提案 |
| `chaeshin_stats` | ストア統計 |

マルチステップ作業の前に類似パターンを検索します。成功ケースとともに過去に失敗した**アンチパターン警告**も返します。完了後に実行グラフを保存し、失敗した実行も理由とともに保存して同じミスを繰り返さないようにします。

<details>
<summary>手動設定（<code>claude</code> CLIがない場合）</summary>

`~/.claude.json` に追加：

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

`~/.openclaw/workspace/skills/chaeshin/` に `SKILL.md` がインストールされます。OpenClawエージェントがTool Graphメモリを使い始めます。

ブリッジCLIでJSON基盤の検索・保存が可能です：

```bash
# 類似ケース検索
python -m chaeshin.integrations.openclaw.bridge retrieve "ステージングデプロイ"

# 成功パターン保存
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "ステージングデプロイ" \
    --graph '{"nodes":[...],"edges":[...]}'

# 統計確認
python -m chaeshin.integrations.openclaw.bridge stats
```

### 単独使用（any agent）

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="SlackにPR要約を送って"))
if results:
    graph = results[0][0].solution.tool_graph
```

### プロジェクト構造

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # MCPサーバー（stdioプロトコル）
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + ブリッジCLI（subprocess）
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # LLM + エンベディングアダプター
│   └── chroma.py           # VectorDBケースストア
├── schema.py               # コアデータ型
├── case_store.py            # CBR検索 / 保存
├── graph_executor.py        # Tool Graph実行エンジン
└── planner.py               # LLM基盤グラフ生成 / 適応 / リプランニング
```

---

## なぜ採薪か？

ほとんどのLLMエージェントはツール呼び出しを即興で行うか（ReAct）、開発者が書いた固定パイプラインに従います。どちらにも限界があります。

- **即興型**：LLMがステップを飛ばしたり、順序を間違えたり、同じミスを繰り返します。
- **固定型**：新しい状況のたびにコードを修正する必要があります。拡張が困難です。

採薪は異なるアプローチを取ります：**うまくいったことを記憶し、再利用する。**

リクエストが来たら類似の過去ケースを探し、その時成功したツール実行グラフを取り出し、必要に応じて修正し、実行した後、成功すれば再び保存します。これが[Case-Based Reasoning](https://ja.wikipedia.org/wiki/%E4%BA%8B%E4%BE%8B%E3%83%99%E3%83%BC%E3%82%B9%E6%8E%A8%E8%AB%96)の**検索 → 再利用 → 修正 → 保持**サイクルです。

## 一般LLM vs 採薪

<p align="center">
  <img src="../../assets/comparison.svg" alt="一般LLM vs 採薪 — チーズトースト比較" width="820"/>
</p>

## コアコンセプト

### Tool Graph — 実行設計図

ツール呼び出しを**グラフ構造**で表現します。DAGではなく一般グラフなので**ループ**も可能です。

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Tool Graph例 — キムチチゲ" width="720"/>
</p>

### CBR Case — 問題・解法・結果・メタ

各ケースは `(problem, solution, outcome, metadata)` タプルです：

```python
Case(
    problem_features=ProblemFeatures(
        request="キムチチゲを作って",
        category="チゲ類",
        keywords=["キムチ", "チゲ", "熟成キムチ"],
    ),
    solution=Solution(
        tool_graph=ToolGraph(nodes=[...], edges=[...])
    ),
    outcome=Outcome(success=True, user_satisfaction=0.90),
    metadata=CaseMetadata(used_count=25, avg_satisfaction=0.88),
)
```

### 不変グラフ + 可変コンテキスト

Tool Graphは実行中に変わりません。変わるのは**実行コンテキスト**（カーソル位置、ノード状態、出力値）だけです。予期しない状況が発生してマッチするエッジがない場合にのみ、LLMにグラフの修正を要求します。修正はdiff形式（ノード/エッジの追加・削除）で行われます。

### 予期しない状況が発生したら？

実行中、常に計画通りにはいきません。採薪は**diff基盤リプランニング**でこれを処理します — マッチするエッジがない場合にのみLLMが介入します：

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="リプランニングシナリオ — 電話、アレルギー、材料不足" width="780"/>
</p>

核心原理：正常実行中はグラフが不変です。**マッチするエッジがない例外**が発生した場合にのみLLMが介入して最小限のdiffでグラフを修正します。全体再生成ではなく変更分のみを適用します。

## インストール

```bash
pip install chaeshin
```

または [uv](https://docs.astral.sh/uv/) で：

```bash
uv pip install chaeshin
```

ソースから：

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # 推奨
# または: pip install -e ".[dev]"
```

## クイックスタート — キムチチゲシェフ

**ルールベースデモ**（APIキー不要）：

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**LLM + VectorDB デモ**（OpenAI + ChromaDB）：

```bash
cp .env.example .env         # OPENAI_API_KEYを入力
uv run python -m examples.cooking.chef_agent_llm
```

**Web UI デモ**（Gradio）：

```bash
cp .env.example .env         # OPENAI_API_KEYを入力
uv run python -m examples.cooking.app
```

ブラウザで料理リクエストを入力すると、CBRパイプラインがステップごとに実行される様子を確認できます。

```python
from chaeshin import CaseStore, GraphExecutor, ProblemFeatures

# 1. CBRケースストアをロード
store = CaseStore()
store.load_json(open("cases.json").read())

# 2. 類似ケース検索
problem = ProblemFeatures(
    request="キムチチゲ2人分作って",
    category="チゲ類",
    keywords=["キムチ", "チゲ"],
)
case = store.retrieve_best(problem)

# 3. Tool Graph実行
executor = GraphExecutor(tools=COOKING_TOOLS)
ctx = await executor.execute(case.solution.tool_graph)

# 4. 成功したら保存
store.retain_if_successful(new_case)
```

## アーキテクチャ

<p align="center">
  <img src="../../assets/architecture.svg" alt="採薪アーキテクチャ" width="600"/>
</p>

## 関連研究

採薪は以下の研究からインスピレーションを受けています：

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM統合サーベイ
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR基盤データサイエンスエージェント
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — スキルライブラリ基盤の経験学習
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — グラフ基盤ツール並列実行
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — 階層的プラン修復

**既存研究との違い：** 採薪はTool GraphをCBRケースとして保存し、ループをサポートする一般グラフを使用し、全体再生成ではなくdiff基盤でグラフを修正し、コードが正常フローを処理しつつLLMは例外状況にのみ介入するハイブリッド実行方式を組み合わせます。

## ライセンス

MIT License — [LICENSE](../../LICENSE) 参照

---

*敎子採薪 — 薪を与えるな、薪の集め方を教えよ。*
