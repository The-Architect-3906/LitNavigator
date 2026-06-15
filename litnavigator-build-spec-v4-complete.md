# LitNavigator · 完整实现 Spec（v4）

## 概述

LitNavigator 是一个**从活的研究文献里长出来、又用活文献教学的有状态导师**，面向"想进入一个陌生研究子领域"的学生 / 工程师 / 研究者。

它不是文献检索器，也不是普通 chatbot。它做四件事，且都对"你这个人"自适应：
1. **教**：直接把概念讲给你（grounded 在论文上、带引用），而不是丢一堆资料让你自己读。
2. **测**：苏格拉底式提问验证你是否真懂，并识别你**具体的误解**。
3. **重教 / 补课**：你没懂就**换种讲法重教**；你缺前置就**回退补课**。
4. **现推**：遇到课表里没有的概念，它**从论文里自己推出前置依赖、挖出领域误解**，并按证据校准地教你"哪里是共识、哪里还在吵"。

> **一句话定位**：给固定课表的家教（Khanmigo / LearnLM）一个研究子领域，它没有课表可教；给静态文献助手（NotebookLM）你的论文，它能一键出测验/讲解，但不建模你、不会因你的误解换讲法、更不会自己排"先学什么"。
> **LitNavigator 的护城河 = 自适应导师循环 × 课程脚手架从活文献现推。** 两半单独都已成熟，这个乘积没人占，且正是前沿学者进新领域的真实痛点。

它**不训练任何模型**：智能来自 retrieval + 人工策展的概念骨架 + **从语料现推的脚手架** + 运行时状态转移。

---

## 1. 定位与创新（全项目的北极星）

### 1.1 竞品结构对照（直接进 PPT，别等评委自己想）

| 系统 | 建模你 | 自适应教/测/重教 | 课程依赖(前置) | 误解诊断 | 内容来自活文献 | 脚手架来源 |
|---|---|---|---|---|---|---|
| Elicit / SciSpace | ✗ | ✗（只检索/总结） | ✗ | ✗ | ✓ | — |
| NotebookLM (2026) | ✗ | ✗（一键静态测验/指南） | ✗ | ✗ | ✓（你上传的） | — |
| Khanmigo / LearnLM | ✓ | ✓ | ✓ | ✓ | ✗（固定课程） | 人工授权课程 |
| **LitNavigator** | ✓ | ✓ | ✓ | ✓ | ✓ | **人工骨架 + 文献现推** |

> 前三行没有任何一行能同时打勾最后两列。**最后一列（脚手架从活文献现推）就是没人占的格子。**

### 1.2 三个"只有教活文献才可能"的能力（novelty 三件套）

1. **前置 induce**：读论文推出"概念 B 的方法预设了 A，所以 A 是 B 的前置"，**自己排教学顺序**。固定课表家教结构上没有这个能力。
2. **误解 mine**：论文天天互相纠正（"与普遍认知相反""一个常见误区是""naive 做法失败，因为…"）。从语料里抽出领域**真实的坑**当误解库——是文献告诉导师学习者会错在哪。
3. **教前沿分歧**：教材讲定论；文献导师能带校准的不确定性教"哪里共识、哪里争议、哪里开放"。这是研究学者进新领域最缺的东西。

### 1.3 期望校准（团队内部清醒用）

这是**在一个被忽视交叉点上的强应用创新**，不是"全新 agentic 架构突破"。自适应导师循环本身是成熟 ITS 标配；novelty 全压在"脚手架现推 + 教前沿"这条轴上。所以铁律两条：(a) demo 必须**真演**至少一次文献现推；(b) PPT 必须显式对标 Khanmigo/NotebookLM 讲清结构差异。其余五项评分维度（实用性、agentic 执行、展示、责任 AI、成本）照常发力。

---

## 2. 架构

### 2.1 双嵌套循环 + 文献现推节点图

