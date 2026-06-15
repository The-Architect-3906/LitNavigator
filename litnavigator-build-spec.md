# LitNavigator · 实现 Spec v2

> 整合外部 review 后的修订版。一句话定位变更:
> **不是"完整文献发现系统",而是"一个会根据 concept-level mastery + 前置依赖 + 测验证据动态改路的文献学习状态机"。**
> 它不训练模型;智能来自 retrieval + 人工策展的概念图 + 运行时状态转移。

---

> **贯穿全局的一条主线:每一处 schema/state 的设计,都只为一个目的——让那条 rationale chain(答错某题 → 映射到某 concept → 它是某目标概念的前置 → 所以改读哪篇)变成真的、可追溯的、经得起评委戳的。** 这条链就是整个项目的价值点,也是 demo 的 money shot。

---

## 1. 架构

### 1.1 MVP 节点图

```
input
  ↓
init_or_load_state
  ↓
planner            ← 只生成初始 concept route,不负责每次动态改路
  ↓
select_next_step   ← 从 route 里挑 pending step
  ↓
retriever          ← 只按当前 concept/paper 找证据
  ↓
presenter          ← "为何读这篇 + 关键段落 + 学习目标"
  ↓
quiz_gen           ← 从 retrieved evidence 出题,题目绑 chunk/paper
  ↓
grader             ← 判分、写 mastery、写 evidence(不决定分支)
  ↓
route_decider  ──┬── advance ───────────► select_next_step
   (条件边核心)   ├── diagnose → diagnose_gap → replan → select_next_step
                 ├── refuse_jump → presenter        (S3,加分项)
                 └── finish
```

**关键:`grader` 不再直接决定走向。** 它只产出分数和证据;`route_decider` 才根据 `mastery / threshold / prereq / off-path` 走条件边。这条 `route_decider` 就是"agent vs workflow"的物理分界,也是 demo 答对/答错分叉(S2)的真实触发点。

### 1.2 节点职责

| 节点 | 职责 | 不该做 |
|---|---|---|
| `init_or_load_state` | 新建或载入 session 的 NavState | — |
| `planner` | 由 concept DAG 拓扑排序出**初始** route | 不做动态改路 |
| `select_next_step` | 选下一个 pending step | — |
| `retriever` | 按当前 concept/paper 找证据 chunk | 不做大范围搜索 |
| `presenter` | 生成阅读理由 + 关键段落 + 学习目标 | — |
| `quiz_gen` | 从 evidence 出题,绑 chunk/paper | 不脱离论文凭空出题 |
| `grader` | 判分、写 mastery、写 evidence | **不重规划** |
| `route_decider` | 据 state 走条件边 | 不判分 |
| `diagnose_gap` | 用掌握度+DAG 找前置缺口 | — |
| `replan` | 插入/调整 route step + 输出 rationale | — |

### 1.3 NavState(修订版)

```python
class NavState(TypedDict):
    session_id: str
    user_id: str | None
    # —— 目标 ——
    topic: str
    user_goal: str
    target_concepts: list[int]
    constraints: dict                  # P2: max_depth / prefer_recent / skip_math
    # —— 图 ——
    concept_dag_version: str
    concept_dag: dict[int, list[int]]  # concept -> prereqs
    # —— 学习状态(灵魂)——
    learner_state: dict[int, dict]     # concept_id -> {mastery, evidence, confidence}
    mastery_threshold: float
    # —— 路线 ——
    reading_path: list[dict]           # RouteStep
    current_step_id: str | None
    current_concept_id: int | None
    current_paper_id: int | None
    route_version: int                 # 改路时 +1,demo 用它证明"真的改了"
    # —— RAG 证据 ——
    retrieved_ctx: list[dict]          # chunk_id, paper_id, text, score, source
    cited_evidence: list[dict]
    # —— 测验 ——
    quiz_items: list[dict]
    user_answers: list[dict]
    last_quiz_result: dict | None
    # —— 诊断与决策 ——
    diagnosis: dict | None
    decision: Literal["advance","diagnose","replan","refuse_jump","finish"] | None
    decision_rationale: str
    # —— 鲁棒性(加分项)——
    off_path_request: dict | None      # P2: S3 refuse_jump 用
    uncertainty_flags: list[str]       # P2: S5 校准语气用
    # —— 日志 ——
    history: list[dict]
```

