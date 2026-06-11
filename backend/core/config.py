"""
共享初始化配置：数据库连接、LLM 模型、记忆存储、状态定义、工具函数。
所有其他模块都从这里导入共享资源。
"""

import os
from typing import Annotated, TypedDict, Any, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)

# 避免代理软件（如 Clash）拦截导致阿里云 DashScope 连接发生 SSL UNEXPECTED_EOF 错误
import os
if "NO_PROXY" in os.environ:
    if "dashscope.aliyuncs.com" not in os.environ["NO_PROXY"]:
        os.environ["NO_PROXY"] += ",dashscope.aliyuncs.com"
else:
    os.environ["NO_PROXY"] = "dashscope.aliyuncs.com"

from langgraph.graph.message import add_messages
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import BaseMessage
from langchain.chat_models import init_chat_model
from langchain_community.utilities.sql_database import SQLDatabase
from sqlalchemy import create_engine


# ============================================================
# 数据库初始化
# ============================================================
postgres_url = os.environ.get("POSTGRES_URL")

if postgres_url:
    # 优化：在 Windows 上，将 localhost 替换为 127.0.0.1 可免除 IPv6 & IPv4 双栈轮询导致的额外 3 秒连接超时时间
    if "@localhost" in postgres_url:
        postgres_url = postgres_url.replace("@localhost", "@127.0.0.1", 1)

if postgres_url and postgres_url.startswith("postgresql://") and "+psycopg" not in postgres_url:
    postgres_url = postgres_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = None
if postgres_url:
    try:
        connect_args = {"connect_timeout": 3} if postgres_url.startswith("postgresql+") else {}
        postgres_engine = create_engine(postgres_url, connect_args=connect_args, pool_pre_ping=True)
        with postgres_engine.connect() as connection:
            connection.close()
        engine = postgres_engine
        safe_url = engine.url.render_as_string(hide_password=True)
        print(f"[DATABASE] PostgreSQL engine connected: {safe_url}")
    except Exception as e:
        print(f"[DATABASE] WARNING: Failed to connect PostgreSQL, falling back to SQLite: {e}")
        engine = None

if not engine:
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "chinook.db")
    engine = create_engine(f"sqlite:///{db_path}")

db = SQLDatabase(engine)


# ============================================================
# LLM 模型初始化
# ============================================================
llm_model = os.environ.get("LLM_MODEL", "anthropic:qwen3.6-plus")
llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
llm_max_retries = int(os.environ.get("LLM_MAX_RETRIES", "1"))
llm_max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "256"))

try:
    if llm_model.startswith("tongyi:"):
        from langchain_community.chat_models import ChatTongyi
        model_real_name = llm_model.split(":", 1)[1]
        model = ChatTongyi(
            model=model_real_name,
            dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY"),
            temperature=llm_temperature,
            streaming=True,
            max_retries=llm_max_retries,
            model_kwargs={"max_tokens": llm_max_tokens},
        )
    else:
        # 优化：增加 timeout=8.0 限制，防止网络抖动时 LLM 请求无限期挂起；开启 streaming=True 支持流式输出，提升用户体验并解决长回复挂起感
        model = init_chat_model(
            llm_model,
            temperature=llm_temperature,
            max_retries=llm_max_retries,
            max_tokens=llm_max_tokens,
            timeout=8.0,
            streaming=True,
        )
    print(f"[MODEL] LLM model initialized: {llm_model} (temp={llm_temperature}, retries={llm_max_retries}, max_tokens={llm_max_tokens})")
except Exception as e:
    print(f"[MODEL] WARNING: Failed to initialize LLM model: {e}")
    model = None


# ============================================================
# 长期记忆与状态持久化 (Checkpointer)
# ============================================================
in_memory_store = InMemoryStore()

from langgraph.checkpoint.memory import MemorySaver

# FastAPI 的 /api/chat/stream 使用 graph.astream()/aget_state()，需要异步兼容的 checkpointer。
# 同步 PostgresSaver 不实现 aget_tuple，会在流式接口中抛 NotImplementedError。
# PostgreSQL 仍用于 FAQ/RAG 数据；线程 checkpoint 暂用 MemorySaver 保证异步接口稳定。
checkpointer = MemorySaver()
postgres_pool = None
print("[CHECKPOINTER] InMemory checkpointer (MemorySaver) initialized for async LangGraph streaming.")


# ============================================================
# 共享状态定义
# ============================================================
class State(TypedDict):
    """常规图 / HITL 图使用的状态结构。"""
    messages: Annotated[list[BaseMessage], add_messages]


# ============================================================
# 工具函数
# ============================================================
def message_content_to_text(content: Any) -> str:
    """Normalize LangChain message content blocks into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")
