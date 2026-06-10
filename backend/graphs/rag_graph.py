"""
RAG 检索问答图。
从向量知识库检索相关段落，构建增强提示词，调用 LLM 生成回答。
"""

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage

from core.config import model, message_content_to_text, checkpointer
from core.rag import rag_store


# ============================================================
# 状态定义
# ============================================================
class RagState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    context: str


# ============================================================
# 辅助函数
# ============================================================
def _build_rag_prompt(references: list) -> str:
    """构建 RAG 系统提示词。"""
    if not references:
        return (
            "你是基于知识库的智能助手。\n"
            "当前知识库为空，无法提供任何参考资料。\n"
            "请根据你自身的知识回答用户的问题。如果不确定，请如实告知。"
        )

    ref_text = "\n".join(
        f"[{i+1}] {doc.page_content}"
        for i, doc in enumerate(references)
    )
    return (
        "你是基于知识库的智能助手。请根据以下参考资料回答问题。\n"
        "如果参考资料不足以回答问题，请明确告知用户知识库中找不到相关信息。\n\n"
        f"参考资料：\n{ref_text}"
    )


# ============================================================
# RAG 问答节点
# ============================================================
def rag_assistant_node(state: RagState) -> dict:
    """检索相关段落，构建增强提示词，调用 LLM 生成回答。"""
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}

    question = message_content_to_text(messages[-1].content)
    references = rag_store.query(question, top_k=5)
    system_prompt = _build_rag_prompt(references)

    try:
        response = model.invoke(
            [SystemMessage(content=system_prompt)] + messages
        )
        return {"messages": [response]}
    except Exception as e:
        print(f"[RAG] Assistant node error: {e}")
        from langchain_core.messages import AIMessage
        err_msg = AIMessage(
            content="【系统提示】系统检测到接口服务繁忙或达到限额，暂时无法生成智能回答，请稍后再试。"
        )
        return {"messages": [err_msg]}


# ============================================================
# 构建 RAG 图
# ============================================================
rag_builder = StateGraph(RagState, input_schema=RagState)
rag_builder.add_node("rag_assistant", rag_assistant_node)
rag_builder.add_edge(START, "rag_assistant")
rag_builder.add_edge("rag_assistant", END)

rag_graph = rag_builder.compile(
    checkpointer=checkpointer,
    name="rag_graph"
)
