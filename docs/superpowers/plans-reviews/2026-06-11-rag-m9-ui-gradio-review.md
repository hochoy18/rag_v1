# M9 Plan Review · Gradio Web UI（4 tab：login / sessions / chat / ingest）

> 评审对象：`plans/2026-06-11-rag-m9-ui-gradio.md`（776 行）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #7/#16 · §1 架构 UI 段 · §2 模块树 ui 段 · §4 API & UI 表 · §5 错误矩阵）
> 参考 review：总报告 `2026-06-11-rag-plans-review.md`（P0-1/P0-5/P1-4/P1-6/P1-11/X-3）· M8 review `2026-06-11-rag-m8-api-chat-review.md` · M7 review `2026-06-11-rag-m7-graph-review.md` · M0-M6 独立 review 报告
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M9 plan 覆盖 11 段模板（Goal / 不包含 / Architecture / Tech Stack / Files / 16 Tasks RED-GREEN / 测试策略 / DoD / 依赖 / 风险 / 修订记录），自带范本目的段（L10）和完整的数据流图（L99-109）。4 tab 拆独立模块、TDD 红绿 16 Tasks/5 天、theme/api_client/auth_state/errors 4 个基础设施 + login/sessions/chat/ingest 4 tab + 5 个组件 + 9 个测试文件——**结构是 RAG V1 路线中最完整的 plan 之一**（与 M8 并列第一）。

**主动吸收了跨 M review 的关键 P0/P1**：P0-1 端口 7860 不冲突（L8）、P0-5 真 PG（L697）、P1-4 ORM updated_at（L402）、P1-6 复合索引（L402）、P1-11 auth 透传（L260）、X-3 全局 settings（L194-204）——6 项在 plan 中显式标注或实现。**这是目前所有 M plan 中吸收已有 review 最彻底的**，值得点赞。

**但前端工程化与 UX 有显著缺口**——Gradio 5.0+ 的 `gr.Error()` toast 没使用、loading spinner 缺、auto-scroll 缺、Enter/Shift+Enter keyboard shortcut 缺、移动端响应式缺、image fallback 缺、CORS 跨域验证缺测试——**10 项是前端可用性 P1 级问题**，集中在 Day 3/4/5 chat+ingest tab。修完 P0 2 项 + P1 15 项 + P2 8 项后是可直接动手的合格 plan。

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐 + 范本目的段 + 数据流图 + 契约边界表 + M9 特有 P0/P1 避雷段——结构在 M0-M9 中与 M8 并列最完整 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 16 Tasks 全部 RED-GREEN-REFACTOR；RED 测试名具体、GREEN 代码段完整（非伪代码）、REFACTOR 提法恰当 |
| 技术深度 | ⭐⭐⭐⭐ | Gradio 5.0 Blocks 4 tab 分离、httpx AsyncClient 封装、gr.BrowserState 持久化、[1][2][3] regex 解析、ingest asyncio 轮询——设计完整；但缺 loading/auto-scroll/toast/keyboard/响应式等前端工程化细节 |
| 已有 review 就绪度 | ⭐⭐⭐⭐⭐ | 6 项已有 P0/P1 全部避雷标注 + 实现方案（P0-1/P0-5/P1-4/P1-6/P1-11/X-3）——M9 是当前路线中吸收已有 review 最彻底的 plan |
| 错误处理 | ⭐⭐⭐⭐ | 401/404/422/502/NetworkError 全分类 + 代码段完整；但缺 error toast（gr.Error）、多次 401 过期提示、image fallback |
| 跨 M 契约 | ⭐⭐⭐⭐ | 依赖表清晰（M0/M1/M2/M7/M8）；风险表标注 CORS/checkpointer/image_ref 等跨 M 风险；但缺 M8 CORS 验证测试 |
| UX 就绪度 | ⭐⭐⭐ | 功能完整但体验粗糙——loading/error toast/auto-scroll/keyboard shortcut/响应式/确认弹窗 6 项 UX 细节全缺 |

**一句话**：M9 plan **结构最完整、TDD 节奏最佳、已有 review 吸收最彻底**，是 M0-M9 中与 M8 并列最成熟的 plan；但**前端 UX 工程化严重不足**（10 项 P1 UX 缺陷 + 2 项 P0 阻塞），修完后是可直接动手的合格 plan。

---

## 已有 review 验证（2026-06-11-rag-plans-review.md）

