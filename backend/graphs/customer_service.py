"""
AI 客服自动回复系统。
流程：规则分流 → FAQ 向量匹配（pgvector） → LLM 兜底回答 → 人工客服中断。
"""

import time
from functools import wraps
from typing import Annotated, TypedDict, Any, List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

from core.config import model, message_content_to_text, checkpointer
from core.faq_store import find_seed_faq_answer, search_faq


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
def log_node_time(func):
    """Print per-node execution time for customer-service graph debugging."""
    @wraps(func)
    def wrapper(state: CustomerServiceState):
        started_at = time.perf_counter()
        print(f"[CustomerService][Node:{func.__name__}] start")
        try:
            result = func(state)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[CustomerService][Node:{func.__name__}] error after {elapsed_ms:.0f}ms: {e}")
            raise
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[CustomerService][Node:{func.__name__}] end elapsed={elapsed_ms:.0f}ms")
        return result
    return wrapper


@log_node_time
def classify_intent(state: CustomerServiceState):
    """快速规则分类，避免客服入口每轮都先调用一次 LLM。"""
    messages = state.get("messages", [])
    if not messages:
        return {"category": "complex"}

    last_message = message_content_to_text(messages[-1].content)
    last_message_stripped = last_message.strip()
    last_message_lower = last_message_stripped.lower()

    # 规则 1：快速规则匹配人工客服
    human_keywords = [
        "找人工", "接人工", "转客服", "转接人工", "人工服务", "人工客服", "转人工", "人工回复",
        "投诉", "人工处理", "人工介入", "human", "agent", "complaint",
    ]
    if any(kw in last_message_lower for kw in human_keywords):
        print(f"[CustomerService] Rule-based intent classification: human")
        return {"category": "human"}

    # 规则 2：常见 FAQ 快速命中，跳过大模型和向量检索
    faq_answer, _ = find_seed_faq_answer(last_message_stripped)
    if faq_answer:
        print("[CustomerService] Rule-based intent classification (seed FAQ match): faq")
        return {"category": "faq"}

    # 未命中明确人工或精确 FAQ 时，先进入 FAQ 检索；未命中再由 LLM 兜底。
    return {"category": "complex"}


@log_node_time
def faq_retriever(state: CustomerServiceState):
    """FAQ 检索节点：命中则直接回答，未命中降级给 LLM。"""
    category = state.get("category", "complex")
    messages = state.get("messages", [])
    if not messages:
        return {"faq_answer": "", "confidence": 0.0}

    if category == "human":
        return {"faq_answer": "", "confidence": 0.0}

    question = message_content_to_text(messages[-1].content)
    question_stripped = question.strip()

    # 优先匹配内存中的 FAQ 和常见问法，避免网络/数据库开销
    answer, seed_score = find_seed_faq_answer(question_stripped)
    if answer:
        print(f"[CustomerService] Exact FAQ match for '{question_stripped}'")
        faq_msg = AIMessage(content=f"【FAQ标准解答】\n{answer}")
        return {
            "faq_answer": answer,
            "confidence": seed_score,
            "messages": [faq_msg]
        }

    started_at = time.perf_counter()
    answer, score = search_faq(question)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    print(f"[CustomerService] FAQ lookup for '{question}': score={score:.4f}, hit={bool(answer)}")
    print(f"[CustomerService] FAQ lookup elapsed: {elapsed_ms:.0f}ms")

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


@log_node_time
def llm_responder(state: CustomerServiceState):
    """复杂问题兜底：用 LLM 生成详细回答。"""
    if state.get("faq_answer"):
        return {}

    messages = state.get("messages", [])[-6:]
    system_prompt = """你是数字音乐商店客服。请用中文简洁回答，优先给可执行步骤。
要求：
1. 回复控制在 120 字以内。
2. 不要展开无关背景。
3. 如果需要人工查询订单、账号或机密数据，在末尾加：[建议转接人工客服]"""
    try:
        started_at = time.perf_counter()
        response = model.invoke([SystemMessage(content=system_prompt)] + messages)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[CustomerService] LLM responder elapsed: {elapsed_ms:.0f}ms")
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


@log_node_time
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

customer_service_graph = customer_service_builder.compile(
    checkpointer=checkpointer,
    name="customer_service_graph"
)