```
input
  ↓
init_or_load_state
  ↓
planner                       ← 由 concept DAG 拓扑排序出初始 route（骨架优先）
  ↓
select_next_concept ──在骨架DAG里?──┬─ 否/用户带新概念 ─► induce_scaffold ─┐
                                    │   （现推前置/误解，写 source='induced'+证据）│
                                    └─ 是 ──────────────────────────────────────┤
                                                                                 ↓
┌─────────────── TUTOR INNER LOOP（单概念授课，"老师"在这里）─────────────────────┐
│ retrieve_evidence  → teach → check → grade                                       │
│   （teach 可标注：此处是共识 / 争议 / 开放问题，按证据校准）                        │
│   ↓                                                                              │
│ tutor_router ──┬── mastered ───────────────────────► EXIT → advance              │
│  （三路核心）  ├── misconception & 前置OK ─► reteach ─┐ 换未用过的讲法，回 teach    │
│                │                              ▲───────┘                           │
│                ├── blocked_by_prereq ────────────────► EXIT → diagnose_gap        │
│                └── off_path_request ─────────────────► EXIT → refuse_jump / induce │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ mastered                    │ blocked_by_prereq
        ▼                             ▼
   advance                       diagnose_gap → replan（插入前置；若前置不在骨架→先 induce）
        ↓                             ↓
 select_next_concept            select_next_concept → ... → finish
```

**三个环/支路各管一件事：**
- **内环（教单概念）= 教师效应**：teach→check→grade→误解则 reteach。
- **外环（跨概念编排）= 课程自适应**：达标 advance / 缺前置 replan。
- **现推支路 = novelty**：遇到骨架里没有的概念/前置/误解，从语料现推并带证据写入。

> `induce_scaffold` 不替代人工骨架，而是**第二条轨道**：骨架是 demo 安全网（保证主路径稳跑），现推是 novelty 硬证据（现场至少演一次）。和检索分档 L0/L1 同一哲学。

### 2.2 节点职责

| 节点 | 职责 | 不该做 |
|---|---|---|
| `init_or_load_state` | 新建/载入 session 的 NavState | — |
| `planner` | 由 concept DAG 拓扑排序出**初始** route | 不动态改路 |
| `select_next_concept` | 选下一 pending concept；**判断是否在骨架 DAG 内** | — |
| `induce_scaffold` | 从 retrieved 论文现推前置边/误解，写 `source='induced'`+证据+置信 | 无证据不断言；与骨架冲突时不静默覆盖（标待校验） |
| `retrieve_evidence` | 按当前 concept 取证据 chunk | 不大范围搜索 |
| `teach` | grounded 讲解 + 前沿标注 + 按 level/误解适配 | 不脱离 chunk；不凭参数记忆；不幻觉引用 |
| `check` | 苏格拉底式：预测/复述/迁移，绑 chunk | 不脱离证据出题 |
| `grade` | 判对错 + 识别误解 + BKT-lite 更新 mastery + 写 evidence | **不决定走向** |
| `tutor_router` | 据 state 走三路条件边 | 不判分 |
| `reteach` | 选未用过的讲法重教，针对误解 correct_model | 不复读；封顶 2 次 |
| `diagnose_gap` | 用 mastery + DAG 找缺失前置 | — |
| `replan` | 插入/调整 route step + 输出 rationale（前置不在骨架→先 induce） | — |

### 2.3 NavState

```python
class ConceptState(TypedDict):
    mastery: float                       # BKT 后验 P(known)，0~1
    confidence: float                    # 系统对该估计的把握（→ S5）
    evidence: list[dict]                 # 哪些 attempt 支撑这个分
    held_misconceptions: list[str]       # 当前持有的具体误解 id（灵魂）
    tried_strategies: list[str]          # 本概念用过的讲法（逼 reteach 换招）
    depth: Literal["recall","apply","explain"]

class NavState(TypedDict):
    session_id: str
    user_id: str | None
    # —— 目标 ——
    topic: str
    user_goal: str
    target_concepts: list[int]
    constraints: dict                    # P2: max_depth / prefer_recent / skip_math
    # —— 图 ——
    concept_dag_version: str
    concept_dag: dict[int, list[int]]    # concept -> prereqs
    # —— 学习状态（灵魂）——
    learner_state: dict[int, ConceptState]
    mastery_threshold: float
    # —— 路线 ——
    reading_path: list[dict]             # RouteStep
    current_step_id: str | None
    current_concept_id: int | None
    current_paper_id: int | None
    route_version: int                   # 改路 +1，demo 用它证明"真改了"
    # —— 授课内循环 ——
    reteach_count: dict[int, int]        # concept_id -> 已重教次数（封顶用）
    last_explanation_strategy: str | None
    # —— 文献现推 ——
    scaffold_origin: dict[int, str]      # concept_id -> 'curated' | 'induced'
    induced_edges: list[dict]            # 现推前置边（含 evidence_chunks, confidence）
    induced_misconceptions: list[dict]   # 现推误解（含 evidence_chunks, confidence）
    frontier_flags: dict[int, str]       # concept_id -> 'consensus' | 'contested' | 'open'
    # —— RAG 证据 ——
    retrieved_ctx: list[dict]            # chunk_id, paper_id, text, score, source
    cited_evidence: list[dict]
    # —— 检验 ——
    quiz_items: list[dict]
    user_answers: list[dict]
    last_check_result: dict | None       # 含 concept_scores + detected_misconception
    # —— 诊断与决策 ——
    diagnosis: dict | None
    decision: Literal["advance","reteach","diagnose","replan",
                      "refuse_jump","induce","finish"] | None
    decision_rationale: str
    # —— 鲁棒性（加分项）——
    off_path_request: dict | None        # P2: S3 refuse_jump 用
    uncertainty_flags: list[str]         # P2: S5 校准语气
    # —— 日志 ——
    history: list[dict]

class RouteStep(TypedDict):
    step_id: str
    concept_id: int
    paper_id: int
    reason: str                          # "为什么现在学这个"
    status: Literal["pending","active","done","skipped"]
    confidence: float
```

