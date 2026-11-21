# Changelog — Agnes Manju Studio v1.0

首发正式版本。Python 3.9+ 标准库套件，将「故事概念 → 剧本 → 分镜图 → 短视频 → 成片」
完整管线拆为可独立调用的子 Skill，全部本地运行、产出落盘到项目文件夹。

## 管线五步（含确认门）

| Step | Skill | 关键能力 |
|------|-------|---------|
| 1 写剧本 | `script-writer` | 三维参数（`--tag` 题材 / `--emotion` 情绪 / `--rhythm` 节奏 / `--target-total` 总时长）、风格双轴（`--director-style` / `--style-extra`）、核心钩子、五路资产（characters / locations / costumes / props / weather） |
| 1.5 总导演（可选） | `script-writer/gen-shotlist.py` | 场次 → 编号分镜（一镜一主动作、全局连号、`director_notes` 全局导演阐述），产物 `*-shotlist.json` |
| 2 分镜图 | `storyboard-gen` | 多参考 I2I（角色三视图 + 背景 + 道具，≤5 张）、五路资产上下文注入、`--shotlist` 镜级出图、逐槽容错 + `*-storyboard-status.json` 断点续跑（`--retry-failed`）、`gen-mosaic.py` 网格总览图 |
| 3 视频 | `video-composer` | 图/文生视频（`--shotlist` 镜级）、多 key 并行（`AGNESAI_API_KEYS` 支持 `key@baseURL` 混平台）、429/503 退避重试、可选 TTS 音频参考嘴型同步、`*-video-status.json` 断点续跑 |
| 4 成片 | `post-production` | TTS 配音、字幕、BGM、场景对齐合成（edge-tts + ffmpeg） |

辅助：`asset-manager`（项目初始化 / 资产追踪 SQLite）、`Agnes-Flash-Suite-Skills`
（Agnes 全能力基础套件：3.0/2.5 对话、生图、生视频四个子 skill）。

## v1.0 亮点

- **三维剧本 + 钩子**：`--rhythm 快` 自动定每场 5s 与钩子密度，`--target-total` 估算场景数
- **五路资产一致性**：剧本输出 locations/costumes/props/weather，分镜提示词按场景注入（未连接资产时显式"不脑补"）
- **镜级颗粒度**：总导演 shotlist（26 镜实测），保持 `scene-N.png/mp4` 命名，merge-videos 零改动
- **批量断点续跑**：每轮写 status 账本（success / error+reason / pending），`--retry-failed` 只补失败槽
- **总览拼图确认**：`gen-mosaic.py` ffmpeg 网格图（黑图过滤 + 短行黑底补齐），一眼看全批
- **JSON 解析容错**：尾逗号修复 + 失败重试，模型偶发坏 JSON 不再中断
- **跨平台**：Windows/Linux/macOS；GBK 控制台自动切 UTF-8；`.env` 从套件根目录向上自动发现（`MANJU_STUDIO_ROOT` 可覆盖项目根）

## 使用

```bash
# 1. 配置 API Key
cp .env.example .env  # 填入 AGNESAI_API_KEY

# 2. 初始化项目
python asset-manager/examples/init-project.py "我的漫剧"

# 3. 写剧本（三维参数可选）
python script-writer/examples/write-script.py "我的漫剧" "故事概念" \
    --tag 逆袭爽文 --rhythm 快 --target-total 180

# 4. 总导演（可选）→ 分镜图 → 总览确认 → 视频 → 成片
python script-writer/examples/gen-shotlist.py "我的漫剧"
python storyboard-gen/examples/gen-storyboard.py "我的漫剧" --shotlist
python storyboard-gen/examples/gen-mosaic.py "我的漫剧"
python video-composer/examples/gen-video.py "我的漫剧" --shotlist
```

详见 [SKILL.md](./SKILL.md) 与 [README.md](./README.md)。

## 约束

- 生视频：固定 720P、4-12s、图片参考 ≤5 张、音频参考 ≤3 段、每 key 1 次/分（脚本自动 65s 间隔 + 退避）
- 生图速率：1K 20/min、2K 10/min、3K/4K 1/min（脚本内置间隔）
- 成片环节需要 ffmpeg（mosaic / 合成）