| ID | 已有 review 项 | Plan 现状 | 本报告 |
|----|---------------|-----------|--------|
| **P0-1** | 端口冲突（TEI 8080 vs http.server） | ✅ 已避雷——L8 `P0-1 端口 7860 不冲突`；L203 `gradio_server_port: int = 7860` | 通过。Gradio 7860 与 M8 FastAPI 8000/TEI 18080/OS 9200/Langfuse 3000 无冲突 |
| **P0-5** | 真 PG 集成测试（不跑 sqlite） | ✅ 已避雷——L697 `conftest.py 的 pg_session fixture（修 P0-5，真 PG）`；Task 16 GREEN 段完整给出 | 通过。`--require-docker` + pg_dsn fixture |
| **P1-4** | updated_at 走 ORM 而非原生 SQL | ✅ 已避雷——L402 `s["updated_at"]` 来自 API response（走 M8 ORM），M9 不直接写 updated_at | 通过。M9 全走 M8 API，不直接操作 DB |
| **P1-6** | chat_sessions 复合索引 | ✅ 已避雷——L402 注释 `# 依赖 P1-6 复合索引` | 通过。list_sessions 依赖 M1 索引加速查询 |
| **P1-11** | protected endpoint 鉴权完整 | ✅ 已避雷——L260 `Authorization: Bearer {self._token}`；L368 `AuthExpired: return "请重新登录"` | 通过。APIClient 在所有端点上注入 Bearer token |
| **X-3** | 全局 settings 单例 | ✅ 已避雷——L253 `settings.ui.api_base_url`（from config import settings）；Task 1 UISettings 继承 BaseSettings | 通过。M9 全局使用 `from app.config import settings` |
| **P0-8** | pyproject.toml 过度装包 | ✅ 已避雷——L171 `pyproject.toml：追加 gradio>=5.0,<6 直接依赖`（仅加 gradio，不装多余包） | 通过 |
| **P2-6** | app/api/__init__.py 聚合 | N/A——M9 不动 `app/api/` | 通过 |
| **P2-7** | app/db/__init__.py 统一导入 | N/A——M9 不直接调 DB | 通过 |
| **P1-18** | pytest-httpx 缺声明 | ✅ 测试矩阵 L707 说 `pytest tests/unit/test_ui_*.py —— mock 为主`——假设 M3 已修 P1-18 | 通过（依赖 M3） |

**验证结论**：已有 review 中影响 M9 的 6 项——**全部 ✅ 已避雷**。M9 是当前 RAG V1 路线中吸收已有 review 最彻底的 plan，P0/X 标注齐全。

---

## M8 review 交叉验证（CORS · 超时 · API 契约）

### 8-1 · M8 review P2-3 CORS middleware 顺序 → M9 应加 CORS 验证测试（**P0-1**）

**位置**：M8 review P2-3 · M9 plan 风险表 L749 · M9 DoD 表（无 CORS 项）

**问题**：
- M8 review P2-3 指出 CORS 中间件顺序（CORSMiddleware 应在 RequestIdMiddleware 之前）——这是一个潜在的实现 bug
- M9 plan 风险表 L749 只说"M8 CORSMiddleware 配 `allow_origins=[settings.ui.cors_origin]`"——**假设 M8 已正确配置并修复了 P2-3**
- 但 M9 DoD 表（L713-726）**没有任何 CORS 验证测试项**——没有集成测试验证 Gradio 7860 → M8 8000 跨域请求能通过
- 如果 M8 的 CORS 配置错了（如 allow_origins 漏了 localhost:7860，或 middleware 顺序导致 preflight 失败），M9 的 login/chat/ingest 全部请求会跨域失败——**这是 M8→M9 的致命依赖断裂**

**修改**（DoD 补一项 + Task 16 E2E 补 CORS 验证）：

```python
# tests/integration/test_m9_gradio_e2e.py —— 补 CORS 冒烟测试
async def test_cors_headers_present():
    """验证 M8 返回 CORS header，M9 跨域请求不报错。"""
    async with httpx.AsyncClient() as client:
        # OPTIONS preflight 模拟 Gradio JS fetch 行为
        resp = await client.options(
            "http://localhost:8000/api/health",
            headers={
                "Origin": "http://localhost:7860",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:7860"
```

DoD 补一行：`[ ] M8 CORS header `Access-Control-Allow-Origin: http://localhost:7860` 由 M9 集成测试验证`

---

### 8-2 · M8 review P0-1 chat 端点超时保护 → M9 chat tab 依赖 M8 修复

**位置**：M8 review P0-1 · M9 plan Task 11 GREEN 段 L523

**问题**：
- M8 review P0-1（P0 级）指出 `POST /api/chat` 端点缺 `asyncio.wait_for(graph.ainvoke(...), timeout=30)`
- 如果 M8 没修 P0-1，`graph.ainvoke` 可能 hang 60s+ → Gradio `APIClient` 默认 timeout=30.0s（L254）会触发 `httpx.TimeoutException` → `NetworkError` 分类
- M9 的 `_handle_chat` handler **没有捕获 `NetworkError`**（L524 只 try/except `AuthExpired`）
- 如果 M8 超时返回 502（修 P0-1 后的行为），M9 的 `classify_response` 会抛 `UpstreamError`——同样没在 chat handler 里被捕获

**修改**（Task 11 GREEN 段补异常处理）：

```python
async def _handle_chat(query, session_id, auth_state_value):
    if not query.strip(): return gr.update(), gr.update(), gr.update(), gr.update(), ""
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    try:
        response = await client.post_chat(query, session_id)
    except AuthExpired:
        return gr.update(), gr.update(), gr.update(), "请重新登录", ""
    except (UpstreamError, NetworkError) as e:
        return gr.update(), gr.update(), gr.update(), f"❌ 服务异常: {e}", ""
    ...
```

风险表补一行：`chat 端点 M8 超时保护未修` | `asyncio.wait_for` 缺，Gradio 客户端 30s timeout 后 `NetworkError` | 补 `UpstreamError`/`NetworkError` try/except；M9 DoD 标记依赖 M8 P0-1 修复

---

### 8-3 · M7 review P0-6 answer_chitchat_node 缺实现 → M9 chat tab 依赖 M7 修复

**位置**：M7 review P0-6 · M9 plan 依赖表 L731-737

