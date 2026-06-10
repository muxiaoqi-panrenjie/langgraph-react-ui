"""
数据库初始化脚本。

运行方式：
    python backend/db/init_db.py

功能：
    1. 创建 pgvector 扩展
    2. 创建 FAQ 表（含向量索引）
    3. 导入初始 FAQ 种子数据（带向量嵌入）
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.faq_store import init_faq_table, seed_faqs


def main():
    print("=" * 50)
    print("  FAQ 数据库初始化")
    print("=" * 50)

    # 1. 创建表和索引
    print("\n[步骤 1/2] 创建 FAQ 表和向量索引...")
    init_faq_table()

    # 2. 导入种子数据
    print("\n[步骤 2/2] 导入初始 FAQ 数据...")
    seed_faqs()

    print("\n" + "=" * 50)
    print("  初始化完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
