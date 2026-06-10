"""
自动下载并安装 pgvector 扩展到 PostgreSQL 17。

用法：
    python install_pgvector.py

步骤：
    1. 从 GitHub 下载 pgvector 预编译 Windows 版本（针对 PostgreSQL 17）
    2. 解压并复制到 PostgreSQL 安装目录
    3. 重启 PostgreSQL 服务
    4. 验证安装
"""

import os
import sys
import shutil
import tempfile
import zipfile
import urllib.request
import subprocess

# ============================================================
# 配置
# ============================================================
PGVECTOR_VERSION = "v0.8.2"
POSTGRES_VERSION = "17"

# GitHub 预编译版本来源
DOWNLOAD_URL = (
    f"https://github.com/andreiramani/pgvector_pgsql_windows/releases/"
    f"download/{PGVECTOR_VERSION}_17.6/"
    f"pgvector-{PGVECTOR_VERSION.lstrip('v')}-pg{POSTGRES_VERSION}-windows-x64.zip"
)

# 备用 Gitee 镜像地址
GITEE_URL = None  # 如果有可用的 Gitee 直链可以填在这里

# PostgreSQL 安装目录
PG_HOME = r"C:\Program Files\PostgreSQL\17"


def detect_postgres_dir():
    """自动检测 PostgreSQL 安装目录。"""
    candidates = [
        PG_HOME,
        r"C:\Program Files\PostgreSQL\17",
        r"C:\Program Files\PostgreSQL\16",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def download_file(url: str, dest: str):
    """下载文件并显示进度。"""
    print(f"正在下载: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
        size = os.path.getsize(dest)
        print(f"下载完成，文件大小: {size / 1024:.1f} KB")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False


def extract_zip(zip_path: str, dest_dir: str):
    """解压 zip 文件。"""
    print(f"正在解压到: {dest_dir}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
        members = zf.namelist()
        print(f"解压完成，包含 {len(members)} 个文件:")
        for m in members:
            print(f"  - {m}")
    return members


def find_files(directory: str, extensions: list[str]) -> dict[str, str]:
    """在目录中查找指定后缀的文件。"""
    found = {}
    for root, dirs, files in os.walk(directory):
        for f in files:
            for ext in extensions:
                if f.endswith(ext):
                    found[ext] = os.path.join(root, f)
    return found


def restart_postgres():
    """重启 PostgreSQL 服务。"""
    print("\n重启 PostgreSQL 服务...")
    service_names = [
        "postgresql-x64-17",
        "postgresql-x64-16",
    ]
    for name in service_names:
        try:
            subprocess.run(
                ["net", "stop", name],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass
        try:
            subprocess.run(
                ["net", "start", name],
                capture_output=True, text=True, timeout=10,
            )
            print(f"PostgreSQL 服务 ({name}) 已重启。")
            return True
        except Exception as e:
            print(f"重启 {name} 失败: {e}")
    print("未找到运行的 PostgreSQL 服务，你可能需要手动重启。")
    return False


def verify_extension():
    """验证 pgvector 扩展是否安装成功。"""
    try:
        import psycopg
        conn = psycopg.connect("host=localhost port=5432 dbname=postgres")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            row = cur.fetchone()
            if row:
                print(f"\n验证成功！pgvector 版本: {row[0]}")
                return True
            else:
                # 尝试创建扩展
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
                cur.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                row = cur.fetchone()
                if row:
                    print(f"\n验证成功！pgvector 版本: {row[0]}（刚刚创建）")
                    return True
        conn.close()
    except Exception as e:
        print(f"\n验证失败: {e}")
        print("请确保 PostgreSQL 正在运行。")
    return False


def main():
    print("=" * 50)
    print("  pgvector 自动安装脚本 (PostgreSQL 17)")
    print("=" * 50)

    # 1. 检测 PostgreSQL 目录
    pg_dir = detect_postgres_dir()
    if not pg_dir:
        print("错误: 未找到 PostgreSQL 安装目录。")
        print("请手动指定 PG_HOME 变量。")
        sys.exit(1)
    print(f"\n检测到 PostgreSQL 安装目录: {pg_dir}")

    share_dir = os.path.join(pg_dir, "share", "extension")
    lib_dir = os.path.join(pg_dir, "lib")

    # 检查是否已安装
    vector_control = os.path.join(share_dir, "vector.control")
    if os.path.exists(vector_control):
        print("pgvector 似乎已经安装了，跳过下载。")
        restart_postgres()
        verify_extension()
        return

    # 2. 下载
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, "pgvector.zip")
        if not download_file(DOWNLOAD_URL, zip_path):
            print("\nGitHub 下载失败，尝试 Gitee 镜像...")
            if GITEE_URL and download_file(GITEE_URL, zip_path):
                pass
            else:
                print("\n所有下载源都失败了。")
                print(f"请手动下载: {DOWNLOAD_URL}")
                print(f"然后解压文件到:")
                print(f"  vector.control  → {share_dir}")
                print(f"  vector.dll      → {lib_dir}")
                print(f"  vector--*.sql   → {share_dir}")
                sys.exit(1)

        # 3. 解压
        members = extract_zip(zip_path, tmp_dir)

        # 4. 找到关键文件
        files = find_files(tmp_dir, [".control", ".dll", ".sql"])

        # 5. 复制到 PostgreSQL 目录
        print("\n复制文件到 PostgreSQL 目录...")
        for ext, src in files.items():
            if ext == ".control" or ext == ".sql":
                dest_dir = share_dir
            elif ext == ".dll":
                dest_dir = lib_dir
            else:
                continue

            filename = os.path.basename(src)
            dest = os.path.join(dest_dir, filename)
            print(f"  {filename} → {dest_dir}")
            shutil.copy2(src, dest)

    # 6. 重启服务
    restart_postgres()

    # 7. 验证
    verify_extension()

    print("\n" + "=" * 50)
    print("  安装流程完成！")
    print("  如果验证成功，现在可以运行 python init_db.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
