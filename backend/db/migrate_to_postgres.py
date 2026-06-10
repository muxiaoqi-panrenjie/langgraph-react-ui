"""
数据迁移脚本：从 SQLite (chinook.db) 迁移音乐商店所有业务表到 PostgreSQL。
因为在 Docker 中新启动的 pgvector 实例是个空库，需要把原有的 SQLite 业务数据导入，
以便多智能体助理（Multi-Agent Assistant）能正常查询顾客、发票、音乐目录等表。

运行方式：
    python backend/db/migrate_to_postgres.py
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, text, VARCHAR, DateTime, Numeric

# 将 backend 目录添加到 Python 搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import postgres_url


def migrate():
    # 1. 确定 SQLite 路径
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chinook.db")
    if not os.path.exists(sqlite_db_path):
        print(f"错误: 未在以下路径找到 SQLite 数据库: {sqlite_db_path}")
        return
    sqlite_engine = create_engine(f"sqlite:///{sqlite_db_path}")

    # 2. 检查 PostgreSQL 连接配置
    if not postgres_url:
        print("错误: 未在 .env 文件中检测到 POSTGRES_URL 环境变量。")
        return
    
    # 确保连接驱动是 psycopg
    pg_url = postgres_url
    if pg_url.startswith("postgresql://") and "+psycopg" not in pg_url:
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    pg_engine = create_engine(pg_url)

    print("=" * 60)
    print("  SQLite (chinook.db) -> PostgreSQL 数据迁移")
    print("=" * 60)
    print(f"源 SQLite 数据库: {sqlite_db_path}")
    print(f"目标 PostgreSQL 数据库: {pg_engine.url.render_as_string(hide_password=True)}")

    # 3. 反射 SQLite 表结构
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    # 过滤掉 SQLite 系统内部表
    tables_to_migrate = []
    for table_name, table in sqlite_meta.tables.items():
        if table_name.startswith("sqlite_"):
            continue
        tables_to_migrate.append(table)

    print(f"\n共检测到 {len(tables_to_migrate)} 个待迁移的业务表。")

    # 4. 在 PostgreSQL 中创建对应的表结构
    # 注意：SQLite 中的 NVARCHAR, DATETIME 等类型在 PostgreSQL 中不被直接支持，
    # 我们需要在复制字段定义时将它们映射为 PostgreSQL 兼容的类型。
    pg_meta = MetaData()
    for table in tables_to_migrate:
        # 修改 SQLite 字段类型以兼容 PostgreSQL
        for column in table.columns:
            type_str = str(column.type).upper()
            if "NVARCHAR" in type_str:
                # 兼容 NVARCHAR -> VARCHAR
                length = getattr(column.type, "length", None)
                column.type = VARCHAR(length)
            elif "DATETIME" in type_str:
                # SQLite 中的 DATETIME -> DateTime
                column.type = DateTime()
            elif "NUMERIC" in type_str:
                # SQLite 中的 NUMERIC -> Numeric
                precision = getattr(column.type, "precision", None)
                scale = getattr(column.type, "scale", None)
                column.type = Numeric(precision, scale)

        # 将修改类型后的表克隆到 pg_meta 下
        table.to_metadata(pg_meta)

    print("\n正在 PostgreSQL 中创建表结构...")
    pg_meta.create_all(bind=pg_engine)
    print("表结构创建/验证完成。")

    # 5. 迁移行数据
    # 利用 PostgreSQL 的 session_replication_role 临时停用外键和触发器检查，
    # 这样我们就不需要按照严格的拓扑顺序依次插入，也不会因为外键约束导致报错。
    print("\n开始迁移数据行...")
    try:
        with pg_engine.begin() as pg_conn:
            pg_conn.execute(text("SET session_replication_role = 'replica';"))
            
            for table in tables_to_migrate:
                table_name = table.name
                
                # 从 SQLite 读取数据
                with sqlite_engine.connect() as sqlite_conn:
                    rows = sqlite_conn.execute(table.select()).fetchall()
                    if not rows:
                        print(f"  - 表 '{table_name}': 无数据，跳过")
                        continue
                    
                    # 组装为 SQLAlchemy 键值对插入数据
                    keys = table.columns.keys()
                    data = [dict(zip(keys, row)) for row in rows]
                    
                    # 先清空目标表中的历史数据，防止重复执行时主键冲突
                    pg_conn.execute(table.delete())
                    
                    # 批量写入 PostgreSQL
                    pg_conn.execute(table.insert(), data)
                    print(f"  - 表 '{table_name}': 成功同步 {len(data)} 条记录")

            # 恢复外键检查
            pg_conn.execute(text("SET session_replication_role = 'origin';"))
        
        print("\n" + "=" * 60)
        print("  数据迁移成功完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n数据迁移失败: {e}")
        print("提示: 请确保 Docker 中的 PostgreSQL 容器正在运行，且连接凭证正确。")


if __name__ == "__main__":
    migrate()