```python
class RouteStep(TypedDict):
    step_id: str
    concept_id: int
    paper_id: int
    reason: str                        # "为什么现在读这篇"
    status: Literal["pending","active","done","skipped"]
    confidence: float
```

> **P1 必须有(撑证据链)**:`learner_state`(带 evidence+confidence)、`reading_path` 为 RouteStep、`current_concept_id`、`route_version`、`retrieved_ctx`/`cited_evidence`、`decision`+`decision_rationale`、`diagnosis`。
> **P2 可后加**:`constraints`、`off_path_request`、`uncertainty_flags`。

---

## 2. 数据规模(冻结这张表,别超)

| 项 | v1 | **v2 MVP** |
|---|---|---|
| 论文数 | ~200 | **30–50** |
| 概念数 | 自动 OpenAlex | **8–15 个手工确认** |
| prerequisite 边 | LLM 半自动 | **15–30 条人工确认** |
| PDF 全文 | GROBID 全量 | **abstract + intro/conclusion 优先**,全文可选 |
| 引用边 | 全量 | **只保留 demo 路径相关的** |
| embedding | SPECTER2/bge-m3 | **先 bge-m3**;SPECTER2 加分项 |
| 概念体系 anchor | OpenAlex Concepts | **OpenAlex Topics**(active) |

数据工程**先人工把控,自动化之后补**。Phase 0 不追求全自动管道。
注意外部 API 只用于**离线**构建数据包:Semantic Scholar 有 rate-limit(introductory ~1 RPS),demo 现场绝不 live fetch。

---

## 3. 数据库 Schema(修订 + 补全)

存储选型不变:**SQLite**(元数据+图边+状态,单文件零运维)+ **Chroma**(向量)+ **networkx**(内存图算法)。子领域只有 30–50 篇,**不要上 Neo4j**。

### 3.1 概念体系:Topics(外部 anchor)+ concepts(内部教学图)

```sql
-- 外部 anchor:OpenAlex Topics(active taxonomy)
CREATE TABLE topics (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE,
    openalex_topic_id TEXT,
    domain          TEXT,
    field           TEXT,
    subfield        TEXT,
    description     TEXT
);

-- 内部教学概念(你们自己策展,是教学依赖图的节点)
CREATE TABLE concepts (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE,
    topic_id        INTEGER REFERENCES topics(id),
    description     TEXT,
    level           INTEGER,
    is_demo_core    BOOLEAN DEFAULT 0      -- 标记 demo 主路径概念
);

-- prerequisite DAG:方向显式 + 带证据(diagnose 的核心)
CREATE TABLE concept_edges (
    prereq_concept  INTEGER REFERENCES concepts(id),   -- 前置
    target_concept  INTEGER REFERENCES concepts(id),   -- 依赖它的后续
    edge_type       TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts')),
    weight          REAL DEFAULT 1.0,
    evidence        TEXT,    -- JSON: 这条边的来源(human/LLM/paper)
    PRIMARY KEY (prereq_concept, target_concept, edge_type)
);
```

> diagnose 的核心逻辑因此可直接表达:**用户卡在 B,B 依赖 A(prereq_concept=A,target_concept=B),A 的 mastery < threshold → replan 插入 A。**

### 3.2 论文 + 分块(RAG/证据/出题都要 chunk)

