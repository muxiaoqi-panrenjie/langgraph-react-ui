# LangGraph React UI

一个基于 React + Vite + TypeScript 的 LangGraph 聊天界面示例，配套 FastAPI 后端，用来演示多智能体切换、流式对话、线程管理和 HITL（Human-in-the-Loop）审批流程。

## 功能

- 支持多个 Assistant / Agent 切换
- 支持 Thread 创建、切换、删除
- 支持流式输出和步骤追踪
- 支持 HITL 中断、审批、拒绝和编辑后继续执行
- 支持本地缓存对话与线程信息
- 后端不可用时，前端会自动降级到本地 mock 行为，便于前端独立调试

## 技术栈

- 前端：React 19、TypeScript、Vite
- 后端：FastAPI、LangGraph、LangChain Core
- UI 依赖：lucide-react、prismjs

## 目录结构

```text
.
├── backend/        # FastAPI + LangGraph 后端
├── public/         # 静态资源
├── src/            # 前端源码
├── package.json    # 前端依赖与脚本
└── README.md
```

## 环境要求

- Node.js 18+
- Python 3.10+
- `pnpm` 或 `npm`

## 本地启动

### 1. 准备环境

- **后端依赖**：进入 `backend` 目录，创建并激活虚拟环境，然后安装 Python 依赖：
  ```bash
  cd backend
  pip install -r requirements.txt
  ```
- **前端依赖**：在项目根目录下安装依赖：
  ```bash
  pnpm install
  ```

### 2. 一键启动前后端

在项目根目录下执行以下命令，即可同时启动前端（Vite）和后端（FastAPI）服务：

```bash
pnpm dev
```

启动脚本会智能检测根目录下的 `.venv` 虚拟环境并使用其中的 Python 解释器启动后端，同时启动 Vite 前端开发服务器，并将两端的控制台输出合并打印（分别带有 `[Backend]` 和 `[Frontend]` 颜色前缀）。

### 3. 单独启动（可选）

如果需要单独启动前端或后端进行调试：

- **单独启动后端**：
  ```bash
  cd backend
  python main.py
  ```
- **单独启动前端**：
  在项目根目录下直接使用 Vite 启动：
  ```bash
  npx vite
  ```

## 环境变量

项目根目录下的 `.env` 主要用于 LangSmith 和 Anthropic 相关配置。常见字段如下：

```bash
LANGSMITH_TRACING="false"
LANGSMITH_PROJECT="langgraph-react-ui"
ANTHROPIC_API_KEY="your_api_key"
ANTHROPIC_API_URL="https://coding.dashscope.aliyuncs.com/apps/anthropic"
ANTHROPIC_BASE_URL="https://coding.dashscope.aliyuncs.com/apps/anthropic"
```

建议不要把真实密钥提交到仓库中。可以自行新建 `.env.example` 作为示例文件。

## 后端接口

后端主要提供以下接口：

- `GET /api/assistants`
- `POST /api/threads`
- `GET /api/threads/{thread_id}/messages`
- `GET /api/interrupt/{thread_id}`
- `POST /api/resume`
- `POST /api/chat/stream`
- `GET /api/tools`

## 本地缓存

前端会在浏览器 `localStorage` 中保存：

- `langgraph_threads`
- `langgraph_messages_{thread_id}`

这可以让页面刷新后保留线程和消息历史。

## 开发说明

- 前端默认请求后端地址为 `http://localhost:8000`
- 如果后端未启动，前端会使用本地 mock 数据和 mock 流式回复
- HITL 流程中，工具调用会触发审批弹窗，处理结果再回传给后端

## 构建

```bash
pnpm build
```

## 预览

```bash
pnpm preview
```

## 说明

这是一个演示型项目，重点在于展示 LangGraph 前后端交互、流式消息处理和人工审批流程。后续如果要接入真实模型或生产环境数据源，建议把 `.env`、后端地址和工具配置拆分成独立的环境模板。