---

## 3. tutor_router：三路条件边（agent vs workflow 的物理分界）

判定顺序：先达标，再误解，再前置；用户引到骨架外时走 `induce`。

```python
MAX_RETEACH = 2

def tutor_router(state) -> str:
    cid = state["current_concept_id"]
    cs = state["learner_state"][cid]

    # 1) 达标 → 推进（外环）
    if cs["mastery"] >= state["mastery_threshold"]:
        return "advance"

    # 2) 本概念内误解，且前置都达标 → 换讲法重教（内环）
    prereqs = state["concept_dag"].get(cid, [])
    prereq_ok = all(state["learner_state"][p]["mastery"] >= state["mastery_threshold"]
                    for p in prereqs)
    if cs["held_misconceptions"] and prereq_ok \
       and state["reteach_count"].get(cid, 0) < MAX_RETEACH:
        return "reteach"

    # 3) 卡在缺失前置 → 回退补课（外环）
    if not prereq_ok:
        return "diagnose"

    # 4) 重教用尽仍不达标 → 也回退补课（防内环死循环）
    return "diagnose"

# off-curriculum：select_next_concept 处先判
#   concept ∉ curated_dag  →  induce_scaffold  →  再进内环
```

> 重教用尽仍不过，不要在内环耗死：升级成回退补课，或标 `confidence` 低、用 S5 坦白"这块暂时没讲透"。诚实比假装教会更得分。

---

## 4. teach / check / grade / reteach

### 4.1 teach —— 把概念讲出来，不是指路
- 输入：concept + `learner_state[cid]`(level + held_misconceptions) + retrieved chunks。
- **每句论断挂真实 chunk，带引用**；禁止凭参数记忆讲、禁止幻觉引用（文献工具幻觉引用是致命反讽）。
- 按 `held_misconceptions` 正面拆错误心智模型。
- **前沿标注**：按证据说出"这是公认结论 / 还在争议 / 是开放问题"。
- 讲法策略从集合里选，首讲默认 `direct_explanation`。

### 4.2 check —— 学习手段，不只是考试

| 题型 | MVP | 作用 |
|---|---|---|
| MCQ | **必须** | deterministic scoring，稳 |
| 预测题 | 推荐 | generation effect |
| 复述/解释题 | 推荐 | 暴露误解最有效 |
| 迁移应用题 | 加分 | 测 depth=apply |

每题强绑 `evidence_chunk_id + source_paper_id`，出题 prompt 必须基于 retrieved chunk。

### 4.3 grade —— 识别"哪种误解"，BKT 更新 mastery

LLM 只做最擅长的：判对错 + 识别命中哪个误解。**mastery 不让 LLM 拍浮点**，用透明 BKT-lite：

```python
P_SLIP, P_GUESS, P_TRANSIT = 0.10, 0.20, 0.30
def bkt_update(p, correct, taught):
    post = (p*(1-P_SLIP)/(p*(1-P_SLIP)+(1-p)*P_GUESS)) if correct \
           else (p*P_SLIP/(p*P_SLIP+(1-p)*(1-P_GUESS)))
    return post + (1-post)*P_TRANSIT if taught else post
```

grade 产出：
```json
{ "score": 0.5,
  "concept_scores": { "contrastive_learning": 0.4, "negative_sampling": 0.2 },
  "detected_misconception": { "concept": "dense_retrieval", "id": "dr_is_keyword_match" },
  "depth": "recall",
  "evidence": [{ "quiz_id": 12, "answer": "B", "correct": false,
                 "mapped_concept": "negative_sampling" }],
  "grader_confidence": 0.9 }
```