```sql
CREATE TABLE papers (
    id          INTEGER PRIMARY KEY,
    arxiv_id    TEXT UNIQUE,
    title       TEXT,
    abstract    TEXT,
    authors     TEXT,           -- JSON
    source_org  TEXT,           -- coverage warning 用(尽力而为,缺失允许)
    year        INTEGER,
    full_text   TEXT,           -- 可选;优先 abstract+intro+conclusion
    pdf_path    TEXT
);

-- 分块:支撑 RAG、引用证据、题目绑定
CREATE TABLE paper_chunks (
    id            TEXT PRIMARY KEY,
    paper_id      INTEGER REFERENCES papers(id),
    section       TEXT,
    chunk_index   INTEGER,
    text          TEXT,
    token_count   INTEGER,
    embedding_id  TEXT          -- 指向 Chroma
);

CREATE TABLE paper_concepts (
    paper_id    INTEGER REFERENCES papers(id),
    concept_id  INTEGER REFERENCES concepts(id),
    relevance   REAL,
    PRIMARY KEY (paper_id, concept_id)
);

CREATE TABLE citations (
    citing_paper INTEGER REFERENCES papers(id),
    cited_paper  INTEGER REFERENCES papers(id),
    PRIMARY KEY (citing_paper, cited_paper)
);
```

### 3.3 检索 L0 保命表(demo 稳定性)

```sql
-- 提前算好 concept → top papers,demo 不依赖实时检索也能跑
CREATE TABLE concept_paper_rank (
    concept_id  INTEGER REFERENCES concepts(id),
    paper_id    INTEGER REFERENCES papers(id),
    rank        INTEGER,
    reason      TEXT,
    PRIMARY KEY (concept_id, paper_id)
);
```

### 3.4 题库 + 作答(强绑证据)

```sql
CREATE TABLE quiz_items (
    id                INTEGER PRIMARY KEY,
    concept_id        INTEGER REFERENCES concepts(id),
    question          TEXT,
    answer_key        TEXT,
    qtype             TEXT,     -- 'mcq' | 'tf_explain' | 'short'
    difficulty        INTEGER,
    evidence_chunk_id TEXT,     -- 必填:题出自哪个 chunk
    source_paper_id   INTEGER REFERENCES papers(id),
    rubric            TEXT,
    expected_concepts TEXT      -- JSON
);

CREATE TABLE quiz_attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT REFERENCES sessions(id),
    quiz_item_id        INTEGER REFERENCES quiz_items(id),
    user_answer         TEXT,
    score               REAL,
    feedback            TEXT,
    concept_score_delta TEXT,   -- JSON
    created_at          TIMESTAMP
);
```

### 3.5 会话 + 状态 + 路线 + 决策日志

```sql
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    topic       TEXT,
    status      TEXT,
    created_at  TIMESTAMP
);

-- 灵魂:每会话每概念一行
CREATE TABLE learner_state (
    session_id  TEXT REFERENCES sessions(id),
    concept_id  INTEGER REFERENCES concepts(id),
    mastery     REAL,
    confidence  REAL,
    evidence    TEXT,           -- JSON: 哪些 attempt 支撑了这个分
    updated_at  TIMESTAMP,
    PRIMARY KEY (session_id, concept_id)
);

-- 路线演化:跨会话不只有 mastery,还有路线历史
CREATE TABLE route_steps (
    session_id   TEXT REFERENCES sessions(id),
    route_version INTEGER,
    step_id      TEXT,
    concept_id   INTEGER REFERENCES concepts(id),
    paper_id     INTEGER REFERENCES papers(id),
    status       TEXT,
    reason       TEXT,
    confidence   REAL,
    created_at   TIMESTAMP,
    PRIMARY KEY (session_id, route_version, step_id)
);

-- 评委追问时最有用的表
CREATE TABLE decisions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT REFERENCES sessions(id),
    route_version  INTEGER,
    from_node      TEXT,
    decision       TEXT,
    rationale      TEXT,
    state_snapshot TEXT,        -- JSON
    created_at     TIMESTAMP
);
```

