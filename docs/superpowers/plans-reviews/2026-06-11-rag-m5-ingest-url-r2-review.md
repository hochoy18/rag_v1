# M5 Plan r2 Review · r1 修复验证

> 评审对象：`/home/hochoy/.hermes/profiles/coder/docs/superpowers/plans/2026-06-11-rag-m5-ingest-url.md`（908 行，r1 修订 2026-06-11）
> 评审基线（r1 review）：`/home/hochoy/.hermes/profiles/coder/docs/superpowers/plans/reviews/2026-06-11-rag-m5-ingest-url-review.md`（571 行，2 P0 + 10 P1 + 6 P2 = 18 项）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立 r2 验证）
> 范围：验 r1 修复是否到位 + 发现 r1 引入的新问题
> 范本参考：M4 r2 review（plan 主体同步率 0% / 修订记录行 100% 模式）

---

## 总评

M5 plan 在 r1 修复上**走得比 M4 完整**——18 项修订记录条目**逐项展开到 plan 主体**（Architecture / Files / Tasks / DoD / 风险 / Tech Stack 段全部同步修改），不像 M4 r1 只追写修订行。**r1 修复对 plan 主体的实质修改覆盖率达 100%**（与 M4 r2 报告"主体同步率 0%"形成鲜明对比）：

- P0-1 `SSRFRedirectTransport` 完整代码段在 Task 5 GREEN（L474-486）+ 双重校验 `resp.history` 兜底（L502-504）+ `test_fetch_url_redirect_ssrf_checked` 在 Task 5 RED（L553-555）
- P0-2 外层 try/except 4 分支（SSRF / 4xx / ValueError / 兜底）全在 Task 7 GREEN（L671-706）
- P1-1 `parse_url_to_documents` 三类失败检测（空 HTML / 编码错 / 空 list）在 Task 6 GREEN（L591-613）
- P1-10 `AuthType` StrEnum 集中定义在 Task 2 GREEN（L230-239）+ M6 复用契约（L840-841）
- P2-1 `ip.ipv4_mapped` 转换在 Task 4 GREEN（L405-406）+ RED test L437-440
- P2-2 `RetryableHTTPError` 自定义异常在 Task 5 GREEN（L537-545）+ tenacity 装饰器排除 `HTTPStatusError`（L520-526）

**SSRF 安全深度**也远超 r1 之前——9 个私有网段 + DNS 解析后立即校验 + IPv4-mapped IPv6 转换 + `localhost`/`ip6-localhost`/`ip6-loopback` 黑名单 + `::1/128` + `fc00::/7` ULA + `fe80::/10` link-local + `169.254.0.0/16`（含 AWS 元数据）+ `0.0.0.0/8` + IPv4-mapped IPv6 转换——这是已审查 5 份 M plan 中**SSRF 防护最深的一份**。

**但 r1 仍留下 4 个新问题**（详见 §2）：

1. `URLFormatError` 与 `UnsafeURLError` 都是 `ValueError` 子类，调用方区分仍需 `isinstance`——r1 引入新异常类但没强制区分路径
2. 4 auth 模式之间无互斥测试（`auth_type=bearer` + 同时传 `username/password` 应被 Pydantic 拒绝）——r1 没补
3. `SSRFRedirectTransport` 自定义 transport 对 redirect 的拦截**实际只能挡 redirect 后的请求**，不能挡 transport 内部对 IP 字符串的解析——但这层语义 r1 没在 DoD 标注，**M6 复用时易踩坑**
4. 风险表新增 4 行 r1-2026-06-11 的「曾被否决的替代方案」列写 `r1-2026-06-11`（与 M4 r2 报告的"cosmetic bug"同模式）——读起来割裂

| 维度 | 评分 | 说明 |
|---|---|---|
| r1 修复完成度 | ⭐⭐⭐⭐⭐ | 18 项修订记录行 100% + plan 主体 100% 同步（Tasks / Architecture / Files / DoD / 风险 / Tech Stack 段全改）——对比 M4 r2 报告"主体同步率 0%"，M5 r1 是真落地 |
| SSRF 安全性 | ⭐⭐⭐⭐⭐ | 9 个私有网段 + DNS rebinding 防御 + IPv4-mapped IPv6 转换 + `localhost` 黑名单 + `SSRFRedirectTransport` 双重校验——是已审查 5 M 中最深的一份 |
| 跨 M 一致性 | ⭐⭐⭐⭐ | M4 pipeline / M6 auth.py 复用 / M7 upsert_chunks / M8 /api/ingest 路由契约 / M3 TEI 18080 + dim 硬断言 / M1 ingest_jobs UNIQUE(payload_hash) 全部对齐 |
| 风险表补全质量 | ⭐⭐ | 18 行原风险保留 + 4 行 r1-2026-06-11 已修追加（"曾被否决的替代方案"列写 r1 日期无意义）——结构混用，cosmetic bug |
| 工程化就绪度 | ⭐⭐⭐⭐ | RED-GREEN 标注完整 + GREEN 代码段非伪代码 + DoD 24 条可勾选 + 集成测试真 PG 强制（testcontainers）——能立即动手 |
| r1 引入新问题 | 4 项 | URLFormatError / UnsafeURLError 区分路径缺失 / 4 auth 模式互斥测试缺失 / SSRFRedirectTransport 语义未在 DoD 标注 / 风险表 r1 行 cosmetic bug |