**问题**：
- M7 review P0-6 指出 `answer_chitchat_node` **完全没有实现**——M7 注册了但没写函数体
- 如果 classify 返回 `intent=chitchat`，graph invoke 崩溃 → M8 路由层返回 500 → M9 chat handler 收到 `UpstreamError`
- M9 依赖表只列了"M7 graph"——没有说 M8/M9 依赖 M7 的 chitchat 分支完整实现
- M9 的 `test_chat_handler_handles_401_by_returning_login_prompt` 只测 401 路径，没测 graph 内部崩溃时的显示

**修改**（依赖表补一行）：

```
| M7 graph chitchat 分支（answer_chitchat_node 实现 / M7 P0-6） | 若 M7 未实现，graph invoke 崩溃返回 500，M9 显示"服务异常" | M9 DoD 不阻塞但 chat 端点的 chitchat 功能不可用 |
```

---

## P0 · 阻塞级（动手前必改）

### P0-1 · CORS 跨域验证缺集成测试（M8→M9 致命依赖断裂）

**位置**：M9 plan DoD L713-726 · 风险表 L749 · 测试矩阵 L706-708

**问题**：
- M8 review P2-3 指出 CORS middleware 顺序问题（CORSMiddleware 应在 RequestIdMiddleware 之前）。M9 假设 M8 已正确配置 `allow_origins=["http://localhost:7860"]`——**但没有任何测试验证这个假设**
- M9 的浏览器端 Gradio 页面（7860）发 fetch 到 FastAPI（8000），如果 CORS header 缺失，`gr.BrowserState` 存 token 的 JS `localStorage`、`APIClient` 的 httpx 请求全部失败
- M9 DoD 表 11 条中**没有任何 CORS 相关项**——这是 M8→M9 接口契约没有测试覆盖的盲区
- 问题不是 CORS 配置难——问题是谁也发现不了它坏了，直到用户打开浏览器

**修改**（三处同步改）：

**1. DoD 表补一项**：
```
[ ] CORS 跨域验证：集成测试 `test_cors_headers_present` 通过（见 §8-1 代码段）
```

**2. Task 16（E2E 测试）补 CORS 冒烟测试**：

```python
# tests/integration/test_m9_gradio_e2e.py — 追加
async def test_cors_headers_present():
    async with httpx.AsyncClient() as client:
        resp = await client.options(
            "http://localhost:8000/api/health",
            headers={"Origin": "http://localhost:7860", "Access-Control-Request-Method": "POST"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:7860"
```

**3. 风险表 L749 补一行**：
```
| CORS 配置未验证 | M8 CORSMiddleware 配置错误或 middleware 顺序问题，M9 所有跨域请求失败 | 集成测试 `test_cors_headers_present` 每次 PR 必过 |
```

---

### P0-2 · docker-compose gradio service 缺 healthcheck，E2E 测试 race condition

**位置**：Task 15 GREEN 段 L663-677

**问题**：
- Task 15 在 docker-compose.yml 加 `gradio` service，`depends_on: { api: { condition: service_healthy } }`——但 gradio 本身**没有 healthcheck 块**
- `gradio` container 启动后，Gradio 的 uvicorn 服务器需要 3-10s 完成 `demo.launch()`（加载 theme、编译 JS 前端、初始化 state）
- E2E 测试（Task 16）在 `docker compose up -d gradio` 后**立即开始**——如果 Gradio 还没 ready，`GradioTestClient` 或 httpx 向 7860 发请求会 `Connection Refused` → 测试假失败
- M8 review P0-3（health check 5 service 探测实现模糊）也是同类问题——M9 应从中吸取教训自己配好

**修改**（Task 15 GREEN 段补 healthcheck）：

```yaml
services:
  gradio:
    build: .
    command: ["python", "-m", "app.ui.gradio_app"]
    ports: ["7860:7860"]
    environment:
      - API_BASE_URL=http://api:8000
    depends_on:
      api: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:7860/ || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s   # Gradio 首次编译前端较慢
```

---

### P0-3 · image 缩略图加载失败缺 fallback，M8 /file 端点可能不存在

**位置**：Task 10 GREEN 段 L486-494 · L491注释 `M9 假设 M8 已有 /file 端点 stub`

**问题**：
- L491 明确写"M9 **假设** M8 已有 /file 端点 stub"——这是一个尚未验证的假设
- M8 plan 的 Files 表（M8 plan L252-253）没有 `/file` 路由——M8 端点列表只有 auth/sessions/chat/ingest/health 5 个
- 如果 M8 没有 `/file` 端点，`image_ref_to_url("http://api:8000/file=/data/imgs/p1.png")` 返回的 URL 404 → `gr.Gallery` 显示 broken image
- `image_ref_to_url` 函数完全没做错误处理——即使 M8 有 `/file` 端点，路径不存在时 gallery 也是 broken
- spec 决策 #16 说 V1 多模态仅元数据+UI 缩略图——broken thumbnail = broken feature，没有 fallback 语义

**修改**（Task 10 GREEN 段补 fallback + Task 15 补 M8 file 端点依赖标注）：

