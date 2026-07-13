# 设备检修知识检索与作业系统

> 面向工业现场的多模态 RAG 设备检修助手。前端 Vue 3 + Vite，后端 FastAPI + SQLAlchemy + Chroma。
> 一套代码同时服务 **PC 工业大屏（1920×1080 / 2K）** 与 **车间手机 / 平板移动端**。

---

## 项目内容

整体由 **前端 SPA** 与 **后端 API 服务** 两部分组成，共用一个仓库；产线检修人员、知识审查员、系统管理员三类角色围绕"找答案 → 跟着做 → 沉淀经验"的闭环协作。

### 核心模块

| 模块 | 路径 | 简介 |
| --- | --- | --- |
| **多模态检索** | `/search` | 文本 + 图片输入，调用 Qwen 视觉理解 + Chroma 向量检索 + LLM 摘要；AI 回答**逐 token 流式输出（SSE 打字机，FIX9 H5）**，引用面板按本次查询 per-message 绑定、含"查看原文→"链接与文档图片缩略图（FIX7 第 1 项 / FIX8），结果默认折叠引用材料，自动展开"推荐工单"卡片便于一键添加。**离开页面前未提交的问题与图片会作为草稿保留**（FIX6 第 9 项）。 |
| **知识库浏览** | `/knowledge/browse` | 一线员工 / 审查员 / 管理员均可查看已入库文档，支持类型过滤、全文预览、**PDF / DOCX 原生预览（iframe Blob URL）**、**PDF / Markdown 导出**（reportlab 多级 CJK 字体回退）。 |
| **知识上传** | `/knowledge/upload` | 一线员工提交"经验分享"，提交后进入待审；附件通过 `parent_id` 自动关联到主条目，主条目审核通过会级联通过其附件（FIX6 第 5 项）。表单内容跨页面保留草稿（FIX6 第 9 项）。 |
| **作业指引（工单）** | `/workflow` | 平台级工单 + 每用户独立进度（`user_ticket_progress`）；"我的工单" / "推荐工单"双栏；用户的"删除"仅当前视图隐藏，工单仍参与推荐（FIX6 第 3 项）。 |
| **工单时间线** | 内嵌组件 | 完整记录 创建 / 加入 / 步骤完成 / 整体完成 / 删除（理由），5 种事件配各自图标与配色；`step_completed` 携带 `stepIndex` 显示"第 N 步：标题"（FIX6 第 4 项）。员工只看自己，审查员 / 管理员可看一条工单下所有用户的轨迹。 |
| **审查工作台** | `/auditor/review` | 知识条目通过 / 驳回 / 下架，所有变更走二次确认对话框；通过 / 驳回级联到关联附件。 |
| **知识库管理** | `/auditor/knowledge` | 审查员 / 管理员对已入库文档增删改，**含 AI 自动入库条目的编辑**（FIX6 第 6 项），保存后自动重建向量索引。 |
| **知识图谱** | `/kg` | ECharts 力图（PC）/ 卡片流（Mobile）。PC 端节点按环形 + 微抖动预放置、`elasticOut` 弹性入场、边延迟分层渐入（FIX5 第 14 项）。审查员可编辑 / 删除节点和边（FIX6 第 6 项）；节点弹窗展示 `source_docs` 关联文档，支持按文档筛选图谱（FIX6 第 8 项）。 |
| **个人中心** | `/profile` | 资料、安全（修改自己的密码，必校验旧密码）、**历史工单 Tab**（已完成 / 已删除带理由，支持"重新添加到作业指引"）。 |
| **用户管理** | `/admin/user` | 管理员独占。任意角色账户增 / 改 / 删 / 重置密码。**重置为随机一次性口令并使旧会话立即失效（FIX9 C5）**，不再恒为 `123456`。默认 `admin` 账号受 `is_default_admin` 保护，不可删除、不可改名、不可降权。 |

### 角色与权限

前端角色：`frontline`（一线检修员）/ `auditor`（审查员）/ `admin`（管理员）；后端枚举：`worker` / `leader` / `admin`。两者通过 `src/constants/roles.ts` **单一来源**统一管理，`mapBackendRole()` / `mapFrontendRole()` 负责互转，菜单 `MENU_ITEMS` 和路由 `meta.roles` 共用一套定义。