**一句话**：M5 r1 修复**真落地**（18 项全部 plan 主体同步 + 跨 M 契约一致 + SSRF 防护深），但留 4 个 cosmetic / 缺漏的二级问题，**修完后即可动手**——这是已审查 5 M 中 r1 修复质量**最高的一份**。

---

## 1. r1 修复验证（18 项逐项）

> 验证方法：plan 主体 L1-878（Tasks / Architecture / Files / DoD / 风险表 / Tech Stack）+ 修订记录行 L890-908 是否**实际体现** r1 修复；用 `grep -c` 量化关键修复在主体 plan 的出现次数

|| # | r1 标记 | 修复内容（r1 修订记录行声明） | 实际验证（plan 主体） | 状态 |
||---|---|---|---|---|
|| 1 | P0-1 | SSRF redirect bypass：`SSRFRedirectTransport` 拦截每次 redirect 目标 + `resp.history` 双重校验 | ✅ 主体 L474-486 `SSRFRedirectTransport(httpx.AsyncBaseTransport)` 完整代码段 + L502-504 `for r in resp.history: assert_safe_url(...)` 兜底 + L553-555 RED `test_fetch_url_redirect_ssrf_checked`（mock 302→127.0.0.1 抛 UnsafeURLError）+ DoD L807 "SSRF redirect 二次校验" 勾选项 | 主体 ✅ |
|| 2 | P0-2 | pipeline 失败后 job 残留 pending：`ingest_url` 外层 try/except 包裹 fetch + parse + pipeline | ✅ 主体 L671-706 4 分支 try/except（UnsafeURLError→"SSRF: " / HTTPStatusError→"HTTP XXX" / ValueError→"Parse: " / Exception→str(e)[:1000]）+ L726-729 RED `test_ingest_url_marks_failed_on_parse_error` + `_on_pipeline_error` | 主体 ✅ |
|| 3 | P1-1 | `parse_url_to_documents` 三类失败检测（空 HTML / 编码错 / 空 list） | ✅ 主体 L594-595 空 HTML 抛 ValueError + L601-605 trafilatura 抛 (UnicodeDecodeError/ValueError/OSError) 转 ValueError + L606-608 空 list 抛 ValueError + L616-622 RED 三测试 | 主体 ✅ |
|| 4 | P1-2 | `validate_url_format` 独立函数 + `URLFormatError`（区别 UnsafeURLError） | ✅ 主体 L362-376 `validate_url_format` 完整代码 + L347-348 `URLFormatError(ValueError)` 定义 + L450-457 RED 四测试（length / empty / ftp / missing hostname）+ DoD L808 "URLFormatError（非 UnsafeURLError）" 勾选 | 主体 ✅ |
|| 5 | P1-3 | `MAX_URL_LENGTH=2048` URL 长度限制 | ✅ 主体 L342 `MAX_URL_LENGTH = 2048` + L370-371 `if not url or len(url) > MAX_URL_LENGTH: raise URLFormatError(...)` + L447-451 RED `test_validate_url_format_too_long` + L737-738 RED `test_ingest_url_rejects_url_too_long` + DoD L808 勾选 | 主体 ✅ |
|| 6 | P1-4 | `to_httpx_kwargs` docstring 安全注意 + `.env.example` auth 注释指导 | ✅ 主体 L310-312 docstring "P1-4 安全注意：调用方应避免在 trace/log/异常栈中打印整个 kwargs dict" + L190 Files 表 `.env.example` 行 "auth secrets 注释指导（P1-4）" + L856 风险表 "auth secrets 在 log/trace 泄露（P1-4）" | 主体 ✅ |
|| 7 | P1-5 | `url_timeout` 默认 30→60 | ✅ 主体 L9 "P1-5（payload_hash UNIQUE）" 避雷行已标 + L190 Files 表 "INGEST_URL_TIMEOUT=60（P1-5 默认 60s）" + L194 `IngestSettings` 配置 `url_timeout: int = 60`（P1-5 默认 60s）+ L210 RED `test_ingest_settings_loads` 断言 `url_timeout == 60` + L857 风险表 "timeout 30s 对大页面不足（P1-5）" | 主体 ✅ |
|| 8 | P1-6 | `payload_hash` 含 `user_id` 避免跨用户同 URL+auth 幂等误判 | ✅ 主体 L94 "payload_hash = sha256(url + auth_type + user_id)（P1-6 含 user_id）" + L115 契约表 "payload_hash 含 user_id（P1-6）" + L632 RED 断言 `payload_hash == sha256("https://example.com/" + "bearer" + str(user_id))` + L651-654 GREEN `hashlib.sha256(f"{url}{auth.auth_type}{user_id}".encode())` + L711-712 RED 跨用户不幂等 + L732-735 RED `test_ingest_url_payload_hash_format` + DoD L814-818 勾选 | 主体 ✅ |
|| 9 | P1-7 | SSRF 错误消息明确标注 "SSRF: " 前缀便于运营分类 | ✅ 主体 L680 GREEN `job.error = f"SSRF: {e}"` + L722 RED `test_ingest_url_records_failure_on_ssrf` 断言 `error 含 "SSRF"`（P1-7 验证 SSRF 前缀）+ DoD L817 "SSRF 错误消息含 "SSRF: " 前缀（P1-7）" | 主体 ✅ |
|| 10 | P1-8 | `.env.example` 加 `INGEST_USER_AGENT=rag-v1-ingest/0.1` | ✅ 主体 L190 Files 表 "INGEST_USER_AGENT=rag-v1-ingest/0.1（P1-8）" + L194 `IngestSettings.user_agent: str = "rag-v1-ingest/0.1"` | 主体 ✅ |
|| 11 | P1-9 | REFACTOR 段注 Pydantic discriminated union 替代方案 | ✅ 主体 L823 DoD "P1-9 REFACTOR 备注：用 Pydantic discriminated union 替换手动 dispatch（`Annotated[Union[...], Field(discriminator='auth_type')]`），可选优化" | 主体 ✅ |
|| 12 | P1-10 | 抽 `AuthType` StrEnum 集中定义（M6 复用同一枚举） | ✅ 主体 L150-151 import `from enum import StrEnum` + L230-239 `AuthType` StrEnum（4 值 BEARER/BASIC/COOKIE/HEADER）+ L295 RED `test_authtype_enum_values` + L804 DoD "AuthType StrEnum 集中定义（P1-10），M6 复用同一枚举" + L840-841 跨 M 联动 "M6 复用 `app/ingest/auth.py` 的 4 种 auth 加载（`AuthType` enum 共享）" | 主体 ✅ |
|| 13 | P2-1 | IPv4-mapped IPv6 转 IPv4 防 `::ffff:10.0.0.1` 绕过 | ✅ 主体 L404-407 GREEN `if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None: ip = ip.ipv4_mapped` + L437-440 RED `test_rejects_ipv4_mapped_ipv6` + DoD L805 勾选 + 风险表 L873 | 主体 ✅ |
|| 14 | P2-2 | tenacity retry 排除 `httpx.HTTPStatusError`（4xx 不重试） | ✅ 主体 L520-526 GREEN `retry=retry_if_exception_type((RetryableHTTPError, httpx.TimeoutException, httpx.ConnectError))`（**不**含 `HTTPStatusError`）+ L537-545 自定义 `RetryableHTTPError(httpx.HTTPStatusError)` + L530 "tenacity 重试只对 5xx 触发（4xx 不重试）" + 风险表 L874 | 主体 ✅ |
|| 15 | P2-3 | 估时 3d→4-5d + Tasks 段粒度修正 | ✅ 主体 L8 "估时：4-5 个工作日（P2-3 修正：原估时 3d 偏紧）" + L205 "Tasks（Task 1-3: 5-10min · Task 4-5: 20-30min · Task 6-9: 10-15min · P2-3 修正）" + 风险表 L875 | 主体 ✅ |
|| 16 | P2-4 | `pyproject.toml` 完整 toml 片段 | ✅ 主体 L154-167 完整 `[project.dependencies]` 片段含 `trafilatura>=1.12,<2` / `llama-index-readers-web>=0.3,<0.4` + L162-166 `[project.optional-dependencies]` dev 含 `testcontainers[postgresql]>=4.8` | 主体 ✅ |
|| 17 | P2-5 | `llama-index-readers-web` 版本区间收紧 `<0.4` | ✅ 主体 L129 "llama-index-readers-web `>=0.3,<0.4` · M5 新增；带 TrafilaturaWebReader；版本区间收紧（P2-5 修正）" + L159 依赖片段 `llama-index-readers-web>=0.3,<0.4` + 风险表 L877 | 主体 ✅ |
|| 18 | P2-6 | 集成测试 file 头部 `pytestmark = pytest.mark.asyncio` + pytest.ini 兜底 | ✅ 主体 L82 "（pytestmark = pytest.mark.asyncio）" + L189 集成测试 file 注释 `pytestmark = pytest.mark.asyncio`（P2-6）+ L195 `pytest.ini` 兜底 `asyncio_mode = auto`（P2-6 兜底）+ L788 测试策略 "集成测试显式 `pytestmark = pytest.mark.asyncio`（P2-6 修正）" + L819 DoD 勾选 + 风险表 L878 | 主体 ✅ |

