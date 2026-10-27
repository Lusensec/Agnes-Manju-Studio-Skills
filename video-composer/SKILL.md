---
name: video-composer
description: |
  视频合成子 Skill。以分镜图片为参考，用 agnes-video-2.5-flash 逐场景生成短视频，可选拼接，自动处理 429 限流与 503 视频队列满（退避重试 + 快速失败，可幂等续跑）。
  触发场景：图片转动态短视频；图生视频；视频拼接。

# Video Composer（视频合成）

> 把分镜图片作为参考，调用 `agnes-video-2.5-flash` 逐场景生成短视频，可选拼接。

## 输入

- 项目名
- 分镜图片路径（自动从 `images/` 读取）

## 输出

- `videos/scene-<id>.mp4` — 每个场景一个视频片段
- `videos/<project>-full.mp4` — 拼接后的完整视频（需要 ffmpeg）

## 视频生成策略

1. 每个场景图片作为 `mode: "reference"` 的输入
2. prompt 用场景 description + 动作提示
3. 时长默认 5s，可配置
4. 提交后轮询 `/agnesapi` 直到 `status=completed`
5. （可选）用 ffmpeg 拼接所有片段

## 音频参考（对白嘴型同步，可选）

Agnes 视频 API 的 reference 模式支持 `audios` 参数（最多 3 段，URL 必须**公网可达**）。
`gen-video.py` 会自动启用：

1. `.env` 里配置 `AGNES_TTS_GITHUB_REPO=owner/repo`（**公开**仓库，Agnes 服务器要能匿名拉取）
2. 先跑 `gen-tts.py` 生成 `videos/audio/line-*.mp3`
3. 再跑 `gen-video.py`：脚本把 TTS 文件幂等上传到该仓库，并把每场景的台词
   （`line-<场景>-<句>.mp3`，≤3 段）作为音频参考提交，prompt 自动追加
   “说话、嘴部随参考音频自然开合”。

注意：音频参考让模型**按台词节奏**生成嘴部动作（大致同步），不是逐音素级
对口型；要逐音素级需另接 Wav2Lip/MuseTalk 类后处理。未配置仓库时自动退回
纯图片参考，不影响流程。

## 多 Key 并行 / 多平台（可选，加速）

Agnes 免费配额按 key 独立分池，且**国内站（api.agnes-ai.cn）与国际站
（apihub.agnes-ai.com）是两个平台、两条队列**。`.env` 配置
`AGNESAI_API_KEYS`（逗号分隔）后，`gen-video.py` 按 key 数开等量 worker
线程，各守自己的 65s 提交节奏，从共享场景队列领任务：

```ini
# 国内 key + 国际 key 混合并行（key@baseURL 语法，不带 @ 用 AGNESAI_BASE_URL 默认国内）
AGNESAI_API_KEYS=sk-国内key,sk-国际key@https://apihub.agnes-ai.com/v1
```

- N 段视频、K 个 key → 墙钟 ≈ ⌈N/K⌉ × (65s + 渲染)，且国内/国际队列互不影响
- 某 worker 被 429/503/网络故障卡住时冷却 90s，其他 worker 继续跑
- 全体 25 分钟无进展 → 本轮 exit 3（外层重试循环照旧兜底）
- 不配置则单 key 串行，行为与原来一致

注意：单平台内的 `video_queue_full`（503）仍是该平台的**全局队列**，多 key
能消除"单 key 串行堵死"的问题，但不能突破单平台自身的并发上限——跨平台
混合（国内 + 国际）才能真正翻倍吞吐。

推荐流程顺序：**写剧本 → 分镜图 → 配音（TTS）→ 视频（带音频参考）→ 字幕 → 合成**。

## 调用方式

```python
# 生成所有场景视频
python examples/gen-video.py "项目名"

# 只生成某个场景
python examples/gen-video.py "项目名" --scene 3

# 镜级模式（总导演 shotlist，逐镜出视频）
python examples/gen-video.py "项目名" --shotlist

# 断点续跑（只补失败/缺失槽，状态账本 scripts/<项目>-video-status.json）
python examples/gen-video.py "项目名" --retry-failed

# 查询视频状态
python examples/poll-video.py <video_id>

# 拼接所有视频（需要 ffmpeg）
python examples/merge-videos.py "项目名"
```

每轮结束都会写 `scripts/<项目>-video-status.json`（逐槽 success/error+reason/pending），
失败原因可据此定位（400=参考 URL 不可达/参数错；429/503=限流或队列满）；
`--retry-failed` 只重做失败槽。

## 用户确认点

运行结束后，**Agent 必须展示/播放视频并等用户确认**，这是流程最后一步。

- 展示：播放视频或展示文件路径
- 询问：「视频 OK？要调时长/重新生成某段？」
- 用户说"完成"→ 流程结束
- 用户说"第 N 段重来"→ `--scene N` 重新生成
- 用户说"拼接"→ 运行 `merge-videos.py`

```
✅ 视频已生成: 5 个片段
   videos/scene-1.mp4 (5s)
   videos/scene-2.mp4 (5s)
   ...

   总时长: ~25s

下一步：
  [1] 拼接完整视频 → python examples/merge-videos.py "项目名"
  [2] 重新生成某场景 → python gen-video.py "项目名" --scene N
  [3] 调整时长 → 修改剧本 duration_hint 后重新运行
  [4] 完成 🎬
```

## 注意事项

- 视频生成每个片段 2-5 分钟，5 个场景总计 10-25 分钟
- **速率限制：1次/分钟**，脚本自动间隔 65s
- 轮询间隔 30s，不要频繁请求
- 拼接需要系统安装 `ffmpeg`（`apt install ffmpeg`）

## 参数约束（agnes-video-2.5-flash）

| 参数 | 限制 |
|------|------|
| size | 固定 720P |
| 时长 | 4-12s（`--duration` 超出自动裁剪） |
| 图片参考 | 最多 5 张 |
| 音频参考 | 最多 3 段 |
| 视频参考 | 不支持 |

## 示例脚本

| 脚本 | 参数 |
|------|------|
| `examples/gen-video.py` | `[项目名] [--scene N] [--duration N] [--shotlist] [--retry-failed]` |
| `examples/poll-video.py` | `<video_id> [api_key]` |
| `examples/merge-videos.py` | `[项目名]` |
| `examples/load_env.py` | 无 |
