# LangGraph 教学文档

本文档不是泛泛介绍 LangGraph，而是结合当前仓库的实际代码，解释它在这个项目里到底在做什么、为什么这样设计、什么时候值得保留、什么时候可以去掉。

## 1. 先说结论

在这个项目里，LangGraph 主要负责三件事：

1. 编排对话流程
2. 保存和恢复状态
3. 处理中断与继续执行

前端聊天界面不是 LangGraph 做的，前端是 React。

后端接口不是 LangGraph 做的，接口是 FastAPI。

LangGraph 在这里承担的是“工作流运行时”的角色，也就是：

- 这一轮消息应该先过哪个节点
- 当前是否需要调用工具
- 是否应该暂停等用户补充信息
- 用户补完信息后从哪一步继续
- 当前线程的历史状态如何保留

如果没有这些需求，很多事情直接在普通后端代码里也能完成。

## 2. LangGraph 是什么

从工程角度看，LangGraph 可以理解成一个“面向 LLM 场景的状态机 / 工作流编排框架”。

它和普通函数调用的区别是：

- 普通后端代码通常是一条直线执行完
- LangGraph 更适合多节点、多状态、可暂停、可恢复的执行过程

它比较擅长的场景：

- 多步骤任务
- 工具调用
- Human-in-the-loop
- 中断 / 恢复
- 多 agent 协作
- 长会话状态保存

## 3. 这个项目里的 LangGraph 在哪里

核心文件有两个：

- `backend/agent.py`
- `backend/main.py`

职责划分如下：

### `backend/agent.py`

这里定义了图、节点、工具、状态结构和图的编译结果。

你可以把它理解为：

- 业务流程定义文件
- agent 工作流定义文件

### `backend/main.py`

这里定义 FastAPI 接口，把前端请求转给对应的 graph 执行。

你可以把它理解为：

- Web API 入口
- 把 HTTP 请求接到 LangGraph 上的适配层

## 4. 这个项目里有哪些图

当前仓库里不是只有一个 graph，而是有 4 类：

### 4.1 `graph`

普通演示图，用于常规 Assistant。

特点：

- 一轮消息进来
- assistant 判断是否要调工具
- 工具执行后再回到 assistant
- 没有复杂的人机中断

### 4.2 `hitl_graph`

带 HITL 的图。

特点：

- 某些工具不是直接执行
- 会先 `interrupt()`
- 前端弹审批框
- 用户 approve / reject / edit 后，再 `resume`

### 4.3 `multi_agent_graph`

这个是当前仓库里最值得研究的一张图。

它体现了 LangGraph 真正的价值：

- 先验证用户身份
- 未验证则中断等待手机号
- 验证成功后读取记忆
- 再交给 supervisor
- supervisor 再调用 invoice 或 music 子 agent
- 最后回写记忆

### 4.4 `rag_graph`

RAG 问答图。

特点：

- 先查向量库 / 文档库
- 拼接参考上下文
- 再交给模型生成答案

它结构相对简单，本质上是“检索 + 生成”的单步图。

## 5. 当前项目的实际执行链路

以 `Multi-Agent Assistant` 为例，完整链路大致如下：

1. 前端发消息到 `POST /api/chat/stream`
2. `backend/main.py` 根据 `assistant_id` 选择 `multi_agent_graph`
3. graph 从 `verify_info` 节点开始执行
4. 如果没有 `customer_id`，判断需要身份验证
5. 进入 `human_input` 节点并触发 `interrupt`
6. 前端收到中断事件，弹出输入框或审批表单
7. 用户提交手机号，前端调用 `POST /api/resume`
8. 后端通过 `Command(resume=...)` 恢复图执行
9. graph 回到 `verify_info`
10. 验证成功后进入 `load_memory`
11. 然后进入 `supervisor`
12. `supervisor` 根据问题类型调用：
    - `invoice_information_subagent`
    - `music_catalog_subagent`
13. 最后进入 `create_memory`
14. 保存本轮用户偏好或上下文
15. 返回最终消息给前端

这整件事如果不用 LangGraph，也能写，但你要自己维护：

- 当前卡在哪个步骤
- 当前线程是否待验证
- 用户补充信息后回到哪一步
- 哪些状态要持久化

这就是它的工程价值所在。

## 6. 关键概念，对照本项目理解

## 6.1 State

State 就是图执行过程中的共享状态。

这个项目里有几种 State：

- `State`
- `MultiAgentState`
- `RagState`

状态里通常放这些内容：