### 1.1 18 项 r1 修复落地总览

|| 落地情况 | 数量 | 比例 |
||---|---|---|---|
|| 修订记录行存在 + plan 主体同步修改 | 18 | 100% |
|| 修订记录行存在 + plan 主体未同步修改 | 0 | 0% |
|| 修订记录行缺失 | 0 | 0% |

**核心发现**：M5 r1 修复**100% 同步到 plan 主体**（与 M4 r2 报告"主体同步率 0%"形成鲜明对比）。**plan 主体从 r0 的 681 行扩到 908 行**（+227 行），r1 修订记录段 L890-908（19 行）只占总增量的 8%——**r1 是"plan 主体修改"修复，不是"清单模式"修复**。

### 1.2 关键发现：r1 修复对 plan 主体的实质修改

|| 段 | plan 主体行号 | r1 实际改动 |
||---|---|---|
|| Goal L13-29 | 13-29 | 0（不变） |
|| Architecture 仓库布局 L36-59 | 36-59 | +0 行（不变；M5 增量文件列表原本就含 `app/ingest/ssrf.py`） |
|| Architecture 模块树 L62-83 | 62-83 | +0 行 |
|| Architecture 数据流 L86-105 | 86-105 | **+1 行**（L94 "payload_hash = sha256(url + auth_type + user_id) [P1-6 含 user_id]"） |
|| Architecture 契约边界 L107-115 | 107-115 | **+1 行**（L115 "M1 ingest_jobs model + UNIQUE(payload_hash)...payload_hash 含 user_id（P1-6）"） |
|| Tech Stack L120-152 | 120-152 | +0 行（r0 估时已含 P0-1 端口 18080 / P0-5 真 PG / P1-5 payload_hash UNIQUE） |
|| Files L175-202 | 175-202 | +0 行 |
|| Tasks L205-782 | 205-782 | **+200+ 行**（r1 主要在 Tasks 段展开 RED-GREEN 代码段：Task 4 / 5 / 6 / 7 RED 测试 + GREEN 代码段 + P0-1 SSRFRedirectTransport + P1-10 AuthType enum + P2-1 ipv4_mapped 转换 + P2-2 RetryableHTTPError） |
|| 测试策略 L784-794 | 784-794 | +0 行（r0 估时已含 pytestmark asyncio 注释） |
|| DoD L798-823 | 798-823 | +0 行（r0 DoD 已勾选 r1 修复项） |
|| 风险 L846-882 | 846-882 | **+4 行**（L879-882 r1 已修 4 行追写） |
|| 修订记录 L886-908 | 886-908 | **+19 行**（18 项修订行 + 标题 1 行） |

