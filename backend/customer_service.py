"""
AI 客服自动回复系统。
流程：意图分类 → FAQ 向量匹配（pgvector） → LLM 兜底回答 → 人工客服中断。
"""

import json
from typing import Annotated, TypedDict, Any, List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

from config import model, message_content_to_text
from faq_store import search_faq


# FAQ 向量检索已迁移至 faq_store.py（基于 pgvector + PostgreSQL）
# 使用 search_faq(query_text) 进行向量相似度匹配

# ============================================================
# 状态定义
# ============================================================
class CustomerServiceState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    category: str       # "faq", "complex", "human"
    faq_answer: str     # 匹配到的 FAQ 答案
    confidence: float   # 匹配置信度


# ============================================================
# 节点函数
# ============================================================
def classify_intent(state: CustomerServiceState):
    """用 LLM 把用户意图分为 faq / complex / human 三类。"""
    messages = state.get("messages", [])
    if not messages:
        return {"category": "complex"}

    last_message = message_content_to_text(messages[-1].content)

    prompt = f"""分析以下用户的最新输入，并将其分类为以下三种意图之一：
1. "faq"：用户提问属于常见的简单咨询（如：退款、修改密码、支付方式、下载歌曲、播放无声音、VIP会员、账号锁定等）。
2. "human"：用户明确要求转人工客服（如：找人工、接人工、转客服、人工服务、投诉等）。
3. "complex"：其他复杂问题，如需要深入解答的业务咨询、音乐推荐、发票查询或多步骤对话。

请严格仅输出以下 JSON 格式，不要包含任何 markdown 标记（如 ```json）或额外文字：
{{
  "category": "faq" 或 "complex" 或 "human"
}}

用户输入："{last_message}"
"""
    try:
        response = model.invoke([SystemMessage(content=prompt)])
        content = message_content_to_text(response.content).strip().lower()

        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
        category = data.get("category", "complex")
        if category not in ["faq", "complex", "human"]:
            category = "complex"
        print(f"[CustomerService] Classified user intent as: {category}")
        return {"category": category}
    except Exception as e:
        print(f"[CustomerService] Intent classification error: {e}")
        return {"category": "complex"}


def faq_retriever(state: CustomerServiceState):
    """FAQ 检索节点：命中则直接回答，未命中降级给 LLM。"""
    category = state.get("category", "complex")
    messages = state.get("messages", [])
    if not messages:
        return {"faq_answer": "", "confidence": 0.0}

    if category == "human":
        return {"faq_answer": "", "confidence": 0.0}

    question = message_content_to_text(messages[-1].content)
    answer, score = search_faq(question)
    print(f"[CustomerService] FAQ lookup for '{question}': score={score:.4f}, hit={bool(answer)}")

    if answer:
        faq_msg = AIMessage(content=f"【FAQ标准解答】\n{answer}")
        return {
            "faq_answer": answer,
            "confidence": score,
            "messages": [faq_msg]
        }
    else:
        new_category = category
        if category == "faq":
            new_category = "complex"
        return {
            "faq_answer": "",
            "confidence": score,
            "category": new_category
        }


def llm_responder(state: CustomerServiceState):
    """复杂问题兜底：用 LLM 生成详细回答。"""
    if state.get("faq_answer"):
        return {}

    messages = state.get("messages", [])
    system_prompt = """你是数字音乐商店的专家客服代表。请根据用户的上下文，友好、专业、详尽地回答用户的问题。
如果用户提问的内容超出了你的服务能力，或者你需要手动查询核心机密数据，你可以在回复的末尾加上：[建议转接人工客服]"""
    try:
        response = model.invoke([SystemMessage(content=system_prompt)] + messages)
        content = message_content_to_text(response.content)
        if "[建议转接人工客服]" in content:
            print("[CustomerService] LLM suggested escalating to human agent via tag.")
            return {"messages": [response], "category": "human"}
        return {"messages": [response]}
    except Exception as e:
        print(f"[CustomerService] LLM responder error: {e}")
        # 如果 LLM 报错（例如 429 额度不足），我们自动推荐转人工，提升用户体验
        err_msg = AIMessage(
            content="【系统提示】由于当前咨询人数较多或系统繁忙，为了更好地解答您的问题，正在为您推荐转接人工客服。请在下方输入您的回复..."
        )
        return {
            "messages": [err_msg],
            "category": "human"
        }


def human_backup(state: CustomerServiceState):
    """人工兜底：通过 interrupt() 暂停，等待人工客服输入。"""
    messages = state.get("messages", [])
    question = message_content_to_text(messages[-1].content) if messages else ""

    response = interrupt({
        "type": "tool_approval",
        "tool_name": "human_agent_reply",
        "args": {"reply": ""},
        "message": f"用户已触发人工客服兜底。用户问题：'{question}'。请输入人工客服的回复内容：",
        "severity": "medium"
    })

    reply = ""
    if isinstance(response, dict):
        if response.get("action") == "approve":
            reply = response.get("reply", "您好，我是人工客服。非常抱歉让您久等了，请问有什么可以帮您的？")
        elif response.get("action") == "edit":
            reply = response.get("reply", "")
        elif response.get("action") == "reject":
            reply = "【人工客服】用户取消了人工服务请求。"
        else:
            reply = response.get("reply", "")
    else:
        reply = str(response)

    human_msg = AIMessage(content=f"【人工客服回复】\n{reply}")
    return {"messages": [human_msg], "category": "complex"}


# ============================================================
# 条件路由
# ============================================================
def should_continue_cs(state: CustomerServiceState):
    category = state.get("category")
    faq_answer = state.get("faq_answer")

    if category == "human":
        return "human_backup"
    if faq_answer:
        return END
    return "llm_responder"


def should_continue_after_llm(state: CustomerServiceState):
    category = state.get("category")
    if category == "human":
        return "human_backup"
    return END


# ============================================================
# 构建智能客服流图
# ============================================================
customer_service_builder = StateGraph(CustomerServiceState, input_schema=CustomerServiceState)
customer_service_builder.add_node("classify_intent", classify_intent)
customer_service_builder.add_node("faq_retriever", faq_retriever)
customer_service_builder.add_node("llm_responder", llm_responder)
customer_service_builder.add_node("human_backup", human_backup)

customer_service_builder.add_edge(START, "classify_intent")
customer_service_builder.add_edge("classify_intent", "faq_retriever")

customer_service_builder.add_conditional_edges(
    "faq_retriever",
    should_continue_cs,
    {
        "human_backup": "human_backup",
        "llm_responder": "llm_responder",
        END: END
    }
)

customer_service_builder.add_conditional_edges(
    "llm_responder",
    should_continue_after_llm,
    {
        "human_backup": "human_backup",
        END: END
    }
)

customer_service_builder.add_edge("human_backup", END)

customer_service_memory = MemorySaver()
customer_service_graph = customer_service_builder.compile(
    checkpointer=customer_service_memory,
    name="customer_service_graph"
)
