# Agnes Manju Studio 🎬

基于 **Agnes AI Flash** 系列的漫剧 / 短视频创作 Skill 套件。

一个故事概念 → 剧本 → 角色三视图/背景/道具/分镜图 → 短视频 → TTS 配音 + 字幕 + 合成，全自动化流水线。

## 特性

- 📝 **AI 剧本生成** — 输入故事概念，自动输出结构化剧本（角色 + 场景 + 台词 + 道具；台词长度受场景时长约束）
- 🎨 **完整视觉资产** — 角色三视图、多表情、纯背景、道具参考、分镜图（多角色一致性 I2I）
- 🎬 **短视频合成** — 图生视频（reference 模式）或文生视频，自动速率控制 + 429/503（队列满）退避重试
- 🎙 **TTS 配音** — edge-tts 免费中文配音，自动按角色分配音色；合成时按场景起点对齐，台词不互相叠音
- 💬 **字幕生成** — 自动 SRT 时间轴（同场景多句自动分窗）
- 🔊 **BGM + 合成** — ffmpeg 合成最终成片（Windows 路径安全）
- 📦 **资产追踪** — SQLite 数据库统一管理，支持搜索/复用
- 📋 **模板预设** — 抖音/B站/小红书/微博 一键配置
- 🔀 **模块化** — 6 个子 Skill，可单独调用
- ⚡ **速率限制防范** — 自动 sleep + 429/503 退避，队列满时快速失败（exit 3），重跑自动跳过已完成片段（幂等）
- 🪟 **跨平台** — Windows（GBK 控制台自动切 UTF-8 输出）/ Linux / macOS