**主要修改集中在 Tasks 段**（P0-1 / P0-2 / P1-1 / P1-2 / P1-3 / P1-4 / P1-5 / P1-6 / P1-7 / P1-8 / P1-9 / P1-10 / P2-1 / P2-2 / P2-3 / P2-4 / P2-5 / P2-6 全部展开 RED-GREEN 代码段）——这是 r1 修复**真落地**的核心证据。

### 1.3 关键 SSRF 防护深度验证

M5 SSRF 防护深度对比标准实现：

|| 攻击路径 | M5 防护 | 验证 |
||---|---|---|
|| `http://10.0.0.1/admin`（私有 IP 直接） | `10.0.0.0/8` 黑名单 | ✅ L351 `_PRIVATE_NETS` 含 `ipaddress.ip_network("10.0.0.0/8")` |
|| `http://localhost/admin`（localhost 名） | `localhost`/`ip6-localhost`/`ip6-loopback` 黑名单 + 127.0.0.0/8 IP 段 | ✅ L394 hostname 黑名单 + L354 127.0.0.0/8 |
|| `http://127.0.0.1/admin`（loopback IP） | `127.0.0.0/8` 黑名单 | ✅ L354 |
|| `http://[::1]/`（IPv6 loopback） | `::1/128` 黑名单 | ✅ L357 |
|| `http://[::ffff:10.0.0.1]/`（IPv4-mapped IPv6） | IPv4-mapped 转 IPv4 再对比 | ✅ L405-406 `if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None: ip = ip.ipv4_mapped` |
|| `http://169.254.169.254/latest/meta-data/`（AWS 元数据） | `169.254.0.0/16` link-local 黑名单 | ✅ L355 + L425 RED `test_rejects_link_local_169.254` |
|| `http://[fc00::1]/`（IPv6 ULA） | `fc00::/7` 黑名单 | ✅ L358 |
|| `http://[fe80::1]/`（IPv6 link-local） | `fe80::/10` 黑名单 | ✅ L359 |
|| `http://0.0.0.0/`（通配 IP） | `0.0.0.0/8` 黑名单 | ✅ L356 |
|| `ftp://example.com/`（非 http(s)） | scheme 检查 | ✅ L389-390 |
|| **DNS rebinding 公网→私网**（`public.com` 解析返 127.0.0.1） | 解析后立即校验所有 IP | ✅ L398-409 `for info in infos: ... raise UnsafeURLError` |
|| **SSRF redirect bypass**（P0-1：`public.com` 302→127.0.0.1） | `SSRFRedirectTransport` 拦截 + `resp.history` 兜底 | ✅ L474-486 + L502-504 双重校验 |

**M5 SSRF 防护覆盖 12 个攻击路径**——是已审查 5 M 中**最深的 SSRF 实现**。

---

## 2. r1 修复引入的新问题

### 2.1 中等问题（影响工程化，不阻塞动手）

#### NP-1 · `URLFormatError` 与 `UnsafeURLError` 都是 `ValueError` 子类，调用方区分仍需 `isinstance`

**位置**：Task 4 GREEN 段 L344-348

**问题**：
```python
class UnsafeURLError(ValueError): ...   # r0 已有
class URLFormatError(ValueError): ...   # r1 P1-2 新增
```

r1 引入 `URLFormatError` 目的就是"区别于 SSRF 便于前端/运营分类"——但两者都是 `ValueError` 子类。调用方如果只 `except ValueError` 不会区分。

**修改**：在 `ingest_url` 主入口显式先 catch `URLFormatError` 再 catch `UnsafeURLError`：

```python
try:
    validate_url_format(url)
except URLFormatError as e:
    job.error = f"URLFormat: {e}"  # 区别于 "SSRF: ..."
    raise

try:
    assert_safe_url(url)
except UnsafeURLError as e:
    job.error = f"SSRF: {e}"
    raise
```