```python
def image_ref_to_url(ref: str) -> str:
    """M7 retrieve 返回的 image_ref → Gradio 可访问的 /file= URL。
    data: 前缀直接返回（base64），路径优先尝试 M8 /file 端点。
    注：M8 必须有 GET /file/{path} 路由（由 M8 或 M12 实现）。
    """
    if ref and ref.startswith("data:"):
        return ref  # data URL 直接传递，不依赖 M8
    if not ref:
        return ""  # 空 → gallery 不显示
    base = settings.ui.api_base_url.rstrip("/")
    return f"{base}/file={ref}"
```

并在 gallery 渲染处加 `gr.Gallery(columns=2, height="auto", show_label=False)`——Gradio 5.0+ Gallery 缺省隐藏空/损坏项。

依赖表 M8 行补：`M8 需实现 GET /file/{path} 端点（stub） | M9 依赖此端点展示 image thumbnail`。

---

## P1 · 重要

### P1-1 · Chat 响应等待时缺 loading 状态

**位置**：Task 11 GREEN 段 L508-534

**问题**：
- 用户在 chat tab 点"发送"后，`_handle_chat` async handler 执行 `client.post_chat()`（httpx 请求 + graph.ainvoke 可能 5-30s）
- 等待期间 `gr.Chatbot` 不显示任何 loading 指示——用户不知道系统在工作还是卡了
- Gradio 5.0+ 的 `gr.Chatbot` 支持 `.loading()` 或 gr.Progress，但 plan 里 chat tab 没有使用

**修改**（`_handle_chat` 包装 + 在等待时显示临时 user message + loading dots）：

```python
# 方案 A：先追加一条 user message + 一条临时 assistant message（含 loading dots）
# app/ui/tabs/chat.py
async def _handle_chat(query, session_id, auth_state_value):
    if not query.strip():
        return gr.update(), gr.update(), gr.update(), gr.update(), ""
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    # 先渲染 user message + loading 占位
    yield [{"role": "user", "content": query}, {"role": "assistant", "content": "▌"}], \
          gr.update(), gr.update(), gr.update(), ""
    try:
        response = await client.post_chat(query, session_id)
    except AuthExpired:
        yield [{"role": "user", "content": query, "loading": True}], gr.update(), gr.update(), "请重新登录", ""
        return
    except (UpstreamError, NetworkError) as e:
        yield ..., f"❌ {e}", ...
        return
    parsed = parse_citations(response["answer"])
    yield ..., ..., ..., ..., ""
```

如果使用 generator handler（`yield`），需加 `fn=...` 的 `outputs` 参数配置（Gradio 5.0+ 支持 generator outputs）。

---

### P1-2 · 错误提示用 gr.Markdown 而非 Gradio 5.0+ gr.Error() toast

**位置**：Task 6 G L370 · Task 11 L524 · Task 13 L612

**问题**：
- 当前所有错误提示用 `gr.Markdown` 或 `gr.update(value="❌ ...")` 渲染在页面正文中——侵入式、占用空间、不消失
- Gradio 5.0+ 支持 `gr.Error()` / `gr.Warning()` / `gr.Info()` 浮动 toast 通知——非侵入、自动淡出
- 401 用 toast + 跳 login tab 比三段式 markdown 好得多

**修改**（handler 内异常分支改 toast）：Gradio 的 `gr.Error` 是一个 class，在 handler 内直接 `raise gr.Error("未登录")` 或在返回中 `gr.Error("...")`。

```python
# 当前（Task 11 L524）：
except AuthExpired:
    return gr.update(), gr.update(), gr.update(), "请重新登录", ""

# 改为（Gradio 5.0+ toast）：
except AuthExpired:
    raise gr.Error("身份已过期，请重新登录")
```

需确认 Gradio 5.0+ Python handler 内 `raise gr.Error()` 不会被框架拦截（Gradio 5.0 文档：在 event handler 中 `raise gr.Error("msg")` 会显示 toast 并中断 handler 执行）。

---

### P1-3 · 新消息后缺 auto-scroll

**位置**：Task 11 GREEN 段 · chat.py 整体

**问题**：
- chat response 渲染到 `gr.Chatbot` 后，用户必须手动滚动到底部看新消息
- 多轮对话后，每次响应都在屏幕外，用户手动滚 → 低劣 UX
- Gradio 5.0+ `gr.Chatbot` 支持 `autoscroll=True` 参数（v5.0+ 新增）

**修改**（Task 11 GREEN 段 `gr.Chatbot` 加参数）：

```python
chatbot = gr.Chatbot(
    type="messages",
    label="对话",
    autoscroll=True,        # 5.0+ 自动滚到底
    show_copy_button=True,  # 5.0+ 复制消息
)
```

如果 Gradio 5.0.0 没有 `autoscroll`，用 JS 回调（`_js`）触发 `scrollIntoView`。

---

### P1-4 · 缺 Enter 发送 / Shift+Enter 换行 keyboard shortcut

**位置**：Task 11 GREEN 段 L512

**问题**：
- 当前 `query = gr.Textbox(placeholder="问点什么...")`——用户不能按 Enter 触发发送
- 所有主流聊天 UI（ChatGPT/Claude/Perplexity）都是 Enter 发送、Shift+Enter 换行
- Gradio 5.0+ `gr.Textbox` 支持 `submit_on_enter=True`

**修改**（Task 11 GREEN 段加 `submit_on_enter`）：

