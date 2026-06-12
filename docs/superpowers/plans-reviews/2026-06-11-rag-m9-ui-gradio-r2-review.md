# M9 Plan r2 Review · r1 修复验证

> 评审对象：`plans/2026-06-11-rag-m9-ui-gradio.md`（r1 版本 · 800 行 · 修订记录声明 22 项 r1 已修）
> 评审基线：r1 review `reviews/2026-06-11-rag-m9-ui-gradio-review.md`（836 行 · 3 P0 + 11 P1 + 8 P2 = 22 项）
> 评审时间：2026-06-11（r2 阶段）
> 评审者：Hermes subagent（独立审查 · 验证 r1 修复质量 + 发现 r1 引入新问题）
> 范围：M9 plan 22 项 r1 修复逐项验证 + r1 修复过程中是否引入新问题 + 跨 M 一致性 12 联动 + 风险表补全质量

---

## 总评

M9 plan r1 的修复**只落地在「修订记录」一栏（L777-799，共 22 行声明）**，**Tasks 1-16 主体文本、Files 表、风险表、DoD 表均未同步回填**。这是 r1 修复的**核心问题**——与 M8 r1 风格（18 项 P0/P1/P2 全部回填到 Task GREEN 段 + Files 表 + 风险表追加 18 行已修条目）形成鲜明对比。

**r1 修复到位率约 30%**——22 项中只有 ~7 项能在 plan 主体（Task 1-16）找到对应代码/配置落地；其余 15 项**仅有修订记录声明**，**主体文本未更新**（典型如 P0-3 image fallback 仅在修订记录写 `try: gr.Image ... except: gr.Markdown("📎 缩略图加载失败")` + on_error 钩子，但 Task 10 L486-494 主体仍是 L486-494 旧 `image_ref_to_url` 无 try/except 包裹、无 NotFound 引导；P1-1 loading 状态修订记录写「`gr.Loading()` 状态组件 + 禁用 input + spinner」，但 Task 11 L508-534 主体仍是 5 个 `gr.update()` 同步返回，无 `yield` 增量更新、无 `gr.update(interactive=False)` 禁用 input；P2-7 修订记录写 `demo.launch(prevent_thread_lock=True, inbrowser=False)`，但 Task 14 L649-651 主体仍是 `demo.launch(server_name=..., server_port=...)`）。

**r1 修复未引入阻塞级新问题**（22 项修复都是局部增强，无架构级破坏），但发现 **6 项 r1 衍生新问题**——其中 2 项 P0 漂移（**r1-漂-1 修订记录 vs plan 主体严重背离** + **r1-漂-2 字段命名 trace_id/request_id 三处不一致未在 r1 统一**）+ 2 项 P1 漂移（**r1-漂-3 M10 联动口径混乱** + **r1-漂-4 风险表未追加 22 行 r1 已修**）+ 2 项 P2 衍生（**r1-漂-5 launch_ui 实际参数漂移** + **r1-漂-6 M9 P0-M9-1~4 段与修订记录命名编号冲突**）。

| 维度 | r1 评分 | r2 评分 | 变化 |
|------|--------|--------|------|
| 主体代码落地 | ⚠️ Tasks 1-16 完整 | ❌ **Tasks 1-16 主体未回填 r1 修复** | 大幅退化 |
| 修订记录透明度 | N/A | ⚠️ **22 行声明但与主体脱节** | 表面充实实际空洞 |
| UI 完整性 | ⭐⭐⭐ | ⭐⭐⭐ | 未变（声明层完整、代码层未动） |
| 跨 M 一致性 | ⭐⭐⭐⭐ | ⚠️ **M8 r2 新-1 字段命名未消化** | 退化 |
| 风险表补全 | ⭐⭐⭐ | ⭐⭐ | 未追加 r1 已修条目 |
| 可立即实施 | ⚠️ P0 阻塞 | ❌ **修订记录 ≠ 实际 plan，须重做主体回填** | 退化 |

**一句话**：r1 修复**在「修订记录」一栏是完整的 22 项**——从 CORS 测试、healthcheck、image fallback、loading、auto-scroll、keyboard shortcut、inbrowser=False、prevent_thread_lock 都列了——但**主体 Tasks 1-16、Files 表、风险表、DoD 表均未同步**。这意味着 reviewer / implementation 看到 plan 主体仍按 r0 旧版写，修订记录仅是「承诺」而非「已落」。**必须做一次 plan 主体回填**（r2 必改 #1），否则 r1 修复就是 22 行空头支票。

---

## 1. r1 修复验证（22 项逐项）

### 1.1 P0 项验证（3 项）

| r1 标记 | 修复内容（修订记录声明） | 实际验证（plan 主体 L/段落） | 状态 |
|---------|----------------------|-----------------------|------|
| **P0-1** | CORS 跨域 E2E 集成测试 `test_gradio_can_call_fastapi_chat`（mock M8 CORSMiddleware 验证 `Access-Control-Allow-Origin`） | 修订记录 L778 声明；plan 主体 Task 16 L685-699（E2E 测试）仍是 `test_full_flow_login_ingest_chat`（login→ingest→chat）**无 CORS 专项测试**；风险表 L749 仍说"Gradio 7860 调 FastAPI 8000 跨域 M8 CORSMiddleware 配 http://localhost:7860"（**假设 M8 已配未验证**）；Files 表 L76 `test_m9_gradio_e2e.py` 端到端**无 CORS 标注** | ⚠️ **声明层到位，主体未回填**（test_gradio_can_call_fastapi_chat 未在 Task 16 RED 段出现） |
| **P0-2** | docker-compose gradio 加 healthcheck（`curl -fsSL http://localhost:7860/ || exit 1`）+ `depends_on: fastapi: { condition: service_healthy }` | 修订记录 L779 声明；plan 主体 Task 15 L663-677 docker-compose gradio 段**仍是旧版**（`ports: ["7860:7860"]` + `depends_on: api: { condition: service_healthy }`，**无 `healthcheck:` 块**） | ⚠️ **声明层到位，主体未回填**（健康检查块未在 YAML 块出现） |
| **P0-3** | image 缩略图 fallback：`try: gr.Image(value=image_url) except: gr.Markdown("📎 缩略图加载失败")` + on_error 钩子 | 修订记录 L780 声明；plan 主体 Task 10 L486-494 `image_ref_to_url` 仍是旧版（仅返 URL 字符串，**无 try/except、无 on_error、无 fallback 渲染逻辑**）；Task 11 L515 `gr.Gallery()` 缺省参数（**未配 on_error**） | ⚠️ **声明层到位，主体未回填**（fallback 逻辑未在代码段出现） |