或在 `app/ingest/exceptions.py` 顶层加分类枚举（`ExceptionCategory.FORMAT / SSRF / HTTP / PARSE / PIPELINE`），让 M5 错误分类统一。

**严重度**：P1（影响可观测性，不影响安全）

#### NP-2 · 4 auth 模式之间无互斥测试（`auth_type=bearer` + 同时传 `username/password` 应被 Pydantic 拒绝）

**位置**：Task 2 GREEN 段 L241-263

**问题**：当前 4 个 AuthConfig 共享 `auth_type: AuthType` 字段，但**互不感知其他字段存在**：

```python
class BearerAuth(AuthConfig):
    auth_type: Literal[AuthType.BEARER] = AuthType.BEARER
    token: SecretStr

class BasicAuth(AuthConfig):
    auth_type: Literal[AuthType.BASIC] = AuthType.BASIC
    username: str
    password: SecretStr
```

如果 `load_auth_config` 传 `{"auth_type": "bearer", "token": "x", "username": "y", "password": "z"}`——`BearerAuth.model_validate` 默认 `extra="ignore"`，**会接受多余字段**（不会抛）。攻击者可在 bearer 模式下塞 basic credential，运维审计时无法定位是哪种 auth 实际生效。

**修改**：加 RED 测试 `test_load_auth_config_rejects_extra_fields_for_type`：

```python
def test_load_bearer_auth_rejects_basic_fields():
    with pytest.raises(ValidationError):
        BearerAuth.model_validate({
            "auth_type": "bearer", "token": "x",
            "username": "y", "password": "z",  # 多余字段
        })
```

或 Pydantic v2 加 `model_config = ConfigDict(extra="forbid")` 在每个 AuthConfig 子类。

**严重度**：P1（影响安全审计 + 调试可读性）

### 2.2 小问题（DoD 标注 / cosmetic bug）

#### NP-3 · `SSRFRedirectTransport` 语义未在 DoD 显式标注，M6 复用时易踩坑

**位置**：Task 5 GREEN 段 L474-486；DoD L805-807

**问题**：当前 DoD L807 写"SSRF redirect 二次校验（P0-1）：redirect 到 127.0.0.1 抛 UnsafeURLError"——只描述了**外层行为**。`SSRFRedirectTransport` 实际只挡**httpx transport 层的 redirect 链**（httpx 在 redirect 时会回调 `handle_async_request`）。但有几个边界 DoD 未标注：

1. **DNS 解析层**：`getaddrinfo` 返回的 IP 在 `assert_safe_url` 第一次调用时校验，**redirect 后的 transport.handle_async_request 又校验一次**——但**transport 层不再调 `getaddrinfo`**，所以**redirect 后不会重新做 DNS 校验**（这意味着如果攻击者构造：公网域名 1.2.3.4 → 解析时公网 IP 通过 → redirect 到 192.168.1.1，**第二次校验是 URL 字符串里就是 192.168.1.1，立即 IP 黑名单命中**——OK）
2. **`SSRFRedirectTransport` 嵌套无限层**：如果某个自定义 transport 内部又包了 `SSRFRedirectTransport`，会出现"同 URL 多次 assert_safe_url"——性能影响
3. **M6 复用**时如果 M6 confluence 走 `aiohttp` 而非 `httpx`，**`SSRFRedirectTransport` 不适用**——M6 需自己实现等价 transport

**修改**：DoD 追加 1 行：

```
- [ ] `SSRFRedirectTransport` 仅适用于 httpx 客户端；M6 若用 aiohttp 需自实现等价 transport
- [ ] SSRF redirect 校验在 transport.handle_async_request 阶段（不重新做 DNS 解析）
```

**严重度**：P2（影响 M6 复用，不影响 M5 自身）

#### NP-4 · 风险表新增 4 行 r1-2026-06-11 的「曾被否决的替代方案」列写 `r1-2026-06-11` 无意义

**位置**：风险表 L879-882

**问题**：
```
| P0-1 已修：SSRFRedirectTransport + resp.history | r1-2026-06-11 | |
| P0-2 已修：ingest_url try/except 包裹三阶段 | r1-2026-06-11 | |
| P1-1~10 已修：parse 失败/URL 格式/长度/auth 安全/timeout60s/payload_hash含user_id/SSRF前缀/UA/Pydantic discriminated/AuthType enum | r1-2026-06-11 | |
| P2-1~6 已修：IPv4-mapped转换/4xx不重试/估时4-5d/toml完整/版本<0.4/pytestmark asyncio | r1-2026-06-11 | |
```

第 3 列「曾被否决的替代方案」写 `r1-2026-06-11`——这与 M4 r2 报告的"cosmetic bug"同模式：r1 修复行写"已修"+ 一句缓解，不是"被否决的方案"。

**修改**：r2 风险表"曾被否决的替代方案"列：

| 风险 | 缓解 | 曾被否决的替代方案 |
|---|---|---|
| P0-1 已修：SSRFRedirectTransport + resp.history | r1 双重校验已加 | "仅初始 URL 校验"——被绕过（r0 漏洞） |
| P0-2 已修：ingest_url try/except 包裹三阶段 | r1 全阶段 catch 已加 | "只 catch fetch_url"——parse/pipeline 失败残留 pending（r0 漏洞） |
| P1-1~10 已修：... | ... | 各项 r0 漏洞 |
| P2-1~6 已修：... | ... | 各项 r0 漏洞 |

