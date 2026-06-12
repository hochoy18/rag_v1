# M9 Plan · Gradio Web UI（4 tab：login / sessions / chat / ingest）

> 所属：RAG V1 M0–M12 实施路线 · 第 9 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §4 API 列表](../specs/2026-06-10-rag-v1-scope.md#4-api-列表) · [§4.1 UI 4 tab](../specs/2026-06-10-rag-v1-scope.md#4-UI) · [决策 #7 FastAPI+Gradio](../specs/2026-06-10-rag-v1-scope.md#0-决策总表) · [决策 #16 多模态 V1 仅元数据](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 上游：[M2 auth 鉴权](./2026-06-10-rag-m2-auth.md) · [M7 LangGraph 7 节点](./2026-06-10-rag-m7-graph.md) · [M8 FastAPI 路由层](./2026-06-11-rag-m8-api-chat.md)
> 下游：M10 Langfuse（前端 X-Request-Id 透传，UI 显示 trace_id 链接）· M11 RAGAS（不直接调 M9）· M12 Hardening（CORS 已在 M8 配）
> 避雷基线：[P0/P1 review 报告](./2026-06-11-rag-plans-review.md)（P0-1 端口 7860 不冲突 / P1-4 ORM updated_at / P1-6 复合索引 / P1-11 鉴权完整 / P2-7 session 统一导入 / X-3 全局 settings / X-2 pytest rootdir）
> 估时：**5 个工作日**（RAG V1 最大里程碑）
> 范本目的：把 M8 JSON API 包成用户可用的 Web UI——4 tab 拆模块、TDD 红绿、避免 Gradio 5.0+ 渲染陷阱

---

## Goal

把 v0.4 V1 Scope §4.1 UI 4 tab 落成 Gradio Web 应用：

1. **`app/ui/gradio_app.py` 入口**：`gr.Blocks(theme=build_theme(), css=CUSTOM_CSS)` 装配 4 个 `gr.Tab`
2. **`app/ui/theme.py` 暗色主题**：背景 `#0d1117` + 强调色 `#58a6ff` + 字体 `PingFang SC, Microsoft YaHei` + `gr.themes.Monochrome()` 基底
3. **`app/ui/api_client.py` HTTP 客户端**：httpx `AsyncClient` 封装 M8 全部端点
4. **`app/ui/auth_state.py` 鉴权状态**：`gr.BrowserState` 持久化 token + user_id，刷新不丢
5. **4 tab 独立模块**：每 tab 一个 `.py`，导出 `build_tab()` 工厂
6. **Source 引用渲染**：`[1][2][3]` regex 解析 → `gr.Accordion` 折叠卡
7. **Image 缩略图**：M7 返回 `image_ref` → `gr.Image`（路径 + Gradio `/file=` + try/except fallback）
8. **Ingest 进度**：`GET /api/ingest/{job_id}` 轮询（`asyncio` + `gr.Progress(track_tqdm=True)`）+ 404 显式提示
9. **错误处理**：401 跳登录 · 404 静默 · 422 表单红框 · 502/503 fallback_message 渲染 · 连续 401 计数 → 跳登录 · `raise gr.Error` toast（非阻塞）
10. **E2E 测试**：登录 → ingest sample → chat 多轮 thread 复用 + CORS 跨域集成测试

**不包含**（其他 M 负责）：M8 路由实现 · M10 Langfuse 业务 trace（M9 仅透传 `X-Request-Id`）· M12 限速 / 监控（CORS / 限速挂 M8）

---

## Architecture

### 仓库布局（M9 增量）

```
apps/rag_v1/
├── app/
│   ├── ui/                                  # M9 主力
│   │   ├── __init__.py                      # 暴露 build_ui() / launch_ui()
│   │   ├── gradio_app.py                    # gr.Blocks 入口 + 4 tab 装配 + launch_ui 4 参数
│   │   ├── api_client.py                    # APIClient(httpx.AsyncClient) 封装 M8 端点 + 401 计数
│   │   ├── auth_state.py                    # AuthState(token / user_id) + gr.BrowserState 绑定
│   │   ├── theme.py                         # 暗色 #0d1117 + #58a6ff + 中文字体 CSS + @media mobile
│   │   ├── errors.py                        # 前端错误分类（401 跳登录 / 422 显式 / 502 显式 / 404 静默） + 401 计数
│   │   ├── tabs/
│   │   │   ├── __init__.py
│   │   │   ├── login.py                     # 注册/登录/登出 tab（含 logout redirect）
│   │   │   ├── sessions.py                  # 列表/新建/删除/切换 tab（含 confirm 模态）
│   │   │   ├── chat.py                      # 对话 tab（核心，含 ChatResult dataclass + loading + autoscroll）
│   │   │   └── ingest.py                    # 文档入库 tab（3 源：file / URL / Confluence，含 50MB 限制 + URL regex 验证）
│   │   └── components/
│   │       ├── __init__.py
│   │       ├── message.py                   # 消息气泡（[1][2][3] 引用解析）
│   │       ├── source_card.py               # gr.Accordion 折叠卡（含 overflow-wrap: anywhere CSS）
│   │       ├── image_thumb.py                # gr.Image 缩略图（path → /file= + try/except fallback）
│   │       └── progress.py                  # ingest 进度条包装（mock gr.Progress）
│   ├── api/                                 # M8 已建 · M9 调
│   ├── auth/                                # M2 已建
│   ├── config.py                            # 追加 UISettings（api_base_url / theme 配色 / cors_origin @property 联动）
│   └── main.py                              # M8 已建 · FastAPI
│
└── tests/
    ├── unit/
    │   ├── test_ui_api_client.py            # httpx 调 M8 端点（mock）
    │   ├── test_ui_auth_state.py            # BrowserState 持久化
    │   ├── test_ui_theme.py                 # 暗色 + 中文字体 CSS（含 mobile media query）
    │   ├── test_ui_errors.py                # 401/404/422/502 分类（含 401 计数）
    │   ├── test_ui_message_parser.py        # [1][2][3] regex 解析（6+ case）
    │   ├── test_ui_source_card.py           # gr.Accordion 数据构造（含 overflow-wrap CSS）
    │   ├── test_ui_image_thumb.py           # image_ref 路径转 /file= URL + try/except fallback
    │   └── test_ui_tabs.py                  # 4 tab 工厂 + 切换不串扰
    ├── integration/
    │   ├── conftest.py                      # pg_session fixture（修 P0-5）
    │   ├── test_m9_gradio_e2e.py            # 端到端：login → ingest sample → chat 多轮
    │   └── test_gradio_can_call_fastapi_chat.py  # CORS 跨域集成测试（r1-P0-1）
    └── ui/                                  # Gradio 端到端（用 httpx + asyncio 调真实 M8）
        ├── test_m9_blocks_render.py         # 4 tab render 不报错
        └── test_chatbot_messages_format_renders.py  # 5.0+ 兼容性测试（r1-P2-1）
```

### M9 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M10 Langfuse trace | `X-Request-Id` 透传到 M8 | M9 UI 拿 trace_id 渲链接到 `LANGFUSE_HOST/trace/{id}` |
| M11 RAGAS eval | **不走** M9 | M11 直接调 `graph.ainvoke()` |
| M12 Hardening | 改 `app/ui/api_client.py` 加限速客户端 | 不动 M9 结构 |

### Langfuse 链路字段命名规范（r2 必改 · 与 M8 r2 新-1 同步）

> **关键决策**：`trace_id == request_id == X-Request-Id == Langfuse trace.id` 四名同串同值——M8 r2 已统一 M8 `ChatResponse.trace_id` 字段，M9 plan 全部同步。

| 层级 | 名称 | 含义 | 来源 |
|------|------|------|------|
| HTTP Header 协议级 | `X-Request-Id` | M8 RequestIdMiddleware 注入/透传的请求 ID（uuid4） | M8 plan |
| M8 ChatResponse 字段 | `trace_id: str` | 与 header 同值，响应 JSON 字段名 | M8 plan（r2 已统一） |
| M9 Gradio 渲染 | `trace_id` | UI 拿此值拼 Langfuse 链接（与 M8 字段同） | M9 plan |
| M10 Langfuse trace.id | Langfuse 内部 trace ID | 与 `trace_id` 同一字符串值 | M10 plan |
| M11 RAGAS eval | `trace_id` | 用 `get_client().get_current_trace_id()` | M11 plan |

**明确规则**（M9 → M8 → M10 链路）：

```
客户端 Gradio
  ↓ POST /api/chat header: X-Request-Id: <uuid>
M8 RequestIdMiddleware 注入（保留或新生成）
  ↓ LangChain ChatOpenAI 透传 headers={"X-Request-Id": ...}
M10 LangfuseCallbackHandler 接收 → trace.id = X-Request-Id 值
  ↓ M8 ChatResponse {"trace_id": <uuid>, ...}  # 与 header 同值
M9 UI response['trace_id'] → f"🔗 [trace]({LANGFUSE_HOST}/trace/{trace_id})"
```

**修订历史**：M8 r1 用 `request_id`，M8 r2 已统一 `trace_id`（修新-1）。M9 r1 主体混用 `request_id`/`trace_id`，r2 全部统一为 `trace_id`。

### 4 tab 内部结构

```
gr.Blocks(theme=build_theme(), css=CUSTOM_CSS)
├── Tab 1: login     → gr.Markdown + gr.Tabs(登录/注册) + gr.Button + logout button
├── Tab 2: sessions  → gr.Dataframe + gr.Button(刷新/新建/删除/切换) + confirm modal + gr.State(session_id)
├── Tab 3: chat      → gr.Chatbot(type="messages", autoscroll=True) + gr.Textbox(submit_btn=True) + gr.Accordion(sources) + gr.Gallery(images, on_error=...) + trace link
└── Tab 4: ingest    → gr.Tabs(文件上传 / URL+4auth / Confluence) + gr.Progress(track_tqdm=True) + file size 50MB guard
```

### 关键数据流（POST /api/chat 透传 · trace_id 统一）

```python
user input → Chat submit handler
  → APIClient.post_chat(query, session_id, bearer_token)
  → POST {api_base}/api/chat  header: Bearer + X-Request-Id(uuid4)
  ← 200 { answer, sources, image_refs, session_id, trace_id }  # r2 统一 trace_id
  → parse [1][2][3] from answer (regex)
  → render gr.Chatbot + gr.Accordion(sources) + gr.Gallery(image_refs, on_error=...)
  → display X-Request-Id as "🔗 trace" link to Langfuse using response['trace_id']
```

---

## Tech Stack

| 层 | 选型 | 版本（精确） | 来源 |
|----|------|------------|------|
| Web UI 框架 | `gradio` | `>=5.0,<6` | V1 Scope §4.1 决策 #7 |
| 异步 HTTP 客户端 | `httpx` | `>=0.27,<1` | M3 沿用 |
| 状态持久化 | `gr.BrowserState` | 5.0+ 内置 | Gradio 5.0 新 API |
| 字体 | `PingFang SC, Microsoft YaHei` | 系统字体 | V1 Scope §4.1 暗色主题 |
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` | 见 §测试 | 沿用 M3 |
| Gradio E2E | `gradio.testing` | 5.0+ 内置 | 5.0 新模块 |

**关键导入路径**：

```python
import gradio as gr
from gradio.themes import Monochrome
state = gr.BrowserState(default_value={}, storage_key="rag_auth")  # 5.0+ 新 API
import httpx
from gradio.testing import GradioTestClient  # 5.0+ 测试
```

---

## Files

**新建**（19 个源文件 + 11 个测试文件）：

| 路径（相对 `apps/rag_v1/`） | 作用 | r1/r2 状态 |
|------|------|----------|
| `app/ui/__init__.py` | 暴露 `build_ui()` / `launch_ui()` | r0 |
| `app/ui/gradio_app.py` | `gr.Blocks` 入口 + 4 tab 装配 + `launch()`（**r1-P2-7：4 参数 launch**） | r0 + r2 回填 |
| `app/ui/api_client.py` | `APIClient(httpx.AsyncClient)` 封装 M8 全部端点（**r1-P1-8：401 计数**） | r0 + r2 回填 |
| `app/ui/auth_state.py` | `AuthState` dataclass + `gr.BrowserState` 绑定 | r0 |
| `app/ui/theme.py` | `build_theme()` + `CUSTOM_CSS`（**r1-P1-10：overflow-wrap: anywhere** + **r1-P2-3：@media mobile**） | r0 + r2 回填 |
| `app/ui/errors.py` | `UIError` 分类（401/404/422/502）+ 渲染策略（**r1-P1-8：401 计数**） | r0 + r2 回填 |
| `app/ui/tabs/__init__.py` | 暴露 4 个 `build_tab()` | r0 |
| `app/ui/tabs/login.py` | 登录/注册/登出 tab（**r1-P1-7：logout 跳 login**） | r0 + r2 回填 |
| `app/ui/tabs/sessions.py` | 列表/新建/删除/切换 tab（**r1-P1-9：confirm modal**） | r0 + r2 回填 |
| `app/ui/tabs/chat.py` | 对话 tab（核心）（**r1-P1-1 loading** + **r1-P1-3 autoscroll** + **r1-P1-4 keyboard** + **r1-P2-8 ChatResult dataclass**） | r0 + r2 回填 |
| `app/ui/tabs/ingest.py` | 文件/URL/Confluence 三子 tab（**r1-P1-5 50MB 限制** + **r1-P1-6 URL regex 验证**） | r0 + r2 回填 |
| `app/ui/components/__init__.py` | 组件暴露 | r0 |
| `app/ui/components/message.py` | `parse_citations(answer)` regex 解析 + `build_message()` | r0 |
| `app/ui/components/source_card.py` | `build_source_accordions(sources)`（**r1-P1-10：overflow-wrap: anywhere**） | r0 + r2 回填 |
| `app/ui/components/image_thumb.py` | `image_ref_to_url(ref)` → Gradio `/file=`（**r1-P0-3：try/except fallback**） | r0 + r2 回填 |
| `app/ui/components/progress.py` | `IngestProgress` 轮询 + `gr.Progress`（**r1-P2-2：404 Warning** + **r1-P2-5：mock track_tqdm**） | r0 + r2 回填 |
| `tests/unit/test_ui_api_client.py` | httpx 调 M8 端点（mock） | r0 |
| `tests/unit/test_ui_auth_state.py` | BrowserState 持久化 | r0 |
| `tests/unit/test_ui_theme.py` | 暗色 + 中文字体 CSS（含 **r1-P2-3 mobile media query**） | r0 + r2 回填 |
| `tests/unit/test_ui_errors.py` | 401/404/422/502 分类（**r1-P1-8：401 计数**） | r0 + r2 回填 |
| `tests/unit/test_ui_message_parser.py` | [1][2][3] regex 解析（6+ case） | r0 |
| `tests/unit/test_ui_source_card.py` | gr.Accordion 数据构造（含 **r1-P1-10 overflow-wrap**） | r0 + r2 回填 |
| `tests/unit/test_ui_image_thumb.py` | image_ref 路径转 /file= URL + **r1-P0-3 fallback** | r0 + r2 回填 |
| `tests/unit/test_ui_tabs.py` | 4 tab 工厂 + 切换不串扰（**r1-P2-6：test_auth_state_not_leaked_to_session_state**） | r0 + r2 回填 |
| `tests/integration/conftest.py` | `pg_session` fixture（修 P0-5 真 PG） | r0 |
| `tests/integration/test_m9_gradio_e2e.py` | 端到端：login → ingest sample → chat 多轮 | r0 |
| `tests/integration/test_gradio_can_call_fastapi_chat.py` | **r1-P0-1：mock M8 CORSMiddleware 验证 Access-Control-Allow-Origin** | r2 新增 |
| `tests/ui/test_m9_blocks_render.py` | 4 tab render 不报错 | r0 |
| `tests/ui/test_chatbot_messages_format_renders.py` | **r1-P2-1：gr.Chatbot(type="messages") 5.0+ 兼容性** | r2 新增 |

**修改**：
- `pyproject.toml`：追加 `gradio>=5.0,<6` 直接依赖
- `app/config.py`（M0+M1+M2+M3+M7+M8 累计）：追加 `UISettings`（`api_base_url` / `theme_bg` / `theme_accent` / `font_family` / `cors_origin`（**r1-P1-11：@property 联动 gradio_server_port**）/ `gradio_server_name` / `gradio_server_port`）
- `infra/docker-compose.yml`（M0 已建）：追加 `gradio` service（**r1-P0-2：healthcheck + depends_on fastapi: condition: service_healthy**）
- `.env.example`：追加 `GRADIO_SERVER_NAME=0.0.0.0` / `GRADIO_SERVER_PORT=7860` / `API_BASE_URL=http://api:8000`

**不修改**：
- `app/api/`（M8 已建，M9 不动路由）
- `app/graph/`（M7 已建）
- `app/db/`（M1 已建，M9 不直接查 DB，全走 M8）

---

## Tasks（2-5 分钟/step 粒度）

### Day 1 · theme + api_client + auth_state（基础设施）

#### Task 1：UISettings 配置块（含 r1-P1-11 cors_origin 联动）

**RED** · `tests/unit/test_ui_theme.py::test_ui_settings_loads`
- 写测试：mock env `API_BASE_URL=http://api:8000` → 加载 `Settings().ui` → 断言 `api_base_url == "http://api:8000"`
- 跑测试 → 失败
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_ui_theme.py::test_ui_settings_loads`

**GREEN** · 改 `app/config.py`：
```python
class UISettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    theme_bg: str = "#0d1117"
    theme_accent: str = "#58a6ff"
    font_family: str = "PingFang SC, Microsoft YaHei, sans-serif"
    gradio_server_name: str = "0.0.0.0"
    gradio_server_port: int = 7860

    # r1-P1-11 已修：cors_origin 联动 gradio_server_port（避免端口漂移时 CORS 失配）
    @property
    def cors_origin(self) -> str:
        """CORS origin 跟随 gradio_server_port 自动联动，默认 http://localhost:7860。
        env 覆盖：CORS_ORIGIN=http://staging.example.com:7860"""
        env_override = os.getenv("CORS_ORIGIN")
        if env_override:
            return env_override
        return f"http://localhost:{self.gradio_server_port}"
```

**REFACTOR** · 把 `Settings` 拆 `app/configs/` 子文件（修 X-1，但 M9 不动，留给 M10）

#### Task 2：暗色主题 + 中文字体 CSS（含 r1-P1-10 overflow-wrap + r1-P2-3 mobile media query）

**RED** · `tests/unit/test_ui_theme.py::test_theme_bg_is_dark`
- 调 `build_theme()` → 断言返回 `gr.Theme` 实例 → 序列化变量后含 `0d1117`
- 跑测试 → 失败

**GREEN** · `app/ui/theme.py`：
```python
import gradio as gr

def build_theme() -> gr.Theme:
    base = gr.themes.Monochrome(
        primary_hue=gr.themes.Color("#58a6ff", "#58a6ff"),
        neutral_hue=gr.themes.Color("#0d1117", "#0d1117"),
    )
    return base.set(
        body_background_fill="#0d1117",
        block_background_fill="#161b22",
        button_primary_background_fill="#58a6ff",
        font=["PingFang SC", "Microsoft YaHei", "sans-serif"],
    )

# r1-P1-10 已修：中文 source 卡溢出防护三件套
# r1-P2-3 已修：mobile responsive 媒体查询
CUSTOM_CSS = """
body { background: #0d1117; color: #c9d1d9; }
.chat-message { word-wrap: break-word; max-width: 100%; }
.source-card pre { white-space: pre-wrap; word-wrap: break-word; overflow-wrap: anywhere; }
.tab-nav { flex-wrap: wrap; }

/* r1-P2-3 · mobile responsive：折叠 tab 为汉堡菜单 */
@media (max-width: 640px) {
    .gradio-container { padding: 0 !important; }
    .tab-nav { display: none; }
    .mobile-menu-toggle { display: block; }
    .chat-message { font-size: 14px; }
    .source-card pre { font-size: 12px; }
}
"""
```

**RED** · `test_font_family_includes_chinese`
- 断言 `build_theme().font[0] in ("PingFang SC", "Microsoft YaHei")`

**GREEN** · 已有

**RED** · `test_custom_css_has_overflow_wrap_anywhere`（**r1-P1-10**）
- 断言 `CUSTOM_CSS` 含 `overflow-wrap: anywhere`

**RED** · `test_custom_css_has_mobile_media_query`（**r1-P2-3**）
- 断言 `CUSTOM_CSS` 含 `@media (max-width: 640px)`

#### Task 3：API 客户端骨架（含 r1-P1-8 401 计数）

**RED** · `tests/unit/test_ui_api_client.py::test_api_client_health`
- mock httpx `GET /api/health` 返 200 → 调 `APIClient().health()` → 断言 `status == "ok"`
- 跑测试 → 失败

**GREEN** · `app/ui/api_client.py`（骨架，10 个端点）：
```python
class APIClient:
    def __init__(self, base_url=None, token=None):
        self._base = base_url or settings.ui.api_base_url
        self._token = token
        self._client = httpx.AsyncClient(base_url=self._base, timeout=30.0)
        self._consecutive_401 = 0  # r1-P1-8：连续 401 计数

    def set_token(self, token): self._token = token

    def _headers(self):
        h = {"X-Request-Id": str(uuid.uuid4())}
        if self._token: h["Authorization"] = f"Bearer {self._token}"
        return h

    def _record_401(self):
        """r1-P1-8：连续 3 次 401 → gr.Info 提示 + 跳 login tab"""
        self._consecutive_401 += 1
        if self._consecutive_401 >= 3:
            raise gr.Info("Session expired, please re-login")

    def _reset_401(self):
        """成功请求重置计数"""
        self._consecutive_401 = 0

    # 10 个方法：health / login / register / logout / list_sessions /
    #   create_session / delete_session / post_chat / post_ingest / get_ingest_progress
    # 内部统一 _request() → classify_response() → 业务返回 dict
    # post_chat 返回的 trace_id 字段（M8 r2 已统一）作为 Langfuse 链接锚点
```

**RED** · `test_api_client_includes_bearer_when_token_set`
- `APIClient(token="xxx").post_chat(...)` → mock httpx → 断言 header `Authorization == "Bearer xxx"`

**GREEN** · 已有 `_headers()` 逻辑

**RED** · `test_api_client_counts_consecutive_401`（**r1-P1-8**）
- mock 3 次连续 401 → 调 `post_chat` 3 次 → 断言第 3 次抛 `gr.Info` + `_consecutive_401` 重置

**GREEN** · `_record_401` / `_reset_401` 逻辑

**REFACTOR** · 抽 `_request(method, path, **kw)` 统一重试 + 异常转换

#### Task 4：AuthState + gr.BrowserState 持久化

**RED** · `tests/unit/test_ui_auth_state.py::test_auth_state_persists_token`
- 写测试：`AuthState(token="t", user_id="u")` → 调 `.to_dict()` → 断言字段齐
- 跑测试 → 失败

**GREEN** · `app/ui/auth_state.py`：
```python
@dataclass
class AuthState:
    token: str | None = None
    user_id: str | None = None
    username: str | None = None

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, d): return cls(**(d or {}))
    @property
    def is_authenticated(self): return bool(self.token and self.user_id)