注册接口固定写入 `worker`，前端注册页不暴露角色字段；管理员在 `/admin/user` 创建账户时**未填密码则生成随机一次性口令（仅本次回显，供转交用户）**，默认 `admin` 账号初始密码仍为 `123456`（受 `is_default_admin` 保护）。登录后可在个人中心自行修改。

---

## 技术栈

### 前端（仓库根目录）

| 维度 | 选型 |
| --- | --- |
| 框架 | Vue 3 + `<script setup>` + TypeScript |
| 构建 | Vite 5 |
| PC UI | Element Plus 2 |
| 移动 UI | Vant 4 |
| 样式 | Tailwind CSS 3 + CSS Variables 设计令牌 |
| 路由 | Vue Router 4（Hash 模式） |
| 状态 | Pinia 2 |
| HTTP | Axios + 类型化封装（`safeCall` / `rawCall`） |
| 图表 | ECharts 5 |
| Markdown / XSS | markdown-it + **DOMPurify 白名单二次净化** |
| 图标 | lucide-vue-next |

### 后端（`backend/`）

| 维度 | 选型 |
| --- | --- |
| Web 框架 | FastAPI |
| 数据库 | SQLAlchemy + SQLite (`loongchip.db`) |
| 向量库 | Chroma（本地持久化） |
| 大模型 | 阿里云 DashScope —— Qwen 文本 / Qwen-VL 视觉 / 文本 Embedding |
| 鉴权 | JWT + bcrypt；`JWT_SECRET` 未改默认值则**拒绝启动**（FIX9 C1） |
| 启动迁移 | `Base.metadata.create_all` + 轻量 `run_migrations()` 补列 |
| 流式 | `/api/chat/query` 走 SSE（`text/event-stream`）逐 token 输出（FIX9 H5） |
| 测试 / CI | pytest + httpx（`backend/tests/`）；GitHub Actions 前端 typecheck + 后端 pytest（FIX9 H2） |

---

## 仓库结构

```
software2026/
├── src/                       前端源码
│   ├── api/                   axios 实例 + 各域接口（auth / kb / ticket / chat / kg / admin / search ...）
│   ├── components/
│   │   ├── common/            跨端通用：TicketTimeline / EmptyState / SimilarityBar / ConfidenceMeter ...
│   │   ├── pc/                PC 专用：TopBar / SideNav / CommandPalette(⌘K)
│   │   └── mobile/            Mobile 专用：AppBar / BottomTabBar / SwipeableCard ...
│   ├── composables/           useDevice / useTheme / useShortcut / useStreamText
│   ├── constants/roles.ts     ★ 角色枚举唯一来源
│   ├── layouts/               PCLayout / MobileLayout
│   ├── router/                单一路由表 + 角色守卫 + 移动端只读
│   ├── stores/                Pinia：user / search / workflow / ui
│   ├── utils/
│   │   ├── markdown.ts        markdown-it + DOMPurify 净化
│   │   ├── permission.ts      菜单可见性 + 角色映射 re-export
│   │   └── format / storage ...
│   ├── views/                 业务页面，多数遵循 index.vue + Pc.vue + Mobile.vue
│   │   ├── login/             登录 + 注册（仅员工）
│   │   ├── search/            多模态检索 + 详情
│   │   ├── workflow/          作业指引主页 + WorkList + 详情
│   │   ├── knowledge/         Browse / Preview / Upload / KnowledgeManage
│   │   ├── audit/             KnowledgeReview
│   │   ├── kg/                知识图谱 PC 力图 / Mobile 卡片
│   │   ├── history/           历史检索
│   │   ├── profile/           个人中心（资料 / 安全 / 历史工单）
│   │   └── admin/             用户管理
│   └── assets/styles/         tokens.css / globals.css / industrial.css / tailwind.css
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI 入口 + 深度健康检查 /api/health + 启动 seed 默认 admin
│   │   ├── api/               auth / kb / chat / ticket(+workflow_router) / kg / admin
│   │   ├── core/              db / config(JWT_SECRET 强制、CORS_ORIGINS) / security(JWT, bcrypt, get_current_user) / migrate
│   │   ├── models/            User / KbDoc / Ticket / UserTicketProgress / TicketEvent / KGNode / QALog ...
│   │   └── services/
│   │       ├── llm.py         DashScope 封装：chat_text / chat_text_stream / vl_describe / embed
│   │       ├── rag.py         Chroma 持久化客户端 + ingest / search / rag_retrieve / build_user_prompt / rag_answer
│   │       └── parser.py      PDF/DOCX 解析 + 图片提取（pypdf page.images）
│   ├── tests/                 pytest：conftest + test_auth / test_security / test_health
│   ├── requirements-dev.txt   pytest + httpx
│   ├── requirements.txt
│   └── Dockerfile             后端镜像（python:3.11-slim + gunicorn）
├── .github/workflows/ci.yml   ★ CI：前端 typecheck + 后端 pytest
├── NEEDS/                     需求与历次修复清单（NEEDS.md / FIX1..7.md）
├── CHANGE/                    变更记录（含 FIX8 / FIX9 设计加固）
├── CLAUDE.md                  对 Claude Code 的工程上下文说明
├── DOCKER.md                  ★ Docker 构建 / 运行 / 分发 / 备份完整指南
├── Dockerfile                 前端镜像（多阶段：node 构建 → nginx 托管）
├── docker-compose.yml         前后端编排 + 三个数据卷
├── docker/nginx.conf          前端 nginx 配置（/api → backend 反代）
├── public/  index.html
├── vite.config.ts  tailwind.config.js  tsconfig.json  package.json
```

