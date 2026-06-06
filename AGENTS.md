# AGENTS.md

本文件定义本仓库内代理工作的约定。目标是让后续修改保持一致、可维护、可验证。

## 项目概况

这是一个 LangGraph 聊天界面项目，前端使用 React + Vite + TypeScript，后端使用 FastAPI + LangGraph。

- 前端目录：`src/`
- 静态资源：`public/`
- 后端目录：`backend/`
- 入口页面：`index.html`

## 工作原则

1. 先读代码，再改代码。优先理解现有实现和局部约定，不要先入为主重构。
2. 保持改动范围最小。只修改完成任务所需的文件和逻辑。
3. 不要回退用户或其他代理已经做过的未请求改动。
4. 不要使用破坏性 Git 命令，例如 `git reset --hard`、`git checkout --`。
5. 手工改文件时优先使用 `apply_patch`。
6. 默认使用 ASCII；只有在项目已有中文内容或用户明确要求时才加入非 ASCII 文本。

## 敏感文件与忽略项

不要提交或恢复以下内容：

- `.env`
- `.venv/`
- `node_modules/`
- `dist/`
- `backend/__pycache__/`

如果需要提供环境变量示例，新增 `.env.example`，不要把真实密钥写进仓库。

## 前端约定

- 前端运行在 Vite 上，默认开发命令是 `pnpm dev`。
- 构建命令是 `pnpm build`。
- 预览命令是 `pnpm preview`。
- 代码风格遵循现有 React 组件拆分方式，优先复用 `src/components/` 和 `src/services/` 中的实现。
- 涉及 UI 改动时，优先保持现有视觉语言，不要顺手重做无关布局。

## 后端约定

- 后端入口是 `backend/main.py`。
- 默认服务地址是 `http://127.0.0.1:8000`。
- 后端依赖见 `backend/requirements.txt`。
- 变更接口时，要同步检查前端 `src/services/langgraph.ts` 的调用和类型。
- 影响流式输出、线程管理、HITL 审批流程时，要一起检查 `src/App.tsx` 和相关组件。

## 验证建议

修改前端后，至少执行：

```bash
pnpm build
```

修改后端后，至少确认：

- 代码能正常启动
- 对应接口路径和返回结构与前端保持一致

如果改动涉及对话流、线程缓存、审批弹窗或工具调用，建议顺手检查一次页面行为和本地缓存键：

- `langgraph_threads`
- `langgraph_messages_{thread_id}`

## 提交前检查

在准备提交前，确认：

1. `git status` 只包含预期文件
2. 没有把 `.env`、构建产物或依赖目录带入暂存区
3. README 与实际命令保持一致
4. 代码变更已经过最基本的构建或运行验证

## 提交信息规范

自动生成或手动编写提交信息时，统一使用 Conventional Commits 风格：

- 新功能：`feat: ...`
- 缺陷修复：`fix: ...`
- 文档修改：`docs: ...`
- 重构：`refactor: ...`
- 样式或格式调整：`style: ...`
- 构建或依赖调整：`build: ...`
- 测试相关：`test: ...`
- 维护类改动：`chore: ...`

提交标题建议使用中文描述，格式示例：

- `feat: 新增线程列表持久化`
- `fix: 修复消息流式输出中断后状态未重置`
- `docs: 补充本地启动说明`

要求：

1. 前缀必须保留英文 Conventional Commits 关键字
2. 后半部分优先使用中文，简洁、明确
3. 不要写成纯英文长句，也不要省略类型前缀
4. 如果一次提交包含多个改动，以最主要的改动类型作为前缀

## 文档维护

如果项目结构、启动方式或环境变量发生变化，要同步更新以下文档：

- `README.md`
- `AGENTS.md`

保持这两份文档一致，避免后续代理按过期说明操作。
