import asyncio
import datetime
import json
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

# 导入图定义
from agent import graph, hitl_graph, multi_agent_graph, rag_graph, customer_service_graph, get_tools_meta, hitl_tools_by_name, message_content_to_text
from core.rag import rag_store, split_text

app = FastAPI(title="LangGraph Custom FastAPI Server")

# 配置 CORS 允许 React 前端跨域连接
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------
# Assistant 列表 - 新增 HITL Demo Agent
# ----------------------------------------------------------
ALL_ASSISTANTS = [
    {"assistant_id": "101 Weather Agent", "name": "101 Weather Agent", "graph_id": "regular"},
    {"assistant_id": "Email Agent", "name": "Email Agent (HITL)", "graph_id": "hitl"},
    {"assistant_id": "Research Agent", "name": "Research Agent", "graph_id": "regular"},
    {"assistant_id": "Deep Agent", "name": "Deep Agent", "graph_id": "regular"},
    {"assistant_id": "Code Agent", "name": "Code Agent", "graph_id": "regular"},
    {"assistant_id": "HITL Demo Agent", "name": "HITL Demo Agent", "graph_id": "hitl"},
    {"assistant_id": "Multi-Agent Assistant", "name": "Multi-Agent Assistant", "graph_id": "hitl"},
    {"assistant_id": "RAG Assistant", "name": "RAG Assistant", "graph_id": "rag"},
    {"assistant_id": "AI Customer Service", "name": "AI 客服自动回复", "graph_id": "hitl"},
]


@app.get("/api/assistants")
async def list_assistants():
    return ALL_ASSISTANTS


@app.post("/api/threads")
async def create_thread():
    thread_id = str(uuid.uuid4())
    return {
        "thread_id": thread_id,
        "created_at": datetime.datetime.utcnow().isoformat()
    }