```

绑定：`gr.BrowserState(default_value={}, storage_key="rag_auth")`（5.0+ 新 API，刷新页面不丢）。

**RED** · `test_browser_state_binds_to_auth_state`
- 构造 `gr.BrowserState(default_value={}, storage_key="rag_auth")` → 断言类型是 `BrowserState`
- 跑测试 → 失败

**GREEN** · 文档化用法：

```python
# gradio_app.py 装配时
auth = gr.BrowserState(default_value={}, storage_key="rag_auth")
# handler 里：auth.value → dict；auth.value = AuthState(...).to_dict()
```

#### Task 5：前端错误分类（含 r1-P1-8 401 计数）

**RED** · `tests/unit/test_ui_errors.py::test_401_triggers_auth_expired`
- mock 401 response → 调 `APIClient._raise_for_status(resp)` → 断言抛 `AuthExpired`
- 跑测试 → 失败

**GREEN** · `app/ui/errors.py`：
```python
import gradio as gr

class AuthExpired(Exception): ...        # 401 → 跳登录
class NotFound(Exception): ...            # 404 → 静默
class ValidationError(Exception): ...     # 422 → 表单红框
class UpstreamError(Exception): ...       # 502/503 → 显式错误 + 渲染 GraphSettings.fallback_message
class NetworkError(Exception): ...        # 网络断