### 4.4 reteach —— 换种讲法，不复读
从 `direct → analogy → worked_example → contrast_case → simpler_decomposition` 选一个 `tried_strategies` 没有的，锚定误解 `correct_model` 重讲，再回 `check`。每次 `tried_strategies.append(s)`、`reteach_count[cid]+=1`。

---

## 5. 文献现推 scaffold（novelty 核心）

### 5.1 双轨原则

| 轨道 | 用途 | 信任 | demo 角色 |
|---|---|---|---|
| 人工骨架 `source='curated'` | demo 主路径的概念/前置/误解 | 高 | 安全网 |
| 文献现推 `source='induced'` | 骨架外概念、或现场演示 | 中（带证据可验） | novelty 硬证据 |

> 和检索 L0/L1 同构。**绝不**让"全自动构造整张图"成为 demo 依赖；现推只在一两个点上发生且带证据。

### 5.2 `induce_prereq`（前置现推）
让 LLM 在 chunk 里找"假设/建立在/扩展自/需先理解"语句，抽 "C 依赖 A" 候选边。**验收门**：每条边 ≥1 引用 chunk；无证据则不写或标低 confidence。写入 `concept_edges(source='induced', evidence=JSON[chunks], weight=confidence)`。

```json
{ "prereq": "negative_sampling", "target": "hard_negative_mining",
  "source": "induced", "confidence": 0.78,
  "evidence": [{ "chunk_id": "c_2207_x", "paper_id": 41,
    "quote_span": "...builds on standard negative sampling by mining harder negatives..." }] }
```

### 5.3 `mine_misconception`（误解现推）
扫描纠正/对比型语言模式（"contrary to (common belief)"、"a common misconception"、"naively"、"it is often (wrongly) assumed"、"unlike prior work"、rebuttal/erratum），抽 `wrong_model`/`correct_model` + 引用。**验收门**：必须指回具体 chunk，否则丢弃。

> 这条最贴题：**误解不是你编的，是这个领域的论文自己说的坑。**

### 5.4 责任 AI / 经得起戳
- 每个 `induced` 元素在 UI 与 rationale 里**显式标注"机器现推 + 可点开证据 + 置信度"**，与 `curated` 区分。
- 现推置信低时用 S5 校准语气："我从这两篇推断 A 是 B 的前置，中等把握，你可推翻。"
- 把"你的现推可靠吗"转成"证据在这，您自己判断"——责任 AI 加分点。

---

## 6. 数据规模（冻结，别超）

| 项 | MVP |
|---|---|
| 论文数 | 30–50 |
| 概念数 | 8–15 手工确认（骨架） |
| 前置边 | 15–30 人工确认；**另留 1–2 概念不进骨架，给现推演示** |
| 误解库 | 人工只做 2–3 个 demo-core 概念；**另留 1 个靠现推挖** |
| 现推候选 | **D1–2 离线预跑一遍**，人工抽验，降现场风险（仍标 induced） |
| PDF 全文 | abstract+intro+conclusion 优先；全文可选 |
| embedding | bge-m3；SPECTER2 加分 |
| 概念体系 anchor | OpenAlex Topics |

> 外部 API 仅离线构建数据包（Semantic Scholar ~1 RPS）；demo 现场不 live fetch。"现推"现场跑的是对**已入库 chunk** 做 LLM 抽取，不联网。

---

## 7. 数据库 Schema（完整）

存储：**SQLite**（元数据+图边+状态，单文件零运维）+ **Chroma**（向量）+ **networkx**（内存图算法）。30–50 篇，**不上 Neo4j**。