**P0 验证小结**：3 项**全部声明到位、主体未回填**。P0-1 跨域测试未在 Task 16 RED 段定义；P0-2 healthcheck 块未在 Task 15 YAML 出现；P0-3 fallback 包裹未在 Task 10/11 代码段出现。**这是 r1 修复最严重的脱节**——3 项 P0 阻塞按 plan 主体读仍是阻塞。

### 1.2 P1 项验证（11 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P1-1** | Chat 等待时显示 `gr.Loading()` 状态组件 + 禁用 input + spinner | 修订记录 L781 声明；plan 主体 Task 11 L519-533 `_handle_chat` 仍是同步 `return`（**非 yield 增量更新**），无 `gr.update(interactive=False)` 禁用 input，**无 `gr.Loading()` 包装** | ⚠️ **声明到位，主体未回填** |
| **P1-2** | 错误提示改用 Gradio 5.0+ `gr.Error(message="...")` toast（非阻塞） | 修订记录 L782 声明；plan 主体 Task 6 L370 `return "❌ 用户名或密码错误"` 仍是 Markdown 字符串；Task 11 L524 `return "请重新登录"` 仍是 Markdown 字符串；Task 13 L612 `return f"✅ 已提交 {len(paths)} 个文件..."` 仍是 Markdown 字符串；**全 plan 无 `raise gr.Error()` 调用** | ⚠️ **声明到位，主体未回填** |
| **P1-3** | 新消息后 auto-scroll：`gr.Chatbot(autoscroll=True)`（5.0+ 内置） | 修订记录 L783 声明；plan 主体 Task 11 L511 `chatbot = gr.Chatbot(type="messages", label="对话")` **无 `autoscroll=True` 参数** | ⚠️ **声明到位，主体未回填** |
| **P1-4** | Enter 发送 / Shift+Enter 换行：`gr.Textbox(submit_btn=True)` + custom JS 监听 | 修订记录 L784 声明；plan 主体 Task 11 L512 `query = gr.Textbox(placeholder="问点什么...", label="问题")` **无 `submit_btn=True` 参数**；L513 仍是 `.click(_handle_chat, ...)`（**非 .submit()**） | ⚠️ **声明到位，主体未回填** |
| **P1-5** | 文件上传前端大小检查：M9 客户端 `if file.size > 50*1024*1024: gr.Warning("文件超过 50MB")` + 拒绝上传 | 修订记录 L785 声明；plan 主体 Task 13 L590 `files = gr.File(file_count="multiple", file_types=[...])` 无 size 参数；L608-612 `_handle_file` 仍是 `paths = [f.name for f in files] if files else []` 直接提交，**无 `file.size > 50MB` 检查、无 `gr.Warning` 拒绝** | ⚠️ **声明到位，主体未回填** |
| **P1-6** | URL ingest 前端验证：regex `^https?://...` + `gr.Textbox` placeholder 提示格式 | 修订记录 L786 声明；plan 主体 Task 13 L594 `url = gr.Textbox(label="URL")` 无 placeholder 格式提示；L613 `# _handle_url / _handle_confluence 类似，结构相同` **URL handler 未实现** | ⚠️ **声明到位，主体未回填** |
| **P1-7** | Logout 后跳 login tab：`gr.Tabs(selected=0)` + `gr.BrowserState` 清除 token | 修订记录 L787 声明；plan 主体 Task 6 L349-373 `build_login_tab` 与 `_handle_login` **无 logout handler 实现**（login.py 主体只写登录/注册 tab，**无登出逻辑**） | ⚠️ **声明到位，主体未回填**（logout handler 缺失） |
| **P1-8** | 多次 401 提示：M9 检测连续 3 次 401 → 弹 `gr.Info("Session expired, please re-login")` + 跳 login | 修订记录 L788 声明；plan 主体 Task 5 L317-334 `classify_response` 仅抛 `AuthExpired`，**无 401 计数**；APIClient 主体 L250-266 仍是无状态 httpx client，**无 `_consecutive_401` 字段** | ⚠️ **声明到位，主体未回填** |
| **P1-9** | Session 删除确认：`gr.Button("Delete").click(fn=lambda: gr.update(visible=True), outputs=confirm_modal)` 模态 | 修订记录 L789 声明；plan 主体 Task 7 L393-394 `del_btn = gr.Button("删除选中")` + `del_btn.click(_delete_selected, [df], df)` **无 confirm 模态** | ⚠️ **声明到位，主体未回填** |
| **P1-10** | 中文 source 卡 CSS：`word-wrap: break-word; white-space: pre-wrap; overflow-wrap: anywhere;` | 修订记录 L790 声明；plan 主体 Task 2 L230-234 `CUSTOM_CSS` 仍是 `body { background: #0d1117; color: #c9d1d9; } .chat-message { word-wrap: break-word; max-width: 100%; } .source-card pre { white-space: pre-wrap; word-wrap: break-word; }` ——**有基础 CSS**（`.source-card pre` 已含 `white-space: pre-wrap`），**但缺 `overflow-wrap: anywhere`** | ⚠️ **部分到位**（基础 wrap 有；overflow-wrap: anywhere 未补） |
| **P1-11** | `cors_origin` 走 `settings.ui.cors_origin`（默认 `http://localhost:7860`，可 env 覆盖） | 修订记录 L791 声明；plan 主体 Task 1 L201 `cors_origin: str = "http://localhost:7860"` 是 UISettings 字段（**已经走 settings**），**但仍是硬编码默认**，**无 `@property` 从 `gradio_server_port` 联动**（r1 review P1-11 建议的 `@property cors_origin` 升级未做） | ⚠️ **半到位**（走 settings 是；联动未做） |

**P1 验证小结**：11 项**全部声明到位、主体未回填或半到位**。P1-1~9 主体文本（Tasks 6/7/11/13）完全是 r0 旧版；P1-10 部分到位（基础 CSS 有但 `overflow-wrap: anywhere` 缺）；P1-11 半到位（走 settings 是真，但 `@property` 联动未做，r1 review P1-11 完整建议**未被消化**）。