---

## 快速开始

> **想跳过环境配置直接跑？** 仓库已内置 Docker 化能力，详见 [`DOCKER.md`](./DOCKER.md)：
> ```bash
> cp backend/.env.example backend/.env   # 填 DASHSCOPE_API_KEY
> docker compose up -d --build           # → http://localhost:8080
> ```

### 前端

```bash
npm install
npm run dev        # → http://localhost:5173 ，/api 自动代理到 127.0.0.1:8000
npm run typecheck  # 仅类型检查（vue-tsc --noEmit）
npm run build      # 类型检查 + 生产构建 → dist/
npm run preview    # 预览生产包
```

### 后端

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt   # 含测试依赖
cp .env.example .env       # 填入 DASHSCOPE_API_KEY、JWT_SECRET、CORS_ORIGINS 等
uvicorn app.main:app --reload   # → http://127.0.0.1:8000

python -m pytest -q tests      # 运行后端测试（auth / security / health）
```

> **生产部署强约束（FIX9 C1）**：`JWT_SECRET` 仍为默认值 `please-change-me` / `change-me-in-prod` 时**后端拒绝启动**。
> 生成强随机串：`python -c "import secrets; print(secrets.token_hex(32))"`。本地开发可设 `ALLOW_INSECURE_JWT=true` 临时绕过。
> **CORS（FIX9 C3）**：默认仅放行 `http://localhost:5173,http://127.0.0.1:5173`；生产请在 `.env` 把 `CORS_ORIGINS` 改为前端实际域名（逗号分隔）。

启动时后端会自动创建表、补迁移、播种默认管理员。

### 默认账户

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员（不可删除） |

注册页只能创建一线员工账户；其他角色由管理员在 `/admin/user` 中创建。

---

## API 层约定

`src/api/request.ts` 提供两个统一封装：

- `safeCall(fn)` —— 处理 `{code,msg,data}` 信封，成功返回 `data.data`，失败 **抛错**。
- `rawCall(fn)` —— 处理 FastAPI 直接返回 JSON 的接口，失败抛错。

> **FIX5 第 16 项**：所有 mock 兜底数据已移除，接口失败时各视图统一用 `EmptyState` / `AlertTriangle` 错误态展示，避免"假数据兜底"造成误导。
> **FIX6 第 11 项**：Token 按路由前缀隔离存储——用户端用 `user_token`，管理端（`#/admin`）用 `admin_token`，避免同浏览器交叉登录时 token 串扰。按 Bearer 注入；401（非登录接口）会清除当前上下文的 token 并 `location.hash = '#/login'`。若后端返回 `detail` 含"其他设备"（单点登录），弹出专属提示后再跳转。
> **FIX9 H5（流式）**：`/api/chat/query` 返回 `text/event-stream`（SSE），前端 `multimodalSearchStream()` 用 `fetch` + `ReadableStream` 手动解析（`EventSource` 不支持 POST/multipart），事件类型 `token` / `meta` / `error` / `done`；其余接口仍走 `safeCall` / `rawCall`。

