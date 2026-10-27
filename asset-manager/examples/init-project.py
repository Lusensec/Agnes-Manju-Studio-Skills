#!/usr/bin/env python3
"""Initialize a manju studio project folder structure + SQLite database.

Usage:
    python init-project.py "项目名"
    python init-project.py          # default: demo
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_env import PROJECT_ROOT


def init_project(name: str) -> Path:
    project_dir = PROJECT_ROOT / name
    for subdir in ["scripts", "images", "videos", "references"]:
        (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    db_path = project_dir / "assets.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            tags TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project, asset_type);
    """)
    conn.commit()
    conn.close()

    print(f"✅ 项目已初始化: {project_dir}")
    print(f"   数据库: {db_path}")
    print(f"\n下一步：")
    print(f"  python script-writer/examples/write-script.py \"{name}\" \"故事概念\"")
    return project_dir


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "demo"
    init_project(name)
