---
name: asset-manager
description: |
  资产管理子 Skill。管理项目文件夹结构，用 SQLite 数据库追踪所有资产（script/image/video/reference），支持定位、修改、复用。
  触发场景：查看/修改/复用资产；项目文件夹初始化；资产索引。

# Asset Manager（资产管理）

> 管理项目文件夹结构，用 SQLite 数据库追踪所有资产，支持定位、修改、复用。

## 功能

| 操作 | 命令 |
|------|------|
| 初始化项目 | `python init-project.py "项目名"` |
| 查看资产列表 | `python list-assets.py "项目名"` |
| 查找资产 | `python find-asset.py "项目名" <关键词>` |
| 记录新资产 | `python track-asset.py "项目名" <类型> <文件路径> [描述] [标签]` |
| 更新资产描述 | `python update-asset.py "项目名" <id> [新描述]` |
| 删除资产记录 | `python delete-asset.py "项目名" <id>` |

## 项目初始化

`init-project.py` 创建：

```
~/manju-studio/projects/<name>/
├── scripts/
├── images/
├── videos/
├── references/
└── assets.db
```

并初始化 `assets.db` 表结构。

## 数据库表结构

```sql
CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    asset_type TEXT NOT NULL,  -- script | image | video | reference
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    tags TEXT
);
CREATE INDEX idx_assets_project ON assets(project, asset_type);
```

## 使用场景

- 其他子 Skill 生成文件后调用 `track-asset.py` 记录
- 用户说"把第 3 个场景的图换成 XX"时，用 `find-asset.py` 定位
- 跨项目复用角色图时，用 `find-asset.py "项目A" "角色名"` 查找

## 示例脚本

| 脚本 | 参数 |
|------|------|
| `examples/init-project.py` | `[项目名]` |
| `examples/list-assets.py` | `[项目名] [类型]` |
| `examples/find-asset.py` | `[项目名] [关键词]` |
| `examples/track-asset.py` | `[项目名] [类型] [文件路径] [描述] [标签]` |
| `examples/load_env.py` | 无 |