后端路由均带 `/api` 前缀（`kg` 路由无前缀但装饰器内联 `/api/kg/...` 全路径），Vite 代理不重写路径。

---

## 安全

- **XSS**：`utils/markdown.ts` = `markdown-it { html:false }` + **DOMPurify** 白名单二次净化；禁用 `<script>` / `<iframe>` / 内联 `style` / `on*` 事件，URL 仅放行 `https?:` / `mailto:` / `#` / `/`。
- **单点登录（FIX6 第 10 项）**：`User.token_version` 每次登录 / 改密递增；JWT 携带 `tv` 字段，`get_current_user` 校验不一致即 401，旧设备 token 立即失效。
- **Token 隔离（FIX6 第 11 项）**：用户端 `user_token` 与管理端 `admin_token` 按 `location.hash` 前缀分流，杜绝同浏览器同账号多角色操作时的串号；登出只清当前上下文，不影响另一端。
- **改密加固（FIX6 第 11 项 / FIX9 C5）**：`PUT /api/auth/change-password` 必须校验旧密码，按 `current_user.id` 显式锁定目标行写入；管理员重置 `PUT /api/admin/users/{id}/reset-password` 一律按路径参数 `id` 查目标用户，**重置为随机一次性口令（`secrets.token_urlsafe`）并 `bump token_version` 使旧会话立即失效**，不再恒为 `123456`；管理员建号未填密码时同样生成随机一次性口令（仅本次回显）。
- **JWT 强制（FIX9 C1）**：`JWT_SECRET` 仍为默认值时后端 `raise SystemExit` 拒绝启动；`ALLOW_INSECURE_JWT=true` 或 `DEBUG=true` 可临时绕过（仅警告）。杜绝掌握源码者伪造任意用户 / 角色 JWT。
- **CORS 收紧（FIX9 C3）**：`CORS_ORIGINS` 默认 `http://localhost:5173,http://127.0.0.1:5173`，生产须在 `.env` 改为前端实际域名；Bearer token 场景 `allow_credentials=False` 使 `allow_headers=["*"]` 直接覆盖 `Authorization`。仅 `CORS_ORIGINS=*` 时退化为完全开放。
- **上传路径穿越（FIX9 C2）**：`os.path.join(UPLOAD_DIR, file.filename)` 改为统一 `os.path.basename(...)`，空名回退 `uuid`，杜绝 `../../etc/x` 逃逸 UPLOAD_DIR 写任意文件。
- **LLM 错误处理（FIX9 C4）**：`chat_text` 补 None 检查并抛 `RuntimeError`，SOP 生成失败转 `HTTPException(502)`，不再泄露 500 堆栈。
- **向量重建原子性（FIX9 H1）**：编辑已通过文档时向量重建移到 `db.commit()` 之前，失败回滚旧向量 + `HTTPException(500)`，避免 `status=approved` 但 Chroma 零向量的不一致。
- **本地存储**：只保存 token，不存明文用户资料；401 自动清除当前上下文 token。
- **路由守卫**：`beforeEach` 验证 token，调用 `/api/auth/me` 拉取实体后再渲染；`meta.roles` 缺权限弹 toast 跳回。
- **后端鉴权**：所有受限路由依赖 `get_current_user` + 角色检查；默认 admin 受 `is_default_admin` 双重保护（用户名 + 标记列）。
- **密码**：bcrypt 哈希，注册 / 修改 / 重置统一校验长度 ≥ 6。
- **上传**：仅放行 `.pdf / .docx / .txt / .md`，单文件 ≤ 50 MB。
- **数据访问**：全 ORM 查询，无字符串拼 SQL。

---

## 设计系统

### 配色