### 1.3 P2 项验证（8 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P2-1** | `gr.Chatbot(type="messages")` 5.0+ 兼容性测试：`test_chatbot_messages_format_renders` | 修订记录 L792 声明；plan 主体测试策略 L705-709 `tests/unit/test_ui_*.py` + L707 `tests/ui/` 提了 GradioTestClient；**Files 表 L164 `test_ui_tabs.py` 列了但无 `test_chatbot_messages_format_renders` 测试名** | ⚠️ **声明到位，测试未在 Files 表/RED 段定义** |
| **P2-2** | Ingest 进度 404 提示：`gr.Warning("Job 不存在或已过期")` + 跳到新 ingest 引导 | 修订记录 L793 声明；plan 主体 Task 12 L573-576 `test_poll_handles_404_gracefully` 仍断言"抛 NotFound 给用户明确提示"——**具体提示文案 `gr.Warning("Job 不存在或已过期")` 与"跳到新 ingest 引导"逻辑未在 Task 12 GREEN 段实现** | ⚠️ **声明到位，主体未回填** |
| **P2-3** | Mobile responsive：CSS media query `@media(max-width: 640px)` 折叠 tab 为汉堡菜单 | 修订记录 L794 声明；plan 主体 Task 2 L230-234 `CUSTOM_CSS` **无 `@media (max-width: 640px)` 媒体查询**（r1 review P2-3 建议的 mobile 段 CSS 未补） | ⚠️ **声明到位，主体未回填** |
| **P2-4** | Plan 引用编号偏移：`gr.Markdown` 引用统一 `§X.Y` 而非裸 L 行号 | 修订记录 L795 声明；plan 主体 L547-548 `RED · tests/unit/test_ui_message_parser.py::test_poll_progress_updates_status（放错文件了，挪到 progress.py 测试）` 仍是裸引用，**未统一为 `§X.Y`** | ⚠️ **声明到位，主体未回填**（引用偏移未修） |
| **P2-5** | `test_poll_uses_gr_progress_tqdm` mock：`unittest.mock.patch("gradio.Progress", MagicMock(track_tqdm=True))` | 修订记录 L796 声明；plan 主体 Task 12 L568-570 RED 测试 `test_poll_uses_gr_progress_tqdm` 仍说"用 `gr.Progress(track_tqdm=True)` 包装 → 调 poll → 断言 tqdm-style 更新触发"——**未给 mock 方法细节** | ⚠️ **声明到位，主体未回填**（mock 细节未补） |
| **P2-6** | test_tabs_do_not_share_state：M9 用 `gr.State` 显式传 session_id，不依赖隐式 state | 修订记录 L797 声明；plan 主体 Task 14 L656-658 `test_tabs_do_not_share_state_across_switches` 仍说"模拟用户在 login tab 输入用户名 → 切到 chat tab → 断言 chat tab 的 State 没拿到 login 用户名"——**未改 mock 方法**（r1 review P2-6 建议的 `test_auth_state_not_leaked_to_session_state` 替代测试未补） | ⚠️ **声明到位，主体未回填** |
| **P2-7** | 启动后浏览器自动打开抑制：`demo.launch(prevent_thread_lock=True, inbrowser=False)`（M12 prod 关键） | 修订记录 L798 声明；plan 主体 Task 14 L649-651 `demo.launch(server_name=settings.ui.gradio_server_name, server_port=settings.ui.gradio_server_port)` **无 `inbrowser=False`、无 `prevent_thread_lock=True`** | ⚠️ **声明到位，主体未回填**（与 P0-2 healthcheck 同模式漂移） |
| **P2-8** | `_handle_chat` 返回 5 个值用 `dataclass ChatResponse` 封装（gr.State 透传） | 修订记录 L799 声明；plan 主体 Task 11 L519-533 `_handle_chat` 仍是 `return (chatbot_update, ..., "")` 5 元 tuple；**无 `ChatResult` dataclass 封装**（r1 review P2-8 建议的 dataclass 方案未实现，注：Gradio 不支持 dataclass 返回值这点 reviewer 已知） | ⚠️ **声明到位，主体未回填** |

**P2 验证小结**：8 项**全部声明到位、主体未回填**。P2-7 `inbrowser=False` 是 M12 prod 关键（避免 docker 容器内 `webbrowser.open` 报 `FileNotFoundError`），落地缺失会导致 prod 启动日志脏 + 启动失败风险。

### 1.4 22 项修复到位率统计

| 级别 | 项数 | 声明 + 主体均到位 | 声明到位 主体未回填 | 完全未到位 |
|------|------|----------------|------------------|----------|
| P0 | 3 | 0 | 3 | 0 |
| P1 | 11 | 0 | 9 | 2（P1-10/11 半到位） |
| P2 | 8 | 0 | 8 | 0 |
| **合计** | **22** | **0** | **20** | **2** |

**总体到位率 0%（严格主体回填标准）/ ~30%（声明 + 部分主体）**——22 项 r1 修复**全部在修订记录一栏声明完整**，**全部 22 项主体代码/配置未回填**。这是 r1 修复与 M8 r1 风格（M8 r1 18/18 全部回填到 Task GREEN 段）的**根本差异**。

**关键差异**：
- M8 r1 修订记录 P0-1 `asyncio.wait_for` 包装在 **Task 7 GREEN 段 L864-878 完整 15 行代码**；M9 r1 修订记录 P0-1 `test_gradio_can_call_fastapi_chat` 在 **Task 16 RED 段无对应行**
- M8 r1 修订记录 P0-2 `lifespan finally 块` 在 **Task 13 GREEN 段 L1146-1157 完整 12 行代码**；M9 r1 修订记录 P0-2 `healthcheck` 块在 **Task 15 YAML 段无对应行**
- M8 r1 修订记录 P2-3 `middleware 注释` 在 **Task 13 GREEN 段 L1171-1184 完整 14 行注释**；M9 r1 修订记录 P2-3 `@media (max-width: 640px)` 在 **CUSTOM_CSS L230-234 无对应行**

---

## 2. r1 修复引入的新问题

r1 修复密度高、声明完整，但**主体未回填**导致 r1 修复本身**未直接引入新阻塞问题**，但暴露了 **6 项 r1 衍生漂移问题**（其中 2 项 P0 漂移 + 2 项 P1 漂移 + 2 项 P2 衍生）：

