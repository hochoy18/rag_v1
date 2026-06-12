# RAG 项目脑暴 Reconcile 报告

> 范围：session `20260608_145040_7202e5`（v0.2 推演 → v0.3 → v0.3-pre → v0.4 定稿源头，134 条消息）
> 对照基线：v0.4 spec `2026-06-08-rag-system-design.md` + V1 Scope `2026-06-10-rag-v1-scope.md` + V2 TODO `2026-06-10-rag-v2-todo.md`
> 状态：**8 项已对齐**，**5 项漂移已纠正**，**2 项未传到下游（建议标注）**
> 用途：实施 M0–M12 时遇到"诶 session 提过 X 怎么不写"时回查

---

## 1. 已对齐（脑暴 → spec 全链路一致，8 项）

| 议题 | 脑暴决策点 | 当前 spec 表述 | 状态 |
|------|----------|--------------|------|
| **三库职责** | v0.2 message 160-165 选 A：llamaindex ingest / langchain LLM / langgraph workflow | V1 Scope §0 #1 同 | ✅ 一致 |
| **数据源** | v0.3-pre message 195 改飞书 → Confluence | V1 Scope §0 #4 file + url + confluence | ✅ 一致 |
| **Memory 持久化** | v0.3 message 193 换掉 `MemorySaver` → `langgraph-checkpoint-postgres` | V1 Scope §0 #12 + 依赖 §8.1 | ✅ 一致 |
| **鉴权方案** | v0.3-pre message 195 随机 token + DB 查表；v0.4 落 7d 滑/30d 硬 | V1 Scope §0 #14 + §3.2 Auth | ✅ 一致 |
| **用户系统** | v0.3 message 193 加 users + chat_sessions + session_id 关联 | V1 Scope §0 #13 + §3.2 Auth + M1 Schema | ✅ 一致 |
| **URL auth 4 模式** | v0.3 message 193 bearer/basic/cookie/header | V1 Scope §0 #15 | ✅ 一致 |
| **多模态 V1 边界** | v0.3 message 193 元数据 + UI 缩略图，不做内容问答 | V1 Scope §0 #16 + V2 §2.1/2.2 推进 | ✅ 一致 |
| **测试用模型** | v0.3 message 193 改 MiniMax-M3 | V1 Scope §0 #20 | ✅ 一致 |

---

## 2. 漂移待修（脑暴 → spec 已纠正，5 项）

这些**不是 spec 错误**，而是脑暴过程中走过的弯路、最终被纠回 spec。最终 spec 是对的，但 V2 TODO / 实施时可能踩到的认知盲区标这里。

### 2.1 langchain 价值评估的反复

| 阶段 | 决策 | 出处 |
|------|------|------|
| v0.3 | 砍 langchain，LLM 直调 anthropic SDK | message 193 1.1 段 |
| v0.3-pre | **保留 langchain**，砍不砍进 V2 TODO 评估 | message 195 第 1 项 |
| v0.4 | 保留 langchain，`app/llm/factory.py` 用 `ChatAnthropic` | message 209 spec §0 #8 |
| V1 Scope §0 #8 | 保留 langchain（langchain==1.0.8） | 2026-06-10 落盘 |
| V2 TODO §1.1 | 评估 langchain 价值 vs 依赖成本 | 2026-06-10 落盘 |

**状态**：✅ 已对齐（脑暴走了 1 步弯路后定型）

**实施注意**：
- M3 工厂实现严格走 langchain `ChatAnthropic`，**不要**走 `anthropic` SDK 直调（这是 v0.3 被否决的方案）
- V2 启动条件达成后，**先评估再砍**（V2 TODO §1.1），不能凭直觉

---

### 2.2 Checkpointer 后端选型