```sql
-- 外部 anchor
CREATE TABLE topics (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, openalex_topic_id TEXT,
    domain TEXT, field TEXT, subfield TEXT, description TEXT
);

-- 内部教学概念（教学依赖图的节点）
CREATE TABLE concepts (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE,
    topic_id INTEGER REFERENCES topics(id),
    description TEXT, level INTEGER, is_demo_core BOOLEAN DEFAULT 0,
    frontier_flag TEXT CHECK(frontier_flag IN ('consensus','contested','open'))
);

-- prerequisite DAG：方向显式 + 溯源 + 证据
CREATE TABLE concept_edges (
    prereq_concept INTEGER REFERENCES concepts(id),
    target_concept INTEGER REFERENCES concepts(id),
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence TEXT,                       -- JSON: 来源 chunks（human/LLM/paper）
    PRIMARY KEY (prereq_concept, target_concept, edge_type)
);

-- 误解库：溯源 + 证据
CREATE TABLE misconceptions (
    id TEXT PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    wrong_model TEXT, correct_model TEXT,
    detect_hint TEXT, reteach_strategy TEXT,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence_chunk_id TEXT
);

-- 论文 + 分块
CREATE TABLE papers (
    id INTEGER PRIMARY KEY, arxiv_id TEXT UNIQUE, title TEXT, abstract TEXT,
    authors TEXT, source_org TEXT, year INTEGER, full_text TEXT, pdf_path TEXT
);
CREATE TABLE paper_chunks (
    id TEXT PRIMARY KEY, paper_id INTEGER REFERENCES papers(id),
    section TEXT, chunk_index INTEGER, text TEXT, token_count INTEGER, embedding_id TEXT
);
CREATE TABLE paper_concepts (
    paper_id INTEGER REFERENCES papers(id),
    concept_id INTEGER REFERENCES concepts(id),
    relevance REAL, PRIMARY KEY (paper_id, concept_id)
);
CREATE TABLE citations (
    citing_paper INTEGER REFERENCES papers(id),
    cited_paper INTEGER REFERENCES papers(id),
    PRIMARY KEY (citing_paper, cited_paper)
);

-- demo 保命：concept → top papers 预计算
CREATE TABLE concept_paper_rank (
    concept_id INTEGER REFERENCES concepts(id),
    paper_id INTEGER REFERENCES papers(id),
    rank INTEGER, reason TEXT,
    PRIMARY KEY (concept_id, paper_id)
);

-- 题库 + 作答（强绑证据）
CREATE TABLE quiz_items (
    id INTEGER PRIMARY KEY, concept_id INTEGER REFERENCES concepts(id),
    question TEXT, answer_key TEXT,
    qtype TEXT,                          -- 'mcq'|'predict'|'explain'|'transfer'
    difficulty INTEGER,
    evidence_chunk_id TEXT,              -- 必填
    source_paper_id INTEGER REFERENCES papers(id),
    rubric TEXT, expected_concepts TEXT,
    targets_misconception TEXT           -- 本题探哪个误解
);
CREATE TABLE quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    quiz_item_id INTEGER REFERENCES quiz_items(id),
    user_answer TEXT, score REAL, feedback TEXT,
    concept_score_delta TEXT, detected_misconception TEXT, created_at TIMESTAMP
);

-- 会话 + 状态（灵魂）
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, user_id TEXT, topic TEXT, status TEXT, created_at TIMESTAMP
);
CREATE TABLE learner_state (
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    mastery REAL, confidence REAL,
    held_misconceptions TEXT,            -- JSON
    tried_strategies TEXT,               -- JSON
    depth TEXT, evidence TEXT, updated_at TIMESTAMP,
    PRIMARY KEY (session_id, concept_id)
);

-- 授课轮次：证明"换了讲法" + 记录 teach 前后表现（学习增益）
CREATE TABLE tutor_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    turn_type TEXT,                      -- 'teach'|'reteach'
    strategy TEXT, pre_check_score REAL, post_check_score REAL,
    cited_chunks TEXT, created_at TIMESTAMP
);

-- 路线演化
CREATE TABLE route_steps (
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER, step_id TEXT,
    concept_id INTEGER REFERENCES concepts(id),
    paper_id INTEGER REFERENCES papers(id),
    status TEXT, reason TEXT, confidence REAL, created_at TIMESTAMP,
    PRIMARY KEY (session_id, route_version, step_id)
);

-- 决策日志（评委追问时最有用）
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER, from_node TEXT,
    decision TEXT, rationale TEXT, state_snapshot TEXT, created_at TIMESTAMP
);

-- 现推审计
CREATE TABLE induction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT, kind TEXT,          -- 'prereq'|'misconception'
    output TEXT, evidence_chunks TEXT, confidence REAL, created_at TIMESTAMP
);
```

> demo 主路径只需打通：`learner_state / concept_edges / misconceptions / tutor_turns / route_steps / decisions / quiz_items+attempts / paper_chunks / induction_log`。schema 可比代码跑到的更完整，但别让"建满所有表"变兔子洞。

---

## 8. 学习科学依据 + 为何 novel

**教学侧（设计依据 + PPT 立论）**