### r1-漂-1 · plan 修订记录与主体 Tasks 1-16 严重背离（**P0 阻塞**）

**位置**：修订记录 L777-799（22 行声明）vs Tasks 1-16 主体（L188-699，~510 行）

**问题**：
- r1 修复是**「append-only 模式」**——只在 plan 末尾追加 22 行修订记录，主体 Tasks 1-16 文本完全没动
- 这与 M8 r1 风格（M8 主体 Tasks 1-14 + Files 表 + 风险表 + DoD 全部回填）形成鲜明对比
- reviewer 看到修订记录说「P0-3 image fallback 已修」翻到 Task 10 L486-494 主体代码段是 `image_ref_to_url` 简单字符串拼接，无 try/except、无 on_error、无 fallback 渲染——**承诺与实现脱节**
- 影响：implementation 工程师会按 plan 主体（旧版）实现，导致 22 项修复**全部漏写**，实际行为与 review 期望不一致

**修改建议**（r2 必改 #1）：
- 对 22 项 r1 修复逐项回填到 plan 主体：P0-1 → Task 16 RED 段 + Files 表；P0-2 → Task 15 YAML 段；P0-3 → Task 10 GREEN 段（image_ref_to_url 加 try/except）+ Task 11 GREEN 段（gr.Gallery 加 on_error）；P1-1 → Task 11 _handle_chat 改 yield；P1-2 → Task 5/6/11/13 全部 `gr.Markdown` 错误改 `raise gr.Error`；... P2-7 → Task 14 launch_ui 加 `prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"]`
- 估算工作量：**~1 个工作日**主体回填（22 项分散在 8 个 Task，约 200 行代码增量 + 50 行 CSS 增量）

### r1-漂-2 · `ChatResponse` 字段命名 trace_id/request_id 在 M9 plan 内三处不一致（**P0 漂移**）

**位置**：plan 主体 L7 + L85 + L105 + L531

**问题**：
- L7 上下游标注：「M10 Langfuse（前端 X-Request-Id 透传，**UI 显示 trace_id 链接**）」
- L85 契约表：「M9 UI 拿 **trace_id** 渲链接到 `LANGFUSE_HOST/trace/{id}`」
- L105 数据流图：`← 200 { answer, sources, image_refs, session_id, **request_id** }` ← M8 输出
- L531 `_handle_chat` 实际代码：`gr.update(visible=True, value=f"🔗 [trace]({settings.langfuse_host}/trace/{response['request_id']}"))` ← 用 **`request_id` 字段**
- **三处命名混乱**：「trace_id」（L7/L85）vs「request_id」（L105/L531）
- r1 修订记录**完全未涉及此问题**——M8 r2 新-1 揭示的 `ChatResponse.request_id` 命名漂移**未被 M9 r1 消化**
- 实际后果：M8 输出 `request_id`，M9 plan 注释说用 `trace_id`，实际代码用 `request_id`——L531 与 L7/L85 矛盾，implementation 时按 M8 字段名写

**修改建议**（r2 必改 #2，与 M8 r2 新-1 同步）：
- **方案 A（推荐）**：`ChatResponse` 字段统一为 `trace_id: str`（M8 plan P1-1 修订时同步），M9 plan L7/L85/L105/L531 全部统一为 `trace_id`；注释明示"`trace_id` = `X-Request-Id` = Langfuse trace.id 三者同一值"
- **方案 B**：M9 plan 全文统一改 `request_id`（与 M8 ChatResponse 一致），删 L7/L85 处的 `trace_id` 字面量
- 选 A 一致性更好——同一字符串三处都用同一名字

### r1-漂-3 · M10 Langfuse 联动口径在 M9 plan 内三处混乱（**P1 漂移**）

**位置**：L7 / L85 / L531 / L800（r1 修订记录 L800 新增的「跨 M 联动落地」行）

**问题**：
- L7 上下游：「M10 Langfuse（前端 X-Request-Id 透传，UI 显示 trace_id 链接）」
- L85 契约表：「M9 UI 拿 trace_id 渲链接到 `LANGFUSE_HOST/trace/{id}`」——**但 L531 实际是 `request_id`**
- L531 实际代码：`f"🔗 [trace]({settings.langfuse_host}/trace/{response['request_id']})"` —— 实际拿 `request_id` 拼 Langfuse 链接
- L800 r1 修订记录「跨 M 联动落地」：「M10 Langfuse 用 X-Request-Id 关联 trace」——口径**与 L7/L85 都不一致**
- **三处都用「Langfuse」字眼，但语义层级混乱**：
  - L7 强调「X-Request-Id 透传」+「trace_id 链接」（两个独立概念）
  - L85 把两者混为「trace_id」（简化口径）
  - L531 实际用 `request_id` 拼 URL（落地口径）
  - L800 强调「X-Request-Id 关联 trace」（M10 业务侧）
- r1 修订记录**未澄清这个口径混乱**——22 项修复全是「前端功能」类，没有一项是「跨 M 命名统一」类

**修改建议**（r2 必改 #3）：
- 在 plan L85 契约表后补一节「Langfuse 链路字段命名规范」：
  - HTTP Header 名称：`X-Request-Id`（M8 RequestIdMiddleware 注入/透传）
  - M8 ChatResponse 字段：`request_id`（与 header 同名）
  - M9 Gradio 渲染：`trace_id` 显示（用户视角的语义名）
  - M10 Langfuse trace.id：与 `request_id` 同一字符串值
  - M11 RAGAS eval：`trace_id`（用 `get_client().get_current_trace_id()`）
  - **明确规则**：`request_id == trace_id == X-Request-Id == Langfuse trace.id`（同一字符串四名）

### r1-漂-4 · 风险表未追加 22 行 r1 已修条目（与 M8 r1 风格不一致）（**P1 漂移**）

**位置**：风险表 L743-753（仅 6 行原风险 + P0-M9-1~4 + P1-M9-1~3 = ~13 行）

