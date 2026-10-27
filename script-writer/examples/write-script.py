#!/usr/bin/env python3
"""Generate a structured comic script using agnes-3.0-flash.

Usage:
    python write-script.py "项目名" "故事概念" [风格] [方向] [时长] [尺寸] [选项]
    风格: 动画|写实|水墨|赛博朋克|二次元 (default: 动画)   # 视觉风格（兼容旧位置参数）
    方向: landscape(16:9)|portrait(9:16) (default: landscape)
    时长: 4-12 (default: 5，未显式给出时按 --rhythm 自动选)
    尺寸: 1K|2K|3K|4K (default: 1K)

三维参数与风格双轴（借鉴 ComfyUI 剧本生成器，可选）：
    --tag 逆袭爽文|甜宠|悬疑|搞笑|热血|治愈|虐心      题材标签
    --emotion 爽|暖|爆笑|热血|紧张|泪                  核心情绪线
    --rhythm 快|中|慢                                  节奏（快=每 1-2 场必出钩子）
    --target-total 180                                  总目标时长（秒，用于估算场景数）
    --director-style 史诗历史|悬疑|喜剧|治愈|无        导演风格（叙事/镜头倾向）
    --style-extra "..."                                  风格自由补充说明
    --hook / --no-hook                                   强制/禁止核心钩子（默认按节奏自动）

Examples:
    python write-script.py "项目" "概念"
    python write-script.py "项目" "概念" 动画 portrait 8 2K
    python write-script.py "项目" "概念" 二次元 portrait 6 1K \\
        --tag 逆袭爽文 --emotion 爽 --rhythm 快 --target-total 180 --director-style 悬疑
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_env import API_KEY, PROJECT_ROOT
from track import track_file

BASE = "https://api.agnes-ai.cn/v1/chat/completions"

TAGS = ["逆袭爽文", "甜宠", "悬疑", "搞笑", "热血", "治愈", "虐心"]
EMOTIONS = ["爽", "暖", "爆笑", "热血", "紧张", "泪"]
RHYTHMS = ["快", "中", "慢"]
DIRECTOR_STYLES = ["史诗历史", "悬疑", "喜剧", "治愈", "无"]

# 节奏 → 每场秒数（未显式传时长时采用）与钩子密度
RHYTHM_SECONDS = {"快": "5", "中": "8", "慢": "12"}
HOOK_RULE = {
    "快": "快节奏：每 1-2 个场景必须出现一个钩子（反转/悬念/视觉冲击），开场 3 秒内必须有强钩子",
    "中": "中节奏：每 2-3 个场景出现一个钩子，结尾留悬念",
    "慢": "慢热铺垫：前 1/3 以氛围与人物建立为主，钩子后置，靠情绪积累引爆",
}

SYSTEM_PROMPT = """你是专业漫剧/短剧编剧。根据用户的故事概念与三维参数（题材/情绪/节奏），
输出严格 JSON（不要 markdown 代码块），结构：
{
  "logline": "一句话概括",
  "hook": "核心钩子：一句话点出最抓观众的悬念/冲突/反转",
  "characters": [
    {"name": "角色名", "description": "外貌详细描述(用于生图)", "personality": "性格", "role": "主角/配角"}
  ],
  "locations": [
    {"name": "场景名", "description": "场景外观详细描述(用于生图：空间/陈设/光线基调)"}
  ],
  "costumes": [
    {"character": "角色名", "name": "服装名", "description": "服装外观详细描述(用于生图：款式/颜色/材质)"}
  ],
  "props": [
    {"name": "道具名", "description": "外观详细描述(用于生图，材质/颜色/尺寸)"}
  ],
  "weather": [
    {"name": "天气/氛围名", "description": "天气或光线氛围描述(用于生图，影响色调与气氛)"}
  ],
  "scenes": [
    {
      "scene_id": 1,
      "title": "场景标题",
      "description": "画面描述(英文，用于生图提示词，包含角色外观+动作+场景+光线)",
      "description_zh": "画面描述(中文，供阅读)",
      "atmosphere": "氛围/光线基调(可选，供视频运镜参考)",
      "location": "场景名(对应 locations 中某项，可选)",
      "props": ["道具名(对应 props，可选)"],
      "dialogue": [
        {"character": "角色名", "line": "台词", "emotion": "情绪"}
      ]
    }
  ]
}
硬性约束：
1. 台词：每个场景 1-2 句、每句不超过 15 个汉字——台词会被 TTS 配音，必须装进"每场景时长"，超长会被截断或叠音，宁短勿长。
2. 五路资产：locations 列出 2-5 个拍摄场景；costumes 每个主要角色 1 套关键服装；props 列出 2-5 个关键道具；
   weather 列出 1-3 种天气/光线氛围。某类确实不涉及就输出空数组 []，不要硬凑。