> **schema 可以比 10 天内代码真正跑到的更完整,但别让"建满所有表"变成兔子洞。** demo 只需打通主路径用到的那几张:`learner_state / concept_edges / route_steps / decisions / quiz_items+attempts / paper_chunks`。

---

## 4. Quiz / Grader(最大可信性风险,重点设计)

两个真实风险:LLM 出题脱离论文、LLM 判 short answer 不稳。对策:

**题型优先级**

| 类型 | MVP | 原因 |
|---|---|---|
| MCQ | **必须有** | deterministic scoring,稳 |
| True/False + explanation | 推荐 | 半自动评分 |
| Short answer | 可选/加分 | 易不稳,后置 |

**每题强绑 evidence**(`evidence_chunk_id` + `source_paper_id`),出题 prompt 必须基于 retrieved chunk,不许凭空生成。

**评分结果细化到 concept 级**——这是"故意答错"时能说出"你不是不懂 dense retrieval,而是卡在 negative sampling 这个前置"的关键:

```json
{
  "score": 0.5,
  "concept_scores": { "negative_sampling": 0.2, "contrastive_learning": 0.7 },
  "evidence": [
    { "quiz_id": 12, "answer": "B", "correct": false, "mapped_concept": "negative_sampling" }
  ],
  "grader_confidence": 0.9
}
```

---

## 5. 检索(分档实现,别一上来做完整 RRF)

| 档 | 做法 | 何时 |
|---|---|---|
| **L0 保命** | `concept_id → concept_paper_rank` 预计算 | Phase 0 就备好,demo 兜底 |
| **L1 最小 RAG** | **SQLite FTS5(BM25)+ Chroma 向量** | 主线;FTS5 自带 BM25,无需 Elasticsearch |
| **L2 完整** | BM25 + 向量 + citation/topic boost + RRF | 加分项,核心做完才上 |

---

## 6. S1–S5 智能信号 → 可测试验收项

| 信号 | 验收标准(可测) |
|---|---|
| **S1 "因为"** | rationale 必须引用 `quiz_result` + `concept_edge` + route change |
| **S2 分叉** | 同一题:答对→`advance`;答错→`diagnose/replan`(真条件边) |
| **S3 反对**(加分) | 用户要跳高级论文时,系统指出缺哪个前置;**"可以看,但不建议作为主路径",不强硬拒绝** |
| **S4 → coverage warning**(改名) | 提示"当前路径论文集中在某几年/某机构/某研究路线,覆盖可能不均",**不叫 bias detection,不做强判断** |
| **S5 校准语气** | rationale 显示 confidence,如 "tentatively recommended" |

> S4 改名是关键防线:`source_org`/立场难可靠抽取,承诺 bias detection 会被评委追问到解释不清。coverage warning 是你能站得住的版本。

---

## 7. 排期(锚定真实硬截止 6/25,非 15 天)

> 注册 6/18,**提交 video+PPT 6/25**,接收通知 6/28,终评 7/8–12。
> 提交一旦锁定无法再加内容 → **一切核心必须 6/25 前 ship**。review 的"D11-15 加分项"在提交之后,故改为"核心提前做完才挤,否则砍",不是后置。

| 日期 | 重点 | 交付物 |
|---|---|---|
| **D1–2 (6/15–16)** | 冻结 domain + 人工数据包 | 30–50 篇 / 8–15 concept / 人工 prereq DAG / concept↔paper 绑定 |
| **D3–4 (6/17–18)** | LangGraph + NavState + **确定性分支**;**6/18 完成注册** | 条件边跑通、LearnerState 落 SQLite、≥1 个真实答对/答错分叉 |
| **D5–6 (6/19–20)** | Retrieval(L0+L1)+ quiz 绑 evidence | chunk 建好、题绑 chunk、grader 写 concept-level mastery |
| **D7–8 (6/21–22)** | **Replan + rationale chain(最核心 demo)** | 答错→插 prereq step;rationale 能说清 错题→concept→前置→下一篇 |
| **D9 (6/23)** | 最小前端 + 录制 | 左 chat / 右 route panel / 右下三色 concept 图;录"答对/答错"两条路径 |
| **D10 (6/24)** | PPT + 缓冲 | 问题→架构→demo→亮点→价值 |
| **6/25** | 提前 2 小时提交 | ✅ |