| 设计 | 理论 |
|---|---|
| 整个立项 | Bloom 2-sigma (1984)：一对一+掌握学习 ≈ +2σ，搬到前沿文献 |
| per-concept mastery + BKT | Bayesian Knowledge Tracing (1994) |
| 不达标不推进 | Mastery Learning (Bloom/Keller) |
| check 即学习 | 检索练习/测试效应 (Roediger & Karpicke 2006) |
| 逼预测/复述/迁移 | ICAP (Chi 2014)：constructive ≫ passive 读论文 |
| 误解→换讲法 | 形成性评价反馈环 (Black & Wiliam) |
| 按 level 调深浅 | 脚手架/渐撤 + 专长反转 (Kalyuga) |

**创新侧（一句话防守）**：自适应导师循环是成熟 ITS 标配（识别误解、自适应反馈、调节节奏）；NotebookLM 已能从论文一键出 grounded 测验/指南——**这两半都不是 novelty**。novelty 在乘积、且**脚手架从活文献现推**：固定课表家教做不到（顺序/误解人写死），静态文献助手做不到（不建模你、不重教、不排序）。

---

## 9. 检索（分档，别一上来做完整 RRF）

| 档 | 做法 | 何时 |
|---|---|---|
| L0 保命 | `concept_paper_rank` 预计算 | Phase 0 备好，demo 兜底 |
| L1 最小 RAG | SQLite FTS5(BM25) + Chroma | 主线；FTS5 自带 BM25，无需 ES |
| L2 完整 | BM25+向量+citation/topic boost+RRF | 加分项，核心做完才上 |

---

## 10. S1–S5 智能信号 → 可测验收

| 信号 | 验收 |
|---|---|
| S1 "因为" | rationale 引用 check_result + 误解/前置边 + 本次动作 |
| S2 分叉 | 同题：对→advance；误解→reteach；缺前置→replan。真三路 |
| S2+ 现推 | 骨架外概念→induce：现推边/误解带证据写入并被使用 |
| S3 反对 | 跳步→指出缺哪个前置，"可看不建议作主路径" |
| S4 coverage warning | 提示论文集中某年/某机构，不做强判断 |
| S5 校准 | 共识/争议/开放分级；现推低置信坦白"暂定，可推翻" |

---

## 11. 硬验收标准（按 milestone 分组，见 §12）

| Test | 内容 | 属阶段 |
|---|---|---|
| T1 状态真实写入 | 一次 check 后 DB 见 mastery 变化 + quiz_attempts + decisions | M1 |
| T2 真三路 | 对→advance；误解→reteach；缺前置→replan，非写死 | M1→M2 |
| T3 reteach 真换讲法 | tried_strategies 出现两个不同 strategy | M2 |
| T4 rationale 可追溯 | check→误解/前置边→cited_chunk→动作 | M1→M2 |
| T5 会话内学习增益 | tutor_turns 内 post_check_score > pre_check_score | M2 |
| T6 现推带证据 | 每条 induced 边/误解 ≥1 cited chunk + source='induced' + induction_log | M3 |
| T7 现推可演 | demo 出现 ≥1 语料现推元素（或离线推好+现场展证据链） | M3 |
| T8 溯源诚实 | UI/rationale 区分 curated vs induced，低置信用 S5 语气 | M3 |
| T9 跳步拦截 | 跳过前置→"可看不建议作主路径，因 [prereq] 未达标" | M2（加分） |
| T10 不幻觉引用 | teach/reteach 每句论断可指回真实 chunk_id | M2 |
| T11 离线可跑 | 不依赖 live arXiv/OpenAlex/S2 | M0 |

---

## 12. 里程碑与分阶段规划（10 天风险阶梯）

**原则**：3 人、硬截止 6/25 锁定（提交后无法补内容）。所以按"垂直切片 + 风险阶梯"分阶段——**每个阶段都是一个自洽、可交、可录的完整系统**，后一阶段是前一阶段的超集。任何时间点都有一个能交的版本。

**目标线**：保底冲到 **M2**（合格进决赛），主攻 **M3**（争金奖）。M1 是地板（基本只够参与奖），别满足于此。

### M0 · Walking Skeleton（地基，不单独 demo）｜目标 D1–D3
- **交付**：LangGraph 状态机端到端在轨跑通（哪怕很笨）：input→planner→present concept→固定 quiz→score→advance；NavState 落 SQLite。
- **内容 track 并行**：30–50 篇入库、8–15 concept、骨架前置边、2–3 误解、**离线预跑现推候选**、概念↔论文绑定。
- **Gate G0**：DB 里能看到 session / learner_state / route 写入（T11 离线可跑）。

