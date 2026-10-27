---
name: script-writer
description: |
  剧本生成子 Skill。用 agnes-3.0-flash 从故事概念生成结构化剧本 JSON（故事、角色设定、分镜脚本、config）。
  触发场景：故事概念转结构化剧本；故事 → 剧本 JSON。

# Script Writer（剧本生成）

> 用 `agnes-3.0-flash` 从故事概念生成结构化剧本 JSON，包含角色设定、分镜脚本。

## 输入

- 项目名（对应 `~/manju-studio/projects/<name>/`）
- 故事概念（自然语言）

## 输出

`scripts/<project>-script.json`，结构如下：

```json
{
  "project": "我的漫剧",
  "logline": "一句话概括",
  "characters": [
    {"name": "角色名", "description": "外貌描述", "personality": "性格", "role": "主角/配角"}
  ],
  "scenes": [
    {
      "scene_id": 1,
      "title": "场景标题",
      "description": "场景描述（用于生图提示词）",
      "dialogue": [
        {"character": "角色名", "line": "台词", "emotion": "情绪"}
      ],
      "duration_hint": "5s"
    }
  ],
  "style": "动画/写实/水墨/赛博朋克",
  "aspect_ratio": "16:9"
}
```

## 调用方式

```python
# examples/write-script.py
python examples/write-script.py "项目名" "故事概念" [风格] [方向] [时长] [尺寸] [选项]
# 基础示例：
python examples/write-script.py "漫剧A" "宇航员遇见太空鱼" 动画 portrait 8 1K
# 三维参数 + 风格双轴（可选，借鉴 ComfyUI 剧本生成器）：
python examples/write-script.py "漫剧A" "概念" 二次元 portrait 6 1K \
    --tag 逆袭爽文 --emotion 爽 --rhythm 快 --target-total 180 --director-style 悬疑
```

参数说明：
- 风格：动画|写实|水墨|赛博朋克|二次元（默认：动画）
- 方向：landscape(16:9)|portrait(9:16)（默认：landscape）
- 时长：4-12s（默认：5；未显式给出时按 --rhythm 自动选 5/8/12）
- 尺寸：1K|2K|3K|4K（默认：1K）
- 三维参数（可选）：`--tag` 题材（逆袭爽文/甜宠/悬疑/搞笑/热血/治愈/虐心）、`--emotion` 情绪线（爽/暖/爆笑/热血/紧张/泪）、`--rhythm` 节奏（快/中/慢，决定钩子密度与场景数）、`--target-total` 总时长秒数（估算场景数）
- 风格双轴（可选）：`--director-style` 导演风格（史诗历史/悬疑/喜剧/治愈/无）、`--style-extra` 自由补充、`--hook`/`--no-hook` 强制/禁止核心钩子

所有参数写入剧本 JSON 的 `config` 字段，后续步骤自动读取。剧本同时输出五路资产
（`characters`/`locations`/`costumes`/`props`/`weather`，旧剧本缺字段时自动补空数组）。

### 总导演：镜级拆分（gen-shotlist.py）

```python
# 把剧本场次展开为编号分镜（一镜一主动作，全局连号 + 全局导演阐述），产物 scripts/<项目>-shotlist.json
python examples/gen-shotlist.py "项目名" [--max-shots 60] [--seconds 5]
```

shotlist 供下游 `gen-storyboard.py --shotlist` / `gen-video.py --shotlist` 逐镜生成，
保持 `scene-<N>.png` / `scene-<N>.mp4` 命名，`merge-videos.py` 无需改动。

## 用户确认点

运行结束后打印下一步建议。**Agent 必须展示结果并等用户确认后才继续，不得自动执行下一步。**

- 展示：剧本摘要（核心钩子 + 角色列表 + 场景标题 + 五路资产计数）
- 询问：「剧本 OK？要调整哪部分？」
- 用户说"继续"→ 执行 Step 2（可选先跑 gen-shotlist.py 做镜级拆分）
- 用户说"改角色 X"→ 运行 `refine-script.py`
- 用户说"重写"→ 重新运行本脚本

```
✅ 剧本已生成: scripts/xxx-script.json
   核心钩子: ...
   角色: 3 个 | 场景: 5 个 | 资产: 场景2/服装2/道具3/天气1

下一步：
  [1] 总导演镜级拆分 → python script-writer/examples/gen-shotlist.py "项目名"
  [2] 直接生成分镜图 → python storyboard-gen/examples/gen-storyboard.py "项目名"
  [3] 修改剧本 → 编辑 JSON 后重新运行本脚本
```

## 示例脚本

| 脚本 | 参数 |
|------|------|
| `examples/write-script.py` | `[项目名] [故事概念] [风格] [方向] [时长] [尺寸] [--tag --emotion --rhythm --target-total --director-style --style-extra]` |
| `examples/gen-shotlist.py` | `[项目名] [--max-shots N] [--seconds N]` |
| `examples/refine-script.py` | `[项目名] [角色名] [新描述]` |
| `examples/load_env.py` | 无 |
