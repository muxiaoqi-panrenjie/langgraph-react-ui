"""
HITL 图：支持人工审批中断。
复用 regular_graph 中的 assistant 节点，但工具节点使用 hitl_tools_by_name。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import ToolMessage

from config import State
from regular_graph import assistant
from tools import hitl_tools_by_name, hitl_tools


# ============================================================
# HITL 工具节点（带中断审批）
# ============================================================
def hitl_tool_node(state: State):
    """执行带中断的工具。

    当工具内部调用 interrupt() 时，LangGraph 会引发 Interrupt 异常，
    图执行暂停并返回 __interrupt__ 信息。调用者通过 Command(resume=...) 恢复。
    """
    messages = state["messages"]
    last_message = messages[-1]

    tool_outputs = []
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_func = hitl_tools_by_name.get(tool_name)
            if tool_func:
                res = tool_func.invoke(tool_args)
                tool_outputs.append(
                    ToolMessage(content=res, tool_call_id=tool_call["id"], name=tool_name)
                )
    return {"messages": tool_outputs}


# ============================================================
# 条件路由
# ============================================================
def should_continue_hitl(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "hitl_tool_node"
    return END


# ============================================================
# 构建 HITL 图
# ============================================================
hitl_workflow = StateGraph(State)
hitl_workflow.add_node("assistant", assistant)
hitl_workflow.add_node("hitl_tool_node", hitl_tool_node)
hitl_workflow.add_edge(START, "assistant")
hitl_workflow.add_conditional_edges("assistant", should_continue_hitl, {
    "hitl_tool_node": "hitl_tool_node",
    END: END,
})
hitl_workflow.add_edge("hitl_tool_node", "assistant")

hitl_memory = MemorySaver()
hitl_graph = hitl_workflow.compile(checkpointer=hitl_memory, name="hitl_graph")