**问题**：
- M8 r1 风险表追加了 18 行 `r1-2026-06-11 ... 已修` 条目（L1363-1411），每行都有「曾被否决的替代方案」
- M9 r1 风险表**完全未追加**——L743-753 仍是 6 行原风险（Gradio 5.0+ Chatbot 强制参数 / BrowserState 5.0+ / Source 引用 regex / Ingest 轮询阻塞 / CORS / image_ref / 中文 chunk / 4 tab 状态串扰 / pytest rootdir）
- 22 项 r1 修复（CORS 集成测试、healthcheck、image fallback、loading、auto-scroll、keyboard、file size、URL validation、logout redirect、401 跟踪、confirm 删除、toast 错误、CSS overflow-wrap、inbrowser=False、prevent_thread_lock、dataclass ChatResult 等）**没有一条进入风险表**
- 风险表的「曾被否决的替代方案」列（M8 r1 最有价值的部分）在 M9 r1 完全缺失
- 影响：reviewer 看不到 r1 修复的决策上下文（为何选 X 不选 Y），追溯性差

**修改建议**（r2 必改 #4）：
- 风险表 L743-753 末尾追加 22 行 r1 已修条目，格式与 M8 r1 一致：
  ```
  || r1-P0-1 已修 · CORS 跨域集成测试 `test_gradio_can_call_fastapi_chat` | mock M8 CORSMiddleware 验证 `Access-Control-Allow-Origin` header | 风险点：M8 P2-3 中间件顺序错 → M9 跨域全挂；替代方案（否决）：用 requests 直接测 / 改 M8 stub / 删 CORS 测试 |
  || r1-P0-2 已修 · docker-compose gradio healthcheck | `curl -fsSL http://localhost:7860/ || exit 1` | 风险点：Gradio 启动 3-10s 编译 JS → E2E race；替代方案（否决）：用 sleep 30 / 删 healthcheck |
  ...
  ```
- 估算：~22 行表格，~1-2 小时工作量

### r1-漂-5 · launch_ui 实际参数与 P2-7 声明漂移（**P2 衍生**）

**位置**：Task 14 L649-651（plan 主体）vs 修订记录 L798（P2-7 声明）

**问题**：
- 修订记录 L798 声明：`demo.launch(prevent_thread_lock=True, inbrowser=False)`（M12 prod 关键）
- plan 主体 Task 14 L649-651：`demo.launch(server_name=settings.ui.gradio_server_name, server_port=settings.ui.gradio_server_port)` ——**完全无 `inbrowser` 与 `prevent_thread_lock` 参数**
- r1 review P2-7 建议的 `share=False, allowed_paths=["/data"]` 也未补
- 影响：docker 容器内启动会尝试 `webbrowser.open()` → 抛 `FileNotFoundError` → Gradio 启动报 warning 但不致命；M12 prod 部署需手动补 launch_ui 改动

**修改建议**（r2 必改 #5，与 r1-漂-1 同步）：
- Task 14 L649-651 改为：
  ```python
  def launch_ui():
      demo = build_ui()
      demo.launch(
          server_name=settings.ui.gradio_server_name,
          server_port=settings.ui.gradio_server_port,
          prevent_thread_lock=True,  # r1-P2-7：M12 prod 关键
          inbrowser=False,            # r1-P2-7：Docker 内禁止开浏览器
          share=False,                # r1-P2-7：V1 不开公网链接
          allowed_paths=["/data"],    # r1-P2-7：允许 M8 /file 端点路径
      )
  ```

### r1-漂-6 · M9 P0-M9-1~4 / P1-M9-1~3 段与 r1 修订记录命名编号冲突（**P2 衍生**）

**位置**：plan L757-769（M9 特有 P0/P1 避雷段）vs L777-799（r1 修订记录）

**问题**：
- plan L757-769 已经有「M9 特有 P0 避雷」4 项（P0-M9-1 4 tab 状态隔离 / P0-M9-2 Source regex robustness / P0-M9-3 Ingest 进度非阻塞 / P0-M9-4 CORS 跨域）和「M9 特有 P1 避雷」3 项（P1-M9-1 Auth BrowserState / P1-M9-2 image_ref 决策 / P1-M9-3 中文 tokenize 溢出）
- r1 修订记录 L777-799 引入 P0-1/2/3、P1-1~11、P2-1~8 编号——**与 P0-M9-1~4 / P1-M9-1~3 编号体系冲突**（r1 P0-3 image fallback ≠ P0-M9-3 Ingest 进度非阻塞）
- 风险表 L743-753 与 L757-769 的避雷段有部分重复（CORS 出现 3 次：风险表 L749 / 避雷段 P0-M9-4 L762 / r1 修订记录 L778）
- implementation 时按编号查找易混淆

**修改建议**（r2 必改 #6）：
- r2 修订时统一编号：
  - P0-M9-1~4 段重命名为「review 衍生」（M9 r1 review 原始 P0 项）
  - r1 修订记录 P0-1/2/3 改为 r1-已修-P0-1/2/3
  - 风险表 L749「CORS：Gradio 7860 → FastAPI 8000 跨域」与避雷段 P0-M9-4 合并
- 或者**反过来**：删 P0-M9-1~4 / P1-M9-1~3 段，统一用 r1 编号体系

### r1 衍生新问题汇总

| # | 问题 | 档次 | 简要说明 |
|---|------|------|----------|
| 1 | 修订记录 22 项与主体 Tasks 1-16 严重背离 | P0 | 22 项修复全声明、全未回填 |
| 2 | `ChatResponse` 字段 trace_id/request_id 三处不一致 | P0 | M8 r2 新-1 未消化 |
| 3 | M10 Langfuse 联动口径三处混乱 | P1 | X-Request-Id / trace_id / request_id / Langfuse trace.id 四名同串 |
| 4 | 风险表未追加 22 行 r1 已修条目 | P1 | 与 M8 r1 风格不一致 |
| 5 | launch_ui 实际参数与 P2-7 声明漂移 | P2 | inbrowser=False / prevent_thread_lock 未在主体 |
| 6 | P0-M9-1~4 与 r1 P0-1/2/3 编号冲突 | P2 | 两套编号体系易混 |

---

## 3. 跨 M 一致性检查（M0/M1/M2/M3/M4/M5/M6/M7/M8/M10/M11/M12）

| 上游/下游 M | 联动点 | M9 plan 处理 | 验证结果 |
|------------|--------|------------|---------|
| **M0** infra | 端口 7860 vs FastAPI 8000/TEI 18080/OS 9200/Langfuse 3000 不冲突 | Files 表 L173 `infra/docker-compose.yml：追加 gradio service（端口 7860，depends_on api）` | ✅ **对齐**（与 M0 r2 端口分配表一致） |
| **M0** infra | `healthcheck` 探测 | 修订记录 L779 声明 `curl -fsSL http://localhost:7860/ \|\| exit 1` + `depends_on: fastapi: { condition: service_healthy }`；主体 Task 15 L663-677 YAML 块**未回填 healthcheck** | ⚠️ **声明到位 主体未回填** |
| **M1** schema | `chat_sessions` 复合索引 `(user_id, is_active, updated_at DESC)` | Task 7 L402 注释 `# 依赖 P1-6 复合索引` + DoD L718 | ✅ **对齐**（M1 r2 已修复合索引） |
| **M1** schema | `chat_sessions.last_message_at` 字段 | ❌ M9 不消费（sessions 列表用 `updated_at`）—— 与 M8 r2 一样未对齐 | ⚠️ **轻度漂移**（M1 r2 加的 `last_message_at` 未在 M9 sessions 排序用） |
| **M1** schema | `users` / `chat_sessions` / `auth_sessions` / `ingest_jobs` 4 表 `idempotency_key` 列 | ❌ M9 未消费（M9 Gradio 双击防护依赖 M8 Idempotency-Key 透传——见 M8 r2 新-4） | ⚠️ **M1 已就位 M8/M9 未对接**（与 M8 r2 一致） |
| **M2** auth | `Authorization: Bearer ***` Header 走 APIClient 全端点 | Task 3 L260 `if self._token: h["Authorization"] = f"Bearer {self._token}"` + 修订记录 L800「M2 Authorization Header」 | ✅ **对齐**（M2 r2 软吊销 + 204 logout 修后 M9 仍可走 Bearer） |
| **M2** auth | 限速（Slowapi） | 修订记录 L800 未提及（挂在 M8，**M9 不感知**） | ✅ **对齐**（M9 不直接处理限速） |
| **M2** auth | 204 logout + idempotency_key 透传 | L800 r1「M2 Authorization Header」声明 | ✅ **对齐** |
| **M3** LLM/embed | `make_llm` 工厂 + `KNOWN_NODES` | M9 不直接调，M9 全走 M8 chat 端点 → M8 调 M7 graph → M7 调 M3 | ✅ **对齐**（间接链路一致） |
| **M3** LLM/embed | TEI 18080 端口 | Files 表 L172 + .env L174 `API_BASE_URL=http://api:8000` | ✅ **对齐**（M3 r2 改 18080 后 M9 配置一致） |
| **M4** ingest-file | `POST /api/ingest/file` + `GET /api/ingest/{job_id}` | 修订记录 L793 声明 ingest 进度 404 提示 `gr.Warning` + 跳新 ingest 引导；Task 12 L573-576 主体未回填 | ⚠️ **声明到位 主体未回填** |
| **M4** ingest-file | M4 r2 补 P0-3 mapping + P1-5 RUNNING | M9 进度展示走 `IngestJob.progress: float \| None` 字段（M4 r2 已加） | ✅ **对齐** |
| **M5** ingest-url | `POST /api/ingest/url` + SSRFRedirectTransport | 修订记录 L786 声明 URL 前端验证 regex `^https?://...`；Task 13 L594 主体未回填 | ⚠️ **声明到位 主体未回填** |
| **M5** ingest-url | M5 r2 修 P0 SSRF 防御 | M9 不感知（后端 M5 端点防御） | ✅ **对齐** |
| **M6** ingest-confluence | `POST /api/ingest/confluence` + auth_type | Task 13 L601-603 `gr.Tab("Confluence")` 主体实现（`_handle_confluence` 同 URL 模式） | ✅ **对齐**（主体已写） |
| **M7** graph | `compile_workflow` 异步包装 + 30s timeout + `state.error` 字段 | 风险表 L741-752 未显式依赖 M7 chitchat（M7 r1 P0-6） | ⚠️ **依赖未标注**（与 r1 review §8-3 揭示一致） |
| **M7** graph | `make_checkpointer` async def | M9 不直接依赖（走 M8 路由层） | ✅ **对齐** |
| **M7** graph | `GraphSettings.fallback_message` | M9 chat tab 503 路径显示 fallback 文本（Task 11 L524 实际未捕获 UpstreamError，**L524 只 try/except AuthExpired**） | ⚠️ **未对齐**（fallback_message 未在 M9 渲染） |
| **M7** graph | `answer_chitchat_node` 实现 | 修订记录未提及；风险表 L741-752 未标注 | ⚠️ **依赖未标注**（与 r1 review §8-3 揭示一致） |
| **M8** FastAPI | `POST /api/chat` 30s timeout | 修订记录 L800「M8 chat_timeout 30s」声明；Task 11 L519-533 主体未补 `try/except (UpstreamError, NetworkError)`（与 r1 review P1-10 揭示一致） | ⚠️ **声明到位 主体未回填** |
| **M8** FastAPI | CORS `allow_origins=["http://localhost:7860"]` | 修订记录 L778 声明 + 风险表 L762「P0-M9-4 CORS」 | ⚠️ **声明到位 主体未回填** |
| **M8** FastAPI | `X-Request-Id` Header 透传 | L7 + L85 + L105 + L531（命名混乱——见 r1-漂-2） | ⚠️ **命名漂移未修** |
| **M8** FastAPI | `ChatResponse.request_id` 字段 | L105 `{ ..., request_id }` + L531 `response['request_id']`——**与 L7/L85「trace_id」冲突** | ⚠️ **三处不一致未在 r1 统一**（M8 r2 新-1 未消化） |
| **M8** FastAPI | `Idempotency-Key` Header 透传 | ❌ M9 未提及（与 M8 r2 新-4 一致） | ⚠️ **M1/M8 已就位 M9 未对接** |
| **M8** FastAPI | `GET /file/{path}` 端点 | 修订记录 L780 image fallback `try/except`；Task 10 L486-494 主体未补 try/except | ⚠️ **声明到位 主体未回填** |
| **M10** Langfuse | `X-Request-Id` 透传 Langfuse trace | 修订记录 L800「M10 Langfuse 用 X-Request-Id 关联 trace」声明；L7/L85/L531 三处口径混乱 | ⚠️ **声明到位 口径混乱**（见 r1-漂-3） |
| **M10** Langfuse | `get_client().get_current_trace_id()` | ❌ M9 plan 未提及（M11/M10 内部用法） | N/A（M9 不直接调 Langfuse） |
| **M11** RAGAS | `trace_id` 关联 `get_client().get_current_trace_id()` | 风险表 L734 标注「M11 RAGAS 不直接调 M9」 | ✅ **对齐**（M9 不消费 M11） |
| **M11** RAGAS | `graph.ainvoke()` 直接调，不走 M8/M9 | 风险表 L734 明示 | ✅ **对齐** |
| **M12** Hardening | `prevent_thread_lock=True, inbrowser=False` prod 部署 | 修订记录 L798 声明；Task 14 L649-651 主体未补 | ⚠️ **声明到位 主体未回填**（见 r1-漂-5） |
| **M12** Hardening | `APISettings.cors_origins` 按 env 切换 | Task 1 L201 `cors_origin: str = "http://localhost:7860"` 硬编码默认，**未联动 `gradio_server_port`** | ⚠️ **半到位**（r1 review P1-11 未消化） |
| **M12** Hardening | `engine.dispose()` lifespan 关闭 | M9 不感知 | ✅ **对齐**（M9 不影响 lifespan） |