- `messages`
- `customer_id`
- `loaded_memory`
- `context`

你可以把它理解成“当前线程的运行上下文”。

## 6.2 Node

Node 就是一段可执行逻辑。

本项目里的典型节点有：

- `assistant`
- `verify_info`
- `human_input`
- `load_memory`
- `supervisor`
- `create_memory`
- `rag_assistant`

节点不一定非得调用模型，它也可以：

- 查数据库
- 做判断
- 读写记忆
- 触发中断

## 6.3 Edge

Edge 就是节点之间怎么连。

例如：

- `START -> verify_info`
- `verify_info -> human_input`
- `verify_info -> load_memory`
- `human_input -> verify_info`
- `supervisor -> create_memory`

如果是条件边，就表示“根据当前状态决定下一步去哪”。

## 6.4 Checkpointer

Checkpointer 用来保存执行状态。

本项目里大量使用 `MemorySaver()`。

它的作用是：

- 当前线程执行到一半中断了
- 以后还能按 `thread_id` 找回状态
- 然后继续跑

注意：`MemorySaver` 适合本地演示，不适合真正生产持久化。

生产环境一般会换成更稳定的存储方案。

## 6.5 Interrupt

这是 LangGraph 很关键的能力。

本项目里有两类典型中断：

1. 工具审批中断
2. 身份验证中断

例如：

- 发邮件前先让人审批
- 删除数据库前先让人审批
- 查询敏感账单前先验证手机号

调用 `interrupt(...)` 后，图不会继续往下跑，而是把“当前需要用户处理什么事”返回给前端。

## 6.6 Resume

中断之后，前端调用：

- `POST /api/resume`

后端再通过：

- `Command(resume=resume_data)`

把用户输入或审批结果送回 graph，graph 再继续执行。

这就是“暂停 - 补信息 - 恢复”的核心机制。

## 7. 为什么这个项目适合用 LangGraph

不是所有项目都适合用它，但这个项目有几类需求正好对得上：

### 7.1 需要中断和恢复

这里不是简单问答，而是：

- 用户先提问题
- 系统发现缺身份信息
- 先停下来要手机号
- 用户补充后继续查订单

这种过程 LangGraph 处理起来比较自然。

### 7.2 需要流程编排

这个项目不是只有一个模型调用，而是多步骤业务流：

- 验证
- 读取记忆
- 路由问题
- 调子 agent
- 保存记忆

### 7.3 需要状态化线程

前端和后端都围绕 `thread_id` 工作，这意味着每条线程不是一次性请求，而是持续会话。

### 7.4 需要多 agent 协作

这里已经不是单工具调用，而是 supervisor + subagent 的结构。

## 8. 什么时候没必要用 LangGraph

如果你的系统只是下面这种，就没必要上 LangGraph：

- 用户发一个问题
- 后端调一次模型
- 模型按需调用工具
- 返回结果

这种情况下，普通后端代码就够了：

- FastAPI
- 模型 SDK
- tools / services
- PostgreSQL

也就是说，以下场景通常可以不用：

- 单轮问答
- 普通数据库查询助手
- 简单客服机器人
- 没有中断恢复的工具调用

## 9. 如果去掉 LangGraph，会变成什么样

去掉后，不是 agent 消失了，而是流程编排从 LangGraph 转移到普通后端代码。

原来是：

- FastAPI -> LangGraph -> 节点 -> 工具 / 子 agent

去掉后会变成：

- FastAPI -> chat handler -> intent router -> services -> response

例如：

- `verification_service`
- `invoice_service`
- `music_service`
- `conversation_state_store`

这些都可以写在后端里。

差别不在“能不能做”，而在：

- 代码是否需要自己维护状态机
- 是否需要自己处理中断恢复
- 是否需要自己管理步骤流转

## 10. 最小示例：理解 LangGraph 的基本结构

下面是一个极简示例，只保留最核心的图结构：

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


def assistant_node(state: ChatState):
    return {
        "messages": [
            {"role": "assistant", "content": "你好，我收到了你的问题。"}
        ]
    }


builder = StateGraph(ChatState)
builder.add_node("assistant", assistant_node)
builder.add_edge(START, "assistant")
builder.add_edge("assistant", END)