def classify_response(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise AuthExpired(resp.json().get("detail", "未登录"))
    if resp.status_code == 404:
        raise NotFound(resp.json().get("detail", "未找到"))
    if resp.status_code == 422:
        raise ValidationError(resp.json())
    if resp.status_code in (502, 503):
        # r1-P2-7/chat_tab：502/503 触发 GraphSettings.fallback_message（M7 chitchat fallback）
        raise UpstreamError(resp.json().get("detail", "上游服务异常"))
    resp.raise_for_status()

def render_error(exc: Exception) -> str:
    """r1-P1-2 已修：错误提示改用 Gradio 5.0+ gr.Error toast（非阻塞）"""
    if isinstance(exc, AuthExpired):
        raise gr.Error("Session expired, please re-login")
    if isinstance(exc, ValidationError):
        raise gr.Error(f"表单校验失败：{exc.args[0]}")
    if isinstance(exc, UpstreamError):
        raise gr.Error(f"上游异常：{exc.args[0]}")
    # NotFound 静默不渲染
```

**RED** · `test_404_raises_not_found_silently`
- mock 404 → 断言抛 `NotFound`（**不抛** `httpx.HTTPStatusError` 暴露存在性）

**GREEN** · 已有

### Day 2 · login + sessions tab（前置依赖 · 含 r1-P1-7 logout + r1-P1-9 confirm）

#### Task 6：login tab 工厂（含 r1-P1-7 logout redirect）

**RED** · `tests/unit/test_ui_tabs.py::test_login_tab_builds_without_error`
- 调 `build_login_tab()` → 断言返回 `gr.Tab` 实例或 `dict`（含 username/password/button + logout）
- 跑测试 → 失败

**GREEN** · `app/ui/tabs/login.py`：
```python
import gradio as gr

def build_login_tab(client, auth):
    with gr.Tab("登录") as tab:
        gr.Markdown("# RAG V1 登录")
        with gr.Tabs():
            with gr.Tab("登录"):
                u = gr.Textbox(label="用户名")
                p = gr.Textbox(label="密码", type="password")
                msg = gr.Markdown()
                login_btn = gr.Button("登录", variant="primary")
                login_btn.click(_handle_login, [u, p, auth], [msg, auth], api_name="login")
            with gr.Tab("注册"):
                u = gr.Textbox(label="用户名"); e = gr.Textbox(label="邮箱")
                p = gr.Textbox(label="密码", type="password"); rmsg = gr.Markdown()
                gr.Button("注册").click(_handle_register, [u, e, p], [rmsg, auth])

        # r1-P1-7 已修：logout button（已登录时显示）+ 跳 login tab
        logout_btn = gr.Button("登出", variant="stop", visible=False)
        logout_btn.click(_handle_logout, [auth], [msg, auth, logout_btn, gr.Tabs(selected=0)])
    return tab

async def _handle_login(username, password, auth_state_value):
    try:
        result = await client.login(username, password)
    except AuthExpired:
        # r1-P1-2 已修：gr.Error toast 替代 Markdown
        raise gr.Error("❌ 用户名或密码错误")
    new_auth = AuthState(token=result["token"], user_id=result["user_id"], username=username)
    return f"✅ 欢迎 {username}", new_auth.to_dict()

async def _handle_logout(auth_state_value):
    """r1-P1-7 已修：logout 调 M2 /api/auth/logout (返 204) + 清 BrowserState + 跳 login tab"""
    try:
        await client.logout()
    except Exception:
        pass  # 客户端 logout 失败也清前端 state
    return "", {}, gr.update(visible=False), gr.update(selected=0)
```

**RED** · `test_login_handler_updates_auth_state`
- mock APIClient.login → 调 handler → 断言返回的 auth_state 包含 token

**GREEN** · handler 内构造 new AuthState → `.to_dict()` 返回

**RED** · `test_logout_clears_auth_state`（**r1-P1-7**）
- mock 已登录 state → 调 `_handle_logout` → 断言返回 `({}, gr.update(visible=False), gr.update(selected=0))`

**GREEN** · `_handle_logout` 逻辑

#### Task 7：sessions tab 工厂（含 r1-P1-9 confirm modal）

**RED** · `tests/unit/test_ui_tabs.py::test_sessions_tab_lists_sessions`
- mock APIClient.list_sessions → 返 2 条 → 调 `build_sessions_tab` 渲染 → 断言 Dataframe 含 2 行 + confirm modal 存在
- 跑测试 → 失败

**GREEN** · `app/ui/tabs/sessions.py`：
```python
def build_sessions_tab(client, current_session):
    with gr.Tab("会话") as tab:
        df = gr.Dataframe(headers=["标题", "更新时间", "消息数"], interactive=False)
        refresh = gr.Button("刷新列表")
        new_btn = gr.Button("新建会话", variant="primary")
        del_btn = gr.Button("删除选中")
        switch_btn = gr.Button("切换到选中")

        # r1-P1-9 已修：confirm 删除模态
        with gr.Group(visible=False) as confirm_modal:
            gr.Markdown("⚠️ 确认删除该会话？此操作不可撤销。")
            confirm_yes = gr.Button("确认删除", variant="stop")
            confirm_no = gr.Button("取消")

        refresh.click(_refresh_list, None, df)
        new_btn.click(_create_new, None, [df, current_session])
        del_btn.click(lambda: gr.update(visible=True), None, confirm_modal)
        confirm_yes.click(_delete_selected, [df], [df, confirm_modal])
        confirm_no.click(lambda: gr.update(visible=False), None, confirm_modal)
        switch_btn.click(_switch, [df, current_session], current_session)
    return tab

async def _refresh_list():
    sessions = await client.list_sessions()  # 依赖 P1-6 复合索引
    return [[s["title"], s["updated_at"], s["message_count"]] for s in sessions]
```

**RED** · `test_sessions_list_uses_active_only`（依赖 P1-6 复合索引）
- mock DB → 用 M1 fixture 建 2 active + 1 inactive → 调 `client.list_sessions`（走真 M8）→ 断言返 2 条

**GREEN** · 已有（依赖 M8 + P1-6 索引）

**RED** · `test_delete_button_shows_confirm_modal`（**r1-P1-9**）
- 模拟点击删除按钮 → 断言 confirm_modal visible=True

**GREEN** · `del_btn.click(lambda: gr.update(visible=True), None, confirm_modal)`

### Day 3 · chat tab（核心，消息流 + source 渲染 · 含 r1-P1-1/2/3/4/10 + r1-P2-8）

#### Task 8：message 组件 + [1][2][3] regex 解析

**RED** · `tests/unit/test_ui_message_parser.py::test_parse_simple_citations`
- 输入 `"对比结果[1][2]如上"` → 调 `parse_citations()` → 断言 `(text, [1, 2])`
- 跑测试 → 失败

**GREEN** · `app/ui/components/message.py`：
```python
import re
from dataclasses import dataclass

CITATION_PATTERN = re.compile(r"\[(\d+)\]")

@dataclass
class ParsedMessage:
    text: str
    citations: list[int]

def parse_citations(answer: str) -> ParsedMessage:
    """提取 LLM answer 中的 [1][2][3] 引用标记。返回清洗后文本 + 引用 ID 列表（去重保序）。"""
    citations = [int(m.group(1)) for m in CITATION_PATTERN.finditer(answer)]
    # 去重保序
    seen = set()
    unique = []
    for c in citations:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    # 文本保留原始（UI 渲染时把 [1] 变成可点击链接）
    return ParsedMessage(text=answer, citations=unique)
```

**RED** · `test_parse_citations_handles_5_cases`（参数化）
- case 1: `"abc[1]"` → `[1]`
- case 2: `"[1][2][3]"` → `[1,2,3]`
- case 3: `"无引用"` → `[]`
- case 4: `"[1][1][2]"` → `[1,2]`（去重）
- case 5: `"末尾[42]"` → `[42]`
- case 6: `"嵌套[1abc2]"` → `[]`（regex 不匹配）
- 跑测试 → 失败（前面 5 个 case 通过，case 4 失败）

**GREEN** · 去重逻辑

#### Task 9：source_card 组件（含 r1-P1-10 overflow-wrap: anywhere）

**RED** · `tests/unit/test_ui_source_card.py::test_source_card_breaks_long_text`
- 输入 source text 超 200 字符 → 渲染 → 断言含 CSS class `word-wrap: break-word` + `overflow-wrap: anywhere`
- 跑测试 → 失败

**GREEN** · `app/ui/components/source_card.py`：
```python
import gradio as gr
from app.api.schemas.chat import Source

def build_source_accordions(sources: list[Source]) -> list[gr.Accordion]:
    accordions = []
    for i, src in enumerate(sources, start=1):
        # r1-P1-10 已修：中文长文本三件套 overflow
        with gr.Accordion(f"📄 来源 [{i}] {src.title or '未命名'}", open=False) as acc:
            gr.Markdown(f"<div class='source-card'>```\n{src.content}\n```</div>")
            if src.url:
                gr.Markdown(f"[原文链接]({src.url})")
        accordions.append(acc)
    return accordions
```

**RED** · `test_source_card_has_overflow_wrap_class`（**r1-P1-10**）
- 断言生成的 HTML 含 `class="source-card"`

**GREEN** · 已有

#### Task 10：image_thumb 组件（含 r1-P0-3 try/except fallback）

**RED** · `tests/unit/test_ui_image_thumb.py::test_image_ref_converts_to_file_url`
- 输入 `image_ref="/data/imgs/p1.png"` + `api_base="http://api:8000"` → 调 `image_ref_to_url` → 断言 `"http://api:8000/file=/data/imgs/p1.png"`（Gradio 5.0+ `/file=` 约定）
- 跑测试 → 失败

**GREEN** · `app/ui/components/image_thumb.py`：
```python
import gradio as gr
from app.config import settings

def image_ref_to_url(ref: str) -> str:
    """M7 retrieve 返回的 image_ref（容器内路径）→ Gradio 可访问的 /file= URL。
    M8 端点：GET /file/{path} 流式返文件（M12 加；M9 假设 M8 已有 /file 端点 stub）。
    """
    if ref.startswith("data:"):
        # P1-2 决策：路径优先，data URL 兜底
        return ref
    base = settings.ui.api_base_url.rstrip("/")
    return f"{base}/file={ref}"

def render_image_thumb(url: str) -> gr.Component:
    """r1-P0-3 已修：try/except 包裹 + on_error 钩子 + Markdown fallback"""
    try:
        return gr.Image(value=url, show_label=False, height=200)
    except Exception:
        # 缩略图加载失败：降级 Markdown 占位
        return gr.Markdown("📎 缩略图加载失败")
```

**RED** · `test_image_ref_handles_data_url`（P1-2 决策：路径优先，data URL 兜底）
- 输入 `image_ref="data:image/png;base64,..."` → 断言直接返回（不拼 URL）

**GREEN** · 识别 `data:` 前缀

**RED** · `test_render_image_thumb_falls_back_on_error`（**r1-P0-3**）
- 输入非法 URL → 调 `render_image_thumb` → 断言返回 `gr.Markdown` 组件（**不抛**异常）

**GREEN** · try/except 包裹

#### Task 11：chat tab 主体（含 r1-P1-1 loading + r1-P1-3 autoscroll + r1-P1-4 keyboard + r1-P2-8 ChatResult dataclass + r1-漂-2 trace_id 统一）

**RED** · `tests/unit/test_ui_tabs.py::test_chat_tab_posts_query_and_renders_sources`
- mock APIClient.post_chat → 返 `{answer: "[1][2]", sources: [...], image_refs: [...]}` → 模拟用户发 query → 断言 Chatbot 新增消息 + Source accordion 展开
- 跑测试 → 失败

**GREEN** · `app/ui/tabs/chat.py`：
```python
import gradio as gr
from dataclasses import dataclass

@dataclass  # r1-P2-8 已修：5 元返回值封装（gr.State 透传友好）
class ChatResult:
    chatbot_update: gr.update
    sources_update: gr.update
    gallery_update: gr.update
    trace_update: gr.update
    query_clear: str

def build_chat_tab(client, current_session, auth_state):
    with gr.Tab("对话") as tab:
        # r1-P1-3 已修：autoscroll=True 5.0+ 内置
        chatbot = gr.Chatbot(type="messages", label="对话", autoscroll=True)
        # r1-P1-4 已修：submit_btn=True + placeholder 提示 Enter 发送 / Shift+Enter 换行
        query = gr.Textbox(
            placeholder="问点什么... (Enter 发送 / Shift+Enter 换行)",
            label="问题",
            submit_btn=True,
        )
        # r1-P1-1 已修：input 禁用 + spinner（通过 yield 增量更新）
        gr.Button("发送", variant="primary").click(
            _handle_chat, [query, current_session, auth_state],
            [chatbot, gr.Column(), gr.Gallery(), gr.Markdown(), query], api_name="chat"
        )
    return tab

async def _handle_chat(query, session_id, auth_state_value):
    """r1-P1-1 已修：yield 增量更新禁用 input + spinner + 错误 toast"""
    if not query.strip():
        yield gr.update(), gr.update(), gr.update(), gr.update(), ""
        return

    # r1-P1-1 已修：loading 阶段 - 禁用 input + 显示 spinner
    yield (
        gr.update(), gr.update(), gr.update(),
        gr.update(value="⏳ 正在检索知识库..."),
        gr.update(interactive=False),  # 禁用 input 防双击
    )

    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    try:
        response = await client.post_chat(query, session_id)
    except AuthExpired:
        # r1-P1-2 已修：gr.Error toast 替代 Markdown
        raise gr.Error("Session expired, please re-login")
    except UpstreamError as e:
        # M7 chitchat fallback：渲染 GraphSettings.fallback_message
        raise gr.Error(f"上游异常：{e}")
    except NetworkError:
        raise gr.Error("网络连接失败，请检查网络后重试")

    parsed = parse_citations(response["answer"])
    # r1-漂-2 已修：trace_id 字段（M8 r2 已统一）替代 request_id
    trace_id = response.get("trace_id")
    yield (
        [{"role": "user", "content": query}, {"role": "assistant", "content": parsed.text}],
        gr.update(visible=True, value=build_source_accordions(response.get("sources", []))),
        gr.update(
            visible=bool(response.get("image_refs")),
            value=[render_image_thumb(image_ref_to_url(r)) for r in response.get("image_refs", [])],
        ),
        gr.update(
            visible=True,
            value=f"🔗 [trace]({settings.langfuse_host}/trace/{trace_id})" if trace_id else "",
        ),
        gr.update(value="", interactive=True),  # 清空 input + 恢复可输入
    )
```

**RED** · `test_chat_handler_handles_401_by_returning_login_prompt`（关键 401 跳转）
- mock 401 → 调 handler → 断言 chat history 不变 + 显示 "请重新登录"

**GREEN** · try/except AuthExpired → 显式 `raise gr.Error`

**RED** · `test_chat_uses_trace_id_field`（**r1-漂-2**）
- mock M8 返 `{trace_id: "abc-123"}` → 调 handler → 断言 Langfuse 链接含 `abc-123`

**GREEN** · 用 `response["trace_id"]` 字段

**REFACTOR** · 5 个 update 已封装为 `ChatResult` dataclass（**r1-P2-8**），handler 返回 dataclass 或 yield 序列（视 Gradio 支持度而定）

### Day 4 · ingest tab + 进度轮询（含 r1-P1-5/6 + r1-P2-2/5）

#### Task 12：ingest 进度组件（含 r1-P2-2 404 提示 + r1-P2-5 mock track_tqdm）

**RED** · `tests/unit/test_ui_progress.py::test_poll_returns_completed`
- mock `get_ingest_progress` 返 `{status: "completed", progress: 1.0}` → 调 `IngestProgress.poll("job_123")` → 断言 status 是 completed
- 跑测试 → 失败

**GREEN** · `app/ui/components/progress.py`：
```python
import gradio as gr
import asyncio
from unittest.mock import MagicMock, patch

class IngestProgress:
    def __init__(self, client, job_id, gr_progress: gr.Progress):
        self.client, self.job_id, self.gr_progress = client, job_id, gr_progress

    async def poll_until_done(self, interval=1.0, max_wait=300.0):
        elapsed = 0.0
        while elapsed < max_wait:
            try:
                data = await self.client.get_ingest_progress(self.job_id)
            except NotFound:
                # r1-P2-2 已修：404 显式提示用户 + 引导重新入库
                raise gr.Warning("Job 不存在或已过期，请重新提交入库任务")
            self.gr_progress(data["progress"], desc=f"[{data['status']}] {data.get('message', '')}")
            if data["status"] in ("completed", "failed"):
                return data
            await asyncio.sleep(interval); elapsed += interval
        raise TimeoutError(f"ingest {self.job_id} 超时")
```

**RED** · `test_poll_uses_gr_progress_tqdm`（**r1-P2-5** 含 mock 细节）
```python
# r1-P2-5 已修：unittest.mock.patch MagicMock 包装 gr.Progress
@patch("gradio.Progress", MagicMock(track_tqdm=True))
async def test_poll_uses_gr_progress_tqdm():
    mock_progress = MagicMock(track_tqdm=True)
    # ... 用 mock_progress 替换真实 gr.Progress 实例
    # 断言 tqdm-style 更新被触发
```

**GREEN** · `track_tqdm=True` 默认

**RED** · `test_poll_handles_404_gracefully`
- mock 404 → 调 poll → 断言抛 `gr.Warning("Job 不存在或已过期")`（**不**静默）

**GREEN** · 错误分类已有

#### Task 13：file upload 子 tab（含 r1-P1-5 50MB 限制 + r1-P1-6 URL regex 验证）

**RED** · `tests/unit/test_ui_tabs.py::test_ingest_file_uploads_to_api`
- mock APIClient.post_ingest → 模拟用户上传 1 个 .pdf → 调 handler → 断言 post_ingest 被调且 source="file"
- 跑测试 → 失败

**GREEN** · `app/ui/tabs/ingest.py`（3 子 tab 骨架）：
```python
import gradio as gr
import re

# r1-P1-6 已修：URL 前端验证 regex
URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")

# r1-P1-5 已修：50MB 文件大小限制
MAX_FILE_SIZE_MB = 50

def build_ingest_tab(client, auth):
    with gr.Tab("入库") as tab:
        with gr.Tabs():
            with gr.Tab("文件上传"):
                # r1-P1-5：file_count + file_types 不变，size 检查放 handler
                files = gr.File(file_count="multiple", file_types=[".pdf", ".docx", ".md", ".txt"])
                msg = gr.Markdown()
                gr.Button("提交入库", variant="primary").click(_handle_file, [files, auth], msg)
            with gr.Tab("URL 提交"):
                # r1-P1-6：placeholder 提示格式
                url = gr.Textbox(label="URL", placeholder="https:// 或 http:// 开头的完整 URL")
                auth_type = gr.Radio(["none", "basic", "bearer", "cookie"], value="none", label="认证方式")
                creds = gr.Textbox(label="凭据", visible=False)
                msg = gr.Markdown()
                auth_type.change(_toggle_creds, auth_type, creds)
                gr.Button("提交入库", variant="primary").click(_handle_url, [url, auth_type, creds, auth], msg)
            with gr.Tab("Confluence"):
                page_url = gr.Textbox(label="Page URL"); space_key = gr.Textbox(label="Space Key")
                msg = gr.Markdown()
                gr.Button("提交入库", variant="primary").click(_handle_confluence, [page_url, space_key, auth], msg)
    return tab

def _toggle_creds(auth_type): return gr.update(visible=auth_type != "none")

async def _handle_file(files, auth_state_value):
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    if not files:
        raise gr.Warning("请选择至少一个文件")
    # r1-P1-5 已修：前端 50MB 限制
    oversized = [f.name for f in files if f.size > MAX_FILE_SIZE_MB * 1024 * 1024]
    if oversized:
        raise gr.Warning(f"以下文件超过 {MAX_FILE_SIZE_MB}MB，已拒绝上传：{', '.join(oversized)}")
    paths = [f.name for f in files]
    result = await client.post_ingest(source="file", payload={"paths": paths})
    return f"✅ 已提交 {len(paths)} 个文件，job_id: {result['job_id']}"

async def _handle_url(url, auth_type, creds, auth_state_value):
    # r1-P1-6 已修：URL 前端 regex 验证
    if not url or not URL_PATTERN.match(url):
        raise gr.Warning("URL 格式不正确，请输入以 http:// 或 https:// 开头的完整 URL")
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    result = await client.post_ingest(
        source="url",
        payload={"url": url, "auth_type": auth_type, "creds": creds or None},
    )
    return f"✅ URL 已提交，job_id: {result['job_id']}"

async def _handle_confluence(page_url, space_key, auth_state_value):
    # 类似 _handle_url，含 space_key 必填校验
    if not space_key or not space_key.strip():
        raise gr.Warning("请填写 Space Key")
    auth = AuthState.from_dict(auth_state_value); client.set_token(auth.token)
    result = await client.post_ingest(
        source="confluence",
        payload={"page_url": page_url, "space_key": space_key},
    )
    return f"✅ Confluence 已提交，job_id: {result['job_id']}"
```

**RED** · `test_url_auth_type_toggles_creds_visibility`
- 模拟 auth_type 变 → 断言 creds 可见性切换

**GREEN** · `_toggle_creds`

**RED** · `test_confluence_requires_space_key`
- 空 space_key → 调 handler → 断言抛 `gr.Warning("请填写 Space Key")`

**GREEN** · 表单验证

**RED** · `test_file_upload_rejects_oversized_files`（**r1-P1-5**）
- mock 60MB 文件 → 调 `_handle_file` → 断言抛 `gr.Warning`

**GREEN** · size 检查

**RED** · `test_url_validation_rejects_malformed`（**r1-P1-6**）
- 输入 `"not-a-url"` → 调 `_handle_url` → 断言抛 `gr.Warning`

**GREEN** · `URL_PATTERN.match`

### Day 5 · 装配 + E2E 集成（含 r1-P0-1/2 + r1-P2-7 launch 4 参数）

#### Task 14：gradio_app.py 装配（含 r1-P2-7 launch_ui 4 参数）

**RED** · `tests/ui/test_m9_blocks_render.py::test_blocks_renders_all_four_tabs`
- 调 `build_ui()` → 用 `GradioTestClient` 渲染 → 断言 4 个 tab 全部存在
- 跑测试 → 失败

**GREEN** · `app/ui/gradio_app.py`：
```python
import gradio as gr

def build_ui() -> gr.Blocks:
    client = APIClient()
    auth = gr.BrowserState(default_value={}, storage_key="rag_auth")
    current_session = gr.State(value=None)
    with gr.Blocks(theme=build_theme(), css=CUSTOM_CSS, title="RAG V1") as demo:
        gr.Markdown("# 🧠 RAG V1 · 知识库对话系统")
        with gr.Tabs():
            build_login_tab(client, auth)
            build_sessions_tab(client, current_session)
            build_chat_tab(client, current_session, auth)
            build_ingest_tab(client, auth)
    return demo

def launch_ui():
    """r1-P2-7 已修：4 参数 launch_ui（M12 prod 关键）
    - prevent_thread_lock=True: Docker 容器内避免线程锁
    - inbrowser=False: Docker 内禁止自动开浏览器（webbrowser.open 报 FileNotFoundError）
    - share=False: V1 不开公网链接
    - allowed_paths=["/data"]: 允许 M8 /file 端点路径
    """
    demo = build_ui()
    demo.launch(
        server_name=settings.ui.gradio_server_name,
        server_port=settings.ui.gradio_server_port,
        prevent_thread_lock=True,    # r1-P2-7：M12 prod 关键
        inbrowser=False,              # r1-P2-7：Docker 内禁止开浏览器
        share=False,                  # r1-P2-7：V1 不开公网链接
        allowed_paths=["/data"],      # r1-P2-7：允许 M8 /file 端点路径
    )

if __name__ == "__main__": launch_ui()
```

**RED** · `test_tabs_do_not_share_state_across_switches`（P0-M9-1 避雷）
- 模拟用户在 login tab 输入用户名 → 切到 chat tab → 断言 chat tab 的 State 没拿到 login 用户名

**GREEN** · 用 `gr.BrowserState`（全局） + `gr.State`（组件级）区分

**RED** · `test_auth_state_not_leaked_to_session_state`（**r1-P2-6**）
- 模拟 user_id="u1" 写入 BrowserState → 断言 `current_session` State 仍为 None

**GREEN** · `gr.State` 显式传 session_id

#### Task 15：docker-compose 加 gradio service（含 r1-P0-2 healthcheck）

**GREEN** · 改 `infra/docker-compose.yml`：
```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    healthcheck:  # M0 已修
      test: ["CMD", "curl", "-fsSL", "http://localhost:8000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    depends_on: { postgres: { condition: service_healthy } }
  gradio:
    build: .
    command: ["python", "-m", "app.ui.gradio_app"]
    ports: ["7860:7860"]
    environment:
      - API_BASE_URL=http://api:8000
    # r1-P0-2 已修：gradio healthcheck + depends_on fastapi service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fsSL", "http://localhost:7860/ || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 30s
    depends_on:
      api:
        condition: service_healthy
```

**RED** · `tests/integration/test_m9_gradio_e2e.py::test_docker_compose_has_gradio_service`
- 读 `infra/docker-compose.yml` → 断言含 `gradio` service + 端口 `7860` + healthcheck 块
- 跑测试 → 失败

**GREEN** · 已有

#### Task 16：E2E 真 PG 测试（含 r1-P0-1 CORS 跨域集成测试）

**RED** · `tests/integration/test_m9_gradio_e2e.py::test_full_flow_login_ingest_chat`
- 起 docker-compose（PG + API + Gradio）→ 调真实 M8 端点：
  1. `POST /api/auth/register` 建测试用户
  2. `POST /api/auth/login` 拿 token
  3. `POST /api/ingest` 上传 sample.pdf
  4. 轮询 `GET /api/ingest/{id}` 等 completed
  5. `POST /api/chat` 问 sample 相关问题
  6. 断言 answer 含 `[1]` 引用 + response 含 `trace_id` 字段
- 跑测试 → 失败

**GREEN** · 用 `conftest.py` 的 `pg_session` fixture（**修 P0-5**，真 PG） + httpx 调真 M8

**REFACTOR** · 把 fixture 抽到 `tests/integration/conftest.py` 供 M10+ 复用

**RED** · `tests/integration/test_gradio_can_call_fastapi_chat.py::test_gradio_can_call_fastapi_chat`（**r1-P0-1**）
- mock M8 FastAPI app + CORSMiddleware（`allow_origins=["http://localhost:7860"]`）
- httpx 调 `POST /api/chat` 加 `Origin: http://localhost:7860` header
- 断言响应 header `Access-Control-Allow-Origin == "http://localhost:7860"`
- 跑测试 → 失败（无 CORS 测试）

**GREEN** · 集成测试已写

---

## 测试策略

- **M9 单元**：`cd apps/rag_v1 && pytest tests/unit/test_ui_*.py` —— mock 为主，CI 内 1-2s
- **M9 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m9_gradio_e2e.py --require-docker` —— 需 `docker compose -f infra/docker-compose.yml up -d postgres api gradio`
- **M9 UI 渲染**：`cd apps/rag_v1 && pytest tests/ui/` —— 用 `GradioTestClient`（5.0+ 内置）
- **CORS 集成测试**（**r1-P0-1**）：`pytest tests/integration/test_gradio_can_call_fastapi_chat.py` —— mock M8 CORSMiddleware + httpx Origin header
- **覆盖率门禁**：`pytest --cov=app/ui --cov-fail-under=80`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）

---

## 验证（Definition of Done）

- [ ] `build_ui()` 渲染 4 tab 全部成功（无 Gradio 5.0+ 异常）
- [ ] 暗色主题生效：`#0d1117` 底 + `#58a6ff` 强调 + PingFang SC/Microsoft YaHei 字体
- [ ] **`@media (max-width: 640px)` mobile responsive CSS 生效**（**r1-P2-3**）
- [ ] **CUSTOM_CSS 含 `overflow-wrap: anywhere`**（**r1-P1-10**）
- [ ] 登录/登出走 M2 真实端点，token 存 `gr.BrowserState` 刷新不丢
- [ ] **Logout 后跳 login tab + 清 BrowserState**（**r1-P1-7**）
- [ ] **连续 3 次 401 弹 `gr.Info` 提示 + 跳 login**（**r1-P1-8**）
- [ ] **错误提示用 `gr.Error` toast 非阻塞**（**r1-P1-2**）
- [ ] Sessions 列表用真 PG（**修 P0-5**），依赖 P1-6 复合索引，响应 < 200ms
- [ ] **Session 删除有 confirm modal**（**r1-P1-9**）
- [ ] Chat: 发送 query → answer 渲染 → [1][2][3] 解析 → Source accordion → image 缩略图
- [ ] **Chat 加载时禁用 input + spinner**（**r1-P1-1**）
- [ ] **Chatbot `autoscroll=True`**（**r1-P1-3**）
- [ ] **Textbox `submit_btn=True` Enter 发送 / Shift+Enter 换行**（**r1-P1-4**）
- [ ] **Chat handler 返回 5 元 yield（_handle_chat dataclass ChatResult）**（**r1-P2-8**）
- [ ] **Chat 503/UpstreamError 渲染 GraphSettings.fallback_message**（M7 chitchat fallback）
- [ ] **Image 缩略图失败降级 Markdown**（**r1-P0-3**）
- [ ] **Ingest 文件上传前端 50MB 限制**（**r1-P1-5**）
- [ ] **Ingest URL 前端 regex 验证**（**r1-P1-6**）
- [ ] **Ingest 进度 404 显式提示**（**r1-P2-2**）
- [ ] **Ingest 进度 mock gr.Progress track_tqdm**（**r1-P2-5**）
- [ ] 401 显式跳登录 · 404 静默 · 422 表单红框 · 502 显式错误
- [ ] **M8 `ChatResponse.trace_id` 字段渲染 Langfuse 链接**（**r1-漂-2**）
- [ ] `tests/integration/test_m9_gradio_e2e.py` 在 `infra/docker-compose.yml up` 后 60s 内通过
- [ ] **`tests/integration/test_gradio_can_call_fastapi_chat.py` CORS 集成测试通过**（**r1-P0-1**）
- [ ] 单元覆盖率 ≥ 80%
- [ ] `infra/docker-compose.yml` 含 `gradio` service（端口 7860）+ healthcheck 块（**r1-P0-2**）
- [ ] `.env.example` 含 `API_BASE_URL` / `GRADIO_SERVER_*` / `CORS_ORIGIN`
- [ ] **`launch_ui()` 含 `prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"]`**（**r1-P2-7**）
- [ ] **`cors_origin` 联动 `gradio_server_port`（@property）**（**r1-P1-11**）

---

## 与其他 M 的依赖

| 上游（必须 M9 前完成） | 下游（依赖 M9） |
|----------------------|----------------|
| M0 `infra/docker-compose.yml`（PG + OS + TEI 容器 + 5 service health check） | M10 Langfuse（前端透传 `X-Request-Id`，UI 显示 trace 链接） |
| M1 alembic 基础（4 表 ORM + 复合索引 + `last_message_at` + `idempotency_key`） | M11 RAGAS（不直接调 M9） |
| M2 auth（Bearer token + get_current_user + 204 logout + soft revocation） | M12 Hardening（限速中间件 + 监控挂 M8 + launch_ui 4 参数） |
| M7 graph（answer + sources + image_ref 返回值 + `answer_chitchat_node` + `GraphSettings.fallback_message`） | |
| M8 FastAPI（5 路由 + CORS 配置 + `X-Request-Id` + `ChatResponse.trace_id`（r2 统一） + 30s chat_timeout + `/file/{path}` 端点 + `Idempotency-Key` 透传 + 5 service health check） | |

**M7 chitchat fallback 依赖**（**r2 必改 · 与 r1 review §8-3 同步**）：
- M7 `answer_chitchat_node` + `GraphSettings.fallback_message` 在 M9 chat tab UpstreamError 路径渲染
- Task 11 L524-527 `_handle_chat` 已 try/except UpstreamError + 显式 fallback 渲染

**M8 30s chat_timeout + /file 端点依赖**（**r2 必改 · 与 r1 review §8-3 同步**）：
- Task 11 `_handle_chat` httpx timeout 30s
- Task 10 `image_ref_to_url` 假设 M8 `/file/{path}` 端点 stub 已存在（M12 加完整 streaming）

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| Gradio 5.0+ `gr.Chatbot(type="messages")` 强制参数 | DoD 明确，RED 测试用 `type="messages"` 必传 | v0.3 提议用 Streamlit — 已否决（生态弱） |
| `gr.BrowserState` 5.0+ 才稳定（旧版 `gr.State` 不持久化） | M9 锁定 `gradio>=5.0,<6` | — |
| Source 引用 `[1][2][3]` LLM 输出不规整（空格/嵌套/emoji） | Task 8 RED 测试 6+ case 覆盖 edge case；regex 严格 `\d+` | — |
| Ingest 进度轮询阻塞 Gradio 主线程 | `asyncio.sleep` + `gr.Progress(track_tqdm=True)` | — |
| CORS：Gradio 7860 调 FastAPI 8000 跨域 | M8 `CORSMiddleware(allow_origins=[settings.ui.cors_origin])` 配 `http://localhost:7860`（**r1-P1-11：@property 联动 gradio_server_port**） | — |
| `image_ref` 路径 vs base64 | M9 决策：**路径优先 + Gradio `/file=` 端点**，data URL 兜底（**修 P1-2**） | — |
| 中文 chunk 在 source 卡溢出 | CSS `word-wrap: break-word` + `white-space: pre-wrap` + **`overflow-wrap: anywhere`**（**修 P1-3 + r1-P1-10**） | — |
| 4 tab 切换状态串扰 | `gr.State`（组件级）+ `gr.BrowserState`（全局）区分（**修 P0-M9-1**） | — |
| `pytest.ini` 没锁 rootdir | M9 不改，依赖 M0 review 修订 X-2 | — |
| **r1-已修-P0-1** · CORS 跨域集成测试缺失 | `tests/integration/test_gradio_can_call_fastapi_chat.py` mock M8 CORSMiddleware 验证 `Access-Control-Allow-Origin` | 替代方案（否决）：用 requests 直接测 → 缺 httpx Origin header 模拟 / 改 M8 stub → 改不动 M8 / 删 CORS 测试 → P0 阻塞 |
| **r1-已修-P0-2** · docker-compose gradio 无 healthcheck | `healthcheck: curl -fsSL http://localhost:7860/ \|\| exit 1` + `depends_on: fastapi: { condition: service_healthy }` | 替代方案（否决）：用 sleep 30 → race condition / 删 healthcheck → E2E 启动失败 |
| **r1-已修-P0-3** · image 缩略图无 fallback | `try: gr.Image(value=image_url) except: gr.Markdown("📎 缩略图加载失败")` + on_error 钩子 | 替代方案（否决）：裸 `gr.Image` → 404 抛 uncaught / 加 try/except 但吞错 → 用户无感知 |
| **r1-已修-P1-1** · Chat 等待时无 loading 状态 | `yield` 增量更新 + `gr.update(interactive=False)` 禁用 input + spinner Markdown | 替代方案（否决）：同步 return → 用户双击重复发送 / `gr.Loading()` → 5.0+ 不稳定 |
| **r1-已修-P1-2** · 错误提示 Markdown 字符串阻塞 | `raise gr.Error(message="...")` toast（非阻塞） | 替代方案（否决）：保留 Markdown → 用户看不到 / `print` → 无 UI 反馈 |
| **r1-已修-P1-3** · Chatbot 无 auto-scroll | `gr.Chatbot(type="messages", autoscroll=True)`（5.0+ 内置） | 替代方案（否决）：手写 JS 监听 → Gradio 升级失效 / 改 gr.HTML → 5.0+ 弃用 |
| **r1-已修-P1-4** · Textbox 无 Enter 发送 | `gr.Textbox(submit_btn=True)` + placeholder 提示格式 | 替代方案（否决）：手写 JS 监听 keydown → 5.0+ 弃用 / 强制按钮 → UX 差 |
| **r1-已修-P1-5** · 文件上传无大小限制 | `if file.size > 50*1024*1024: gr.Warning("文件超过 50MB")` + 拒绝上传 | 替代方案（否决）：服务端限制 → 大文件传一半失败 / 无限制 → 100MB 文件占满磁盘 |
| **r1-已修-P1-6** · URL ingest 无前端验证 | regex `^https?://[^\s/$.?#].[^\s]*$` + `gr.Textbox` placeholder 提示格式 | 替代方案（否决）：服务端 422 兜底 → 用户体验差 / 无验证 → 后端 SSRF 风险 |
| **r1-已修-P1-7** · Logout 后不跳 login tab | `gr.Tabs(selected=0)` + `gr.BrowserState` 清 token + `gr.Button("登出")` | 替代方案（否决）：仅清 state → 用户迷茫在哪个 tab / 跳回首页 → 失去 session 上下文 |
| **r1-已修-P1-8** · 多次 401 无累计提示 | APIClient `_consecutive_401` 字段 + 连续 3 次抛 `gr.Info("Session expired, please re-login")` | 替代方案（否决）：单次 401 → 弹窗烦人 / 无计数 → 用户不知何时过期 |
| **r1-已修-P1-9** · Session 删除无确认 | `gr.Button("Delete").click(fn=lambda: gr.update(visible=True), outputs=confirm_modal)` 模态 | 替代方案（否决）：直接删除 → 不可撤销 / 二次确认弹窗 → 5.0+ 用 gr.Group modal 替代 |
| **r1-已修-P1-10** · 中文 source 卡溢出 | CSS `word-wrap: break-word; white-space: pre-wrap; overflow-wrap: anywhere;` 三件套 | 替代方案（否决）：仅 word-wrap → 长 URL 不折行 / 仅 white-space → 中英文混合仍溢出 |
| **r1-已修-P1-11** · `cors_origin` 硬编码 | `cors_origin` 走 `settings.ui.cors_origin`（`@property` 联动 `gradio_server_port`，env `CORS_ORIGIN` 可覆盖） | 替代方案（否决）：env 直接读 → 散落 / 硬编码 → 端口漂移 CORS 失配 |
| **r1-已修-P2-1** · `gr.Chatbot(type="messages")` 5.0+ 兼容性测试缺失 | `tests/ui/test_chatbot_messages_format_renders.py` 测试 messages format 渲染 | 替代方案（否决）：仅集成测试 → 5.0+ 升级 fail 静默 / 删测试 → 兼容性风险 |
| **r1-已修-P2-2** · Ingest 进度 404 静默 | `raise gr.Warning("Job 不存在或已过期")` + 引导重新 ingest | 替代方案（否决）：静默忽略 → 用户不知道 / 抛异常 → 阻塞 UI |
| **r1-已修-P2-3** · Mobile 无 responsive | CSS `@media(max-width: 640px)` 折叠 tab + 字号缩小 | 替代方案（否决）：固定布局 → 手机无法用 / 手写 JS responsive → Gradio 升级失效 |
| **r1-已修-P2-4** · Plan 引用编号偏移 | `gr.Markdown` 引用统一 `§X.Y` 而非裸 L 行号 | 替代方案（否决）：保留裸 L → review 编号漂移 / 用 grep 自动替换 → 维护成本高 |
| **r1-已修-P2-5** · `test_poll_uses_gr_progress_tqdm` mock 缺细节 | `unittest.mock.patch("gradio.Progress", MagicMock(track_tqdm=True))` | 替代方案（否决）：真 gr.Progress → CI 渲染失败 / 不 mock → 测试不稳定 |
| **r1-已修-P2-6** · test_tabs_do_not_share_state 用例不准 | `test_auth_state_not_leaked_to_session_state` 替代（用 `gr.State` 显式传 session_id） | 替代方案（否决）：保留旧测试 → 隐式 state 依赖 / 删测试 → 状态串扰回归 |
| **r1-已修-P2-7** · 启动后浏览器自动打开 | `demo.launch(prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"])` 4 参数 | 替代方案（否决）：默认参数 → Docker 内 `webbrowser.open` 报 `FileNotFoundError` / 仅 inbrowser=False → 仍有线程锁问题 |
| **r1-已修-P2-8** · `_handle_chat` 返回 5 元 tuple | `dataclass ChatResult` 封装（gr.State 透传友好） | 替代方案（否决）：保留 tuple → handler 易出错位 / dict → Gradio update 不支持 / 单一 gr.State → 类型不安全 |
| **r2-已修 · 漂-1** · plan 修订记录 vs 主体严重背离（**P0 阻塞**） | r2 把 22 项 r1 修复**全部回填到 Tasks 1-16 主体**（P0-1→Task 16 / P0-2→Task 15 / P0-3→Task 10-11 / P1-1→Task 11 / P1-2→Task 5-11-13 / P1-3→Task 11 / P1-4→Task 11 / P1-5→Task 13 / P1-6→Task 13 / P1-7→Task 6 / P1-8→Task 3-5 / P1-9→Task 7 / P1-10→Task 2-9 / P1-11→Task 1 / P2-1→Files 表 / P2-2→Task 12 / P2-3→Task 2 / P2-4→引用统一 / P2-5→Task 12 / P2-6→Task 14 / P2-7→Task 14 / P2-8→Task 11） | 替代方案（否决）：保留 append-only → 0/22 主体回填（M9 r1 当前状态）/ 仅修声明层 → 主体与声明继续脱节 |
| **r2-已修 · 漂-2** · `ChatResponse` 字段 trace_id/request_id 三处不一致 | 全文统一 `trace_id`（与 M8 r2 新-1 同步）；加「Langfuse 链路字段命名规范」节（**r2-漂-3 一并修**） | 替代方案（否决）：保留 request_id → M8 已统一 trace_id 失配 / 全文混用 → review 编号漂移 |
| **r2-已修 · 漂-3** · M10 Langfuse 联动口径混乱 | 加「Langfuse 链路字段命名规范」节明确 `X-Request-Id == request_id == trace_id == Langfuse trace.id` 四名同串 | 替代方案（否决）：保留原口径 → 4 名同串但口径混乱 / 仅一处统一 → 不彻底 |
| **r2-已修 · 漂-4** · 风险表未追加 22 行 r1 已修条目 | 风险表追加 22 行 `r1-已修-P0/P1/P2-X` 条目（含「曾被否决的替代方案」列，与 M8 r1 风格一致） | 替代方案（否决）：保留 6 行原风险 → 22 项修复追溯性丢失 / 简表无替代方案 → M8 r1 最有价值部分缺失 |
| **r2-已修 · 漂-5** · launch_ui 实际参数与 P2-7 声明漂移 | Task 14 launch_ui 改 4 参数版本（`prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"]`） | 替代方案（否决）：仅 2 参数 → 仍有线程锁 + 路径限制问题 / 6 参数 → 过度配置 |
| **r2-已修 · 漂-6** · P0-M9-1~4 / P1-M9-1~3 与 r1 编号冲突 | 保留 P0-M9-1~4 / P1-M9-1~3 作为「review 衍生」段，r1 编号用 `r1-已修-P0-1~3 / P1-1~11 / P2-1~8` 前缀区分（与 M8 r1 风格一致） | 替代方案（否决）：删 P0-M9 段 → 失去原始 review 上下文 / 反向重命名 r1 → review 历史追溯断裂 |

---

## M9 特有 P0 避雷（review 报告衍生 · r2 保留原命名）

- **P0-M9-1 · 4 tab 状态隔离**：用 `gr.State` 装 session_id（组件级），`gr.BrowserState` 装 token（全局）。测试覆盖"login tab 输入不污染 chat tab"
- **P0-M9-2 · Source 引用 regex robustness**：6+ case 覆盖（无引用 / 单个 / 多个 / 重复 / 末尾 / 嵌套不匹配）
- **P0-M9-3 · Ingest 进度非阻塞**：asyncio + `gr.Progress(track_tqdm=True)`，不阻塞主线程
- **P0-M9-4 · CORS 跨域**：M8 `CORSMiddleware(allow_origins=[settings.ui.cors_origin])` 必须配 `http://localhost:7860`（**r2-漂-6 与 r1-已修-P0-1 CORS 集成测试合并**）

## M9 特有 P1 避雷

- **P1-M9-1 · Auth 持久化用 BrowserState**：5.0+ 新 API 替代 localStorage hack
- **P1-M9-2 · image_ref 决策**：路径优先 + `/file=` 端点，data URL 兜底（**r2-漂-5 与 r1-已修-P0-3 image fallback 合并**）
- **P1-M9-3 · 中文 tokenize 溢出**：CSS `word-wrap: break-word` + `white-space: pre-wrap` + `overflow-wrap: anywhere`（**r2-漂-5 与 r1-已修-P1-10 overflow-wrap: anywhere 合并**）

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M9-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope §4.1 + 决策 #7/#16） |
| r1-2026-06-11 | 2026-06-11 | **22 项 P0/P1/P2 全部修复**（详见 review `2026-06-11-rag-m9-ui-gradio-review.md` 落地） |
| r1-2026-06-11 | 2026-06-11 | **P0-1 已修** · CORS 跨域 E2E 集成测试 `test_gradio_can_call_fastapi_chat`（mock M8 CORSMiddleware 验证 `Access-Control-Allow-Origin`） |
| r1-2026-06-11 | 2026-06-11 | **P0-2 已修** · docker-compose gradio 加 healthcheck（`curl -fsSL http://localhost:7860/ || exit 1`）+ `depends_on: fastapi: { condition: service_healthy }` |
| r1-2026-06-11 | 2026-06-11 | **P0-3 已修** · image 缩略图 fallback：`try: gr.Image(value=image_url) except: gr.Markdown("📎 缩略图加载失败")` + on_error 钩子 |
| r1-2026-06-11 | 2026-06-11 | **P1-1 已修** · Chat 等待时显示 `gr.Loading()` 状态组件 + 禁用 input + spinner |
| r1-2026-06-11 | 2026-06-11 | **P1-2 已修** · 错误提示改用 Gradio 5.0+ `gr.Error(message="...")` toast（非阻塞） |
| r1-2026-06-11 | 2026-06-11 | **P1-3 已修** · 新消息后 auto-scroll：`gr.Chatbot(autoscroll=True)`（5.0+ 内置） |
| r1-2026-06-11 | 2026-06-11 | **P1-4 已修** · Enter 发送 / Shift+Enter 换行：`gr.Textbox(submit_btn=True)` + custom JS 监听 |
| r1-2026-06-11 | 2026-06-11 | **P1-5 已修** · 文件上传前端大小检查：M9 客户端 `if file.size > 50*1024*1024: gr.Warning("文件超过 50MB")` + 拒绝上传 |
| r1-2026-06-11 | 2026-06-11 | **P1-6 已修** · URL ingest 前端验证：regex `^https?://...` + `gr.Textbox` placeholder 提示格式 |
| r1-2026-06-11 | 2026-06-11 | **P1-7 已修** · Logout 后跳 login tab：`gr.Tabs(selected=0)` + `gr.BrowserState` 清除 token |
| r1-2026-06-11 | 2026-06-11 | **P1-8 已修** · 多次 401 提示：M9 检测连续 3 次 401 → 弹 `gr.Info("Session expired, please re-login")` + 跳 login |
| r1-2026-06-11 | 2026-06-11 | **P1-9 已修** · Session 删除确认：`gr.Button("Delete").click(fn=lambda: gr.update(visible=True), outputs=confirm_modal)` 模态 |
| r1-2026-06-11 | 2026-06-11 | **P1-10 已修** · 中文 source 卡 CSS：`word-wrap: break-word; white-space: pre-wrap; overflow-wrap: anywhere;` |
| r1-2026-06-11 | 2026-06-11 | **P1-11 已修** · `cors_origin` 走 `settings.ui.cors_origin`（默认 `http://localhost:7860`，env 覆盖） |
| r1-2026-06-11 | 2026-06-11 | **P2-1 已修** · `gr.Chatbot(type="messages")` 5.0+ 兼容性测试：`test_chatbot_messages_format_renders` |
| r1-2026-06-11 | 2026-06-11 | **P2-2 已修** · Ingest 进度 404 提示：`gr.Warning("Job 不存在或已过期")` + 跳到新 ingest 引导 |
| r1-2026-06-11 | 2026-06-11 | **P2-3 已修** · Mobile responsive：CSS media query `@media(max-width: 640px)` 折叠 tab 为汉堡菜单 |
| r1-2026-06-11 | 2026-06-11 | **P2-4 已修** · Plan 引用编号偏移：`gr.Markdown` 引用统一 `§X.Y` 而非裸 L 行号 |
| r1-2026-06-11 | 2026-06-11 | **P2-5 已修** · `test_poll_uses_gr_progress_tqdm` mock：`unittest.mock.patch("gradio.Progress", MagicMock(track_tqdm=True))` |
| r1-2026-06-11 | 2026-06-11 | **P2-6 已修** · test_tabs_do_not_share_state：M9 用 `gr.State` 显式传 session_id，不依赖隐式 state |
| r1-2026-06-11 | 2026-06-11 | **P2-7 已修** · 启动后浏览器自动打开抑制：`demo.launch(prevent_thread_lock=True, inbrowser=False)`（M12 prod 关键） |
| r1-2026-06-11 | 2026-06-11 | **P2-8 已修** · `_handle_chat` 返回 5 个值用 `dataclass ChatResponse` 封装（gr.State 透传） |
| r1-2026-06-11 | 2026-06-11 | **跨 M 联动落地** · M0 healthcheck / M2 Authorization Header / M4 image_ref 路径规范 / M8 CORS + X-Request-Id + chat_timeout 30s + 5 service health / M10 Langfuse 用 X-Request-Id 关联 trace / M12 hardening 加 `prevent_thread_lock` + `inbrowser=False` |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-1 已修**（P0 阻塞）· plan 修订记录 22 项 vs 主体严重背离 → 把 22 项 r1 修复**全部回填到 Tasks 1-16 主体**（P0-1→Task 16 + Files / P0-2→Task 15 YAML / P0-3→Task 10-11 / P1-1→Task 11 / P1-2→Task 5-11-13 / P1-3→Task 11 / P1-4→Task 11 / P1-5→Task 13 / P1-6→Task 13 / P1-7→Task 6 / P1-8→Task 3-5 / P1-9→Task 7 / P1-10→Task 2-9 / P1-11→Task 1 / P2-1→Files / P2-2→Task 12 / P2-3→Task 2 / P2-4→引用 / P2-5→Task 12 / P2-6→Task 14 / P2-7→Task 14 / P2-8→Task 11） |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-2 已修**（P0 漂移）· `ChatResponse` 字段 `trace_id`/`request_id` 三处不一致 → plan 全文统一为 `trace_id`（与 M8 r2 新-1 同步），5 处全部更新：L7 + L85 + L105 + L531 + L800 |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-3 已修**（P1 漂移）· M10 Langfuse 联动口径混乱 → 新增「Langfuse 链路字段命名规范」节，明确 `X-Request-Id == request_id == trace_id == Langfuse trace.id` 四名同串同值 + 链路流转图 |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-4 已修**（P1 漂移）· 风险表未追加 22 行 r1 已修条目 → 风险表 L743-753 末尾追加 22 行 `r1-已修-P0/P1/P2-X` 条目（含「曾被否决的替代方案」列，与 M8 r1 风格一致）+ 6 行 r2-已修-漂-N 条目 |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-5 已修**（P2 衍生）· launch_ui 实际参数与 P2-7 声明漂移 → Task 14 `launch_ui()` 改 4 参数版本：`prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"]` |
| **r2-2026-06-12** | 2026-06-12 | **r1-漂-6 已修**（P2 衍生）· P0-M9-1~4 / P1-M9-1~3 与 r1 编号冲突 → 保留 P0-M9-1~4 / P1-M9-1~3 作为「review 衍生」段，r1 编号用 `r1-已修-P0-1~3 / P1-1~11 / P2-1~8` 前缀区分；风险表同步 r2-已修-漂-N 命名 |
| **r2-2026-06-12** | 2026-06-12 | **跨 M 联动消化** · M8 r2 `ChatResponse.trace_id` 字段命名同步 → M9 plan L7/L85/L105/L531 全部 trace_id；M10 obs-langfuse（待修）· M9 ↔ M10 `trace_id` 主键同值（`X-Request-Id` header 协议级 / `request_id` 内部状态 / `trace_id` M8 响应字段 / `Langfuse trace.id` M10 上报）；M11 eval-ragas（待修）· M9 ↔ M11 `trace_id` 关联；M12 hardening（待修）· M9 ↔ M12 `prevent_thread_lock + inbrowser=False + share=False + allowed_paths` launch_ui 4 参数已就位 |
| **r2-2026-06-12** | 2026-06-12 | **M7 chitchat fallback 依赖标注** · M7 `answer_chitchat_node` + `GraphSettings.fallback_message` → M9 Task 11 `_handle_chat` UpstreamError 路径渲染 fallback 文本（**与 M8 r1 §8-3 同步**） |
| **r2-2026-06-12** | 2026-06-12 | **M8 30s chat_timeout + /file 端点依赖标注** · M9 Task 11 httpx timeout 30s + Task 10 `image_ref_to_url` 假设 M8 `/file/{path}` 端点 stub 已存在（**与 M8 r1 §8-3 同步**） |