**跨 M 一致性总结**：
- **完全对齐**：M0（端口）/M1（基本字段）/M2/M3/M4（基本）/M5（基本）/M6/M11——8 个 M 联动基本对齐
- **声明到位 主体未回填**：M0（healthcheck）/M4（进度 404 提示）/M5（URL 验证）/M8（CORS + chat_timeout + /file 端点）/M12（inbrowser=False）——5 个 M 联动有声明无主体
- **轻度漂移**：M1（`last_message_at` 未消费）/M1+M8（`idempotency_key` 未消费）/M8（`request_id` 字段命名 vs M9 `trace_id` 渲染——见 r1-漂-2）/M10（口径混乱——见 r1-漂-3）/M12（cors_origin 联动未做）——5 个 M 联动有漂移
- **依赖未标注**：M7（`answer_chitchat_node` + `fallback_message` 在 M9 chat tab 渲染）——1 个 M 联动缺标注

**关键发现**：跨 M 一致性**整体对齐 + 5 项声明层到位但主体未回填 + 5 项轻度漂移**——比 r1 review 揭示的更复杂，主要原因是 r1 修复在「声明层」展开但未回填到「主体层」，导致 M 联动声明有但实现无。

---

## 4. 风险表补全质量

| 维度 | 评估 | 说明 |
|------|------|------|
| **原风险行保留** | ✅ **6 行原风险全保留** | L743-753 6 行原风险全保留（Gradio 5.0+ Chatbot 强制参数 / BrowserState 5.0+ / Source regex / Ingest 轮询阻塞 / CORS / image_ref / 中文 chunk / 4 tab 状态串扰 / pytest rootdir） |
| **M9 特有避雷段** | ⚠️ **P0-M9-1~4 / P1-M9-1~3 与 r1 编号冲突** | L757-769 已有 4 + 3 项避雷段；r1 修订记录 L777-799 引入 P0-1/2/3、P1-1~11、P2-1~8——**两套编号体系并存**（见 r1-漂-6） |
| **r1 已修条目追加** | ❌ **未追加** | 风险表 L743-753 **完全无 r1 已修条目**——与 M8 r1 风格（M8 风险表追加 18 行 r1 已修）不一致 |
| **曾被否决的替代方案** | ⚠️ **仅原风险行有（部分）** | 原风险行 L743-753 有「曾被否决的替代方案」列（r1 review 之前就有）；r1 已修条目**无替代方案列**——M8 r1 最有价值的部分在 M9 r1 缺失 |
| **风险条目粒度** | ⚠️ **原风险粒度粗** | 6 行原风险是「高层风险」（如「CORS：Gradio 7860 调 FastAPI 8000 跨域」），r1 修复（CORS 集成测试、healthcheck、image fallback、loading、toast、inbrowser=False 等 22 项）**无独立风险条目** |
| **跨 M 风险显式标注** | ⚠️ **M7 联动 / M8 P0-1 联动** | 风险表 L741-752 隐式依赖 M7 graph chitchat（**未显式标注**）；M8 P0-1 chat 超时保护在 r1 修订记录 L800 提了「chat_timeout 30s」但风险表无独立行 |
| **衍生新问题风险表** | ❌ **6 项 r1 衍生漂移未补入风险表** | r1-漂-1~6 在本 review 发现但 plan 风险表未追加（r2 review 后应补入） |