| 阶段 | 决策 | 出处 |
|------|------|------|
| v0.3 | 提议 OpenSearch checkpointer | message 193 1.2 段提"是否可以用 opensearch" |
| v0.3-pre | **强烈不建议**，列了 5 条理由（事务、写入模式、官方支持等） | message 195 第 2 项 |
| v0.4 | 保留 Postgres checkpointer | message 209 spec §0 #12 |
| M7 plan | Postgres 优先 / SQLite 降级 | `2026-06-10-rag-m7-graph.md` §Architecture |

**状态**：✅ 已对齐（OpenSearch checkpointer 已被否决）

**实施注意**：
- M7 `make_checkpointer()` 工厂**只接 PG 和 SQLite 两个后端**，**不要**写 OpenSearch checkpointer 实现
- 如果实施时发现"PG 部署太重"，正确路径是降级 SQLite（plan 已支持），**不是**换 OpenSearch

---

### 2.3 Confluence 抓取范围（V1 边界）

| 阶段 | 决策 | 出处 |
|------|------|------|
| v0.3 | 3.1+3.2+3.3+3.4 全做（400-500 行） | message 197 |
| v0.3-pre | 提 3 选项（A 全部 / B 精炼 / C 折中） | message 197 末尾 |
| v0.3-final | 选 **C 折中**（V1 = 3.1+3.2+3.4 + **3.3 推 V1.1**） | message 200 确认 |
| v0.4 spec | 3.1+3.2+3.4 估 250 行，3.3 进 TODO V1.1 | message 209 spec §6 |

**状态**：✅ 已对齐

**实施注意**：
- M6 plan 写的是 file/url/confluence 三个 reader，**不**包含整 space CQL
- V1.1 加 space 抓取时，**复用 M6 的 source 配置**（同 reader 多个 source），**不**重写 reader
- 整 space CQL 估算 60-80 行，孤儿处理 + cursor 翻页 + 限速 token bucket

---

### 2.4 Confluence 部署形态

| 阶段 | 决策 | 出处 |
|------|------|------|
| v0.3 提议 | Cloud / DC / Server 三选一 | message 195 §4.1 |
| v0.3 确认 | **Cloud + Basic auth** | message 196 |
| v0.4 spec | "Confluence 取代飞书" + V1 Scope §0 决策 #19 | 落盘 |

**状态**：✅ 已对齐

**实施注意**：
- M6 confluence reader 用 REST v2 + Basic auth，**不**写 Data Center 适配
- 未来如要支持 DC，加 `auth.type=pat`（personal access token）分支即可，**不**重写 reader

---

### 2.5 V2 启动条件（隐含但未明示）

| 阶段 | 决策 | 出处 |
|------|------|------|
| v0.3 / v0.4 | V2 TODO 列表一堆，但**没说 V2 什么时候启动** | message 195 + 209 |
| V2 TODO 落盘 | 顶部加"V2 启动前置条件"段 | `2026-06-10-rag-v2-todo.md` §0.0 |

**状态**：⚠️ 半对齐（V2 启动条件是 V2 TODO 落盘时**新加**的，**不是**脑暴产物）

**实施注意**：
- V1 收尾后不能"立刻"上 V2，必须等 V1 跑稳 ≥ 2 周 + RAGAS ≥ 0.75 + 1 个付费企业客户
- 这条是 V2 TODO §0.0 加的工程纪律，脑暴时没明确，spec 落盘时补的

---

## 3. 未传到下游（脑暴提过，spec 没接住，2 项）

### 3.1 表格结构化抽取（V2）

| 来源 | 表述 |
|------|------|
| 脑暴 v0.3 message 193 §1.5 | "表格元素保留表格 HTML/Markdown"（仅说保留结构，未说 LLM 抽取） |
| 脑暴 v0.3 message 195 §3 | "V2: 表格结构化抽取 + 表格 embedding 增强" |
| V2 TODO §2.3 | 表格结构化抽取（LLM 转 MD + summary + 三维 chunk） |

**状态**：✅ 已对齐（V2 TODO §2.3 已含）

