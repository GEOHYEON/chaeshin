# Setting an Evening Dinner Table — Detailed Scenario (English)

> A complete walkthrough of Chaeshin's CBR (Case-Based Reasoning) engine, illustrated through the everyday task of **preparing a full Korean dinner table**.
> Includes both a success scenario and a failure scenario.

---

## Table of Contents

1. [Background: Tool Definitions](#1-background-tool-definitions)
2. [Scenario A: Success Case — End to End](#2-scenario-a-success-case)
3. [Scenario B: Failure Case — Escalation and Recovery](#3-scenario-b-failure-case)
4. [Comparison](#4-comparison)

---

## 1. Background: Tool Definitions

Tools available to the "Dinner Table" agent:

| Tool | Description | Input Example | Output Example |
|------|-------------|---------------|----------------|
| `check_fridge` | List available ingredients | `{}` | `{ingredients: ["pork", "tofu", "aged_kimchi", "eggs", "spinach", ...]}` |
| `check_allergies` | Check family allergies | `{members: ["mom","dad","child"]}` | `{result: {child: ["shrimp"]}}` |
| `suggest_menu` | Recommend menu from ingredients | `{ingredients: [...], servings: 3, exclude: ["shrimp"]}` | `{menu: {soup: "doenjang_jjigae", main: "jeyuk_bokkeum", sides: ["spinach_namul","egg_roll","kimchi"]}}` |
| `search_recipe` | Get recipe for a dish | `{dish: "jeyuk_bokkeum"}` | `{steps: [...], time: "25min", difficulty: "medium"}` |
| `prep_ingredients` | Wash/cut/blanch ingredients | `{ingredient: "spinach", method: "blanch"}` | `{status: "done", time_taken: "5min"}` |
| `cook` | Actual cooking (stir-fry/boil/grill) | `{dish: "jeyuk_bokkeum", step: "stir_fry", heat: "high"}` | `{status: "done", taste: "OK"}` |
| `taste_check` | Check and adjust seasoning | `{dish: "doenjang_jjigae", check: ["salt","umami"]}` | `{taste: "OK"}` or `{taste: "bland", suggestion: "add salt"}` |
| `plate` | Portion and plate dishes | `{dishes: [...], servings: 3}` | `{status: "done"}` |
| `set_table` | Arrange everything on the table | `{menu_list: [...], seats: 3}` | `{layout: "done", missing: []}` |
| `set_timer` | Cooking timer | `{minutes: 20, target: "doenjang_jjigae"}` | `{status: "timer_started"}` |

---

## 2. Scenario A: Success Case

### User Request

```
"Set up tonight's dinner table. 3 servings. My kid is allergic to shrimp."
```

---

### STEP 1: Retrieve (Search Past Cases)

The agent's first action is to **search for similar past requests**.

```python
chaeshin_retrieve(
    query="set dinner table 3 servings allergy",
    category="home_cooking",
    keywords="dinner,full_table,3_servings,allergy,home_cooking"
)
```

**Search Results:**

```
cases: []           # First time — no matching case
warnings: []        # No failure history either
```

> **Decision:** No matching case → must create a new graph from scratch.

---

### STEP 2: Decompose (Hierarchical Breakdown)

Chaeshin v2 decomposes complex requests into **3 layers**.

```
L3 (Strategy): "Set dinner table"
│
├── L2 (Pattern): "Decide menu"
│   ├── L1 (Execution): check_fridge
│   ├── L1 (Execution): check_allergies
│   └── L1 (Execution): suggest_menu
│
├── L2 (Pattern): "Cook soup/stew"
│   ├── L1 (Execution): search_recipe → prep_ingredients → cook → taste_check
│   └── L1 (Execution): set_timer
│
├── L2 (Pattern): "Cook main dish"
│   ├── L1 (Execution): search_recipe → prep_ingredients → cook
│   └── L1 (Execution): taste_check
│
├── L2 (Pattern): "Prepare side dishes"
│   ├── L1 (Execution): prep_ingredients(spinach) → cook(namul)
│   ├── L1 (Execution): prep_ingredients(eggs) → cook(egg_roll)
│   └── L1 (Execution): plate(kimchi)  ← already exists
│
└── L2 (Pattern): "Set the table"
    └── L1 (Execution): plate(all) → set_table
```

**Difficulty calculation:** `depth = 3` → difficulty = 3 (triggers Chaeshin since `difficulty >= 2`)

---

### STEP 3: Tool Graph Generation

The decomposition produces an executable Tool Graph:

```
                    ┌────────────────┐
              ┌─────┤ n1: check_fridge├─────┐
              │     └────────────────┘     │
              │                             │     parallel
              │     ┌───────────────────┐   │     execution
              └─────┤ n2: check_allergies├──┘
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │  n3: suggest_menu  │
                    └────────┬──────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
   ┌──────▼────────┐ ┌──────▼────────┐ ┌───────▼───────┐
   │n4: search_recipe│n5: search_recipe│ │n8: prep_ingred│
   │ (doenjang_jjigae)│ (jeyuk_bokkeum)│ │ (side dishes) │
   └──────┬────────┘ └──────┬────────┘ └───────┬───────┘
          │                  │                  │
   ┌──────▼──────┐   ┌──────▼──────┐   ┌───────▼───────┐
   │  n6: cook   │   │  n7: cook   │   │   n9: cook    │  parallel
   │(doenjang)   │   │(jeyuk)      │   │(namul+egg_roll)│  cooking
   └──────┬──────┘   └──────┬──────┘   └───────┬───────┘
          │                  │                  │
   ┌──────▼──────┐   ┌──────▼──────┐           │
   │n10: taste   │   │n11: taste   │           │
   └──────┬──────┘   └──────┬──────┘           │
          │                  │                  │
          └──────────┬───────┴──────────────────┘
                     │
            ┌────────▼────────┐
            │  n12: plate     │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  n13: set_table │
            └─────────────────┘
```

---

### STEP 4: Execute — Layer-by-Layer Detailed Log

#### Layer 1: Check Ingredients + Allergies (Parallel)

```
[12:00:00] ▶ n1: check_fridge — START
[12:00:00] ▶ n2: check_allergies — START (parallel)
[12:00:01] ✅ n1: check_fridge — DONE
           Output: {ingredients: ["pork","tofu","aged_kimchi","spinach","eggs","doenjang","potato","onion","green_onion","chili_powder","sesame_oil"]}
[12:00:01] ✅ n2: check_allergies — DONE
           Output: {result: {child: ["shrimp"]}, severe_allergy: false}
```

> **Edge evaluation:** `n2.output.severe_allergy == false` → proceed to n3

#### Layer 1: Menu Decision

```
[12:00:02] ▶ n3: suggest_menu — START
           Input: {ingredients: ["pork","tofu",...], servings: 3, exclude: ["shrimp"]}
[12:00:03] ✅ n3: suggest_menu — DONE
           Output: {menu: {soup: "doenjang_jjigae", main: "jeyuk_bokkeum", sides: ["spinach_namul","egg_roll","kimchi"]}}
```

#### Layer 2: Recipe Search + Prep (Parallel)

```
[12:00:03] ▶ n4: search_recipe(doenjang_jjigae) — START
[12:00:03] ▶ n5: search_recipe(jeyuk_bokkeum) — START (parallel)
[12:00:03] ▶ n8: prep_ingredients(sides) — START (parallel)
[12:00:04] ✅ n4: DONE → {steps: ["make_broth","dissolve_doenjang","add_veggies","boil"], time: "20min"}
[12:00:04] ✅ n5: DONE → {steps: ["make_sauce","marinate","stir_fry"], time: "25min"}
[12:00:06] ✅ n8: DONE → {spinach: "blanched", eggs: "beaten"}
```

#### Layer 2: Main Cooking (Parallel)

```
[12:00:06] ▶ n6: cook(doenjang_jjigae) — START
[12:00:06] ▶ n7: cook(jeyuk_bokkeum) — START (parallel)
[12:00:06] ▶ n9: cook(side_dishes) — START (parallel)
[12:00:26] ✅ n6: DONE → {taste_status: "check_needed"}
[12:00:31] ✅ n7: DONE → {taste_status: "check_needed"}
[12:00:16] ✅ n9: DONE → {spinach_namul: "OK", egg_roll: "OK"}
```

#### Layer 2: Taste Check

```
[12:00:26] ▶ n10: taste_check(doenjang_jjigae) — START
[12:00:27] ✅ n10: DONE → {taste: "bland", suggestion: "add 1 spoon doenjang"}
```

> **Edge evaluation:** `n10.output.taste == bland` → **LOOP triggered! Return to n6** (loop_count: 1)

```
[12:00:27] 🔄 LOOP: n10 → n6 (seasoning insufficient, re-cook)
[12:00:27] ▶ n6: cook(doenjang_jjigae) — RESTART (add doenjang, boil 5 more min)
[12:00:32] ✅ n6: DONE
[12:00:32] ▶ n10: taste_check — RESTART
[12:00:33] ✅ n10: DONE → {taste: "OK"}
```

> **Edge evaluation:** `n10.output.taste == OK` → proceed to n12

```
[12:00:31] ▶ n11: taste_check(jeyuk_bokkeum) — START
[12:00:32] ✅ n11: DONE → {taste: "OK"}
```

#### Layer 3: Plate + Set Table

```
[12:00:33] ▶ n12: plate — START
[12:00:35] ✅ n12: DONE → {status: "all_plated"}

[12:00:35] ▶ n13: set_table — START
[12:00:36] ✅ n13: DONE → {layout: "done", missing: []}
```

---

### STEP 5: Retain (Save to Memory)

Execution succeeded → save as a CBR case.

```python
chaeshin_retain(
    request="Set dinner table 3 servings with allergy handling",
    category="home_cooking",
    keywords="dinner,full_table,3_servings,allergy,doenjang,jeyuk,side_dishes",
    graph={"nodes": [...], "edges": [...]},  # 13 nodes, 17 edges
    satisfaction=0.92,
    summary="Full dinner (doenjang_jjigae + jeyuk_bokkeum + 3 sides) for 3. Taste loop triggered once for soup."
)
```

---

### Next Time a Similar Request Comes In

```
User: "Set up dinner for 4 tonight."
```

```python
chaeshin_retrieve(query="set dinner table 4 servings", keywords="dinner,full_table")
```

```
cases: [{case_id: "dinner_full_table_001", similarity: 0.87}]
```

> **Decision:** similarity 0.87 > 0.7 → **Adapt the existing graph!**
> Only change: `servings: 3 → 4`, re-check allergies. No need to build from scratch.

---

## 3. Scenario B: Failure Case

### User Request

```
"Set up dinner tonight. 3 servings, but I don't think there's much in the fridge."
```

---

### STEP 1: Retrieve

```python
chaeshin_retrieve(
    query="set dinner table 3 servings low ingredients",
    category="home_cooking",
    keywords="dinner,full_table,low_ingredients"
)
```

**Results:** (Assuming Scenario A's success case is stored)

```
cases: [{case_id: "dinner_full_table_001", similarity: 0.78}]
warnings: []
```

> **Decision:** Existing case found → Adapt and use.

---

### STEP 2: Adapt + Start Execution

#### Layer 1: Check Fridge

```
[18:00:00] ▶ n1: check_fridge — START
[18:00:01] ✅ n1: DONE
           Output: {ingredients: ["eggs", "kimchi", "green_onion", "soy_sauce"]}  ← Very limited!
```

#### Layer 1: Menu Suggestion — FIRST FAILURE

```
[18:00:02] ▶ n3: suggest_menu — START
           Input: {ingredients: ["eggs","kimchi","green_onion","soy_sauce"], servings: 3}
[18:00:03] ❌ n3: suggest_menu — FAILED!
           Output: {error: "cannot_compose_full_table", reason: "insufficient for soup and main dish",
                    possible_dishes: ["egg_roll", "kimchi_fried_rice"]}
```

> **Problem:** `suggest_menu` returns an error — can't compose a "full table."
> The existing graph expects `n3 → n4,n5,n8`, but no matching edge for an error output.

---

### STEP 3: L1 Replan (First Replanning Attempt)

```
[18:00:03] 🔧 Replan trigger: unexpected output at n3, no matching edge
```

The Planner generates a diff-based fix:

```json
{
  "reasoning": "Full table impossible with 4 ingredients. Downgrade to simple meal.",
  "added_nodes": [
    {"id": "n3-1", "tool": "suggest_menu", "params_hint": {"mode": "simple_meal"}, "note": "Re-suggest as simple meal"}
  ],
  "removed_nodes": ["n4", "n5", "n8"],
  "added_edges": [
    {"from_node": "n3", "to_node": "n3-1", "condition": "n3.output.error != null"}
  ]
}
```

#### L1 Replan Execution

```
[18:00:04] ▶ n3-1: suggest_menu(simple_meal) — START
[18:00:05] ✅ n3-1: DONE
           Output: {menu: {main: "kimchi_fried_rice", side: ["egg_roll"]}, warning: "no_soup"}
```

---

### STEP 4: L2 Escalation — "This isn't a full table"

Agent checkpoint validation:

```
[18:00:05] ⚠️ L2 Checkpoint: User requested "full dinner table" but current plan = 1 main + 1 side
           "Full table" (한상) = soup + main + 3+ sides (standard Korean dinner)
           Current plan does NOT satisfy the request.
```

> **L1 replan cannot fix this** → **Escalate to L2**

```
[18:00:05] 📤 Escalation: L1 → L2
           Reason: "Full table requirements not met (no soup, insufficient sides)"
```

L2 Replan generates options:

```json
{
  "reasoning": "Insufficient ingredients. Must go shopping, order delivery, or downgrade expectations.",
  "options": [
    "A: Simple meal with current ingredients (NOT a full table)",
    "B: Go grocery shopping first, then full table",
    "C: Order soup delivery + cook the rest at home"
  ]
}
```

> **L2 also cannot self-resolve** → **Ask the user**

---

### STEP 5: User Feedback

```
Agent: "The fridge only has eggs, kimchi, green onion, and soy sauce.
        A full dinner table isn't possible. Here are your options:
        A) Kimchi fried rice + egg roll (quick and simple)
        B) Go shopping first, then make a full spread
        C) Order soup delivery + cook the rest
        What would you like?"

User: "Just go with A. Let's keep it simple."
```

---

### STEP 6: Execute Downsized Graph

```
[18:00:30] ▶ n7-new: cook(kimchi_fried_rice) — START
[18:00:45] ✅ n7-new: DONE → {taste: "OK"}

[18:00:30] ▶ n9-new: cook(egg_roll) — START (parallel)
[18:00:40] ✅ n9-new: DONE → {taste: "OK"}

[18:00:45] ▶ n12: plate — START
[18:00:46] ✅ n12: DONE

[18:00:46] ▶ n13: set_table — START
[18:00:47] ✅ n13: DONE → {layout: "done", note: "simple_meal"}
```

---

### STEP 7: Retain (Save Both Failure and Success)

#### Save Failure Pattern (Anti-pattern)

```python
chaeshin_retain(
    request="Apply full-table graph when fridge has only 4 ingredients",
    category="home_cooking",
    keywords="dinner,full_table,low_ingredients,failure,escalation",
    success=False,
    error_reason="Only 4 ingredients. Full table graph fails at suggest_menu (n3). Don't apply full-table graph when ingredients < 6.",
    satisfaction=0.0
)
```

#### Save Downsized Success Pattern

```python
chaeshin_retain(
    request="Switch to simple meal when ingredients insufficient for full table",
    category="home_cooking",
    keywords="dinner,simple_meal,low_ingredients,kimchi_fried_rice,egg_roll",
    graph={...},  # downsized graph
    satisfaction=0.70,
    summary="User wanted full table but fridge was nearly empty. Switched to simple meal. User accepted."
)
```

---

### Next Time a Similar Request Comes In

```
User: "Make dinner tonight. Not much in the fridge."
```

```python
chaeshin_retrieve(query="dinner low ingredients", keywords="dinner,low_ingredients")
```

```
cases: [
  {case_id: "dinner_simple_001", similarity: 0.82, problem: "simple meal when ingredients insufficient"}
]
warnings: [
  {case_id: "dinner_fail_001", error: "Full table graph fails with 4 ingredients at suggest_menu",
   advice: "Do NOT apply full-table graph when ingredients are limited"}
]
```

> **Decision:**
> - Success case: Use simple meal graph directly
> - Warning: Don't try full-table graph with limited ingredients
> - → Start with simple meal graph from the beginning. No escalation needed!

---

## 4. Comparison

| Aspect | Scenario A (Success) | Scenario B (Failure → Recovery) |
|--------|---------------------|-------------------------------|
| **Request** | Dinner table, 3 servings | Dinner table, 3 servings (low ingredients) |
| **Retrieve** | No match (first run) | Existing case matched (0.78) |
| **Decompose** | L3→L2→L1 normal | Adapted existing graph |
| **Nodes executed** | 13 (all) | 13 → failed → reduced to 5 |
| **Loops** | 1 (soup taste check) | None |
| **Escalation** | None | L1 → L2 → User |
| **Final result** | Full table (soup + main + 3 sides) | Simple meal (fried rice + egg roll) |
| **Satisfaction** | 0.92 | 0.70 |
| **Cases saved** | 1 success | 1 anti-pattern + 1 downsized success |
| **Learning effect** | Reuse for next full table | Prevent full-table attempt with low ingredients |

---

## Key Takeaways

1. **Retrieve First**: Always search past cases before planning. Reuse when similarity > 0.7.
2. **Layer Decomposition**: Complex requests split into L3→L2→L1. Each layer executes independently.
3. **Edge Conditions**: Node outputs determine the next path. `taste == bland` → loop; `taste == OK` → proceed.
4. **Escalation**: L1 failure → L1 replan → L2 → User. Step-by-step escalation, never skipping levels.
5. **Anti-patterns**: Failures are saved too, preventing the same mistake from recurring.
6. **Parallel Execution**: Independent tasks (fridge check + allergy check, soup + main + sides) run in parallel.
