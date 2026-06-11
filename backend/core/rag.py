"""
RAG (Retrieval-Augmented Generation) 核心模块

提供文档切分、向量化、存储和检索功能。
使用 DashScope text-embedding-v3 作为嵌入模型，
使用 InMemoryVectorStore 作为内存向量存储。
"""

import os
import uuid
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


# --- Embeddings ---

import requests
import urllib3
from typing import List
from langchain_core.embeddings import Embeddings

# 禁用 SSL 警告（避免 verify=False 产生的警告日志）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DashScopeMultimodalEmbeddings(Embeddings):
    """自定义通义多模态向量模型 Embeddings 包装器。
    
    使用 requests 直接调用通义多模态向量接口，并禁用 SSL 验证以避免本地证书/TLS 握手报错。
    """
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key
        self.url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"

    def _embed(self, texts: List[str]) -> List[List[float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        embeddings = []
        for text in texts:
            data = {
                "model": self.model,
                "input": {
                    "contents": [
                        {"text": text}
                    ]
                }
            }
            resp = requests.post(self.url, headers=headers, json=data, verify=False, timeout=5)
            if resp.status_code == 200:
                res_json = resp.json()
                embedding = res_json["output"]["embeddings"][0]["embedding"]
                embeddings.append(embedding)
            else:
                raise ValueError(f"DashScope Multimodal Embedding failed: {resp.status_code} {resp.text}")
        return embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]


_embeddings: Optional[Embeddings] = None


def get_embeddings() -> Embeddings:
    """获取多模态向量模型单例。"""
    global _embeddings
    if _embeddings is None:
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        model_name = os.environ.get("DASHSCOPE_EMBEDDING_MODEL") or "text-embedding-v3"
        if not api_key:
            # 兼容旧版本，降级读取 ANTHROPIC_API_KEY
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            
        if api_key and model_name == "tongyi-embedding-vision-plus-2026-03-06":
            # 用户提供的多模态向量模型专有 Key 或模型
            _embeddings = DashScopeMultimodalEmbeddings(
                model=model_name,
                api_key=api_key
            )
        else:
            # 备用：默认的 DashScopeEmbeddings
            _embeddings = DashScopeEmbeddings(
                model=model_name,
                dashscope_api_key=api_key,
            )
    return _embeddings


# --- Document Processor ---

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
)


def split_text(text: str) -> list[str]:
    """将长文本切分为段落。"""
    chunks = _splitter.split_text(text)
    return chunks


# --- Vector Store ---

class RAGVectorStore:
    """封装 PGVector 向量存储，支持 PostgreSQL 持久化文档添加、查询、删除。"""

    def __init__(self):
        self._store = None

    def _get_store(self):
        if self._store is None:
            from core.config import engine, postgres_url
            # 如果数据库不是 PostgreSQL (例如降级为了 SQLite 或连接失败)，
            # 我们直接抛出友好异常，避免由于 TCP timeout 导致整个后台线程被挂起 30 秒
            is_postgres = engine is not None and engine.dialect.name == "postgresql"
            if not is_postgres:
                raise RuntimeError("PostgreSQL 数据库未连接，RAG 向量存储不可用")

            from langchain_postgres import PGVector
            self._store = PGVector(
                embeddings=get_embeddings(),
                collection_name="rag_documents",
                connection=postgres_url
            )
        return self._store

    def add_documents(self, texts: list[str], source: str) -> int:
        """添加文档段落，返回添加的 chunk 数量。"""
        if not texts:
            return 0

        store = self._get_store()
        docs = []

        for text in texts:
            chunk_id = str(uuid.uuid4())
            doc = Document(
                page_content=text,
                metadata={"source": source, "chunk_id": chunk_id},
            )
            docs.append(doc)

        store.add_documents(docs)
        return len(docs)

    def query(self, text: str, top_k: int = 5) -> list[Document]:
        """检索最相关的段落。"""
        store = self._get_store()
        results = store.similarity_search(text, k=top_k)
        return results

    def list_documents(self) -> list[dict]:
        """从数据库查询已上传的文档及其 chunk 数量。"""
        from core.config import engine
        from sqlalchemy import text
        query = text("""
            SELECT cmetadata->>'source' AS source, COUNT(*) AS chunk_count
            FROM langchain_pg_embedding
            WHERE cmetadata->>'source' IS NOT NULL
            GROUP BY cmetadata->>'source'
        """)
        try:
            with engine.connect() as conn:
                rows = conn.execute(query).fetchall()
                return [{"source": row[0], "chunk_count": row[1]} for row in rows]
        except Exception as e:
            print(f"[RAG Store] Error listing documents: {e}")
            return []

    def get_document_chunks(self, source: str) -> list[dict]:
        """获取指定文档的所有 chunk。"""
        from core.config import engine
        from sqlalchemy import text
        query = text("""
            SELECT id, document
            FROM langchain_pg_embedding
            WHERE cmetadata->>'source' = :source
        """)
        try:
            with engine.connect() as conn:
                rows = conn.execute(query, {"source": source}).fetchall()
                return [{"chunk_id": row[0], "text": row[1]} for row in rows]
        except Exception as e:
            print(f"[RAG Store] Error getting chunks: {e}")
            return []

    def remove_document(self, source: str) -> bool:
        """删除指定文档的所有 chunk。"""
        from core.config import engine
        from sqlalchemy import text
        query = text("""
            DELETE FROM langchain_pg_embedding
            WHERE cmetadata->>'source' = :source
        """)
        try:
            with engine.connect() as conn:
                res = conn.execute(query, {"source": source})
                conn.commit()
                return res.rowcount > 0
        except Exception as e:
            print(f"[RAG Store] Error removing document: {e}")
            return False

    def clear_all(self) -> None:
        """清空所有文档。"""
        from core.config import engine
        from sqlalchemy import text
        query = text("DELETE FROM langchain_pg_embedding")
        try:
            with engine.connect() as conn:
                conn.execute(query)
                conn.commit()
        except Exception as e:
            print(f"[RAG Store] Error clearing: {e}")


# 全局单例
rag_store = RAGVectorStore()
