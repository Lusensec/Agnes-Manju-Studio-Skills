# ComfyUI Agnes Flash Suite 参考分析 —— 可借鉴思想与节点清单

> 分析对象：
> - 仓库：[Lusensec/ComfyUI-Agnes-Flash-Suite](https://github.com/Lusensec/ComfyUI-Agnes-Flash-Suite)（v1.12.0，29 个节点，自包含 API 客户端）
> - 工作流：`漫剧创作工作流.json`（litegraph 格式，88 节点 / 24 种节点类型）
>
> 目标：提炼可落回 **Agnes-Manju-Studio-Skills（CLI/Skill 套件）** 的思想与节点设计。

---

## 一、ComfyUI 套件节点总览（29 个）

| 类别 | 节点 | 核心设计 |
|------|------|---------|
| 配置 | API Key 配置 ×全局 | base_url 五级优先级链：节点输入 > api_key_config.json > 环境变量 > config.yaml > 内置默认 |
| 文本 | 文本输入 / 字符串合并（上中下三段，中段=人工衔接语） | 纯本地，无 API 依赖 |
| 文本 | LLM 对话（thinking 开关 + reasoning_effort） | 通用扩写/改写/批量转换 |
| 文本 | 剧本生成（**三维参数**：题材标签 × 情绪 × 节奏；节奏决定每场秒数，target_duration 估算场次；输出=核心钩子+分场四行结构） | 剧本类型可定制 |
| 文本 | 解说剧本生成（口播稿） | 解说赛道 |
| 文本 | 场景切分 / 总导演（章节/剧本 → 编号分镜 ×60 + all_scenes JSON 数组合并输出） | 全链"一根线"的源头 |
| 文本 | 资产提取（**5 路 JSON**：角色/场景/服装/道具/天气） | 跨镜一致性的资产底座 |
| 文本 | 分镜提示词（单条/批量 60 路，可注入资产 5 路 JSON；3 路分段 all_prompts_1_20/_21_40/_41_60） | 提示词=英文生图指令 |
| 文本 | 视频提示词（单条/批量 20 路，mode=keyframe/text/reference 对应 3 个视频节点；台词非空才注入） | 免手写运镜 |
| 文本 | 三视图提示词（单条/批量：左 1/3 特写 + 右 2/3 三视图分栏 + PBR 风格 + 自动去除矛盾字样） | 三视图专用模板 |
| 文本 | 资产提示词（单条/批量：art-director 模板，纯主体正视图 + 风格尾词） | 资产→英文提示词 |
| 文本 | 文本拆分（JSON 数组/JSON 对象/【】括号块/编号列表/空行段落 5 模式，≤20 路 + all_items） | 扇出工具 |
| 图像 | 图像生成（1K-4K × 8 画幅；n>1 自动降级） | 官方六槽提示词结构 |
| 图像 | 图生图（主参考 + 额外 5 张；strength 转提示词指令；4 槽结构"显式保留"） | 多图合成 |
| 图像 | 三视图（21:9 宽幅；reference_image 定妆图回流） | 分栏布局 |
| 图像 | 三视图批量 / 分镜图批量（20 槽/波，线程池 max_concurrency=10，status JSON {success/error/empty} + all_images 批量张量） | 分波控 RPM |
| 图像 | 图像反推提示词 | 参考 |
| 图像 | 图像拼图（批量张量→2 列网格总览，黑图过滤，纯本地 PIL） | 一眼看全批 |
| 视频 | 文生视频 / 关键帧生视频 / 参考视频生成（503/429 退避重试 0-30 次；seed 可复现；下载 3 次重试 + video_url 抢救） | 逐条生成 |

**共同设计哲学**：① 批量节点一律"JSON 数组进 / JSON 数组 + status 出"，一根线到底免逐槽手接；② 每条失败不影响其他条，槽号保位；③ 空输入=零 API 调用；④ 全部 LLM 类节点带 reasoning_effort 档位；⑤ 退避参数（retries/max_wait）全部用户可调。

---

## 二、漫剧创作工作流（88 节点）管线拆解

节点统计：`AgnesNovelAPIKeyConfig ×14`、`AgnesNovelTextToVideo ×10`、`SaveVideo ×10`、`ShowText ×35`、其余各 ×1-2。

```
[故事文本 TextSource]
   └→ StringMerge(概念+短剧约束) ─┬→ 剧本生成 ScreenplayGenerator（tag=逆袭爽文, emotion=爽, rhythm=快节奏,
   │                              │    target_duration=180s, temp=0.8）
   ├→ 风格选择 StyleSelector（视觉=现代都市 × 导演=历史史诗 + extra）
   ├→ 资产提取 AssetExtractor → 5 路 JSON（角色/场景/服装/道具/天气）
   ├→ 总导演 DirectorMaster → all_scenes（编号分镜 ≤60，5s/镜）
   │
   ├─ 资产线: 资产提示词批量(角色/cinematic, 并发10) → 三视图提示词批量 → 三视图批量(2K, 21:9)
   │          → 图像拼图(总览 mosaic)
   ├─ 分镜线: 分镜提示词批量(all_scenes + 注入 5 路资产 JSON, 分段 20/波)
   │          → 分镜图批量(2K, 16:9, 20 图/波 ×3 波) → 图像拼图(总览)
   └─ 视频线: 视频提示词批量(3 实例各连一段 all_prompts, mode=text, duration=12)
              → 10 × [APIKeyConfig + 文生视频(seed=55555555, wait=3600s, retries=10) + SaveVideo]
```

关键参数思想：**每个视频节点独立挂一个 KeyConfig**（14 个配置节点 = 1 全局 + 10 逐镜 + 3 批量 + 1 剧本），实现"哪条 key 出哪段"的细粒度绑定与并行；**seed 固定 55555555** 保证批次内风格可复现；**retries=10 / max_wait=3600s** 明显比默认（5/600）激进，靠多 key 并行消化队列。

---

## 三、可借鉴思想汇总表（核心）

> 落点 = 本套件对应模块/脚本；优先级：P0=高价值低成本，P1=中等，P2=扩展项。

| # | 思想 / 节点 | 我们现状 | 借鉴方案（落到哪个脚本） | 优先级 |
|---|------------|---------|------------------------|:---:|
| 1 | **剧本三维参数**：题材标签 tag（逆袭爽文/甜宠/悬疑/搞笑/热血/治愈/虐心…）× 情绪（爽/暖/爆笑/热血/紧张/泪）× 节奏（快 5-8s/中 8-12/慢 12-15）+ target_duration 总时长估算场次 | `write-script.py` 只有 风格/方向/单场景时长/尺寸 | `write-script.py` 增加 `[tag] [emotion] [rhythm] [总时长]` 参数，SYSTEM_PROMPT 按节奏定每场秒数与钩子密度（快=每 1-2 场一钩子），config 落 JSON | P0 |
| 2 | **核心钩子开场**：剧本首行"核心钩子"，节奏快时 1-2 场必出钩子 | SYSTEM_PROMPT 无钩子要求 | 剧本 JSON 增加 `hook` 字段 + prompt 约束 | P0 |
| 3 | **风格双轴**：visual_style（画面长什么样）× director_style（故事怎么讲）+ extra 自由补充；输出 style_json 机器可读 | config 只有单值 `style` | config 拆 `visual_style` / `director_style` / `style_extra`，生图生视频 prompt 分别取用 | P0 |
| 4 | **资产 5 路提取**（角色/场景/服装/道具/天气 JSON）注入分镜/视频提示词 → 跨镜一致性 | 剧本只有 characters + props；gen-video 仅注入 character 参考图 | 剧本 JSON 扩 5 类资产；`gen-storyboard.py`/`gen-video.py` 的 prompt 按场景注入相关资产描述（"未连接资产时显式标注不脑补"） | P0 |
| 5 | **总导演 = 场次→编号分镜（镜级 shot list）**：5s/镜，≤60 镜，all_scenes JSON | 场景直接出图，无镜级拆分 | 新增 `script-writer/examples/gen-shotlist.py`：LLM 把剧本 scene 扩写成编号 shot（画面/动作/运镜/时长），存 `*-shotlist.json`，下游按 shot 生图生视频 | P0 |
| 6 | **status JSON + 断点续跑**：`{success/error/empty + reason}`，重跑只补失败槽 | 批量脚本要么全过要么 exit 3 | 生图/生视频批量落盘 `*-batch-status.json`（槽号=场景号），`--retry-failed` 只重做失败项 | P0 |
| 7 | **mosaic 总览拼图**：批量图 → 2 列网格 + 槽号 + 黑图过滤，纯本地 PIL | 生成后靠逐张展示确认 | 新增 `storyboard-gen/examples/gen-mosaic.py`（PIL 网格拼图 `*-overview.png`），供 Agent "展示图片请确认" 环节一眼看全批 | P0 |
| 8 | **seed 可复现**：视频 seed 固定值（工作流用 55555555） | `gen-video.py` 无 seed | `submit_video` 加可选 `seed`（`.env`/`--seed`，0=随机） | P1 |
| 9 | **退避参数化**：retries 0-30（间隔 10/30/60/60…）、max_wait 可配（工作流 3600s） | `retry_api` 固定 4 次、`poll_video` 固定 600s | 读 `AGNES_VIDEO_RETRIES`（默认 10）/`AGNES_VIDEO_WAIT`（默认 3600） | P1 |
| 10 | **视频下载 3 次重试 + URL 抢救**：下载失败报 video_url/task_id 供手动下载 | 下载失败即中断 | `gen-video.py` 下载环节加 2/5/10s 重试，失败打印可抢救 URL | P1 |
| 11 | **LLM 批量并发（线程池 max_concurrency）**：提示词批量节点默认并发 10，频繁 429 调小 | LLM 调用全串行 | shotlist/分镜提示词/视频提示词类脚本加 `--concurrency N`（LLM 限宽于生图，N=5-10 安全） | P1 |
| 12 | **分波出图（20 张/波 ×3 实例）控 RPM** | `gen-storyboard.py` 全量串行（3s/7s 间隔） | 加 `--wave 20`：每波 20 张 + 波间缓冲，1K 档可并发 2-3 张（20 次/分上限内） | P1 |
| 13 | **官方提示词模板**：文生图六槽 [主体]+[场景/环境]+[风格]+[光照]+[构图]+[质量]；图生图四槽（显式"保留什么"）；多图五槽 | prompt 拼接待风格词映射，无槽位规范 | `gen-storyboard.py`/`gen-character.py` 内置六槽模板；`multi-image-combine`（新套件）已支持，补文档 | P1 |
| 14 | **三视图 21:9 + 分栏布局**（左 1/3 特写 + 右 2/3 三视图，PBR 风格，白底无阴影） | `gen-character.py three-view` 默认比例未定 | three-view 默认 21:9 + 内置分栏布局指令 | P1 |
| 15 | **空输入=零 API 调用 + [跳过] 日志**；缺 Key=全槽报错但零调用 | 部分脚本空输入直接崩 | 统一 skip 语义：无剧本/无资产 → 打印提示不调 API、exit 0 | P1 |
| 16 | **reasoning_effort 档位 + 空响应排查**（200 但正文空=思考预算耗尽 → 降档/换 2.5） | thinking-mode 示例有，批量脚本无 | 批量 LLM 脚本加 `--thinking none/low/…`；空响应自动降档重试 1 次 | P2 |
| 17 | **逐镜 Key 绑定（14 个 KeyConfig）**：哪条 key 出哪段可追溯 | 多 key worker 池随机领取 | status.json 记录 `slot → api_key(脱敏)` 映射，便于排查与配额核算 | P2 |
| 18 | **成本估算表 + 错峰提示**（单集 20 场景 ≈ $2.3；20-24 点队列最忙） | README 只有速率限制 | README 增"成本/时长估算 + 错峰建议"小节 | P2 |
| 19 | **解说剧本模式（口播稿）**：对观众的叙述腔文案 | 管线只有对白 | 扩展 `write-script.py --mode narration`（解说向，单旁白角色），post-production 走 narration TTS | P2 |
| 20 | **字符串三段合并（中段=人工衔接语）** | 无 | `refine-script.py` 支持"两段剧本+过渡语"拼接；成本低可并入 #5 | P2 |

### 明确**不**借鉴（ComfyUI 特有 / 前端特性）

- 节点配色/工具面板/OUTPUT_TOOLTIPS（`OUTPUT_TOOLTIPS`、节点染色、文档面板）——无 UI 场景
- 旧实例自愈迁移（`agnes-migrate.js` widget 重映射）——CLI 无历史实例问题；但思想可迁移：脚本参数改名时用别名兼容旧参数（同 `COMIC_STUDIO_ROOT` 回退做法）
- 批量张量 (N,H,W,3) / VHS 视频输出——我们的产物本来就是文件
- 黑图占位槽——用 status.json（#6）替代，不产生占位文件

---

## 四、落地路线图建议

```
P0（1-2 天，直接提升出片质量与可确认性）
  ① write-script.py 三维参数 + hook + 风格双轴（#1 #2 #3）
  ② 剧本 5 路资产 + 注入（#4）
  ③ gen-shotlist.py 总导演镜级拆分（#5）
  ④ batch-status.json + --retry-failed（#6）
  ⑤ gen-mosaic.py 总览拼图（#7）

P1（1 周，提速与可控性）
  ⑧ #8 seed、#9 退避参数化、#10 下载抢救
  ⑪ #11 LLM 并发、#12 分波出图、#13 六槽模板、#14 三视图 21:9、#15 空输入 skip

P2（按需）
  #16 思考档位、#17 key 映射、#18 成本表、#19 解说模式、#20 衔接语
```

> 依赖顺序：#5（shot list）是 #12 分波出图与 #11 提示词并发的载体；#4（资产 5 路）是 #13 提示词模板的注入源——建议 P0 阶段按 ①→②→③→④→⑤ 顺序做。