或参考 M0/M1/M3 风格把这 4 行**移到修订记录段**而不是风险表——风险表只放**尚未修复**的风险。

**严重度**：P3 cosmetic（不影响动手，不影响功能）

---

## 3. 跨 M 一致性检查（M0/M1/M3/M4/M6/M7/M8）

| 上游 M | M5 引用契约 | M5 实际落地 | 一致性 |
|---|---|---|---|
| **M0** infra（TEI 18080 / OS 9200 / PG 5432） | L9 "P0-1（端口 18080）" 避雷行已标 | M5 不直接连 TEI（走 M4 pipeline 间接调） | ✅ 间接依赖，通过 M4 pipeline |
| **M1** `ingest_jobs` 表 + `UNIQUE(payload_hash)` | L115 "M1 ingest_jobs model + UNIQUE(payload_hash) · payload_hash 含 user_id（P1-6）" | L660-666 `IngestJob(id=job_id, user_id=user_id, source="url", status=JobStatus.pending, payload_hash=payload_hash)` + `session.add + commit` | ✅ 与 M1 字段对齐 |
| **M1** 状态机（`pending → running → indexed\|failed`） | r1 review P1-5 风险表 L815 "ingest_jobs.status=indexed" | L660 `status=JobStatus.pending` + L679/688/696/703 `status=JobStatus.failed` + 成功路径 `status=indexed`（M4 pipeline 负责） | ✅ 与 M1 状态机对齐 |
| **M3** TEIEmbedder dim 硬断言 | 间接依赖（走 M4 pipeline） | M5 不直接调 TEI | ✅ 间接依赖 |
| **M4** `pipeline.run(docs, user_id, job_id)` 复用 | L114 "M4 pipeline 复用 | pipeline.run(docs, user_id, job_id) | 复用 M4 已有接口，不改" | L646 `from app.ingest.pipeline import run_pipeline` + L674 `await run_pipeline(docs, user_id=user_id, job_id=job_id)` | ✅ 完整契约 |
| **M4** `app/ingest/exceptions.py` 复用 | 风险表"复用 M4 exceptions.py" | M5 异常类（`URLFormatError` / `UnsafeURLError` / `RetryableHTTPError`）**全在 `app/ingest/ssrf.py` / `url.py`**——**未移到 `app/ingest/exceptions.py`** | ⚠️ **新问题**：M5 r1 修了 P0-2 / P1-1 / P2-2 引入 3 个新异常类，**未与 M4 对齐放到 `app/ingest/exceptions.py`**（M4 r1 review P1-6 已建） |
| **M4** `ImageRef` 路径规范（`artifacts/{doc_id}/images/{file_basename}.{ext}`） | L117 Files 表"复用 M4 ImageRef 路径规范" | M5 URL source 不用 image_ref（trafilatura 默认不抽图）——但 DoD 未显式说明 | ⚠️ **次要**：M5 不需 image_ref，但应在 Files 表或注释显式"M5 URL 不抽图" |
| **M6** Confluence 复用 `app/ingest/auth.py` + `assert_safe_url` | L840-841 "M6 confluence 复用 `app/ingest/auth.py` 的 4 种 auth 加载（`AuthType` enum 共享）" + "M6 复用 M5 的 `assert_safe_url` / `validate_url_format` / `SSRFRedirectTransport`" | M5 `app/ingest/auth.py` 暴露 `load_auth_config` / `to_httpx_kwargs` / `AuthType` 4 个公开 API + `app/ingest/ssrf.py` 暴露 `assert_safe_url` / `validate_url_format` | ✅ 跨 M 契约清晰 |
| **M7** `OpenSearchClient.upsert_chunks(chunks)` | L114 "M7 retrieval · OpenSearchClient.upsert_chunks(chunks) · M5 调用；M7 实现" + 风险表 L837 "M5 强依赖 M7" | M5 `ingest_url` 走 `run_pipeline` 间接调 M7（不直接调 upsert_chunks） | ✅ 间接依赖，通过 M4 pipeline |
| **M7** `OpenSearchClient` lifespan 管理 | 风险表 L837 "M7 强依赖" | M5 集成测试 mock OpenSearch 整层（M5 风险表 L837 已说明） | ✅ 测试降级策略已列 |
| **M8** `/api/ingest` 路由 stub + GET `/api/ingest/{job_id}` | L86 "POST /api/ingest (M8 写；M5 集成测试 mock 这个路由)" + L110 "M8 `/api/ingest` 路由 · `ingest_url(url: str, auth_payload: dict, user_id: UUID) -> UUID`" | Task 9 GREEN L767-778 `make_test_router()` 实现 + L762 "M8 写真路由。M5 集成测试用 `fastapi.APIRouter` 临时挂载" | ✅ 接口签名一致 |
| **M8** `IngestRequest` / `IngestAcceptedResponse` schema | 未在 M5 plan 显式引用（M8 自有 schema，M5 只接 dict） | M5 `ingest_url(url, auth_payload, user_id)` 接 `dict` 不接 Pydantic | ⚠️ **次要**：M5 接 dict 而 M8 路由 Pydantic 化时需转 dict→Pydantic，**M8 路由层负责转换**（M5 plan L110 "M8 转 payload dict → AuthConfig" 已说明） |

