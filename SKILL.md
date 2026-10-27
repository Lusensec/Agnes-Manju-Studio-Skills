---
name: agnes-comic-studio
description: |
  Agnes Comic Studio 漫剧/短视频创作套件（基于 Agnes AI Flash 系列）。统一入口，子 Skill 可独立使用。
  将「故事概念 → 剧本 → 分镜图 → 短视频」完整流程拆解为可独立调用的子 Skill，每步结束后询问用户是否继续或修改。所有产出资产统一存储在项目文件夹下，用 SQLite 数据库追踪定位。

  子 Skill 列表：
  - script-writer（剧本 + 角色设定 + 分镜脚本 + 模板预设；agnes-3.0-flash）
  - storyboard-gen（角色三视图/背景/道具/分镜图 + URL 存储；agnes-image-2.5-flash）
  - video-composer（图生视频 + 限流/队列满自动重试 + 可选 TTS 音频参考嘴型同步；agnes-video-2.5-flash）
  - post-production（TTS 配音 + 字幕 + BGM + 最终合成（场景对齐配音）；edge-tts + ffmpeg）
  - asset-manager（资产追踪 / 项目文件夹管理；本地）
  - Agnes-Flash-Suite-Skills（基础能力：agent 编程/生图/生视频/对话/思考；4 个模型子 Skill）

  跨平台支持：Windows/Linux/macOS；中文 GBK 控制台自动切 UTF-8 输出；.env 从套件根目录向上自动发现。

  触发场景：漫剧创作、短视频制作、故事→剧本→分镜图→视频、分镜生图、图生视频、TTS 字幕合成、资产追踪。

# Agnes Comic Studio

> 基于 Agnes AI Flash 系列的漫剧/短视频创作套件。统一入口，子 Skill 可独立使用。

## 概述

将"故事概念 → 剧本 → 分镜图 → 短视频"的完整创作流程拆解为可独立调用的子 Skill，每个步骤结束后**询问用户是否继续或修改**，支持反复迭代。所有产出资产统一存储在指定项目文件夹下，用 SQLite 数据库追踪定位。

| 子 Skill | 核心能力 | 对应 Agnes 模型 | 触发场景 |
|----------|---------|---------------|---------|
| **Agnes-Flash-Suite-Skills** | 基础能力（agent 编程/生图/生视频/对话/思考） | 3.0/2.5 全系列 | 直接调用 Agnes API |
| **script-writer** | 剧本 + 角色设定 + 分镜脚本 + 模板预设 | `agnes-3.0-flash` | 故事概念 → 结构化剧本 |
| **storyboard-gen** | 三视图/背景/道具/分镜 + URL 存储 | `agnes-image-2.5-flash` | 剧本 → 逐镜头生图 |
| **video-composer** | 图生视频（reference）+ 429/503 退避重试 + 可选 TTS 音频参考（对白嘴型同步） | `agnes-video-2.5-flash` | 图片 → 动态视频 |
| **post-production** | TTS 配音（场景对齐）+ 字幕 + BGM + 最终合成 | edge-tts + ffmpeg | 后期制作 |
| **asset-manager** | 资产追踪、项目文件夹管理 | 无（本地） | 文件定位、修改、复用 |

## 资产目录结构

每个项目自动创建如下文件夹（默认 `~/comic-studio/projects/<project-name>/`）：

```
project-name/
├── scripts/          # 剧本 JSON（故事、角色、分镜）
├── images/           # 分镜图、角色参考图
├── videos/           # 生成的短视频 MP4
├── references/       # 用户上传的参考素材
└── assets.db         # SQLite 数据库（资产索引）
```

`assets.db` 表结构：

```sql
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    asset_type TEXT NOT NULL,   -- script | image | video | reference
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    tags TEXT                   -- 逗号分隔标签
);
```

## 创作流程（主 Pipeline）

```
用户输入故事概念
    ↓
[配置] 选择参数：
   - 横屏(16:9) / 竖屏(9:16)
   - 视频时长 (4-12s)
   - 风格 (动画/写实/水墨/赛博朋克/二次元)
   - 图片尺寸 (1K/2K)
    ↓
[Step 1: script-writer]  生成剧本 JSON
    ↓  询问用户：继续 / 修改剧本 / 调整角色
[Step 2: storyboard-gen] 逐镜头生成图片
    ↓  询问用户：继续 / 重新生成某镜头 / 调整风格
[Step 2.5: post-production/gen-tts.py] 对白配音（推荐先出 TTS，视频才能做嘴型同步）
     ↓
[Step 3: video-composer] 图片 → 短视频（可选；配置 AGNES_TTS_GITHUB_REPO 后自动带音频参考）
    ↓  询问用户：继续 / 调整时长 / 跳过视频
输出完整项目
```

### 配置交互示例

Agent 在用户给出故事概念后，应主动询问：

