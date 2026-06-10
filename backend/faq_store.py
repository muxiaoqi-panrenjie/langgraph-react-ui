"""
FAQ 向量存储模块 — 基于 pgvector + PostgreSQL。

将 FAQ 问答对存储在 PostgreSQL 中，使用 pgvector 进行向量相似度检索。
替代原有的内存字典 + 纯 Python 余弦相似度计算方案。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, Text, DateTime, text, func
from sqlalchemy.orm import DeclarativeBase, Session
from pgvector.sqlalchemy import Vector

from config import engine
from rag import get_embeddings


# ============================================================
# 初始 FAQ 种子数据
# ============================================================
SEED_FAQS = {
    "如何申请退款？": "退款政策：您可以在购买后7天内，且未下载该歌曲的前提下，申请全额退款。请在订单详情页提交申请，或者联系人工客服处理。",
    "如何修改账户密码？": "您可以在「个人中心」->「账户安全」页面，点击「修改密码」并按照提示验证原密码后进行修改。",
    "支持哪些支付方式？": "我们目前支持微信支付、支付宝、信用卡以及 PayPal 等主流支付方式。",
    "如何下载已购买的歌曲？": "购买成功后，您可以在「我的音乐」->「已购歌曲」页面，点击歌曲条目右侧的「下载」按钮，选择音质后即可下载本地文件。",
    "为什么播放音乐没有声音？": "请先检查您的设备音量是否开启，并确认浏览器未静音。如果是客户端，请尝试清理缓存或重启应用。如仍无声音，可联系客服检测。",
    "如何升级为 VIP 会员？": "点击页面右上角的「开通VIP」按钮，选择套餐（月卡/季卡/年卡）并完成支付，即可升级为 VIP 会员，享受无损音质和免费下载特权。",
    "账号被锁定怎么办？": "若因密码输错多次导致账号被锁定，系统将在30分钟后自动解锁。您也可以点击「找回密码」重新验证手机或邮箱来即时解锁。",
}


# ============================================================
# 数据库方言检测
# ============================================================
_is_postgres = engine.dialect.name == "postgresql"


# ============================================================
# 延迟初始化 ORM 模型（需要运行时探测向量维度）
# ============================================================
_Base: Optional[type] = None
_FaqItem: Optional[type] = None
_embedding_dim: Optional[int] = None
_initialized: bool = False


def _get_embedding_dim() -> int:
    """调用嵌入模型探测向量维度（只执行一次）。"""
    global _embedding_dim
    if _embedding_dim is None:
        vec = get_embeddings().embed_query("dimension probe")
        _embedding_dim = len(vec)
        print(f"[FAQ Store] Detected embedding dimension: {_embedding_dim}")
    return _embedding_dim


def _ensure_model():
    """确保 ORM 模型已根据实际向量维度创建。"""
    global _Base, _FaqItem
    if _FaqItem is not None:
        return

    dim = _get_embedding_dim()

    class Base(DeclarativeBase):
        pass

    class FaqItem(Base):
        __tablename__ = "faqs"

        id = Column(Integer, primary_key=True, autoincrement=True)
        question = Column(Text, nullable=False, unique=True)
        answer = Column(Text, nullable=False)
        embedding = Column(Vector(dim))
        created_at = Column(DateTime, server_default=func.now())

        def __repr__(self):
            return f"<FaqItem id={self.id} question='{self.question[:20]}...'>"

    _Base = Base
    _FaqItem = FaqItem


# ============================================================
# 公开 API
# ============================================================

def init_faq_table():
    """创建 pgvector 扩展和 FAQ 表（幂等操作，可重复调用）。"""
    global _initialized

    if not _is_postgres:
        print("[FAQ Store] WARNING: 需要 PostgreSQL 才能使用 pgvector 向量检索，FAQ 功能已禁用。")
        return

    if _initialized:
        return

    _ensure_model()

    # 启用 pgvector 扩展
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    # 创建表
    _Base.metadata.create_all(engine)

    # 创建 HNSW 向量索引（适用于任意数据量，余弦距离）
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_faqs_embedding "
                "ON faqs USING hnsw (embedding vector_cosine_ops)"
            ))
            conn.commit()
    except Exception as e:
        # 索引创建失败不影响功能，只是检索会慢一些
        print(f"[FAQ Store] Index creation skipped: {e}")

    _initialized = True
    print("[FAQ Store] FAQ 表和向量索引初始化完成。")


def seed_faqs():
    """将初始 FAQ 种子数据写入数据库（仅在表为空时执行）。"""
    if not _is_postgres:
        return

    _ensure_model()
    init_faq_table()

    with Session(engine) as session:
        count = session.query(_FaqItem).count()
        if count > 0:
            print(f"[FAQ Store] FAQ 表已有 {count} 条记录，跳过种子导入。")
            return

        embeddings_model = get_embeddings()
        for question, answer in SEED_FAQS.items():
            embedding = embeddings_model.embed_query(question)
            item = _FaqItem(question=question, answer=answer, embedding=embedding)
            session.add(item)

        session.commit()
        print(f"[FAQ Store] 成功导入 {len(SEED_FAQS)} 条 FAQ 种子数据。")


def search_faq(query_text: str, threshold: float = 0.85) -> tuple[str, float]:
    """使用 pgvector 向量检索最匹配的 FAQ。

    将用户问题转为向量，通过 pgvector 的余弦距离运算符 (<=>) 检索最相似的 FAQ。
    pgvector 返回的是余弦距离（0~2），转换为余弦相似度 = 1 - distance。

    Args:
        query_text: 用户问题文本
        threshold: 余弦相似度阈值，默认 0.85

    Returns:
        (answer, score) 元组。未命中时返回 ("", best_score)。
    """
    if not _is_postgres:
        return "", 0.0

    try:
        _ensure_model()
        embeddings_model = get_embeddings()
        query_vec = embeddings_model.embed_query(query_text)

        # pgvector 的 <=> 是余弦距离，similarity = 1 - distance
        with Session(engine) as session:
            # 使用列的 cosine_distance 方法生成 <=> 运算符
            dist_col = _FaqItem.embedding.cosine_distance(query_vec)
            sim_col = (1 - dist_col).label("similarity")

            result = (
                session.query(_FaqItem.answer, sim_col)
                .order_by(dist_col)
                .limit(1)
                .first()
            )

            if result is None:
                return "", 0.0

            score = float(result.similarity)
            if score >= threshold:
                return result.answer, score
            return "", score

    except Exception as e:
        print(f"[FAQ Store] 检索失败: {e}")
        return "", 0.0


def add_faq(question: str, answer: str) -> bool:
    """手动添加一条 FAQ。

    Args:
        question: 问题文本
        answer: 答案文本

    Returns:
        是否添加成功
    """
    if not _is_postgres:
        return False

    try:
        _ensure_model()
        embeddings_model = get_embeddings()
        embedding = embeddings_model.embed_query(question)

        with Session(engine) as session:
            item = _FaqItem(question=question, answer=answer, embedding=embedding)
            session.add(item)
            session.commit()
            print(f"[FAQ Store] 新增 FAQ: {question[:30]}...")
            return True
    except Exception as e:
        print(f"[FAQ Store] 添加 FAQ 失败: {e}")
        return False


def delete_faq(faq_id: int) -> bool:
    """根据 ID 删除一条 FAQ。"""
    if not _is_postgres:
        return False

    try:
        _ensure_model()
        with Session(engine) as session:
            item = session.get(_FaqItem, faq_id)
            if item:
                session.delete(item)
                session.commit()
                print(f"[FAQ Store] 删除 FAQ id={faq_id}")
                return True
            return False
    except Exception as e:
        print(f"[FAQ Store] 删除 FAQ 失败: {e}")
        return False


def list_faqs() -> list[dict]:
    """列出所有 FAQ 记录。"""
    if not _is_postgres:
        return []

    try:
        _ensure_model()
        with Session(engine) as session:
            items = session.query(_FaqItem).all()
            return [
                {
                    "id": item.id,
                    "question": item.question,
                    "answer": item.answer,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ]
    except Exception as e:
        print(f"[FAQ Store] 列出 FAQ 失败: {e}")
        return []