```python
query = gr.Textbox(
    placeholder="问点什么...（Enter 发送，Shift+Enter 换行）",
    label="问题",
    submit_on_enter=True,    # 5.0+ 按 Enter 触发 .click() 或 .submit()
)
chatbot = gr.Chatbot(...)
query.submit(
    _handle_chat, [query, current_session, auth_state],
    [chatbot, source_column, image_gallery, trace_link, query],
)
```

同时删掉 `gr.Button("发送")` 或保持作为辅助入口。

---

### P1-5 · Ingest file upload 缺前端文件大小检查

**位置**：Task 13 GREEN 段 L589-591

**问题**：
- `gr.File(file_count="multiple", file_types=[".pdf", ".docx", ".md", ".txt"])`——没有 `file_size` 参数
- 用户可能选 200MB PDF → 上传到 M8 → M8 转发到 M4 pipeline → spec §5 说"附件超大 (>50MB) 跳过"
- 50MB 上传到服务端才被拒，浪费带宽+时间
- Gradio 5.0+ `gr.File` 不支持原生文件大小过滤，需前端 JS 或 handler 内检查

**修改**（Task 13 GREEN 段 `_handle_file` 加前端检查）：

```python
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

async def _handle_file(files, auth_state_value):
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    if files:
        # 前端检查
        for f in files:
            if f.size and f.size > MAX_FILE_SIZE:
                return f"❌ 文件 {f.name} 超过 50MB，跳过提交"
        paths = [f.name for f in files]
        result = await client.post_ingest(source="file", payload={"paths": paths})
        return f"✅ 已提交 {len(paths)} 个文件，job_id: {result['job_id']}"
    return "⚠️ 未选择文件"
```

---

### P1-6 · URL ingest 前端验证缺

**位置**：Task 13 GREEN 段 L594-599

**问题**：
- URL Textbox 无验证：用户可能输入 `javascript:alert(1)`、`ftp://`、空格、空字符串
- 空 URL + click "提交入库" → handler 调 `client.post_ingest(source="url", ...)` → M5 服务端 422 ValidationError
- 前端验证好于后端返回 422

**修改**（Task 13 `_handle_url` 补验证）：

```python
import re

URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

async def _handle_url(url_str, auth_type, creds, auth_state_value):
    if not url_str or not url_str.strip():
        return "⚠️ 请输入 URL"
    if not URL_PATTERN.match(url_str.strip()):
        return "❌ URL 格式不正确（需以 http:// 或 https:// 开头）"
    if len(url_str) > 2048:
        return "❌ URL 长度超过 2048 字符"
    # ... 后续逻辑
```

---

### P1-7 · Logout 后不跳转 login tab

**位置**：Task 6 GREEN 段 · login.py 登出逻辑

**问题**：
- 登出逻辑在 `_handle_logout` 中只会清 auth_state，不会切换到 login tab
- 用户点"登出"后留在当前 tab（如 chat 或 sessions）→ 看到空白 UI（因为 token 清空了）
- 良好的 UX：登出后自动显示 login tab + "已退出登录" toast

**修改**（登出 handler 返 gr.Tabs selected 索引）：

```python
def _handle_logout(auth_state_value):
    return {}, gr.Tabs(selected=0)  # Tab 0 = login tab
```

需 `build_login_tab` 返回 tab 索引信息，或全局 `gr.Tabs` 使用 `.change` 监听。

---

### P1-8 · 多次 401 后 session 过期提示

**位置**：Task 5 errors.py · Task 11 chat.py

**问题**：
- 当前 401 在 chat handler 中被捕获，返回 `"请重新登录"`——但如果用户连续遇到 401（如 token 过期后多发了几条消息），每次都是同一提示
- 没有区分"首次 401"和"多次 401"：多次触发说明 session 已过期，应强制跳登录页
- 没有在 `APIClient` 层面做 401 自动 logout

**修改**（APIClient._request 加 401 标记 + handler 检测）：

```python
# app/ui/api_client.py
class APIClient:
    def __init__(self, ...):
        ...
        self._consecutive_401 = 0
    
    async def _request(self, method, path, **kw):
        resp = await self._client.request(method, path, headers=self._headers(), **kw)
        if resp.status_code == 401:
            self._consecutive_401 += 1
        else:
            self._consecutive_401 = 0
        classify_response(resp)
        return resp.json()
    
    @property
    def session_expired(self):
        return self._consecutive_401 >= 3
```

`build_chat_tab` 在 handler 入口检 `client.session_expired → gr.Error("登录已过期") + clear auth_state`。

---

### P1-9 · Session 删除缺确认弹窗

**位置**：Task 7 GREEN 段 L393-395

**问题**：
- `del_btn.click(_delete_selected, [df], df)`——点击就删，无确认弹窗
- 误触删除后不可恢复（chat_sessions 物理删除或软删除）
- Gradio 5.0+ 不支持原生 confirm dialog，需 `gr.Button` 的 `_js` 参数调 JS `confirm()`

**修改**（删除按钮加 JS confirm）：

```python
del_btn = gr.Button("删除选中")
del_btn.click(
    _delete_selected, [df], df,
    _js="(idx) => confirm('确认删除选中的会话？此操作不可恢复。') ? idx : null",
)
```

如果 `confirm()` 返 false（取消），handler 不执行（`prevent_concurrent=True` 确保）。

---

### P1-10 · 中文 source 卡中文溢出 CSS 被 5.0+ CSS 覆盖

**位置**：Task 9 GREEN 段 · Task 2 CUSTOM_CSS L230-234

