# 採薪 (Chaeshin)

> **"给代理一个计划，它能解决一个任务。教会它检索计划，它能解决所有任务。"**

**採薪**是一个用于LLM工具调用（Tool Calling）的Case-Based Reasoning（CBR）框架。它存储过去成功的工具执行图，在遇到类似问题时检索并复用，根据情况进行调整后执行。

敎子採薪 — *不要给木柴，要教会如何采薪。*

[English](../../README.md) | [한국어](../ko/README.md)

---

## 集成 — 一行配置

两个平台共享 `~/.chaeshin/cases.json` — 在Claude Code中积累的案例可以在OpenClaw中使用，反之亦然。

<p align="center">
  <img src="../../assets/integrations.svg" alt="採薪集成架构 — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Chaeshin [MCP](https://modelcontextprotocol.io/) 服务器将注册到Claude Code中。以下4个工具将被添加：

| 工具 | 说明 |
|------|------|
| `chaeshin_retrieve` | 搜索类似案例 — 返回成功案例 + 反模式警告 |
| `chaeshin_retain` | 保存执行图（成功和失败均保存） |
| `chaeshin_anticipate` | 预测建议 — 基于当前上下文的主动建议 |
| `chaeshin_stats` | 存储统计 — 查看案例库统计信息 |

在执行多步骤任务之前，先搜索是否存在类似模式。检索时不仅返回成功案例，还会返回过去失败的**反模式警告**。任务完成后保存执行图，失败的执行也会连同原因一起保存，以避免重复同样的错误。

<details>
<summary>手动配置（当 <code>claude</code> CLI 不可用时）</summary>

添加到 `~/.claude.json`：

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

`SKILL.md` 将被安装到 `~/.openclaw/workspace/skills/chaeshin/`。OpenClaw代理将开始使用Tool Graph记忆。

通过桥接CLI可以进行基于JSON的检索/保存：

```bash
# 搜索类似案例
python -m chaeshin.integrations.openclaw.bridge retrieve "deploy to staging"

# 保存成功模式
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "deploy to staging" \
    --graph '{"nodes":[...],"edges":[...]}'

# 查看统计
python -m chaeshin.integrations.openclaw.bridge stats
```

### 独立使用 (any agent)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```

### 项目结构

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # MCP 服务器 (stdio 协议)
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + 桥接 CLI (subprocess)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # LLM + 嵌入适配器
│   └── chroma.py           # VectorDB 案例存储
├── schema.py               # 核心数据类型
├── case_store.py            # CBR 检索 / 保留
├── graph_executor.py        # Tool Graph 执行引擎
└── planner.py               # 基于LLM的图创建 / 适应 / 重规划
```

---

## 为什么选择採薪？

大多数LLM代理要么即兴进行工具调用（ReAct风格），要么遵循开发者预设的固定流水线。两种方式都有局限性：

- **即兴型**：LLM可能会跳过步骤、弄错顺序，或重复同样的错误。
- **固定型**：每个新场景都需要修改代码。难以扩展。

採薪采用不同的方法：**记住有效的方案，然后复用。**

当请求到来时，採薪搜索类似的历史案例，取出当时成功的工具执行图，必要时进行修改，执行后，如果成功则再次保存。这就是 [Case-Based Reasoning](https://en.wikipedia.org/wiki/Case-based_reasoning) 的经典循环：**检索 → 复用 → 修订 → 保留**。

## 普通LLM vs 採薪

<p align="center">
  <img src="../../assets/comparison.svg" alt="普通LLM vs 採薪 — 芝士吐司对比" width="820"/>
</p>

## 核心概念

### Tool Graph — 执行蓝图

工具调用以**图结构**表示。不是DAG，而是支持**循环**的一般图。

<p align="center">
  <img src="../../assets/tool-graph.svg" alt="Tool Graph 示例 — 泡菜汤" width="720"/>
</p>

### CBR Case — 问题-解法-结果-元数据

每个案例是一个 `(problem, solution, outcome, metadata)` 元组：

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

### 不可变图 + 可变上下文

Tool Graph在执行过程中不会改变。改变的只是**执行上下文**（游标位置、节点状态、输出值）。当出现意外情况且没有匹配的边时，才会请求LLM以diff形式（添加/删除节点和边）修改图。

### 当出现意外情况怎么办？

执行过程中并不总是按计划进行。採薪通过**基于diff的重规划**来处理 — 仅在没有匹配边时LLM才介入：

<p align="center">
  <img src="../../assets/replan-scenarios.svg" alt="重规划场景 — 电话、过敏、缺少食材" width="780"/>
</p>

核心原理：正常执行时图是不可变的。只有当出现**没有匹配边的异常**时，LLM才介入，以最小的diff修改图。不是完全重新生成，而是只应用变更部分。

## 安装

```bash
pip install chaeshin
```

或使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv pip install chaeshin
```

从源码安装：

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # 推荐
# 或: pip install -e ".[dev]"
```

## 快速开始 — 泡菜汤厨师

**基于规则的演示**（无需API密钥）：

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**LLM + VectorDB 演示**（OpenAI + ChromaDB）：

```bash
cp .env.example .env         # 填入 OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```

**Web UI 演示**（Gradio）：

```bash
cp .env.example .env         # 填入 OPENAI_API_KEY
uv run python -m examples.cooking.app
```

在浏览器中输入烹饪请求，可以看到CBR流水线逐步执行的过程。

```python
from chaeshin import CaseStore, GraphExecutor, ProblemFeatures

# 1. 加载CBR案例库
store = CaseStore()
store.load_json(open("cases.json").read())

# 2. 搜索类似案例
problem = ProblemFeatures(
    request="김치찌개 2인분 해줘",
    category="찌개류",
    keywords=["김치", "찌개"],
)
case = store.retrieve_best(problem)

# 3. 执行 Tool Graph
executor = GraphExecutor(tools=COOKING_TOOLS)
ctx = await executor.execute(case.solution.tool_graph)

# 4. 成功则保存
store.retain_if_successful(new_case)
```

## 架构

<p align="center">
  <img src="../../assets/architecture.svg" alt="採薪架构" width="600"/>
</p>

## 相关研究

採薪从以下研究中获得了启发：

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM 集成综述
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — 基于CBR的数据科学代理
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — 基于技能库的经验学习
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — 基于图的工具并行执行
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — 层次化计划修复

**与现有研究的不同之处：** 採薪将Tool Graph作为CBR案例存储，使用支持循环的一般图（而非仅DAG），采用基于diff的图修改而非完全重新生成，并结合代码处理正常流程而LLM仅在异常情况下介入的混合执行方式。

## 许可证

MIT License — 参见 [LICENSE](../../LICENSE)

---

*敎子採薪 — 不要给木柴，要教会如何采薪。*
