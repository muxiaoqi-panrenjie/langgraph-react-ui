"""
共享初始化配置：数据库连接、LLM 模型、记忆存储、状态定义、工具函数。
所有其他模块都从这里导入共享资源。
"""

import os
from typing import Annotated, TypedDict, Any, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)

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
try:
    model = init_chat_model("anthropic:qwen3.6-plus", max_retries=3)
    print("[MODEL] LLM model initialized successfully.")
except Exception as e:
    print(f"[MODEL] WARNING: Failed to initialize LLM model: {e}")
    model = None


# ============================================================
# 长期记忆存储
# ============================================================
in_memory_store = InMemoryStore()


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
