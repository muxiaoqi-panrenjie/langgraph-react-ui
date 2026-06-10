"""
常规 Agent 图：无中断，支持天气/邮件/研究/电影/代码等多个 Agent。
assistant 节点同时也被 HITL 图复用。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from config import State, message_content_to_text
from tools import tools_by_name, regular_tools, hitl_tools


# ============================================================
# 助手节点（LLM 路由）—— 根据 assistant_id 分发到不同 Agent
# ============================================================
def assistant(state: State, config: RunnableConfig = None):
    messages = state["messages"]
    last_message = messages[-1]

    # 如果最后一条是 ToolMessage，总结工具结果
    if isinstance(last_message, ToolMessage):
        reply = f"根据工具的查询结果，以下是为您整理的信息：\n\n{last_message.content}"
        return {"messages": [AIMessage(content=reply)]}

    content = last_message.content.lower() if last_message.content else ""

    assistant_id = "101 Weather Agent"
    if config and "configurable" in config:
        assistant_id = config["configurable"].get("assistant_id", "101 Weather Agent")

    # A. 101 Weather Agent
    if assistant_id == "101 Weather Agent":
        if any(k in content for k in ["weather", "天气", "旧金山", "sf"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "get_weather",
                            "args": {"location": "旧金山"},
                            "id": "call_weather_mock_id"
                        }]
                    )
                ]
            }
        reply = f"【101 天气助手】您好！您可以试着问我天气相关问题。"
        return {"messages": [AIMessage(content=reply)]}

    # B. Email Agent (HITL 版本)
    elif assistant_id == "Email Agent":
        if any(k in content for k in ["email", "邮件", "发送", "发信", "mail"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "send_email_hitl",
                            "args": {
                                "to_address": "manager@company.com",
                                "subject": "工作周报汇报",
                                "body": last_message.content
                            },
                            "id": "call_email_hitl_id"
                        }]
                    )
                ]
            }
        reply = f"【邮件助手】您可以尝试发送一封邮件给我。"
        return {"messages": [AIMessage(content=reply)]}

    # C. Research Agent
    elif assistant_id == "Research Agent":
        if any(k in content for k in ["research", "paper", "论文", "学术", "检索", "文献"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "search_papers",
                            "args": {"query": last_message.content},
                            "id": "call_research_mock_id"
                        }]
                    )
                ]
            }
        reply = f"【学术研究助手】您可以尝试检索学术论文。"
        return {"messages": [AIMessage(content=reply)]}

    # D. Deep Agent
    elif assistant_id == "Deep Agent":
        if any(k in content for k in ["movie", "电影", "科幻", "sci-fi"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "search_movies",
                            "args": {"genre": "科幻"},
                            "id": "call_movie_mock_id"
                        }]
                    )
                ]
            }
        reply = f"【深度思考智能体】我可以帮您搜索电影或回答复杂问题！"
        return {"messages": [AIMessage(content=reply)]}

    # E. Code Agent
    elif assistant_id == "Code Agent":
        if any(k in content for k in ["code", "代码", "编程", "写代码", "python", "java", "javascript", "js", "cpp", "c++"]):
            lang = "python"
            if "java" in content:
                lang = "java"
            elif "javascript" in content or "js" in content:
                lang = "javascript"
            elif "cpp" in content or "c++" in content:
                lang = "c++"
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "write_code",
                            "args": {"language": lang, "requirement": last_message.content},
                            "id": "call_code_mock_id"
                        }]
                    )
                ]
            }
        reply = f"【代码生成助手】您可以试着让我写代码。"
        return {"messages": [AIMessage(content=reply)]}

    # F. Music Store Supervisor
    elif "supervisor" in assistant_id.lower():
        reply = f"【音乐商店监督员】已收到您的指示。"
        return {"messages": [AIMessage(content=reply)]}

    # G. HITL Agent (HITL Demo - 支持所有 HITL 工具)
    elif "hitl" in assistant_id.lower() or "approval" in assistant_id.lower():
        content_lower = content
        if any(k in content_lower for k in ["delete", "删除", "drop", "destroy"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "delete_database",
                            "args": {"database_name": "production_db"},
                            "id": "call_delete_hitl_id"
                        }]
                    )
                ]
            }
        elif any(k in content_lower for k in ["purchase", "采购", "buy", "购买"]):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "make_purchase",
                            "args": {"item_name": "Enterprise Server", "amount": 1500.0},
                            "id": "call_purchase_hitl_id"
                        }]
                    )
                ]
            }
        reply = f"【HITL 演示助手】我支持需要人工审批的操作。试试：'删除 production_db 数据库' 或 '采购一台企业服务器'。"
        return {"messages": [AIMessage(content=reply)]}

    # H. 默认
    reply = f"您好！我是智能体（{assistant_id}）。收到您的消息。"
    return {"messages": [AIMessage(content=reply)]}


# ============================================================
# 工具节点（常规，无中断）
# ============================================================
def tool_node(state: State):
    messages = state["messages"]
    last_message = messages[-1]

    tool_outputs = []
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_func = tools_by_name.get(tool_name)
            if tool_func:
                res = tool_func.invoke(tool_args)
                tool_outputs.append(
                    ToolMessage(content=res, tool_call_id=tool_call["id"], name=tool_name)
                )
    return {"messages": tool_outputs}


# ============================================================
# 条件路由
# ============================================================
def should_continue(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END


# ============================================================
# 构建常规图
# ============================================================
workflow = StateGraph(State)
workflow.add_node("assistant", assistant)
workflow.add_node("tool_node", tool_node)
workflow.add_edge(START, "assistant")
workflow.add_conditional_edges("assistant", should_continue, {
    "tool_node": "tool_node",
    END: END,
})
workflow.add_edge("tool_node", "assistant")

memory = MemorySaver()
graph = workflow.compile(checkpointer=memory, name="regular_graph")