**实施注意**：
- M4-M6 ingest pipeline 处理表格时，**只做 HTML→MD 转换**，**不**做 LLM 抽取（V2 范畴）
- V2 §2.3 是 M3 工厂的延伸（M2/M3 LLM 复用）

---

### 3.2 Confluence 评论 / 版本 / 增量同步（V1.1）

| 来源 | 表述 |
|------|------|
| 脑暴 v0.3-pre message 195 §4 | "V1.1: Confluence 评论 / V1.1: Confluence 增量同步 / V1.1: Confluence 页面版本" |
| V1.1 TODO 落盘 | 6 项均含（整 space CQL / 评论 / 增量 / 版本 / Playwright / classify 双轨） |

**状态**：✅ 已对齐

**实施注意**：
- V1.1 启动时，**M6 reader 改 3 处**（加评论 / 加 webhook / 加 CQL），不动 M0-M5
- 不要把 V1.1 项塞进 V1 计划——会撑爆 7 周估时

---

## 4. 总结

### 4.1 数字核对（spec vs 脑暴）

| 项 | 脑暴 v0.4 | V1 Scope | 一致 |
|----|----------|---------|------|
| 三库 | llamaindex + langchain + langgraph | 同 | ✅ |
| 节点数 | 7 节点（classify/rewrite/retrieve/rerank/answer + load/save_memory） | V1 Scope §1 架构图标的也是 7 个核心 + 1 save_memory 占位 | ✅ |
| 数据源 | file + url + confluence | V1 Scope §0 #4 | ✅ |
| Memory | PostgresCheckpointer | V1 Scope §0 #12 | ✅ |
| 鉴权 | 随机 token + DB 查表 | V1 Scope §0 #14 | ✅ |
| LLM 抽象 | langchain BaseChatModel | V1 Scope §0 #8 | ✅ |
| 多模态边界 | V1 元数据 + UI 缩略图 | V1 Scope §0 #16 | ✅ |
| 部署 | Docker Compose 本机 | V1 Scope §0 #6 | ✅ |
| 测试模型 | MiniMax-M3 | V1 Scope §0 #20 | ✅ |
| 估时 | M0-M12 ~7 周 | V1 Scope §7 ~7 周 | ✅ |

**没有任何"已经写进 spec 但脑暴没提过"的项**。spec 是脑暴的精确提炼。

### 4.2 实施时的高频踩坑点

按"脑暴走过弯路 + 实施时易忘"排序：

1. **不要砍 langchain**（v0.3 提案被否决）—— M3 工厂严格用 `ChatAnthropic`
2. **不要用 OpenSearch 做 checkpointer**（v0.3 提案被否决）—— M7 工厂只接 PG/SQLite
3. **V1 不做整 space 抓取**（v0.3 提议被精炼）—— M6 reader 只做单 page + 子页 + attachments
4. **V1 不做多模态 VLM 答图**（v0.3 边界已定）—— M4-M6 图片元素仅落元数据
5. **V1 不上 JWT**（v0.3 选 DB 查表）—— M2 走 `auth_sessions` 表，不发 JWT
6. **Confluence 走 Cloud Basic auth**（v0.3 部署形态已定）—— M6 reader 不写 DC 适配
7. **V2 启动有前置条件**（V2 TODO 落盘时新加的）—— V1 收尾后不能立刻上 V2

### 4.3 建议的下一步

**不需刷 spec/plan**——脑暴 → spec 已经对齐。

**可刷**（非必须）：
- V1 Scope §0 决策总表加一栏"出处"列，标注每条决策的脑暴 session id（提升可追溯性）
- M3/M7 plan §风险表 加一栏"曾被否决的替代方案"（如"曾考虑 OpenSearch checkpointer，已否决"）
- M6 plan §Files 加一句"V1 不含整 space CQL（v0.3 精炼）"

如要刷，告诉我刷哪几份。

---

## 5. 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| reconcile-r0 | 2026-06-10 | 初稿：对照 session `20260608_145040_7202e5` 134 条消息与 V1 Scope / V2 TODO |