**问题**：
- `CUSTOM_CSS` 定义了 `.source-card pre { white-space: pre-wrap; word-wrap: break-word; }`
- 但 `source_card.py` 的 `gr.Markdown(f"```\\n{src.content}\\n```")` 渲染在 Gradio 5.0+ 的 `prose` 类名下——Gradio 5.0 自带的 tailwind prose 类优先级高于 `pre` 元素选择器
- 实际测试中，中文长文本可能不换行（overflow-x scroll）而不是 wrap
- plan 没有提供实际 CSS 覆盖测试（Task 9 RED 只断言 CSS class 存在，不测真实渲染）

**修改**（CUSTOM_CSS 提高优先级 + 测试补渲染断言）：

```css
/* 提高优先级覆盖 Gradio 5.0 prose 样式 */
.source-card pre,
.source-card code,
.gr-box .source-card pre {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    max-width: 100% !important;
}
```

Task 9 RED 测试 `test_source_card_breaks_long_text` 补：
```python
# 除 CSS class 外，断言 rendered HTML 含 word-break 属性
assert "overflow-wrap: break-word" in source_card_html
```

---

### P1-11 · Config 中 `cors_origin` 默认值耦合 7860

**位置**：Task 1 GREEN 段 L202

**问题**：
- `cors_origin: str = "http://localhost:7860"`——硬编码假设 Gradio 总是 7860
- 如果 `.env` 改了 `GRADIO_SERVER_PORT=7861`，`cors_origin` 也要手动改——同步问题
- 应该从 `gradio_server_port` 自动拼接

**修改**（config.py UISettings 用 `@computed_field` 或 model_validator 自动生成）：

```python
class UISettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    theme_bg: str = "#0d1117"
    theme_accent: str = "#58a6ff"
    font_family: str = "PingFang SC, Microsoft YaHei, sans-serif"
    gradio_server_name: str = "0.0.0.0"
    gradio_server_port: int = 7860

    @property
    def cors_origin(self) -> str:
        """自动从 gradio_server_name + port 拼接。"""
        host = "localhost" if self.gradio_server_name == "0.0.0.0" else self.gradio_server_name
        return f"http://{host}:{self.gradio_server_port}"
```

---

## P2 · 优化

### P2-1 · `gr.Chatbot(type="messages")` 5.0+ 兼容性未验证

**位置**：Task 11 GREEN 段 L511 · Tech Stack L131

**问题**：
- `type="messages"` 在 Gradio 5.0 是强制参数（5.0 以前的 `type="tuples"`/`type="messages"` 兼容）
- 但 plan 没有单元测试验证这个参数在 **安装的 Gradio 版本** 上可用
- 如果 `gradio>=5.0,<6` 装到了 5.0.0-beta，`type="messages"` 可能还没稳定

**修改**（Task 11 RED 补版本兼容性测试）：

```python
# tests/unit/test_ui_tabs.py
def test_chatbot_type_messages_supported():
    """Gradio 5.0+ 必须支持 gr.Chatbot(type='messages')。"""
    import gradio as gr
    # 构造实例不报错即可
    chatbot = gr.Chatbot(type="messages", label="test")
    assert chatbot.type == "messages"
```

---

### P2-2 · Ingest 进度 404 提示缺指导

**位置**：Task 12 GREEN 段 L573-576

**问题**：
- `test_poll_handles_404_gracefully` 断言抛 `NotFound` 且"给用户明确提示"
- 但提示内容没定义——用户只知道"找不到"，不知道怎么办
- good UX：告知 job_id + 可能原因 + 操作建议

**修改**（errors.py NotFound 加 context）：

```python
class NotFound(Exception):
    """404 — 静默，不暴露存在性。"""
    def __init__(self, detail="未找到", resource_type=None, resource_id=None):
        self.detail = detail
        self.resource_type = resource_type
        self.resource_id = resource_id
    
    def user_message(self):
        if self.resource_type == "ingest_job":
            return f"⚠️ 任务 {self.resource_id} 未找到，可能已过期或被清理"
        return self.detail
```

---

### P2-3 · Mobile responsive 缺

**位置**：M9 plan 全篇

**问题**：
- Gradio 5.0 默认移动端支持较差（宽屏优先）
- 4 tab 的 layout 在手机屏幕（<768px）上会挤变形
- Gradio 支持 CSS media query 和 `responsive=True` 参数

**修改**（CUSTOM_CSS 补 mobile query）：

```css
/* Mobile responsive */
@media (max-width: 768px) {
    .chat-message { font-size: 14px; }
    .source-card pre { font-size: 12px; }
    .gr-gallery { --gr-gallery-columns: 1; }
}
```

---

### P2-4 · Plan 部分引用编号偏移

**位置**：L547-548

**问题**：
- `RED · tests/unit/test_ui_message_parser.py::test_poll_progress_updates_status（放错文件了，挪到 progress.py 测试）`
- 注释说"放错文件了"但 plan 没有修正——文本内引用 `test_ui_message_parser` 但实际应该 `test_ui_progress`
- 实施了人在写 `test_ui_message_parser.py` 时找不到这个测试

**修改**：Task 12 RED 两步改为：
1. `tests/unit/test_ui_message_parser.py` 行删掉
2. 只留 `tests/unit/test_ui_progress.py::test_poll_returns_completed`

