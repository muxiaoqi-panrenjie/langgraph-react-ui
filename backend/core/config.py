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
llm_max_retries = int(os.environ.get("LLM_MAX_RETRIES", "3"))

try:
    model = init_chat_model(llm_model, temperature=llm_temperature, max_retries=llm_max_retries)
    print(f"[MODEL] LLM model initialized: {llm_model} (temp={llm_temperature}, retries={llm_max_retries})")
except Exception as e:
    print(f"[MODEL] WARNING: Failed to initialize LLM model: {e}")
    model = None


# ============================================================
# 长期记忆与状态持久化 (Checkpointer)
# ============================================================
in_memory_store = InMemoryStore()

checkpointer = None
postgres_pool = None

if postgres_url:
    try:
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver
        
        # psycopg3 ConnectionPool 不支持 "postgresql+psycopg://" 方案，因此需使用标准的 "postgresql://" 方案
        pg_conn_url = postgres_url
        if pg_conn_url.startswith("postgresql+psycopg://"):
            pg_conn_url = pg_conn_url.replace("postgresql+psycopg://", "postgresql://", 1)
        
        # 使用连接池，并设置 autocommit=True 避免事务阻塞导致 CREATE INDEX 失败
        postgres_pool = ConnectionPool(pg_conn_url, kwargs={"autocommit": True})
        checkpointer = PostgresSaver(postgres_pool)
        checkpointer.setup()
        print("[CHECKPOINTER] PostgresSaver initialized successfully.")
    except Exception as e:
        print(f"[CHECKPOINTER] WARNING: Failed to initialize PostgresSaver: {e}")
        checkpointer = None

if not checkpointer:
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    print("[CHECKPOINTER] InMemory checkpointer (MemorySaver) fallback initialized.")


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