```
收到！故事概念已记录。开始前请确认几个参数：

  1. 画面方向：横屏(16:9) / 竖屏(9:16)？
  2. 视频时长：每段 5s（默认）/ 其他 4-12s？
  3. 风格：动画（默认）/ 写实 / 水墨 / 赛博朋克 / 二次元？
  4. 图片尺寸：1K（默认，快）/ 2K（慢一倍）？

回复 "默认" 可全部用默认值，或逐项指定。
```

用户确认后，参数写入剧本 JSON 的 `config` 字段，后续步骤自动读取。

## ⚠️ Agent 行为准则（每步必须确认）

**每个 Step 执行完毕后，Agent 必须 STOP 并向用户确认，不得自动跳到下一步。**

| Step | 完成后 Agent 应做 |
|------|-----------------|
| Step 1 剧本 | 展示剧本摘要（角色数、场景数、logline）→ 问用户：「剧本 OK？要改哪部分？」 |
| Step 2 分镜图 | 展示生成的图片 → 问用户：「图片满意吗？要重新生成某张？」 |
| Step 3 视频 | 展示/播放视频 → 问用户：「视频 OK？要调时长或重新生成？」 |

**用户回复"继续/满意/OK"才执行下一步。用户说"改 XX"则回到当前步骤修改后重新确认。**

脚本末尾打印的「下一步」是给用户看的操作提示，Agent 不应忽略它直接链式执行。

## 快速开始（Python）

每个子 Skill 的 `examples/` 目录包含可直接运行的脚本，**支持命令行参数**：

> 先配置 `AGNESAI_API_KEY`：复制 `.env.example` 为**套件根目录**下的 `.env`（脚本自动向上发现），或设置环境变量。Windows 中文控制台无需额外处理，脚本已内置 UTF-8 输出。

```bash
# 初始化项目
python asset-manager/examples/init-project.py "我的漫剧"

# Step 1: 写剧本
python script-writer/examples/write-script.py "我的漫剧" "一个宇航员在太空遇见一条会说话的鱼"

# 用户确认后 → Step 2: 生成分镜图
python storyboard-gen/examples/gen-storyboard.py "我的漫剧"

# 用户确认后 → Step 3: 生成视频（可选）
python video-composer/examples/gen-video.py "我的漫剧"
```

> 每个 Step 脚本运行结束后会打印"下一步建议"，Agent 根据用户回复决定是否继续、修改或重试。

## 各子 Skill 文档

- [script-writer/SKILL.md](./script-writer/SKILL.md)
- [storyboard-gen/SKILL.md](./storyboard-gen/SKILL.md)
- [video-composer/SKILL.md](./video-composer/SKILL.md)
- [asset-manager/SKILL.md](./asset-manager/SKILL.md)
- [Agnes-Flash-Suite-Skills/SKILL.md](./Agnes-Flash-Suite-Skills/SKILL.md)

## 技术规格

| 特性 | 值 |
|------|-----|
| 依赖 | Python 3.9+（标准库），无 GPU 要求 |
| 生图超时 | 360s |
| 生视频超时 | 600s（通常 2-5 分钟） |
| 计费 | Agnes AI 当前免费 |
| 存储 | 本地文件 + SQLite，无云依赖 |

## 速率限制

| 模型 | 限制 | 脚本自动间隔 |
|------|------|-------------|
| `agnes-image-2.5-flash` 1K | 20次/分 | 3s |
| `agnes-image-2.5-flash` 2K | 10次/分 | 7s |
| `agnes-image-2.5-flash` 3K/4K | 1次/分 | 60s |
| `agnes-video-2.5-flash` | **1次/分/key**（多 key 可并行，国内/国际平台可混用） | 65s + 429/503（video_queue_full）退避重试；队列满时脚本 exit 3 快速失败，稍后重跑自动跳过已完成片段；`.env` 配置 `AGNESAI_API_KEYS`（支持 `key@baseURL` 混平台语法，如 `sk-x,sk-y@https://apihub.agnes-ai.com/v1`）后按 key 数开并行 worker（详见 video-composer/SKILL.md） |

视频模型额外约束：
- size 固定 720P（不可选）
- 时长 4-12s（超出自动裁剪）
- 图片参考最多 5 张
- 音频参考最多 3 段（URL 需公网可达；`.env` 配置 `AGNES_TTS_GITHUB_REPO` 后 gen-video.py 自动上传 TTS 并携带音频参考，见 video-composer/SKILL.md）
- 不支持视频参考

## 使用场景

| 需求 | 推荐操作 |
|------|---------|
| 快速出一张概念图 | 直接调用 `Agnes-Flash-Suite-Skills` 文生图 |
| 完整漫剧从 0 到成片 | 走主 Pipeline（3 步） |
| 已有剧本，只要分镜图 | 跳过 Step 1，从 `storyboard-gen` 开始 |
| 已有图片，想做成视频 | 从 `video-composer` 开始 |
| 查看/修改已有资产 | 调用 `asset-manager` |