---

### P2-5 · 缺 `test_poll_uses_gr_progress_tqdm` 的测试如何 mock gr.Progress 的具体实现

**位置**：Task 12 RED L568-570

**问题**：
- RED 说用 `gr.Progress(track_tqdm=True)` 包装 → 调 poll → 断言 tqdm-style 更新触发
- 但在单元测试中，`gr.Progress` 是 Gradio UI 对象——没法直接 mock
- 实际可行的做法：mock `gr.Progress.__call__` 或传一个 mock callable

**修改**（Task 12 RED 测试补 mock 方法说明）：

```python
# 实际测试写法：
def test_poll_uses_gr_progress_tqdm():
    mock_progress = MagicMock(spec=gr.Progress)
    progress_comp = IngestProgress(mock_client, "job_123", mock_progress)
    
    # 执行 poll（mock 网络）
    data = await progress_comp.poll_until_done(interval=0.01, max_wait=1.0)
    
    # 断言 gr.Progress 被调用来更新进度
    mock_progress.assert_called()
    call_args = mock_progress.call_args
    assert call_args[0][0] >= 0.0  # progress value
```

---

### P2-6 · test_tabs_do_not_share_state_across_switches 的 mock 实现不完整

**位置**：Task 14 RED L656-658

**问题**：
- RED 说"模拟用户在 login tab 输入用户名 → 切到 chat tab → 断言 chat tab 的 State 没拿到 login 用户名"
- 但 `gr.BrowserState` 是浏览器 localStorage ——单元测试无法模拟跨 tab 的 BrowserState 隔离
- GradioTestClient 也不支持模拟用户点击不同 tab

**修改**：改为 mock 测试 `AuthState` vs `gr.State` 的隔离逻辑：

```python
def test_auth_state_not_leaked_to_session_state():
    auth = gr.BrowserState(default_value={}, storage_key="rag_auth")
    session = gr.State(value=None)
    # 模拟 login 后 auth 被设
    auth.value = {"token": "xxx", "user_id": "1", "username": "test"}
    # 断言 session 不受影响
    assert session.value is None  # session 是组件级 State
```

---

### P2-7 · 缺 Gradio 启动后浏览器自动打开抑制

**位置**：Task 14 GREEN 段 L649-651

**问题**：
- `demo.launch(server_name=settings.ui.gradio_server_name, server_port=settings.ui.gradio_server_port)`
- Gradio 默认 `inbrowser=True`——在 docker 容器内会尝试打开浏览器（报错不影响但日志脏）
- Docker 容器内没有浏览器，`webbrowser.open` 会抛 `FileNotFoundError`

**修改**（launch_ui 加 `inbrowser=False`）：

```python
def launch_ui():
    demo = build_ui()
    demo.launch(
        server_name=settings.ui.gradio_server_name,
        server_port=settings.ui.gradio_server_port,
        inbrowser=False,           # Docker 内禁止开浏览器
        share=False,               # V1 不开公网链接
        allowed_paths=["/data"],   # 允许 M8 /file 端点路径
    )
```

---

### P2-8 · `_handle_chat` 返回 5 个值但调用方配置只有 5 个 output——维护成本高

**位置**：Task 11 L513-516

**问题**：
- `[chatbot, gr.Column(), gr.Gallery(), gr.Markdown(), query]`——5 个 output 组件
- handler 返回 5 个 `gr.update()`/string——顺序一旦错，UI 错乱
- 任何组件增减都要同步改 3 处（调用方 outputs、handler 签名、handler return）

**修改**（Task 11 REFACTOR 段提前落实——用 dataclass 打包）：

```python
@dataclass
class ChatResult:
    chatbot: gr.Chatbot
    source_column: gr.Column
    image_gallery: gr.Gallery
    trace_link: gr.Markdown
    query: gr.Textbox

# handler 内
return ChatResult(
    chatbot=[...],
    source_column=gr.update(...),
    image_gallery=gr.update(...),
    trace_link=gr.update(...),
    query="",
)
```

虽然 Gradio 不支持 dataclass 返回值，但可以作为 python `dict` 或 `list` 的中间表示——或在 `gr.Blocks.load` 回调中用 JS 处理。

---

## 交叉验证总结

### M7→M9 依赖链

| 项 | M7 review | M9 依赖 | 状态 |
|----|-----------|---------|------|
| answer_chitchat_node 缺实现 | M7 P0-6 | M9 chat 端点的 chitchat 路径不可用 | ⚠️ 依赖表未标注（见 §8-3） |
| graph 超时保护缺 | M7 P0-4 | M9 chat handler 30s timeout 后 `NetworkError` 未捕获（见 §8-2） | ❌ P1-10 补异常捕获 |
| checkpointer API 兼容 | M7 P0-2/P0-3 | M9 不直接依赖 checkpointer | ✅ 通过 |
| 节点级异常传播 | M7 P0-8 | M9 chat 端点收到 500 → `UpstreamError` | ✅ 已分类 |

### M8→M9 依赖链

| 项 | M8 review | M9 依赖 | 状态 |
|----|-----------|---------|------|
| CORS 中间件配置 | M8 P2-3 | M9 跨域请求依赖 M8 CORS header | ❌ **P0-1** 缺验证测试 |
| chat 超时保护 | M8 P0-1 | M9 chat 端点的 httpx 30s timeout | ⚠️ P1-10 补异常处理 |
| /file 端点 stub | 未实现 | M9 image thumbnail 依赖 | ❌ **P0-3** image fallback 缺 |
| 路由鉴权完整 | M8 P1-11 | M9 全走 Bearer token | ✅ 通过 |