| 名称 | 值 | 用途 |
| --- | --- | --- |
| Primary 深空蓝 | `#0B2545` | 顶栏、标题、关键操作 |
| Accent 机械橙 | `#F26B1F` | 主按钮、高亮、进度、警示 |
| AI 青 | `#00B7C2` | 多模态 / AI 入口 |
| Success / Warning / Danger | `#2E7D32` / `#ED6C02` / `#C62828` | 状态语义 |

支持 **暗色模式**、**高对比度模式**（强光下产线）、**字号档位**（base / lg / xl）、**手套模式**（1.3× 触控区）。

### 响应式断点

- `< 640px` → mobile（底部 Tab + 固定输入区）
- `640–1024px` → tablet（mobile 布局，组件略放宽）
- `≥ 1024px` → pc（完整三栏）

### 关键交互

- **⌘K / Ctrl+K** 命令面板（PC）
- **拖拽 / 粘贴** 上传图片，缩略图条带
- **AI 打字机** 流式输出诊断结论（`useStreamText`）
- **左滑驳回 / 右滑通过**（审核移动端 `SwipeableCard`）
- **长按麦克风** 模拟语音输入
- **震动反馈** 移动端步骤完成 / 错误时触发 `navigator.vibrate`

---

## 主要后端接口（节选）

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册（强制 worker） |
| POST | `/api/auth/login` | 登录 → JWT（每次登录 `token_version` +1） |
| GET | `/api/auth/me` | 当前用户 |
| PUT | `/api/auth/change-password` | 修改自己的密码（校验旧密码） |
| GET/POST/PUT/DELETE | `/api/admin/users` | 管理员账户 CRUD |
| PUT | `/api/admin/users/{id}/reset-password` | 重置为**随机一次性口令** + 旧会话失效（FIX9 C5） |
| POST | `/api/kb/upload` | 文档 / 经验上传（支持 `parent_id` 关联附件） |
| POST | `/api/kb/text` | 纯文本知识入库 |
| POST | `/api/kb/text-with-files` | 文本经验 + 支撑附件（先建主条目再挂 `parent_id`） |
| GET | `/api/kb/list` | 浏览列表（主条目下挂 `attachments[]`） |
| GET | `/api/kb/{id}` | 文档详情 |
| GET | `/api/kb/image/{image_name}` | 解析出的文档图片（引用面板缩略图） |
| GET | `/api/kb/{id}/download` | 原始文件下载（PDF/DOCX inline 预览） |
| GET | `/api/kb/{id}/export?format=pdf\|md` | 导出 |
| PUT | `/api/kb/{id}` | 编辑文档（审查员/管理员，含重建向量） |
| POST | `/api/kb/{id}/review` | 审核通过 / 驳回（级联附件） |
| POST | `/api/chat/query` | 多模态问答（文本 + 可选图片，**SSE 流式**，FIX9 H5） |
| POST | `/api/chat/correct` | 保存用户对 AI 回答的手动修正（`qa_log_id`） |
| GET / POST | `/api/ticket` | 列出 / 创建工单 |
| POST | `/api/ticket/recommend` | 相似工单推荐（仅排除当前 TB 进度） |
| POST | `/api/ticket/{id}/add` | 加入他人工单（新建独立进度） |
| PATCH | `/api/ticket/{id}/progress` | 推进步骤（附带 `stepIndex`） |
| PATCH | `/api/ticket/{id}` | 兼容旧前端：标记我的进度完成 |
| DELETE | `/api/ticket/{id}` | 删除（未完成需理由） |
| GET | `/api/ticket/{id}/timeline` | 时间线（审查员 / 管理员可看所有用户） |
| GET | `/api/ticket/{id}/tools` · `/manuals` | 工单关联工具 / 手册 |
| GET | `/api/workflow/{id}/tools` · `/manuals` | 同上（`/api/workflow` 别名路由） |
| GET | `/api/ticket/history` | 个人历史工单（含已删除） |
| GET | `/api/kg/graph` | 知识图谱节点 + 边（支持 `filter_doc_id`） |
| PUT/DELETE | `/api/kg/node/{node_id}` | 图谱节点编辑 / 删除（审查员/管理员） |
| PUT/DELETE | `/api/kg/edge/{edge_id}` | 图谱边关系编辑 / 删除（审查员/管理员） |
| GET | `/api/kb/{docId}/chunk/{chunkId}` | 节点对应原文片段 |

---