**风险表补全质量评估**：**不足**——6 行原风险保留完整；P0-M9-1~4 / P1-M9-1~3 避雷段保留；但 r1 修复 22 项**完全未进入风险表**，且 r1 衍生 6 项漂移也未补入。这是 r1 修复的「声明层 vs 主体层」脱节在风险表上的体现。

---

## 5. 落地建议

### 5.1 r2 必改（P0 阻塞，动手前必看）

1. **r1-漂-1**（P0 阻塞）：**plan 主体 Tasks 1-16 大规模回填 22 项 r1 修复**——按声明逐项回填到对应 Task 主体 + Files 表 + DoD 表（见 §1.4 22 项统计表「主体未回填」列）。**估算工作量：~1 个工作日**（200 行代码 + 50 行 CSS + 30 行测试代码）
2. **r1-漂-2**（P0 漂移）：**`ChatResponse` 字段命名 trace_id/request_id 在 M9 plan 全文统一**（与 M8 r2 新-1 同步）——L7/L85/L105/L531 + L800 5 处统一为同一命名（推荐 A：`trace_id`）

### 5.2 r2 应改（P1 重要）

3. **r1-漂-3**（P1 漂移）：**M9 plan 加「Langfuse 链路字段命名规范」节**——明确 `X-Request-Id` / `request_id` / `trace_id` / `Langfuse trace.id` 四名同串规则
4. **r1-漂-4**（P1 漂移）：**风险表追加 22 行 r1 已修条目**——格式与 M8 r1 风险表一致，含「曾被否决的替代方案」列

### 5.3 r2 可选优化（实施阶段复核即可）

5. **r1-漂-5**（P2 衍生）：Task 14 L649-651 `launch_ui` 改 4 参数版本（含 `prevent_thread_lock=True, inbrowser=False, share=False, allowed_paths=["/data"]`）——与 r1-漂-1 同步即可
6. **r1-漂-6**（P2 衍生）：**M9 避雷段编号体系统一**——P0-M9-1~4 / P1-M9-1~3 重命名「review 衍生 P0/P1」或合并入 r1 编号