@app.get("/api/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    """获取线程历史消息。同时检查是否有待处理的中断。"""
    config = {"configurable": {"thread_id": thread_id}}

    state = None
    for g in [graph, hitl_graph, multi_agent_graph, rag_graph, customer_service_graph]:
        try:
            s = g.get_state(config)
            if s.values.get("messages"):
                state = s
                break
        except Exception:
            continue

    if not state:
        try:
            state = multi_agent_graph.get_state(config)
        except Exception:
            try:
                state = rag_graph.get_state(config)
            except Exception:
                return []

    messages = state.values.get("messages", [])

    formatted = []
    for m in messages:
        role = "user"
        if m.type == "ai":
            role = "assistant"
        elif m.type == "system":
            role = "system"
        elif m.type == "tool":
            role = "tool"

        tool_calls = getattr(m, "tool_calls", None)

        formatted.append({
            "id": m.id,
            "role": role,
            "content": message_content_to_text(m.content),
            "name": getattr(m, "name", None),
            "tool_calls": tool_calls
        })

    return formatted


# ----------------------------------------------------------
# HITL 相关 API
# ----------------------------------------------------------
@app.get("/api/interrupt/{thread_id}")
async def get_interrupt(thread_id: str):
    """检查指定线程是否有待处理的中断。

    如果有中断，返回中断信息供前端展示审批表单。
    """
    config = {"configurable": {"thread_id": thread_id}}

    for g in [hitl_graph, graph, multi_agent_graph, rag_graph]:
        try:
            state = g.get_state(config)
            interrupts = state.tasks[0].interrupts if state.tasks else []
            if interrupts:
                interrupt_data = interrupts[0].value
                return JSONResponse({
                    "thread_id": thread_id,
                    "interrupt": interrupt_data,
                })
        except Exception:
            continue

    return JSONResponse({"thread_id": thread_id, "interrupt": None})


@app.post("/api/resume")
async def resume_execution(request: Request):
    """恢复被中断的线程执行。

    接收用户的审批决策（approve/reject/edit），通过 Command(resume=...) 恢复图执行。
    """
    body = await request.json()
    thread_id = body.get("thread_id")
    resume_data = body.get("resume_data", {})
    assistant_id = body.get("assistant_id", "HITL Demo Agent")

    config = {"configurable": {"thread_id": thread_id, "assistant_id": assistant_id}}

    # 确定使用哪个图
    if assistant_id == "Multi-Agent Assistant":
        the_graph = multi_agent_graph
    elif assistant_id in ["Email Agent", "HITL Demo Agent"]:
        the_graph = hitl_graph
    elif assistant_id == "RAG Assistant":
        the_graph = rag_graph
    elif assistant_id == "AI Customer Service":
        the_graph = customer_service_graph
    else:
        the_graph = graph

    # 从 LangGraph 的 Command 恢复执行
    from langgraph.types import Command
    result = the_graph.invoke(Command(resume=resume_data), config)

    # 获取最后一条消息内容
    messages = result.get("messages", [])
    last_msg = messages[-1] if messages else None
    content = message_content_to_text(last_msg.content) if last_msg else ""

    return {"content": content, "thread_id": thread_id}


# ----------------------------------------------------------
# 主对话流路由
# ----------------------------------------------------------
@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """主对话流路由。接收用户消息并在 LangGraph 中执行。"""
    body = await request.json()
    thread_id = body.get("thread_id")
    assistant_id = body.get("assistant_id", "101 Weather Agent")
    message = body.get("message")

    # 根据 assistant_id 决定使用哪个图
    if assistant_id == "Multi-Agent Assistant":
        the_graph = multi_agent_graph
    elif assistant_id in ["Email Agent", "HITL Demo Agent"]:
        the_graph = hitl_graph
    elif assistant_id == "RAG Assistant":
        the_graph = rag_graph
    elif assistant_id == "AI Customer Service":
        the_graph = customer_service_graph
    else:
        the_graph = graph

    config = {"configurable": {"thread_id": thread_id, "assistant_id": assistant_id}}
    inputs = {"messages": [{"role": "user", "content": message}]}

    async def event_generator():
        async for chunk in the_graph.astream(inputs, config, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                # 处理 LangGraph interrupt 信号：__interrupt__ 节点的 node_output 是 tuple，不是 dict
                # 直接通知前端有中断，跳过正常消息处理
                if node_name == "__interrupt__":
                    interrupt_val = node_output[0].value if isinstance(node_output, tuple) and node_output else {}
                    yield f"data: {json.dumps({'type': 'interrupt', 'interrupt': interrupt_val})}\n\n"
                    continue

                # 其余节点的输出必须是 dict，否则跳过
                if not isinstance(node_output, dict):
                    continue

                messages = node_output.get("messages", [])
                last_msg = messages[-1] if messages else None

                status = "completed"
                tool_name = None

                if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    status = "calling_tool"
                    tool_name = ", ".join([tc["name"] for tc in last_msg.tool_calls])

                # 1. 步骤变更通知
                yield f"data: {json.dumps({'type': 'step', 'node': node_name, 'status': status, 'toolName': tool_name})}\n\n"

                # 2. 助手文本流式输出
                if node_name in ["assistant", "supervisor", "rag_assistant", "llm_responder", "faq_retriever"] and last_msg and last_msg.content:
                    content = message_content_to_text(last_msg.content)
                    for char in content:
                        yield f"data: {json.dumps({'type': 'token', 'text': char})}\n\n"
                        await asyncio.sleep(0.015)

        # 3. 执行完成后检查是否有中断
        config_check = {"configurable": {"thread_id": thread_id}}
        for g in [hitl_graph, graph, multi_agent_graph, customer_service_graph]:
            try:
                state = g.get_state(config_check)
                tasks = state.tasks
                if tasks and tasks[0].interrupts:
                    interrupt_data = tasks[0].interrupts[0].value
                    yield f"data: {json.dumps({'type': 'interrupt', 'interrupt': interrupt_data})}\n\n"
                    break
            except Exception:
                continue

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ----------------------------------------------------------
# 工具元数据
# ----------------------------------------------------------
@app.get("/api/tools")
async def list_tools():
    return get_tools_meta()


# ----------------------------------------------------------
# RAG 文档管理 API
# ----------------------------------------------------------
@app.post("/api/rag/upload")
async def upload_document(request: Request):
    """上传文档：切分段落 → 向量化 → 存入向量库。"""
    body = await request.json()
    content = body.get("content", "").strip()
    source = body.get("source", "untitled").strip()

    if not content:
        return JSONResponse({"error": "文档内容不能为空"}, status_code=400)

    # 切分段落
    chunks = split_text(content)

    # 向量化并入库
    chunk_count = rag_store.add_documents(chunks, source)

    return {"chunk_count": chunk_count, "source": source}


@app.get("/api/rag/documents")
async def list_documents():
    """列出已上传的文档。"""
    return rag_store.list_documents()


@app.get("/api/rag/documents/{source}/chunks")
async def get_document_chunks(source: str):
    """获取指定文档的切片内容。"""
    chunks = rag_store.get_document_chunks(source)
    # 检查文档是否存在，防止返回空数组时分不清是空文档还是不存在的文档
    existing_sources = [d["source"] for d in rag_store.list_documents()]
    if source not in existing_sources:
        return JSONResponse({"error": f"文档 {source} 不存在"}, status_code=404)
    return chunks


@app.delete("/api/rag/documents")
async def clear_all_documents():
    """清空所有文档。"""
    rag_store.clear_all()
    return {"message": "所有文档已清空"}


@app.delete("/api/rag/documents/{source}")
async def delete_document(source: str):
    """删除指定文档。"""
    success = rag_store.remove_document(source)
    if success:
        return {"message": f"文档 {source} 已删除"}
    return JSONResponse({"error": f"文档 {source} 不存在"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