## 验收快查

| 项 | 状态 |
| --- | --- |
| `npm run typecheck` | ✅ 0 错误 |
| 注册仅创建员工账户 | ✅ |
| 默认管理员 `admin / 123456`，不可删除 | ✅ |
| 个人改密（验旧密码）+ 管理员重置（按路径参数锁定，**随机一次性口令** + 旧会话失效） | ✅ FIX9 C5 |
| `JWT_SECRET` 默认值时后端拒绝启动（`ALLOW_INSECURE_JWT` 可绕过） | ✅ FIX9 C1 |
| CORS 默认仅放行本地前端，`CORS_ORIGINS` 可配置 | ✅ FIX9 C3 |
| 上传文件名 `basename` 防路径穿越 | ✅ FIX9 C2 |
| 单点登录：新登录使旧设备 token 失效（`token_version`） | ✅ FIX6 第 10 项 |
| Token 隔离：用户端 `user_token` / 管理端 `admin_token` 按路由前缀分流 | ✅ FIX6 第 11 项 |
| 审查员 `/auditor/review` + `/auditor/knowledge`，操作前二次确认 | ✅ |
| 知识库导入：附件 `parent_id` 关联主条目，审核级联 | ✅ FIX6 第 5 项 |
| 知识库导出 PDF / Markdown + PDF 二进制原生预览 | ✅ FIX6 第 2 项 |
| 知识库编辑：审查员/管理员可修改文档内容，自动重建向量 | ✅ FIX6 第 6 项 |
| 工单：完成可直接删，未完成需理由；他人工单可"添加到我的" | ✅ |
| 工单软删除仅隐藏当前用户视图，仍参与平台推荐 | ✅ FIX6 第 3 项 |
| 工单时间线（员工只看自己 / 审查员 admin 看全部，带图标配色） | ✅ FIX6 第 4 项 |
| 知识图谱节点编辑/删除、边编辑/删除（`kg_overrides` 覆盖层） | ✅ FIX6 第 6 项 |
| 知识图谱节点关联文档列表 + 按文档筛选 | ✅ FIX6 第 8 项 |
| 搜索 / 上传页表单内容跨页面保留草稿 | ✅ FIX6 第 9 项 |
| 多模态检索：引用折叠，推荐工单自动展示 | ✅ |
| 引用面板 per-message 绑定 + 查看原文 + 图片缩略图 | ✅ FIX7 第 1 项 / FIX8 |
| AI 回答 SSE 流式打字机输出 | ✅ FIX9 H5 |
| `/api/health` 深度探活 DB / Chroma / DashScope | ✅ FIX9 H3 |
| 后端 pytest（auth / security / health）+ GitHub Actions CI | ✅ FIX9 H2 |
| 知识图谱弹性入场动画 | ✅ |
| 全站无 Mock 兜底数据 | ✅ |
| 角色枚举单一来源（`src/constants/roles.ts`） | ✅ |
| XSS：markdown-it + DOMPurify | ✅ |
| 全部信创 / LoongArch / 银河麒麟 UI 标签已移除（FIX5 第 15 项） | ✅ |

---

## 部署

仓库已内置 Docker 化能力：前端 Vue + 后端 FastAPI 一键编排，含 Nginx 反代、CJK PDF 字体、健康检查与三个持久化数据卷。

```bash
cp backend/.env.example backend/.env   # 填入 DASHSCOPE_API_KEY
docker compose up -d --build
# 浏览器打开 http://localhost:8080  ·  默认 admin / 123456
```

**完整的构建、运行、镜像分发（save/load）、数据备份、国内网络排错与生产注意事项请见 → [`DOCKER.md`](./DOCKER.md)。**

如不使用 Docker，前端构建产物 `dist/` 为标准静态文件，可由 nginx / Apache 托管；后端任意能跑 Python 3.10+ 的服务器即可：

```nginx
server {
  listen 80;
  root /var/www/maintenance;
  location / { try_files $uri $uri/ /index.html; }
  location /api/ { proxy_pass http://backend:8000/; }
}
```

后端首次启动会创建 `loongchip.db` 与 Chroma 持久化目录；如需重置，直接删除即可重新播种。

---

## License

仅用于评审与演示。© 2026