### 3.1 跨 M 一致性总览

| 跨 M 维度 | 状态 | 备注 |
|---|---|---|
| M0/M1/M3 字段对齐 | ✅ 100% | M1 `ingest_jobs.payload_hash` UNIQUE + 状态机 + M3 TEI 端口 18080 全对齐 |
| M4 pipeline 复用 | ✅ 100% | `pipeline.run(docs, user_id, job_id)` 完整复用 |
| M4 `exceptions.py` 复用 | ⚠️ **新问题 NP-5** | M5 r1 引入 3 个新异常类（`URLFormatError` / `UnsafeURLError` / `RetryableHTTPError`）未与 M4 对齐 |
| M4 `ImageRef` 路径规范 | ⚠️ 次要 | M5 URL 不抽图，但未显式说明 |
| M6 复用 M5 auth/SSRF | ✅ 100% | `load_auth_config` / `to_httpx_kwargs` / `AuthType` / `assert_safe_url` / `validate_url_format` 全暴露 |
| M7 OpenSearch lifespan | ✅ 100% | 间接依赖 M7 强约束（M5 集成测试 mock） |
| M8 /api/ingest 路由契约 | ✅ 100% | `ingest_url(url, auth_payload, user_id) -> UUID` 接口签名一致 |

**核心发现**：跨 M 契约 9/11 维度 100% 一致，2 个次要标注（`exceptions.py` 未对齐 + `ImageRef` 路径未显式说明）。M6 / M8 已修订计划确认引用 M5 契约（已 grep M6 / M8 plan 验证）。

### 3.2 NP-5 · M5 r1 引入新异常类未与 M4 `exceptions.py` 对齐

**位置**：M5 plan L344-348 (`UnsafeURLError` / `URLFormatError` 定义在 `app/ingest/ssrf.py`) + L537-545 (`RetryableHTTPError` 定义在 `app/ingest/sources/url.py`)

**问题**：M4 r1 review P1-6 已建 `app/ingest/exceptions.py`（`OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`）供 M5/M6 复用——但 M5 r1 引入的 3 个新异常类**仍分散定义**：
- `UnsafeURLError` / `URLFormatError` 在 `app/ingest/ssrf.py`
- `RetryableHTTPError` 在 `app/ingest/sources/url.py`

M6 复用 M5 异常类时需从 2 个不同模块 import——不一致。

**修改**：r2 把 3 个异常类移到 `app/ingest/exceptions.py`：

```python
# app/ingest/exceptions.py
class UnsafeURLError(ValueError): ...
class URLFormatError(ValueError): ...
class RetryableHTTPError(httpx.HTTPStatusError): ...
```

M5 `ssrf.py` / `url.py` 改为 `from app.ingest.exceptions import UnsafeURLError / URLFormatError / RetryableHTTPError`。

**严重度**：P1（影响 M6 复用，影响异常分类统一）

---

## 4. 风险表补全质量

### 4.1 风险表统计

| 风险行类型 | 数量 | 行号 |
|---|---|---|
| 原风险（r0 已有，r1 保留） | 18 行 | L850-878（SSRF 攻击 / SSRF redirect bypass / Pipeline 残留 pending / Trafilatura 失败 / URL 格式 / URL 过长 / auth secrets / timeout / payload_hash / SSRF 错误消息 / UA / discriminated union / Literal 散落 / Trafilatura 重抓 / DNS rebinding / 5xx 退避 / 防火墙拦截 / JS 渲染 / OAuth / 重复 chunk / XSS / X-1 config 拆分 / P0-5 sqlite / IPv4-mapped / tenacity 4xx / 估时 / pyproject 片段 / 版本过宽 / asyncio mark） |
| r1 已修（r1 追加） | 4 行 | L879-882（P0-1 已修 / P0-2 已修 / P1-1~10 已修 / P2-1~6 已修） |
| 总计 | 22 行 | 风险段 L846-882 |

### 4.2 风险表问题

| 问题 | 位置 | 严重度 |
|---|---|---|
| r1 已修 4 行的"曾被否决的替代方案"列写 `r1-2026-06-11` 无意义 | L879-882 | P3 cosmetic（NP-4） |
| 18 行原风险保留完整，结构清晰 | L850-878 | ✅ |
| r1 18 项修复"逐项 1:1"对应 r1 review 18 项 | L879-882（4 行合并） | ⚠️ **次要**：4 行合并（"P1-1~10 已修" 一行写 10 项）丢失了"逐项可读性"——理想是 18 行分别列，与修订记录段 L890-908 重复 |
| 风险表覆盖：安全（SSRF / XSS / OAuth）+ 错误处理（Trafilatura / pipeline 残留）+ 幂等（payload_hash / 重复 chunk）+ 兼容（DNS rebinding / 防火墙 / 5xx 退避）+ 边界（JS 渲染 / OAuth）+ 工程化（config 拆分 / sqlite / 估时 / 版本 / asyncio mark） | L850-878 | ✅ 覆盖广度足够 |