### M1 · Navigator（floor，首个可交可录系统）｜目标 D4–D5
- **加**：planner 由 DAG 排路线；真实 quiz 绑 evidence；grade 用 BKT-lite 写 mastery；router 两路（advance / diagnose→replan 插前置）。
- **Money shot ①**：自适应改路（答错→插入前置→route_version+1）。
- **可演**："路线因你的测验而改"。
- **Gate G1**：T1 + 真条件边（对→advance / 错→replan，非写死）+ T4 rationale 可追溯。
- **定位**：完整但**未差异化**（≈ 聪明阅读清单 / Elicit+）。**到此即有合格提交物。**

### M2 · Tutor（teacher capability，竞争力门槛）｜目标 D5–D7
- **加内环**：presenter→`teach`（grounded 讲解，agent 亲自教、带引用）；`check`（苏格拉底）；grade 加**误解识别**；`reteach`（换未用过讲法）；router 升**三路**（+reteach）。
- **Money shot ②**：同概念换讲法重教（误解→换 analogy 再教→过）。
- **可演**："老师没让你去读 PDF，而是亲自讲；你没懂，换个讲法再讲一遍。"
- **Gate G2**：T2（三路真分支）+ T3（reteach 真换策略）+ T5（学习增益 pre<post）+ T10（不幻觉引用）。
- **定位**：真·导师，但**仍是成熟 ITS**。进决赛有戏，novelty 不突出。

### M3 · 文献现推（novelty，金奖目标线）｜目标 D7–D8
- **加**：`induce_scaffold`（现推前置 + 挖误解，带 source='induced'+证据+置信）；teach 加前沿标注（共识/争议/开放）；off-curriculum 触发现推。
- **Money shot ③**：从论文现推脚手架（用户问骨架外概念→agent 现推前置/误解，带可点开证据，教成 contested）。
- **可演**："agent 自己读前沿、替你把这个新概念的位置和坑理出来。"——和 Khanmigo/NotebookLM 拉开的那刀。
- **Gate G3**：T6（现推带证据）+ T7（≥1 现推可演 / 离线推好现场展证据链）+ T8（溯源诚实）。
- **定位**：**占住没人占的格子。金奖叙事。**

### M4 · 锦上添花（仅当 M3 提前完成）｜D 余量
优先级：Langfuse trace → S3 refuse_jump → coverage warning(S4) → 多概念现推 → 更好/交互式 UI → 跨会话记忆 → RRF → SPECTER2 → GROBID 全文。

### 提交与展示（贯穿，非阶段）｜D9–D10
- **D9**：最小前端（左 chat / 右 route+证据面板 / 右下三色 concept 图）+ 录制**当前已达阶段**的 demo。
- **D10**：PPT（问题→对标 Khanmigo/NotebookLM→架构(双环+现推)→当前阶段的 money shots→学习科学→价值）+ 缓冲。
- **6/25**：提前 ≥2h 提交。

### 时间-进度联动（go / no-go 决策表）

| 检查点 | 理想进度 | 若落后 → 动作 |
|---|---|---|
| **D3 晚** | M0 通过（骨架跑通） | 数据包砍到 30 篇 / 8 concept，先保骨架跑通 |
| **D5 晚** | M1 通过（navigator 可录） | **冻结在 M1，确保有可交物**；压缩 M2 范围 |
| **D7 晚** | M2 通过（tutor 可录） | 冻结 M2；M3 只做"离线推好 + 现场展证据"的最低版 |
| **D8 晚** | M3 通过（现推可演） | M3 不稳→回退录 M2，M3 仅在 PPT 里作"已实现能力 + 证据截图"呈现 |
| **D9** | 录完当前最高阶段 | — |

### 三条铁律（写显眼，反复看）
1. **phase gate 不过，绝不进下一阶段。** 半成品的 M3 崩了，比打磨好的 M2 伤得多——终评会现场戳、提交物锁死无法补。
2. **每过一个 gate 立即打 tag / 存可运行快照。** 任何时刻都能回退到"上一个能交的版本"。
3. **目标：保底 M2、主攻 M3。** 只到 M1 基本是参与奖。

---

## 13. 冻结 demo 脚本（三场景，对应三阶段）

**Topic:** "I want to understand retrieval-augmented generation (RAG) for scientific QA."
初始骨架路线：`Dense retrieval → Contrastive learning → RAG pipeline → Evaluation/hallucination`

