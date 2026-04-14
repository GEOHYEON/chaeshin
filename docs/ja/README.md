# Chaeshin (採薪) 採薪

**成功したパターンを記憶するLLMエージェント。** 毎回ツール呼び出しを即興するのではなく、Chaeshinは成功した実行パターンを保存・再利用します。タスクをこなすほどエージェントが賢くなります。

<p align="center">
  <img src="../../assets/comparison.svg" alt="通常のLLM vs Chaeshin — 同じミスの繰り返し vs 学習済みパターン" width="820"/>
</p>

[English](../../README.md) | [한국어](../ko/README.md) | [中文](../zh/README.md) | [Español](../es/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md)

---

## 問題

ほとんどのLLMエージェントはツール呼び出しを**即興**するか、**ハードコード**されたパイプラインに従います：

- **即興型**（ReActスタイル）：ステップを飛ばしたり、順序を間違えたり、同じミスを繰り返します。
- **ハードコード型**：新しいシナリオのたびにコード変更が必要。スケールしません。

## 解決策

Chaeshinはうまくいったことを記憶します。似たリクエストが来ると、実証済みのツール実行グラフを取得し、状況に合わせて適応し、実行して結果を保存します。これが[Case-Based Reasoning](https://ja.wikipedia.org/wiki/%E4%BA%8B%E4%BE%8B%E3%83%99%E3%83%BC%E3%82%B9%E6%8E%A8%E8%AB%96)です：**検索 → 再利用 → 修正 → 保持。**

失敗も保存されるため、同じミスは二度と繰り返されません。

```
1日目:   エージェントが全てをゼロから即興
7日目:   20件のケースが蓄積 — よくあるパターンが再利用される
30日目:  100件以上 — 即興はほぼ不要、実証済みパターンに従う
```

---

## クイックスタート

### 1. インストール

```bash
pip install chaeshin
```

### 2. エージェントに接続

```bash
chaeshin setup claude-code       # Claude Code (MCP + 自動学習)
chaeshin setup claude-desktop    # Claude Desktop
chaeshin setup openclaw          # OpenClaw
```

これだけです。Claudeが自動的に：
- **マルチステップタスクの前に** → 過去のパターンを検索
- **タスク完了後に** → 実行グラフを保存
- **失敗時に** → 失敗パターンを保存して二度と繰り返さない

<details>
<summary>その他のインストール方法</summary>

[uv](https://docs.astral.sh/uv/)を使用（推奨）：

```bash
uv pip install chaeshin
```

`uvx`を使用（グローバルインストール不要）：

```bash
uvx chaeshin setup claude-code --uvx
```

手動MCP設定（`~/.claude.json`に追加）：

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
<summary>スタンドアロンライブラリとして使用（任意のエージェント）</summary>

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```
</details>

### 3. デモを試す

```bash
git clone https://github.com/GEOHYEON/chaeshin.git && cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent   # APIキー不要
```

<details>
<summary>LLM + VectorDB デモ（OpenAI + ChromaDB）</summary>

```bash
cp .env.example .env         # OPENAI_API_KEYを入力
uv run python -m examples.cooking.chef_agent_llm
```
</details>

<details>
<summary>Web UI デモ（Gradio）</summary>

```bash
cp .env.example .env
uv run python -m examples.cooking.app
```
</details>

詳細なウォークスルーは[クイックスタートガイド](../../docs/quickstart.md)をご覧ください。

---

## 仕組み

### Tool Graph

ツール呼び出しは単純なリストではなく**グラフ**として構造化されます。ノードはツール呼び出し、エッジは順序と条件を定義します。ループもサポートされます（例：「味見 → 味が薄い → さらに煮る → 再度味見」）。

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Tool Graph — ノード、エッジ、条件、ループ" width="720"/>
</p>

### 不変グラフ + 可変コンテキスト

グラフは実行中に変更されません。更新されるのは**実行コンテキスト**（カーソル、ノード状態、出力値）のみです。予期しない状況が発生しマッチするエッジがない場合、LLMが完全再生成ではなく最小限の**diff**でグラフを修正します。

### 予期しない状況が発生したら

実行が常に計画通りに進むとは限りません。Chaeshinは**diff基盤のリプランニング**でこれに対処します：

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="リプランニング — 電話、アレルギー、材料不足" width="780"/>
</p>

---

## 完全な例 — ディナーテーブルの準備

完全なウォークスルー：「3人分の夕食を準備、子供はエビアレルギーあり。」検索、レイヤー分解、並列調理、味見チェックループ、失敗時のエスカレーションまで全ステップを紹介します。

<p align="center">
  <img src="../../assets/dinner-table-success.ja.svg" alt="成功 — 検索 → 分解 → 実行 → 保持" width="820"/>
</p>

<p align="center">
  <img src="../../assets/dinner-table-failure.ja.svg" alt="失敗 — L1 → L2 → ユーザー → リカバリーへのエスカレーション" width="820"/>
</p>

シナリオの詳細解説：
[English](../../examples/dinner-table/scenario_en.md) ·
[한국어](../../examples/dinner-table/scenario_ko.md) ·
[日本語](../../examples/dinner-table/scenario_ja.md) ·
[中文](../../examples/dinner-table/scenario_zh.md)

---

## 連携

全プラットフォームが `~/.chaeshin/cases.json` を共有します — Claude Codeで保存したケースはOpenClawでも使え、その逆も可能です。

<p align="center">
  <img src="../../assets/integrations.svg" alt="連携アーキテクチャ — Claude Code & OpenClaw" width="820"/>
</p>

| プラットフォーム | コマンド | 内容 |
|----------|---------|-------------|
| Claude Code | `chaeshin setup claude-code` | MCPサーバー + 自動学習ルール (`CLAUDE.md`) |
| Claude Desktop | `chaeshin setup claude-desktop` | `claude_desktop_config.json` を自動編集 |
| OpenClaw | `chaeshin setup openclaw` | ワークスペースに `SKILL.md` をインストール |

セットアップ後に3つのツールが利用可能になります：

| ツール | 説明 |
|------|-------------|
| `chaeshin_retrieve` | 過去のケースを検索 — 成功と失敗を分けて返します |
| `chaeshin_retain` | 実行グラフを保存（成功・失敗の両方） |
| `chaeshin_stats` | ケースストアの統計を表示 |

---

## モニター — ビジュアルグラフエディタ

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="ビジュアルグラフエディタ" width="720"/>
</p>

Next.jsとReact Flowで構築されたWebベースのTool Graphエディタです。ノードをドラッグ&ドロップし、エッジを描画し、条件を設定し、`~/.chaeshin/cases.json` からケースをインポート/エクスポートできます。

```bash
cd chaeshin-monitor && pnpm install && pnpm dev
```

---

## アーキテクチャ

<p align="center">
  <img src="../../assets/architecture.svg" alt="Chaeshinアーキテクチャ" width="600"/>
</p>

<details>
<summary>プロジェクト構造</summary>

```
chaeshin/
├── schema.py               # コアデータ型 (Case, ToolGraph, GraphNode, GraphEdge)
├── case_store.py           # CBR 4Rサイクル: 検索、再利用、修正、保持
├── graph_executor.py       # Tool Graphランナー (並列、ループ、条件)
├── planner.py              # LLM基盤グラフ生成 / 適応 / リプランニング (diff基盤)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
├── integrations/
│   ├── claude_code/        # MCPサーバー (FastMCP) + CLAUDE.md自動学習テンプレート
│   ├── openclaw/           # SKILL.md + ブリッジCLI
│   ├── openai.py           # LLM + エンベディングアダプター
│   ├── chroma.py           # ChromaDBベクターケースストア
│   └── chaebi.py           # Chaebiマーケットプレイス同期
└── agents/                 # v2: Orchestrator, Decomposer, Executor, Reflection
chaeshin-monitor/           # Next.js Web UI
examples/cooking/           # デモエージェント (キムチチゲ、テンジャンチゲ、リカバリーシナリオ)
examples/dinner-table/      # 完全ウォークスルー (4言語)
```
</details>

## 要件

- Python 3.10+
- コア機能には必須依存関係なし
- オプション: `openai` (LLMアダプター), `chromadb` (ベクターストア), `httpx` (Chaebiマーケットプレイス)

## 関連研究

Chaeshinは以下の研究からアイデアを得ています：

- [CBR for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM統合サーベイ
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR基盤データサイエンスエージェント
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — 経験駆動型学習によるスキルライブラリ
- [GAP (2025)](https://arxiv.org/html/2510.25320v1) — グラフによるツール並列実行
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — 階層的プラン修復

**何が違うのか？** Tool GraphをCBRケースとして保存、DAGだけでなくループをサポートする一般グラフ、完全再生成ではなくdiff基盤の修正、そしてコードが正常フローを処理しLLMは例外時にのみ介入するハイブリッド実行方式を採用しています。

## ライセンス

MIT — [LICENSE](../../LICENSE) 参照

---

*敎子採薪 — 薪を与えるな、薪の集め方を教えよ。*