### 5.4 跨 M 契约验收点

- **M0**：端口 7860 ✅；healthcheck 探测 ⚠️（声明到位 主体未回填）
- **M1**：复合索引 ✅；`last_message_at` ⚠️（未消费）；`idempotency_key` ⚠️（M1/M8 已就位 M9 未对接）
- **M2**：Authorization Header ✅；logout 204 ✅；限速挂 M8 ✅
- **M3**：`make_llm` 工厂间接链路一致 ✅；TEI 18080 端口 ✅
- **M4**：进度 404 提示 ⚠️（声明到位 主体未回填）
- **M5**：URL 验证 ⚠️（声明到位 主体未回填）
- **M6**：Confluence auth_type ✅
- **M7**：`answer_chitchat_node` ⚠️（依赖未标注）；`fallback_message` ⚠️（M9 chat 503 路径未渲染）
- **M8**：CORS ⚠️（声明到位 主体未回填）；chat_timeout ⚠️（声明到位 主体未回填）；`X-Request-Id` 命名 ⚠️（见 r1-漂-2）；`/file` 端点 ⚠️（声明到位 主体未回填）；`Idempotency-Key` ⚠️（未对接）
- **M10**：Langfuse `X-Request-Id` 关联 ⚠️（口径混乱——见 r1-漂-3）
- **M11**：不走 M9 ✅；`graph.ainvoke()` 直接调 ✅
- **M12**：`prevent_thread_lock=True, inbrowser=False` ⚠️（声明到位 主体未回填——见 r1-漂-5）；`cors_origin` 联动 ⚠️（r1 review P1-11 未消化）

### 5.5 TDD 顺序建议

- **Day 1**（Tasks 1-5）：UISettings / theme / APIClient / AuthState / errors——**P1-11 cors_origin 联动**可顺手修
- **Day 2**（Tasks 6-7）：login / sessions tab——**P1-7 logout redirect** + **P1-9 confirm 删除** 必补
- **Day 3**（Task 8-11）：chat tab 核心——**P1-1 loading** + **P1-2 toast** + **P1-3 auto-scroll** + **P1-4 keyboard** + **P1-10 UpstreamError 捕获** 必补
- **Day 4**（Tasks 12-13）：ingest tab——**P1-5 file size** + **P1-6 URL validation** + **P2-2 404 提示** 必补
- **Day 5**（Tasks 14-16）：装配 + E2E——**P0-1 CORS 集成测试** + **P0-2 healthcheck** + **P2-7 inbrowser=False** + **P2-8 dataclass** 必补

### 5.6 抄 M8 r1 范本的结构闪光点（值得 M9 复制）

- **M8 修订记录 → 主体回填**：M8 r1 18 项每项都在 Task GREEN 段找到对应代码（见 M8 r2 review §1.4 100% 到位统计）——**M9 应按此模式重做主体回填**
- **M8 风险表 18 行 r1 已修 + 替代方案列**（L1363-1411）：每条都有「曾被否决的替代方案」提供决策上下文——**M9 风险表应追加 22 行同格式**
- **M8 跨 M 联动表**（L198-207）：显式标注 M7 review 影响本 M 的 5 项 P0——**M9 跨 M 联动段应补 M7/M8 联动（M7 answer_chitchat_node + M8 chat_timeout + M8 Idempotency-Key + M8 /file 端点）**
- **M8 5 service health check 并行**（L412-538）：`asyncio.gather` + `ServiceHealth` 类 + `HealthResponse.services`——**M9 进度轮询 IngestProgress 借鉴此模式**
- **M8 `settings.health.*` 配置化**：URL/timeout/auth 全部从 settings 读——**M9 `UISettings` 借鉴此模式（`theme_bg` / `theme_accent` / `font_family` / `cors_origin` / `gradio_server_*`）**

---

## 6. 总结

**M9 plan r1 修复质量**：**声明层完整、主体层缺失**——22 项 r1 修复在修订记录 L777-799 全部声明到位（CORS 集成测试 / healthcheck / image fallback / loading / auto-scroll / keyboard / file size / URL validation / logout redirect / 401 跟踪 / confirm 删除 / toast 错误 / CSS overflow-wrap / inbrowser=False / prevent_thread_lock / dataclass ChatResult / mock gr.Progress / mock state 隔离 / mobile responsive / 引用编号统一 / etc.），**但 plan 主体 Tasks 1-16 + Files 表 + DoD 表 + 风险表完全未同步**。这是 RAG V1 路线中**「声明层 vs 主体层」脱节最严重的 r1 修复**——M8 r1 18 项全回填到主体（见 M8 r2 review §1.4 100% 到位），M9 r1 22 项**0/22 全回填**。

**M9 plan 跨 M 一致性**：**整体对齐 + 5 项声明到位主体未回填 + 5 项轻度漂移 + 1 项依赖未标注**——M0（端口 ✅ / healthcheck ⚠️）/M1（基本 ✅ / last_message_at ⚠️ / idempotency_key ⚠️）/M2 ✅/M3 ✅/M4（基本 ✅ / 进度 404 ⚠️）/M5（基本 ✅ / URL 验证 ⚠️）/M6 ✅/M7（基本 ✅ / chitchat ⚠️ 依赖未标注 / fallback_message ⚠️ 未渲染）/M8（CORS ⚠️ / chat_timeout ⚠️ / X-Request-Id 命名 ⚠️ / /file ⚠️ / Idempotency-Key ⚠️）/M10（口径混乱 ⚠️）/M11 ✅/M12（inbrowser=False ⚠️ / cors_origin 联动 ⚠️）。

**M9 plan 可立即实施度**：**低**——**22 项 r1 修复声明与主体脱节是当前最大阻塞**；3 项 r1 衍生 P0 漂移（修订记录 vs 主体脱节 + 字段命名混乱 + Langfuse 口径混乱）也需 r2 必改。修完 6 项 r2 必改 + 应改（共 6 项）+ Task 主体回填（~1 工作日）后即可进入 implementation 阶段。

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M9-review-r2 | 2026-06-11 | r2 review（22 项 r1 修复 0/22 主体回填验证 + 6 项 r1 衍生漂移 + 12 M 跨 M 一致性 + 风险表补全质量评估） |