**场景 ②（属 M2）· 同概念 reteach**
teach dense retrieval → check 暴露误解"以为就是关键词/BM25 匹配"(`dr_is_keyword_match`) → 前置达标 → `reteach` 换 analogy 重讲 embedding 空间近邻 → 再 check 过。`mastery 0.40→0.81`，`tried_strategies=[direct, analogy]`。

**场景 ①（属 M1）· 跨概念 reroute**
teach contrastive learning → check 在 negative-sampling 题失败 → 映射到前置 `negative_sampling`(mastery<threshold) → `replan` 在 contrastive learning 前插入 negative-sampling primer，`route_version+1`。

**场景 ③（属 M3）· 文献现推 ★ novelty 硬证据**
用户引入骨架外概念："我老看到 hard negative mining，它该排在哪、有什么坑?"
→ `induce_scaffold`：
  - 前置边：`negative_sampling → hard_negative_mining`，证据"…builds on standard negative sampling…"(标 induced, conf 0.78)；
  - 误解：从论文挖出"以为负样本越多越好"→correct："hard negatives 比数量更关键"(标 induced, 引用 chunk)；
  - 前沿标注：讲成 `contested`——"怎么挖 hard negatives 还没定论，我给你两派"。
→ slot 进 route 并教，现推元素带**可点开证据**、与人工骨架视觉区分。

> **三个 money shot 的递进就是全片价值**：换讲法（像老师）→ 回退补课（像有课程观的老师）→ **从论文现推脚手架（像真在读前沿、替你把领域结构理出来的研究伙伴）**。第三个把 LitNavigator 和 Khanmigo/NotebookLM 彻底拉开。
> **录哪几个场景，取决于你冻结在哪个 milestone**：M1 录场景①；M2 加场景②；M3 加场景③。

**反事实（S2，必现演）**：场景②的题答对→直接 advance 不 reteach。两路并排，感知智能全靠这个反差。

---

## 14. MVP 删除 / 必保清单

**删除/降级**：全自动构造整张 concept DAG（现推只在 1–2 点）· 多跳前置链现推 · PDF 全文当主路径 · 200 篇 · GROBID 全量 · S4 强 bias detection（→coverage warning）· 跨会话记忆 · 完整 RRF · SPECTER2 · 完整交互式概念图（静态三色够）

**必保（删了就退化）**：
- 删了退化成 **Elicit**：LearnerState · 条件边 · grade 写 mastery · diagnose · replan · rationale
- 删了退化成 **会出题的领航员**：teach grounded 讲解 · reteach 换讲法 · 误解识别 · 三路 router · tutor_turns
- 删了退化成 **Khanmigo/NotebookLM 套壳（无 novelty）**：`induce_scaffold` 现推 · source 溯源+证据 · 前沿标注 · 场景③

---

## 15. 定位语（写进 PPT 和 README）

> **EN:** LitNavigator is a stateful tutor that is **built from and teaches through the living research literature**. It induces a concept's prerequisites and mines a field's misconceptions directly from the papers (each shown with its citing evidence), models your concept-level mastery and specific misconceptions, re-teaches differently when you don't get it, re-routes when you're missing a prerequisite, and teaches the frontier's open disagreements with calibrated confidence. Unlike fixed-curriculum tutors that teach an authored course, and unlike static source-grounded assistants that generate one-shot quizzes without a learner model, LitNavigator's curriculum, misconceptions, and teaching content all come from the live corpus.

> **中：** LitNavigator 是一个**从活文献里长出来、又用活文献教学的有状态导师**。它直接从论文里 induce 概念前置、mine 领域误解（每项都带可点开的引用证据），建模你对关键概念的掌握度与具体误解，没懂换讲法重教，缺前置回退补课，并带校准的不确定性教前沿的开放分歧。它不像固定课表的家教（教写死的课程），也不像静态文献助手（不建模你、一键出测验）——它的课程、误解和讲解内容**全部来自活的语料**。

---

## 16. 一句话

LitNavigator = 自适应导师循环 × 课程脚手架从活文献现推。10 天按风险阶梯走：M0 骨架 → M1 navigator（地板，可交）→ M2 tutor（教师能力，保底进决赛）→ M3 文献现推（novelty，争金奖）→ M4 锦上添花。每过一阶段都留一个可交可录的快照，gate 不过不进下一阶段。学习直接发生在对话里、脚手架来自活文献、每步可追溯——这就是被评委戳时不塌、又能争金奖的那一版。
