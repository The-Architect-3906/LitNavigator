<div align="center">

# 🧭 LitNavigator

**从论文出发、手把手带你入门一个陌生研究领域的 AI 导师。**

*它不会甩给你一堆论文加一份阅读清单，而是真的把概念讲明白：讲完考你、考出问题就换个讲法再讲、发现你缺前置就先带你补。而这套"课程表"本身，是它从一堆活论文里自己梳理出来的。*

![Status](https://img.shields.io/badge/status-in%20development-orange)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Framework](https://img.shields.io/badge/agent-LangGraph-black)
![License](https://img.shields.io/badge/license-MIT-green)
![ICCSE 2026](https://img.shields.io/badge/ICCSE%202026-Agentic%20AI%20Competition-purple)

</div>

---

## 这是什么

闯进一个陌生的研究子领域，最难的从来不是没资料，而是资料太多、没人替你理头绪——上百篇论文彼此预设背景，还时不时互相打架。现在的工具帮不上这个忙：要么帮你检索论文（Elicit、Connected Papers），要么就你上传的论文答疑（NotebookLM）。它们都不教你，也都不知道你到底已经懂了什么。

**LitNavigator 是一个把"活的研究文献"当教材的有状态 AI 导师。** 你给它一个领域和一个目标，它会：

- 📖 **讲**：直接把概念讲给你听，内容都落在真实论文上、带引用，而不是让你"自己去读这篇"。
- ❓ **考**：用苏格拉底式提问确认你是不是真懂，并精确定位你卡在哪个误区。
- 🔁 **换个讲法再讲**：你没懂，它就换个类比、换个例子重讲，而不是把同一句话再说一遍。
- ⛏️ **回头补课**：一旦考出来你缺某个前置，它会把前置插进你的学习路线里。
- 🌐 **自己把课程表理出来**：前置依赖、领域里的常见误区，全是它直接从论文里推出来的，每一条都附得上出处。

全程不训练任何模型——它的"聪明"来自检索、一张概念/误区图、从文献现推的脚手架，以及一套始终在更新的学习状态。

---

## 演示

<!-- 录好 30–60 秒的 GIF 放到这里 → docs/demo.gif -->
<div align="center">
<img src="docs/demo.gif" alt="LitNavigator 演示" width="720"/>
</div>

重点看三个瞬间：

1. **"我换个角度再讲一遍。"** 你把 dense retrieval 理解成了关键词匹配，它立刻换成"在嵌入空间里找近邻"的类比重讲——你对这个概念的掌握度从 `0.40` 涨到 `0.81`。
2. **"这个你得先补一下。"** 一道对比学习的题暴露出你 negative sampling 没过关，它就在往下讲之前先插一节前置，你的学习路线当场就变了。
3. **"这个概念不在你的图谱里，我去论文里给你理一理。"** 你随口问起 hard-negative mining，它现读论文、推出它建立在 negative sampling 之上，还顺手挖出论文自己点名的一个误区，然后把它当成"还在争议中的话题"来教——每一步都点得开证据。

---

## 为什么不用现成的工具

| | 建模"你" | 自适应教/考/重教 | 前置排序 | 误区诊断 | 内容取自活文献 | 课程从哪来 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Elicit / SciSpace** | ✗ | ✗ | ✗ | ✗ | ✓ | — |
| **NotebookLM** | ✗ | ✗ | ✗ | ✗ | ✓（你上传的） | — |
| **Khanmigo / LearnLM** | ✓ | ✓ | ✓ | ✓ | ✗（固定课程） | 人工授权课程 |
| **LitNavigator** | ✓ | ✓ | ✓ | ✓ | ✓ | **人工策展 + 从论文现推** |

最后一列才是真正没人占住的位置：一个自适应导师，它的前置、误区和讲解内容全都来自开放的研究前沿。而这，恰恰是研究者闯进一个新领域时的真实处境。

---

## 工作原理

LitNavigator 是两个嵌套的循环：外层管"接下来学什么"，内层把一个概念真正教到你懂为止。另外还有一条旁路，让它能在需要时从语料里现推出缺失的脚手架。

```mermaid
flowchart TD
    A([学习目标]) --> P[planner 规划<br/>从概念图排出学习路线]
    P --> S{概念在<br/>人工图谱里？}
    S -->|新概念 / 图谱外| I[induce_scaffold 现推<br/>从论文推前置 & 挖误区<br/>带证据]
    I --> R
    S -->|在| R[检索证据]
    R --> T[teach 讲解<br/>基于论文的适配讲解]
    T --> C[check 检验<br/>苏格拉底式：预测 / 复述 / 应用]
    C --> G[grade 评判<br/>识别误区 · BKT 更新掌握度]
    G --> RT{tutor_router 路由}
    RT -->|已掌握| ADV[推进到下一概念]
    RT -->|有误区| RE[reteach 重教<br/>换一种讲法]
    RE --> T
    RT -->|缺前置| DG[诊断 + 改路<br/>插入前置概念]
    DG --> S
    ADV --> S

    classDef base fill:#dde6f2,stroke:#3f4b5e,color:#0f1b2b,stroke-width:1.5px;
    classDef teach fill:#d7ccff,stroke:#5b49c4,color:#1c1444,stroke-width:1.5px;
    classDef route fill:#ffdf9e,stroke:#b3700d,color:#43280a,stroke-width:1.5px;
    classDef induce fill:#c7ecd4,stroke:#258a51,color:#0c3019,stroke-width:1.5px;
    classDef gap fill:#ffd0bf,stroke:#cf4f24,color:#481606,stroke-width:1.5px;
    class A,P,S,R,ADV base;
    class T,C,G,RE teach;
    class RT route;
    class I induce;
    class DG gap;
```

- **外层循环**（`planner → 选概念 → …… → 推进 / 改路`）：决定下一步学什么，遇到前置缺口就把缺的概念补进来。
- **内层循环**（`teach → check → grade → reteach`）：教一个概念，发现误区就换种讲法重教。
- **`induce_scaffold`**：一旦你走出图谱，它就从论文里推前置、挖误区，每条都标好"机器推导"并附上引用。

每个决策都留得下一条理由链：你的答题情况 → 对应的概念/误区 → 它采取的动作。没有黑箱。

---

## 核心特性

- **状态是真在用的**：一套逐概念的掌握度 + 误区模型（轻量级 BKT 知识追踪）在驱动每一次教学决策，不是无状态的 chatbot。
- **有据可查，绝不编引用**：讲解都落在真实片段上；现推出来的前置和误区，也都带着它们被推出来的原文。
- **教前沿教得诚实**：概念会被标成共识 / 争议 / 开放，置信度经过校准，会明确告诉你哪里还没定论。
- **全程可审计**：路线怎么改的、用了哪种重教策略、脚手架怎么推出来的，都有记录、都能查。

---

## 快速开始

> 前置要求：Python 3.11+，以及一个 LLM API key（系统与模型无关，我们用的是 Qwen）。

```bash
git clone https://github.com/<your-org>/litnavigator.git
cd litnavigator
pip install -r requirements.txt

cp .env.example .env          # 填上你的 LLM API key

# 离线构建语料、概念图、题库和误区库
python -m litnav.ingest --topic "RAG for scientific QA"

# 启动导师
python -m litnav.app
```

构建这一步全程离线（论文、向量、概念/前置图都在本地建好），所以跑起来之后整个会话不依赖任何外部 API。

---

## 项目结构

```
litnavigator/
├── litnav/
│   ├── graph/          # LangGraph 状态机：节点 + 条件边
│   ├── nodes/          # planner, teach, check, grade, reteach, induce_scaffold, replan
│   ├── retrieval/      # FTS5(BM25) + Chroma 向量检索
│   ├── scaffold/       # 前置推导 + 误区挖掘
│   ├── state.py        # NavState / 学习者模型
│   └── app.py          # 入口 / UI
├── data/               # SQLite（图 + 状态）+ Chroma 索引
├── docs/               # 演示素材、架构说明
└── README.md
```

---

## 路线图

我们按风险阶梯来开发：每个里程碑都是一个能独立跑、能演示的完整系统，所以无论进度到哪一步，手上总有一个能交的版本。

- [ ] **M0 · 跑通骨架** —— 端到端状态机 + 离线语料
- [ ] **M1 · Navigator** —— 自适应学习路线，遇到前置缺口会自动改路（亮点 ①）
- [ ] **M2 · Tutor** —— 基于论文讲解 + 误区驱动的换讲法重教（亮点 ②）
- [ ] **M3 · 文献现推脚手架** —— 从语料里推前置、挖误区（亮点 ③，真正拉开差距的地方）
- [ ] **M4 · 打磨** —— 决策追溯界面、覆盖度提示、混合检索、跨会话记忆

> **当前进度：** `M_`（随时更新）

---

## 学习科学依据

这套设计不是拍脑袋，每一处都对应着成熟的研究：

- **Bloom 的 2-sigma 问题**：一对一辅导 + 掌握学习能带来约两个标准差的效果差距，我们把这套搬到了研究前沿。
- **贝叶斯知识追踪（BKT）**：逐概念掌握度模型的来历。
- **检索练习 + ICAP 框架**：考试本身就是一种学习手段，而且我们逼你去预测、复述、应用，而不是被动地读。
- **形成性评价 + 脚手架**：先诊断、再换讲法重教，随着你越来越熟练逐步撤掉辅助。

---

## 负责任的 AI

- 讲解都落在真实段落上，引用绝不编造——对一个文献工具来说，这是底线。
- 凡是现推出来的脚手架，一律标明是机器推导，附上证据和置信度，你随时能推翻它。
- 不确定性是校准过的：争议就说争议，开放问题就说开放问题。
- 测验是形成性的，不是用来给你打分——它存在的唯一目的就是帮你学会。

---

## 技术栈

`LangGraph` · `SQLite`（+ FTS5/BM25） · `Chroma` · `bge-m3` 向量 · `networkx` · Qwen（与模型无关）

---

## 致谢

本项目为 **ICCSE 2026 Agentic AI Competition**（第九届群智科学与工程国际会议）而做，由南洋理工大学、清华大学、山东大学、新疆大学、英属哥伦比亚大学和阿里巴巴联合主办。原型开发得到 QoderWork 与阿里云"云工开物"的算力支持。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