### M3→M9 依赖链

| 项 | M3 review | M9 依赖 | 状态 |
|----|-----------|---------|------|
| pytest-httpx 依赖 | M3 P1-18 | M9 单元测试 mock httpx | ✅ 假设 M3 已修 |
| gradio>=5.0,<6 依赖 | 无 | M9 核心依赖 | ✅ pyproject 列明 |

---

## 新发现问题汇总

| ID | 级别 | 区域 | 问题 | 位置 |
|----|------|------|------|------|
| P0-1 | P0 | CORS | M8→M9 CORS 跨域验证缺集成测试 | DoD L713-726 |
| P0-2 | P0 | Docker | gradio service 缺 healthcheck，E2E race | Task 15 L663-677 |
| P0-3 | P0 | Image | image thumbnail 加载失败缺 fallback，M8 /file 端点可能不存在 | Task 10 L486-494 |
| P1-1 | P1 | Chat | 等待响应时缺 loading 状态 | Task 11 L508-534 |
| P1-2 | P1 | Error | 错误提示用 gr.Markdown 而非 gr.Error() toast | Task 6/11/13 |
| P1-3 | P1 | Chat | 新消息后缺 auto-scroll | Task 11 L511 |
| P1-4 | P1 | Chat | 缺 Enter 发送/Shift+Enter 换行 keyboard shortcut | Task 11 L512 |
| P1-5 | P1 | Ingest | file upload 缺前端文件大小检查（>50MB） | Task 13 L589-591 |
| P1-6 | P1 | Ingest | URL ingest 前端验证缺（格式/长度/空） | Task 13 L594-599 |
| P1-7 | P1 | Login | logout 后不跳转 login tab | Task 6 login.py |
| P1-8 | P1 | Error | 多次 401 后 session 过期检查缺 | Task 5 errors.py |
| P1-9 | P1 | Session | session 删除缺确认弹窗 | Task 7 L393-395 |
| P1-10 | P1 | Chat | M8 超时/502 的 UpstreamError 在 chat handler 未捕获 | Task 11 L524 |
| P1-11 | P1 | Config | cors_origin 硬编码 7860，不随 port 联动 | Task 1 L202 |
| P2-1 | P2 | Chat | gr.Chatbot(type="messages") 版本兼容性未验证 | Tech Stack L131 |
| P2-2 | P2 | Ingest | 进度 404 提示缺操作指导 | Task 12 L573-576 |
| P2-3 | P2 | CSS | 移动端响应式缺 | plan 全篇 |
| P2-4 | P2 | Plan | 引用编号偏移（test_ui_message_parser→test_ui_progress） | L547-548 |
| P2-5 | P2 | Test | gr.Progress mock 实现方法未说明 | Task 12 L568-570 |
| P2-6 | P2 | Test | test_tabs_do_not_share_state mock 无法在 GradioTestClient 实现 | Task 14 L656-658 |
| P2-7 | P2 | Docker | lauch() 缺 inbrowser=False（容器内报错） | Task 14 L649-651 |
| P2-8 | P2 | Refactor | _handle_chat 返回 5 个值硬编码，维护成本高 | Task 11 L513-516 |

---

## 落地建议

### 实施顺序

按 P0 → P1 → P2 优先修完，然后按 Day 1-5 顺序实施：

1. **动手前必改**：P0-1（CORS 集成测试）+ P0-2（gradio healthcheck）+ P0-3（image fallback）
2. **Day 1-2 基础设施阶段随改**：P1-11（cors_origin 联动）+ P2-7（inbrowser=False）
3. **Day 3 chat tab 阶段**：P1-1（loading）+ P1-3（auto-scroll）+ P1-4（keyboard shortcut）+ 迁移 gr.Markdown error→gr.Error toast（P1-2）
4. **Day 4 ingest tab 阶段**：P1-5（file size check）+ P1-6（URL validation）
5. **Day 5 装配阶段**：P1-7（logout redirect）+ P1-9（confirm dialog）+ P1-8（401 tracking）
6. **Day 5 E2E 阶段**：P0-1（CORS test）
7. **剩余 P2** 作为优化任务放在 5 个工作日之后的 polish session

### 风险提醒

- **M8 CORS 中间件顺序问题（M8 P2-3）**是最致命的——如果 M8 没修，M9 做再多也没用。M9 开写前应确认 M8 merge 后 `curl -X OPTIONS -H "Origin: http://localhost:7860" http://localhost:8000/api/health` 返回正确的 header
- **M7 answer_chitchat_node 缺实现（M7 P0-6）**——M9 的 chat tab 能工作（即使 chitchat 路径请求会 500），但用户体验差。建议在 M9 chat tab 的 handler 里加 try/except 兜底，或 M9 实施前确认 M7 已修
- **M8 /file 端点**——如果 M8 或 M12 不实现，M9 的 image thumbnail 功能需要降级到只支持 data URL（M7 graph 返回的 image_ref 格式相关）

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M9-review-r0 | 2026-06-11 | 初稿（基线 V1 Scope §4.1 + 决策 #7/#16） |
