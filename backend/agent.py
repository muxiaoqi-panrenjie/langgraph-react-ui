"""
Agent 聚合入口：从各子模块导入并汇总所有 LangGraph 图和工具。
main.py 通过此文件获取所需的图和函数，保持对外接口不变。

拆分结构：
  config.py          — DB / LLM / 共享状态 / 工具函数
  tools.py           — 所有工具函数（常规 + HITL）+ 中间件
  regular_graph.py   — 常规 Agent 图（含 assistant 路由逻辑）
  hitl_graph.py      — HITL 审批图
  multi_agent.py     — 多智能体客服系统（音乐 + 发票 + 记忆）
  rag_graph.py       — RAG 检索问答图
  customer_service.py — AI 客服自动回复（FAQ + 意图分类 + 人工兜底）
"""

from core.config import message_content_to_text
from core.tools import regular_tools, hitl_tools, hitl_tools_by_name
from graphs.regular_graph import graph
from graphs.hitl_graph import hitl_graph
from graphs.multi_agent import multi_agent_graph, music_tools, invoice_tools
from graphs.rag_graph import rag_graph
from graphs.customer_service import customer_service_graph


def get_tools_meta():
    """返回所有工具的元数据，用于前端 HITL 审批表单生成。"""
    result = []
    for t in regular_tools + hitl_tools + music_tools + invoice_tools:
        result.append({
            "name": t.name,
            "description": t.description or "",
        })
    return result