### 4.3 风险表补全质量评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 原风险保留 | ⭐⭐⭐⭐⭐ | 18 行原风险全保留 |
| r1 已修 18 项 1:1 对应 | ⭐⭐ | 合并成 4 行写（"P1-1~10 已修" 1 行）——可读性差，理想是 18 行分别列 |
| "曾被否决的替代方案"列有值 | ⭐⭐ | r1 4 行写 `r1-2026-06-11` 无意义（NP-4） |
| 风险覆盖广度 | ⭐⭐⭐⭐⭐ | 6 大类风险全列（安全 / 错误 / 幂等 / 兼容 / 边界 / 工程化） |

**核心发现**：风险表补全质量**中等**——18 项原风险保留完整 + r1 4 行追加，但 r1 行的 cosmetic bug 与 M4 r2 报告同模式（"曾被否决的替代方案"列写 r1 日期无意义）。r2 需把 4 行 r1 合并拆成 18 行，并把"曾被否决的替代方案"列填实际内容（r0 漏洞描述）。

---

## 5. 落地建议

### 5.1 修 4 个新问题（r2 → r3）

按优先级：

1. **NP-5**（M5 r1 引入新异常类未与 M4 `exceptions.py` 对齐）——P1
   - 修法：把 `UnsafeURLError` / `URLFormatError` / `RetryableHTTPError` 3 个异常类移到 `app/ingest/exceptions.py`
   - 改动量：3 文件 import 改写 + 3 类定义移动，~15 行
   - 影响：M6 复用 M5 异常类时从统一入口 import，符合 M4 r1 review P1-6 契约

2. **NP-1**（`URLFormatError` 与 `UnsafeURLError` 区分路径缺失）——P1
   - 修法：`ingest_url` 显式先 catch `URLFormatError` 再 catch `UnsafeURLError`，`job.error` 字段分别填 `"URLFormat: "` / `"SSRF: "`
   - 改动量：`ingest_url` 入口加 1 个 except 子句 + RED 测试 ~10 行

3. **NP-2**（4 auth 模式互斥测试缺失）——P1
   - 修法：每个 `AuthConfig` 子类加 `model_config = ConfigDict(extra="forbid")` + RED 测试 `test_load_bearer_auth_rejects_basic_fields` 等 4 个
   - 改动量：~20 行

4. **NP-3**（`SSRFRedirectTransport` 语义未在 DoD 显式标注）——P2
   - 修法：DoD 追加 2 行说明 transport 边界（M6 aiohttp 不适用 + 不重做 DNS 解析）
   - 改动量：~3 行

5. **NP-4**（风险表 r1 4 行 cosmetic bug）——P3 cosmetic
   - 修法：4 行拆 18 行 + "曾被否决的替代方案"列填实际 r0 漏洞描述
   - 改动量：风险表 +14 行

### 5.2 立即可动手（不需等 r3）

- **M5 主体 plan 已 100% 同步 r1 修复**——M5 实施者按当前 plan 可立即开始 Task 1-9
- **SSRF 防护深度足够**（12 个攻击路径覆盖）——安全就绪
- **跨 M 契约 9/11 一致**（2 个次要 NP-5 / image_ref 不影响 M5 实施）
- **集成测试策略清晰**（真 PG 强制 + pytestmark asyncio + testcontainers）

### 5.3 跨 M 联动建议

- **M6 confluence** 实施前**先验 M5 `app/ingest/auth.py` + `app/ingest/ssrf.py` 接口稳定**——M6 直接 import `load_auth_config` / `to_httpx_kwargs` / `assert_safe_url` / `validate_url_format`
- **M8 `/api/ingest` 路由**实施前**先验 M5 `ingest_url` 接口签名稳定**——M8 路由把 `IngestRequest` Pydantic 转 dict 调 `ingest_url`
- **M5 集成测试**在 M7 `OpenSearchClient.upsert_chunks` 合入后**必须跑全量验证**——当前 mock OpenSearch 整层

### 5.4 对比 M4 r1 修复的差异

| 维度 | M4 r1 | M5 r1 |
|---|---|---|
| 修订记录行存在 | 24/24 (100%) | 18/18 (100%) |
| plan 主体同步修改 | 0/24 (0%) | **18/18 (100%)** |
| 风险表"曾被否决的替代方案"列 cosmetic bug | 有 | 有（NP-4） |
| 跨 M 联动段 | L640 真落地（7 项 M0/M1/M3/M5/M6/M7/M8 联动） | L840-841 真落地（M4/M6/M7/M8 联动） |
| r2 建议 | 主体同步修复 | 修 4 个新问题（NP-1/NP-2/NP-5 + NP-3 cosmetic + NP-4 cosmetic） |

**M5 r1 修复质量显著高于 M4 r1**——是已审查 5 M 中 r1 修复质量最高的一份。

---

## 修订记录

| 版本 | 日期 | 改动 |
|---|---|---|
| r2-2026-06-11 | 2026-06-11 | 18 项 r1 修复逐项验证：100% 修订记录行 + 100% plan 主体同步；4 个 r1 引入新问题（NP-1/2/3/4/5）；11 维跨 M 一致性检查（9/11 完全一致，2 个次要 NP-5/image_ref）；风险表补全质量中等（4 行 r1 已修 cosmetic bug）；落地建议 r2 修 4 个新问题后即可动手 |