3. 场景数按用户指定的节奏与总时长估算（用户会给出建议范围），不得超出该范围。
4. 钩子：按用户节奏参数执行钩子密度要求；"hook" 字段写全片核心钩子。
5. 每个 scene 尽量填 location（场景名须与 locations 中一致）与 props 引用，方便下游注入资产一致性。"""


def call_agnes(prompt: str, model: str = "agnes-3.0-flash") -> str:
    data = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 8192
    }).encode()
    req = urllib.request.Request(
        BASE, data=data,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=120).read()
    return json.loads(resp)["choices"][0]["message"]["content"]


def parse_args(argv: list) -> dict:
    """Positional args (project, concept, style, orientation, duration, img_size)
    + optional flags; flags may appear in any order after the positionals."""
    a = {"flags": {}, "positional": []}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            key = tok.lstrip("-")
            if key in ("hook", "no-hook"):
                a["flags"][key] = True
            else:
                i += 1
                if i >= len(argv):
                    print(f"[ERROR] 选项 --{key} 缺少取值")
                    sys.exit(1)
                a["flags"][key] = argv[i]
        else:
            a["positional"].append(tok)
        i += 1
    return a


def extract_json(raw: str):
    """Pull the JSON object out of an LLM reply; light repair for
    trailing commas. Returns dict or None."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    text = raw[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        repaired = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)
    p = parse_args(argv)
    pos, flags = p["positional"], p["flags"]

    project = pos[0]
    concept = pos[1]
    style = pos[2] if len(pos) > 2 else "动画"
    orientation = pos[3] if len(pos) > 3 else "landscape"
    duration_given = len(pos) > 4
    duration = pos[4] if duration_given else None
    img_size = pos[5] if len(pos) > 5 else "1K"

    tag = flags.get("tag", "")
    emotion = flags.get("emotion", "")
    rhythm = flags.get("rhythm", "")
    target_total = flags.get("target-total", "")
    director_style = flags.get("director-style", "")
    style_extra = flags.get("style-extra", "")

    # Validate
    valid_orient = ["landscape", "portrait"]
    if orientation not in valid_orient:
        print(f"[ERROR] 方向无效: {orientation}，可选: {valid_orient}")
        sys.exit(1)
    valid_sizes = ["1K", "2K", "3K", "4K"]
    if img_size not in valid_sizes:
        print(f"[ERROR] 尺寸无效: {img_size}，可选: {valid_sizes}")
        sys.exit(1)
    if tag and tag not in TAGS:
        print(f"[WARN] 未知题材 {tag}，可选: {TAGS}（仍按原值生成）")
    if emotion and emotion not in EMOTIONS:
        print(f"[WARN] 未知情绪 {emotion}，可选: {EMOTIONS}（仍按原值生成）")
    if rhythm and rhythm not in RHYTHMS:
        print(f"[ERROR] 节奏无效: {rhythm}，可选: {RHYTHMS}")
        sys.exit(1)
    if director_style and director_style not in DIRECTOR_STYLES:
        print(f"[WARN] 未知导演风格 {director_style}，可选: {DIRECTOR_STYLES}（仍按原值生成）")

    # duration: explicit positional > rhythm default > "5"
    if not duration:
        duration = RHYTHM_SECONDS.get(rhythm, "5")
    duration = str(max(4, min(12, int(duration))))

    # 场景数建议范围
    if target_total:
        n_est = max(3, min(15, round(int(target_total) / int(duration))))
        scene_range = f"{n_est}（总时长 {target_total}s ÷ 每场 {duration}s 估算）"
    else:
        scene_range = "3-8"

    # 钩子：默认按节奏自动，可 --hook / --no-hook 覆盖
    if "hook" in flags:
        hook_req = "必须设计核心钩子（hook 字段 + 开场钩子场景）"
    elif "no-hook" in flags:
        hook_req = "无需刻意设计钩子"
    else:
        hook_req = HOOK_RULE.get(rhythm, "在结尾或中段设置至少一个钩子/悬念")

    aspect_ratio = "16:9" if orientation == "landscape" else "9:16"
    ratio_label = "横屏" if orientation == "landscape" else "竖屏"

    proj_dir = PROJECT_ROOT / project
    script_dir = proj_dir / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"📝 正在生成剧本...",
        f"   项目: {project}",
        f"   概念: {concept}",
        f"   视觉风格: {style} | {ratio_label}({aspect_ratio}) | {duration}s/场 | {img_size}",
        f"   三维参数: 题材={tag or '—'} | 情绪={emotion or '—'} | 节奏={rhythm or '—'} | 总时长={target_total or '—'}s",
        f"   导演风格: {director_style or '—'} | 场景数建议: {scene_range}",
        "",
    ]
    print("\n".join(lines))

    prompt = f"""项目名: {project}
故事概念: {concept}
题材标签: {tag or '（未指定，按概念自选最贴近的一种）'}
核心情绪线: {emotion or '（未指定）'}
节奏: {rhythm or '中'}（每场 {duration} 秒，场景数 {scene_range}）
总目标时长: {target_total + ' 秒' if target_total else '未指定'}
视觉风格: {style}
导演风格: {director_style or '（未指定，默认自然叙事）'}
风格补充: {style_extra or '（无）'}
画面方向: {ratio_label}({aspect_ratio})
每场景时长: {duration} 秒
钩子要求: {hook_req}

请输出完整剧本 JSON。"""

    # Call the model; retry once if it returns unparseable JSON (transient
    # trailing commas / cut-off are common). extract_json also repairs commas.
    script = None
    last_raw = ""
    for attempt in range(2):
        raw = call_agnes(prompt)
        last_raw = raw
        script = extract_json(raw)
        if script:
            break
        print(f"   ⚠️  第 {attempt+1} 次返回的 JSON 无法解析，重试...")

    if not script:
        print("[ERROR] 模型未返回有效 JSON:\n" + last_raw[:500])
        sys.exit(1)

    script["project"] = project
    script["style"] = style
    # 五路资产保底字段（旧剧本没有则补空数组）
    for k in ("locations", "costumes", "weather", "characters", "props"):
        script.setdefault(k, [])
    config = {
        "orientation": orientation,
        "aspect_ratio": aspect_ratio,
        "video_duration": duration,
        "image_size": img_size,
        "style": style,
        "visual_style": style,
        "director_style": director_style,
        "style_extra": style_extra,
        "tag": tag,
        "emotion": emotion,
        "rhythm": rhythm,
        "target_total": target_total,
        "hook": script.get("hook", ""),
    }
    script["config"] = config
    script["created_at"] = datetime.now(timezone.utc).isoformat()

    out = script_dir / f"{project}-script.json"
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    tag_str = f"题材={tag},情绪={emotion},节奏={rhythm}" if (tag or emotion or rhythm) else "风格=" + style
    track_file(project, "script", str(out), f"剧本: {concept[:50]}",
               f"{tag_str},场景数={len(script.get('scenes', []))}")

    n_chars = len(script.get("characters", []))
    n_scenes = len(script.get("scenes", []))
    n_assets = sum(len(script.get(k, [])) for k in ("locations", "costumes", "props", "weather"))
    print(f"✅ 剧本已保存: {out}")
    print(f"   核心钩子: {script.get('hook', '（模型未输出）')}")
    print(f"   角色: {n_chars} 个 | 场景: {n_scenes} 个 | 资产: 场景{len(script.get('locations', []))}/服装{len(script.get('costumes', []))}/道具{len(script.get('props', []))}/天气{len(script.get('weather', []))}")
    print(f"   配置: {ratio_label} | {style} | {duration}s/场 | {img_size}\n")

    print("下一步：")
    print(f"  [1] 总导演镜级拆分 → python script-writer/examples/gen-shotlist.py \"{project}\"")
    print(f"  [2] 直接生成分镜图 → python storyboard-gen/examples/gen-storyboard.py \"{project}\"")
    print(f"  [3] 修改剧本 → 编辑 {out.name} 后重新运行")
    print(f"  [4] 调整某角色 → python refine-script.py \"{project}\" \"角色名\" \"新描述\"")


if __name__ == "__main__":
    main()