graph = builder.compile()
result = graph.invoke({
    "messages": [{"role": "user", "content": "你好"}]
})
```

这说明 LangGraph 最核心的东西只有 4 个：

- State
- Node
- Edge
- Compile

## 11. 对照当前项目，应该重点读哪些代码

如果你要真正学会这个仓库里的 LangGraph，建议按这个顺序读：

### 第一步：先读入口路由

看 `backend/main.py` 里的：

- `/api/chat/stream`
- `/api/resume`
- `/api/interrupt/{thread_id}`

重点理解：

- graph 是怎么被选中的
- stream 是怎么发给前端的
- interrupt 是怎么暴露给前端的
- resume 是怎么继续执行的

### 第二步：再读普通图

看 `backend/agent.py` 里的：

- `workflow`
- `graph`

重点理解：

- assistant 怎么决定要不要调工具
- tool node 怎么回到 assistant

### 第三步：再读 HITL 图

看：

- `send_email_hitl`
- `delete_database`
- `make_purchase`
- `hitl_workflow`
- `hitl_graph`

重点理解：

- 为什么工具内部会调用 `interrupt()`
- 为什么恢复后还能继续执行

### 第四步：重点读多智能体图

看：

- `verify_info`
- `human_input`
- `should_interrupt`
- `load_memory`
- `supervisor_agent`
- `create_memory`
- `multi_agent_final`
- `multi_agent_graph`

重点理解：

- 身份验证如何驱动流程跳转
- 为什么 `human_input` 后要再回 `verify_info`
- supervisor 和 subagent 是怎样配合的

### 第五步：最后读 RAG 图

看：

- `RagState`
- `rag_assistant_node`
- `rag_graph`

重点理解：

- 检索结果如何注入提示词
- RAG 图为什么结构比多智能体图简单很多

## 12. 这个项目里 LangGraph 和前端是怎么配合的

前端并不知道图的内部结构，但它知道几类事件：

- `step`
- `token`
- `interrupt`

也就是说，前端不关心“图里有几个节点”，它只关心：

- 现在执行到哪一步了
- 有没有流式输出
- 是否需要用户干预

所以实际分层是：

- LangGraph 负责后端流程
- FastAPI 负责协议转换
- React 负责展示和交互

这是一个比较干净的职责边界。

## 13. 生产环境里常见的实现方式

从现在主流做法看，通常有 3 种：

### 13.1 单 Agent + Tool Calling

最常见。

适合：

- 简单助手
- 普通工具调用
- 业务清晰、流程不长

### 13.2 普通后端状态机

也很常见。

适合：

- 业务流程明确
- 规则多于推理
- 想降低框架复杂度

### 13.3 LangGraph 这类图编排

适合：

- 长流程
- 中断恢复
- 多 agent
- 人机协同

所以不是所有 agent 项目都要用 LangGraph。

## 14. 学这个项目时最容易混淆的点

### 14.1 LangGraph 不是前端框架

它不负责 UI。

### 14.2 LangGraph 不是模型本身

模型还是 `qwen3.6-plus`，LangGraph 只是组织调用顺序。

### 14.3 LangGraph 不是数据库

它可以保存状态，但不等于业务数据存储。

### 14.4 多 agent 不等于一定高级

如果业务简单，多 agent 往往只是增加复杂度。

## 15. 这个项目后续怎么演进更合理

如果你后面继续维护这个仓库，我建议这样判断：

### 保留 LangGraph 的条件

满足以下任意几条，就值得保留：

- 继续做 HITL
- 继续做 resume
- 继续做多节点流程
- 继续做多 agent
- 继续做状态化线程执行

### 可以考虑去掉 LangGraph 的条件

如果目标收缩成下面这样，可以考虑移除：

- 只做普通聊天
- 只做数据库问答
- 不再需要中断恢复
- 不再做多 agent
- 后端希望尽量简单

## 16. 推荐学习路径

如果你是第一次学 LangGraph，不要一上来就研究多智能体图。

建议顺序：

1. 先理解 StateGraph 的基本结构
2. 再理解 tool call 循环
3. 再理解 interrupt / resume
4. 最后看 supervisor + subagent

对应到本项目，就是：

1. 先看 `graph`
2. 再看 `hitl_graph`
3. 再看 `multi_agent_graph`
4. 最后看 `rag_graph`

## 17. 一句话总结

对这个仓库来说，LangGraph 的核心价值不是“让模型更聪明”，而是：

**把一个需要状态、需要中断恢复、需要多步骤流转的后端智能体流程，组织成一个可运行、可恢复、可扩展的工作流。**

如果你接下来要继续深入，我建议下一步直接画一张“本项目 `multi_agent_graph` 执行流程图”，这样你会比只看代码快很多。
