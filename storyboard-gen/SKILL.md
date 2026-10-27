---
name: storyboard-gen
description: |
  分镜生成子 Skill。读取剧本 JSON，用 agnes-image-2.5-flash 生成全套视觉资产：角色三视图、纯背景、道具、分镜图，URL 存储。
  触发场景：逐镜头分镜图生成；角色三视图/背景/道具图。

# Storyboard Generator（分镜生成）

> 读取剧本 JSON，生成全套视觉资产：角色三视图、纯背景、道具、分镜图。

## 输入

- 项目名
- 剧本 JSON 路径（自动从 `scripts/` 目录读取）

## 输出

| 文件 | 说明 |
|------|------|
| `images/character-<name>.png` | 角色单张参考 |
| `images/character-<name>three-view.png` | 角色三视图（正面/侧面/背面） |
| `images/character-<name>expression.png` | 角色多表情（6格） |
| `images/bg-<id>.png` | 纯背景图（无角色） |
| `images/prop-<name>.png` | 道具/物品参考图 |
| `images/scene-<id>.png` | 分镜图（完整画面） |

## 调用方式

```bash
# 全套分镜（角色 + 场景）
python examples/gen-storyboard.py "项目名"

# 镜级模式（总导演 shotlist，逐镜出图）
python examples/gen-storyboard.py "项目名" --shotlist

# 断点续跑（只补失败/缺失槽，状态账本 scripts/<项目>-storyboard-status.json）
python examples/gen-storyboard.py "项目名" --retry-failed

# 角色三视图
python examples/gen-character.py "项目名" "角色名" three-view

# 角色多表情
python examples/gen-character.py "项目名" "角色名" expression

# 纯背景（无角色）
python examples/gen-background.py "项目名" [场景ID]

# 道具/物品
python examples/gen-props.py "项目名" [道具名]

# 总览拼图（网格总览，供用户一眼确认全批）
python examples/gen-mosaic.py "项目名" [--kind scene|char|all] [--cols 2] [--cell 720x405]
```

## 用户确认点

运行结束后，**Agent 必须展示生成的图片并等用户确认**。

- 展示：优先跑 `gen-mosaic.py` 生成总览图（一张网格图看全批；竖屏项目用 `--cell 405x720`），再列关键单图
- 询问：「图片满意吗？要重新生成某张？」
- 用户说"继续"→ 执行 Step 3（视频）
- 用户说"第 N 张重来"→ `--scene N`（或 `--retry-failed` 补失败槽）
- 用户说"补个三视图"→ `gen-character.py "项目" "角色名" three-view`

## 剧本 JSON 资产字段

`write-script.py` 自动输出五路资产（缺字段时自动补空数组）：
`characters` / `locations` / `costumes` / `props` / `weather`。
`gen-storyboard.py` 会按场景引用的 `location` / `props` 注入资产描述到提示词
（跨镜一致性，借鉴 ComfyUI 资产注入）。

## 速率限制（agnes-image-2.5-flash）

| 尺寸 | 限制 | 脚本间隔 |
|------|------|---------|
| 1K | 20次/分 | 3s |
| 2K | 10次/分 | 7s |
| 3K | 1次/分 | 60s |
| 4K | 1次/分 | 60s |

## 示例脚本

| 脚本 | 参数 |
|------|------|
| `examples/gen-storyboard.py` | `[项目名] [--scene N] [--size 1K\|2K] [--shotlist] [--retry-failed]` |
| `examples/gen-character.py` | `[项目名] [角色名] [sheet\|three-view\|expression]` |
| `examples/gen-background.py` | `[项目名] [场景ID]` |
| `examples/gen-props.py` | `[项目名] [道具名]` |
| `examples/gen-mosaic.py` | `[项目名] [--kind scene\|char\|all] [--cols N] [--cell WxH]` |
| `examples/load_env.py` | 无 |
| `examples/track.py` | 内部使用 |
