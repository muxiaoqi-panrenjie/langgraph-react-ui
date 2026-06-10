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
            resp = requests.post(self.url, headers=headers, json=data, verify=False, timeout=15)
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
        model_name = os.environ.get("DASHSCOPE_EMBEDDING_MODEL") or "tongyi-embedding-vision-plus-2026-03-06"
        if not api_key:
            # 兼容旧版本，降级读取 ANTHROPIC_API_KEY
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            
        if api_key and (api_key.startswith("sk-de") or model_name == "tongyi-embedding-vision-plus-2026-03-06"):
            # 用户提供的多模态向量模型专有 Key 或模型
            _embeddings = DashScopeMultimodalEmbeddings(
                model=model_name,
                api_key=api_key
            )
        else:
            # 备用：默认的 DashScopeEmbeddings
            _embeddings = DashScopeEmbeddings(
                model="text-embedding-v3",
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
    """封装 InMemoryVectorStore，支持文档添加、查询、删除。"""

    def __init__(self):
        self._store: Optional[InMemoryVectorStore] = None
        # 记录 source -> chunk_ids 的映射，用于删除
        self._source_index: dict[str, list[str]] = {}

    def _get_store(self) -> InMemoryVectorStore:
        if self._store is None:
            self._store = InMemoryVectorStore(get_embeddings())
        return self._store

    def add_documents(self, texts: list[str], source: str) -> int:
        """添加文档段落，返回添加的 chunk 数量。"""
        if not texts:
            return 0

        store = self._get_store()
        chunk_ids: list[str] = []

        for text in texts:
            chunk_id = str(uuid.uuid4())
            doc = Document(
                page_content=text,
                metadata={"source": source, "chunk_id": chunk_id},
            )
            store.add_documents([doc], ids=[chunk_id])
            chunk_ids.append(chunk_id)

        self._source_index[source] = chunk_ids
        return len(chunk_ids)

    def query(self, text: str, top_k: int = 5) -> list[Document]:
        """检索最相关的段落。"""
        store = self._get_store()
        results = store.similarity_search(text, k=top_k)
        return results

    def list_documents(self) -> list[dict]:
        """列出已上传的文档及其 chunk 数量。"""
        return [
            {"source": source, "chunk_count": len(chunk_ids)}
            for source, chunk_ids in self._source_index.items()
        ]

    def get_document_chunks(self, source: str) -> list[dict]:
        """获取指定文档的所有 chunk。"""
        if source not in self._source_index:
            return []

        chunk_ids = self._source_index[source]
        store = self._get_store()
        docs = store.docstore.mget(chunk_ids)
        return [
            {"chunk_id": doc.metadata.get("chunk_id"), "text": doc.page_content}
            for doc in docs if doc
        ]

    def remove_document(self, source: str) -> bool:
        """删除指定文档的所有 chunk。"""
        if source not in self._source_index:
            return False

        store = self._get_store()
        chunk_ids = self._source_index.pop(source)

        # InMemoryVectorStore 没有直接的 delete 方法，需要重建
        # 重新创建 store，排除被删除的 chunk
        all_docs = store.docstore.mget(list(store.index_to_docstore_id.values()))
        remaining_docs = [
            d for d in all_docs
            if d and d.metadata.get("source") != source
        ]
        remaining_ids = [d.metadata["chunk_id"] for d in remaining_docs]

        new_store = InMemoryVectorStore(get_embeddings())
        if remaining_docs:
            new_store.add_documents(remaining_docs, ids=remaining_ids)

        self._store = new_store
        return True

    def clear_all(self) -> None:
        """清空所有文档。"""
        self._store = None
        self._source_index.clear()


# 全局单例
rag_store = RAGVectorStore()