## 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.9+ | 仅用标准库 + `edge-tts`（TTS 需要） |
| Agnes AI API Key | 免费注册 [platform.agnes-ai.cn](https://platform.agnes-ai.cn) |
| ffmpeg（可选） | 视频拼接/合成需要：Windows `winget install Gyan.FFmpeg` / macOS `brew install ffmpeg` / Linux `apt install ffmpeg` |
| edge-tts（可选） | TTS 配音：`pip install edge-tts`（国内可走阿里云镜像） |

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 AGNESAI_API_KEY
```

`.env` 放在**套件根目录**即可：所有子技能的示例脚本会自动向上查找（含 `<套件根>/.env`、`<子技能>/.env`、当前目录 `./.env`），也支持直接用环境变量 `AGNESAI_API_KEY`。找不到 `.env` 不会崩溃，只是 `API_KEY` 为空（各脚本会提示）。

可选环境变量（写入 `.env`）：
```
AGNESAI_API_KEY=sk-xxx
MANJU_STUDIO_ROOT=/path/to/your/projects   # 自定义项目根目录（默认 ~/manju-studio/projects；旧变量 COMIC_STUDIO_ROOT 仍兼容）
AGNESAI_BASE_URL=https://api.agnes-ai.cn/v1   # /v1 根，脚本自行拼接 /videos 等路径；国际版 https://apihub.agnes-ai.com/v1
```

> ⚠️ 主套件的 `AGNESAI_BASE_URL` 是 **/v1 根**；`Agnes-Flash-Suite-Skills/` 子套件的 `.env` 用 **host 根**（不带 `/v1`，其脚本自行拼接 `/v1/...`）。两者语义不同，请勿混用。

> 💡 **Windows 注意**：中文 Windows 默认 GBK 控制台，脚本已内置 stdout/stderr 自动切 UTF-8，直接 `python xxx.py` 即可，无需手动 `chcp 65001`；生成的 JSON/SRT 一律 UTF-8。

### 2. 初始化项目

```bash
python asset-manager/examples/init-project.py "我的漫剧"
```

### 3. 选择预设（可选）

```bash
# 查看可用预设
python script-writer/examples/presets.py

# 使用预设（输出参数供下一步使用）
python script-writer/examples/presets.py douyin
# 输出: orientation=portrait, aspect_ratio=9:16, video_duration=5, image_size=1K, style=动画
```

预设列表：
| 名称 | 用途 | 方向 | 时长 | 风格 |
|------|------|------|------|------|
| `douyin` | 抖音竖屏短剧 | 9:16 | 5s | 动画 |
| `bilibili` | B站横屏动画 | 16:9 | 8s | 二次元 |
| `xhs` | 小红书图文漫 | 3:4 | 4s | 二次元 |
| `weibo` | 朋友圈短动画 | 1:1 | 4s | 动画 |

### 4. 生成剧本（Step 1）

```bash
python script-writer/examples/write-script.py "项目名" "故事概念" [风格] [方向] [时长] [尺寸]
```

示例：
```bash
python script-writer/examples/write-script.py "暴雨外卖" "外卖小哥暴雨夜送最后一单" 动画 portrait 5 1K
```

输出：`scripts/项目名-script.json`

### 5. 生成视觉资产（Step 2）

```bash
# 角色三视图
python storyboard-gen/examples/gen-character.py "项目名" "角色名" three-view

# 角色多表情
python storyboard-gen/examples/gen-character.py "项目名" "角色名" expression

# 纯背景（无角色）
python storyboard-gen/examples/gen-background.py "项目名" [场景ID]

# 道具/物品
python storyboard-gen/examples/gen-props.py "项目名" [道具名]

# 全套分镜（角色参考 + 逐场景图，自动存 URL）
python storyboard-gen/examples/gen-storyboard.py "项目名"
```

输出：`images/` + `scripts/项目名-image-urls.json`（URL 供视频 reference 模式用）

### 6. 生成视频（Step 3）

```bash
# 全量（自动读 image-urls.json 做 reference 模式）
python video-composer/examples/gen-video.py "项目名"

# 单场景
python video-composer/examples/gen-video.py "项目名" --scene 3

# 自定义时长
python video-composer/examples/gen-video.py "项目名" --duration 8

# 拼接
python video-composer/examples/merge-videos.py "项目名"
```

> **可选：对白嘴型同步** — 若希望人物说话时嘴部随台词动起来：先把 Step 7 的 `gen-tts.py`
> 提前到本步骤之前运行（生成 `videos/audio/line-*.mp3`），并在 `.env` 配置
> `AGNES_TTS_GITHUB_REPO=owner/repo`（**公开** GitHub 仓库，用于托管 TTS 文件供
> Agnes 服务器拉取）。之后 `gen-video.py` 会自动上传 TTS 并以音频参考模式生成视频。
> 未配置则自动退回纯图片参考。详见 `video-composer/SKILL.md`「音频参考」一节。

### 7. TTS 配音 + 字幕 + 合成（Step 4）

```bash
# 生成配音
python post-production/examples/gen-tts.py "项目名"

# 生成字幕
python post-production/examples/gen-subtitles.py "项目名"

# 最终合成（视频 + 配音 + BGM + 字幕）
python post-production/examples/final-compose.py "项目名" [--bgm music.mp3]
```

输出：`videos/项目名-final.mp4`

### 8. 查看/管理资产

```bash
python asset-manager/examples/list-assets.py "项目名" [类型]
python asset-manager/examples/find-asset.py "项目名" "关键词"
python asset-manager/examples/track-asset.py "项目名" reference "path" "描述" "tag1,tag2"
```

## 完整工作流（Agent 交互示例）

```
用户："帮我做一个关于暴雨夜外卖的漫剧"
    ↓
Agent："收到！请确认参数：
        1. 画面方向？ 2. 时长？ 3. 风格？ 4. 尺寸？
        （回复'默认'或选预设：douyin/bilibili/xhs/weibo）"
用户："竖屏，5秒，动画，1K"
    ↓
Step 1: write-script.py → 展示剧本 → "OK？要改哪部分？"
用户："继续"
    ↓
Step 2a: gen-character.py three-view ×2
Step 2b: gen-background.py
Step 2c: gen-props.py
Step 2d: gen-storyboard.py → 展示图片 → "满意吗？"
用户："继续"
    ↓
Step 3: gen-video.py → 播放视频 → "OK？"
用户："加配音和字幕"
    ↓
Step 4: gen-tts.py → gen-subtitles.py → final-compose.py
       → 播放最终成片 → "完成 🎬"
```

## 项目文件结构

```
Agnes-Manju-Studio-Skills/
│
├── SKILL.md                          # 主入口（RikkaHub Skill 格式）
├── README.md                         # 本文件
├── .env.example                      # API Key 模板
├── .gitignore
│
├── Agnes-Flash-Suite-Skills/         # 子 Skill 1: 基础能力（按模型拆 4 个子 Skill，各自含 SKILL.md + examples/）
│   ├── SKILL.md                      # 套件主文档（skill name 仍为 agnes-flash-suite）
│   ├── README.md
│   ├── .env.example
│   ├── agnes-3.0-flash/               # Agent 编程: basic-chat / image-understanding / tool-calling / thinking-mode
│   ├── agnes-2.5-flash/               # 对话/推理: 同上 4 个示例脚本
│   ├── agnes-2.5-image-flash/         # 生图: text-to-image(±base64) / image-to-image / multi-image-combine
│   └── agnes-2.5-video-flash/         # 生视频: text-to-video / keyframe / image-reference / audio-reference(±base64) / query-video
│
├── script-writer/                    # 子 Skill 2: 剧本生成
│   ├── SKILL.md
│   └── examples/
│       ├── load_env.py
│       ├── track.py
│       ├── presets.py                # 模板预设（douyin/bilibili/xhs/weibo）
│       ├── write-script.py
│       └── refine-script.py
│
├── storyboard-gen/                   # 子 Skill 3: 视觉资产
│   ├── SKILL.md
│   └── examples/
│       ├── load_env.py
│       ├── track.py
│       ├── gen-storyboard.py         # 分镜 + URL 存储 + 多角色 I2I
│       ├── gen-character.py          # sheet / three-view / expression
│       ├── gen-background.py         # 纯背景
│       └── gen-props.py              # 道具
│
├── video-composer/                   # 子 Skill 4: 视频合成
│   ├── SKILL.md
│   └── examples/
│       ├── load_env.py
│       ├── track.py
│       ├── gen-video.py              # reference 模式 + 429 重试
│       ├── poll-video.py
│       └── merge-videos.py
│
├── post-production/                  # 子 Skill 5: 后期制作
│   ├── SKILL.md
│   └── examples/
│       ├── load_env.py
│       ├── track.py
│       ├── gen-tts.py                # edge-tts 配音
│       ├── gen-subtitles.py          # SRT 字幕
│       └── final-compose.py          # ffmpeg 最终合成
│
└── asset-manager/                    # 子 Skill 6: 资产管理
    ├── SKILL.md
    └── examples/
        ├── load_env.py
        ├── track.py
        ├── init-project.py
        ├── track-asset.py
        ├── list-assets.py
        └── find-asset.py
```

## 资产数据库（assets.db）

每个项目一个 SQLite，自动记录所有产出：

```sql
-- asset_type 值:
--   script | image | image_three-view | image_expression
--   | image_background | image_prop | video | video_final
--   | audio | subtitle | reference
```

## 速率限制

| 模型 | 限制 | 脚本自动间隔 |
|------|------|-------------|
| `agnes-image-2.5-flash` 1K | 20次/分 | 3s |
| `agnes-image-2.5-flash` 2K | 10次/分 | 7s |
| `agnes-image-2.5-flash` 3K/4K | 1次/分 | 60s |
| `agnes-video-2.5-flash` | **1次/分** | 65s + 429/503 退避（共享队列高峰会满，脚本快速失败后重跑即可续接） |

视频约束：size 固定 720P，时长 4-12s，图片参考最多 5 张。

## 作为 RikkaHub Skill 安装

```
skill_install_from_url https://raw.githubusercontent.com/Lusensec/Agnes-Manju-Studio-Skills/master/SKILL.md
```

安装后对 AI 说：
- "用 douyin 预设帮我做 XX 漫剧"
- "生成角色三视图和道具"
- "加配音和字幕"
- "拼接最终成片"

## 许可

MIT