**加分项(仅当核心提前完成,6/25 前挤;否则直接砍)**,优先级:
1. Langfuse trace → 2. S3 refuse_jump → 3. coverage warning → 4. 更好 UI → 5. Hybrid RRF → 6. SPECTER2 → 7. GROBID 全文

---

## 8. 最小可交付 demo 脚本(冻结成这个)

**Topic:** "I want to understand retrieval-augmented generation for scientific QA."

初始路线:`Dense retrieval → Contrastive learning → RAG pipeline → Evaluation/hallucination`
用户读 dense retrieval 论文后答题。

**分支 A(答对):**
> Both dense-retrieval questions correct. Mastery(dense retrieval) 0.42 → 0.78. Above threshold → move to contrastive learning.

**分支 B(答错):**
> Missed the negative-sampling question. In the concept graph it's a **prerequisite** for contrastive learning. Inserting a short prerequisite reading before continuing.

路线从 `Dense retrieval → Contrastive learning → RAG pipeline`
变成 `Dense retrieval → Negative-sampling primer → Contrastive learning → RAG pipeline`。

**这条"路线因你的测验结果而改变"就是整个项目的价值点。**

---

## 9. 硬验收标准(用测试验收,不用"功能完成")

| Test | 内容 |
|---|---|
| **T1 状态真实写入** | 一次 quiz 后 SQLite 能看到:`learner_state.mastery` 变化、`quiz_attempts` 插入、`decisions` 插入 |
| **T2 真条件边** | 同 session:答对→`advance`;答错→`diagnose→replan`。**必须真分支,非前端写死** |
| **T3 rationale 可追溯** | 每条 rationale 能追到 `quiz_item_id → concept_id → concept_edge → paper_id → route_step_id` |
| **T4 跳步拦截** | 用户"跳过前置直接给高级论文" → 系统"可以看,但不建议作主路径,因为 [prereq] 未达标且 [target] 依赖它" |
| **T5 离线可跑** | demo 现场不依赖 live arXiv/OpenAlex/S2;外部 API 仅用于离线构建 |

---

## 10. MVP 删除 / 必保清单

**从 MVP 删除或降级:** 200 篇论文 · GROBID 全量解析 · 自动构造完整 concept DAG · S4 bias detection(改 coverage warning)· 跨会话记忆彩蛋 · 完整 RRF · 完整交互式概念图(静态三色足够)

**必须保留(删了就退化成 Elicit):** LearnerState · 条件边 · grader 写 mastery · diagnose 找前置缺口 · replan 改 reading_path · decision rationale

---

## 11. 定位语(写进 PPT 和 README)

> **EN:** LitNavigator is a stateful literature-learning copilot that adapts the reading path based on concept-level mastery, prerequisite dependencies, and quiz evidence. It does not train a model; its intelligence comes from retrieval, a curated concept graph, and runtime state transitions.

> **中:** LitNavigator 不是普通文献 RAG,而是一个基于 LearnerState 的文献学习状态机。它根据用户对关键概念的掌握度、概念依赖关系和测验证据,动态调整阅读路径。

---

## 12. 一句话

把"完整文献系统"砍成"可验证的自适应学习闭环"。核心闭环 `paper → quiz → mastery → diagnose → replan` 先做真,数据缩到 30–50 篇人工可控,题目全绑 evidence,Concepts 换 Topics,S4 改 coverage warning,RRF/SPECTER2/GROBID/Langfuse 全后置。这版十几天能做完,且被评委戳时不塌。
