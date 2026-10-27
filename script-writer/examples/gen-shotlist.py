#!/usr/bin/env python3
"""总导演（Director Master）：把剧本的场次展开为编号分镜 shotlist。

每个 shot 只含一个主动作（一镜一动作），全局连号，附全局导演阐述
（色调/光线/运镜连续性原则），产物供 gen-storyboard.py / gen-video.py
以 --shotlist 模式逐镜生成画面与视频。

Output: scripts/<project>-shotlist.json

Usage:
    python gen-shotlist.py "项目名" [--max-shots 60] [--seconds 5] [--model agnes-3.0-flash]
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


def call_agnes(prompt: str, model: str, max_tokens: int = 8192) -> str:
    data = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        BASE, data=data,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=180).read()
    return json.loads(resp)["choices"][0]["message"]["content"]


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


SYSTEM_PROMPT = """你是专业漫剧总导演。任务：把给定剧本的场次（scenes）逐场展开成可直接喂给生图/生视频模型的"分镜镜头表"（shot list）。

输出严格 JSON（不要 markdown 代码块）：
{
  "director_notes": "全局导演阐述（一段话）：整片色调基调 / 光线原则 / 运镜与节奏 / 跨镜连续性规则（如固定色温、同一场景光线方向一致、角色外形不变）",
  "shots": [
    {
      "shot": 1,
      "scene_id": 1,
      "title": "中文短标题",
      "frame": "英文生图提示词：[角色外形+动作]+[场景/环境]+[风格]+[光线]+[构图]+[质量词]，6 槽结构",
      "camera": "中文运镜：景别(远/全/中/近/特写)+机位运动(固定/缓推/横移/摇镜等)",
      "seconds": 5,
      "dialogue": "该镜头台词（无则为空字符串）"
    }
  ],
  "total_seconds": 150
}

硬性约束：
1. shot 全局从 1 连号；一镜只含一个主动作，时长 = 用户指定的每镜秒数（默认 5）。
2. 总镜头数不超过用户给定的上限；不够展开时优先保证开场钩子与结尾反转。
3. frame 中的角色外形必须与用户提供的"角色外形基准"完全一致（跨镜一致性），不得自行更改发型/服装/配色。
4. 同一 scene_id 内的镜头场景/光线保持一致；scene_id 切换时允许换场景。
5. dialogue 只能取自该 scene 的台词（可拆句），不得新增台词。
6. 若剧本带 氛围/天气/道具 等资产信息，把它融进 frame 的环境与光线描述。"""


def asset_brief(script: dict, max_each: int = 4) -> str:
    parts = []
    for key, label in (("locations", "场景"), ("costumes", "服装"), ("props", "道具"), ("weather", "天气/光线")):
        items = script.get(key, [])
        if not items:
            continue
        desc = "; ".join(
            f"{it.get('name', '')}：{it.get('description', '')}".strip("： ")
            for it in items[:max_each]
        )
        parts.append(f"{label} → {desc}")
    return "\n".join(parts)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    project = args[0]

    max_shots, seconds, model = 60, 5, "agnes-3.0-flash"
    i = 1
    while i < len(args):
        if args[i] == "--max-shots":
            max_shots = int(args[i + 1]); i += 2
        elif args[i] == "--seconds":
            seconds = max(4, min(12, int(args[i + 1]))); i += 2
        elif args[i] == "--model":
            model = args[i + 1]; i += 2
        else:
            i += 1

    proj_dir = PROJECT_ROOT / project
    scripts = list((proj_dir / "scripts").glob(f"{project}-script.json"))
    if not scripts:
        print(f"[ERROR] 未找到剧本: {proj_dir}/scripts/{project}-script.json", file=sys.stderr)
        sys.exit(1)
    script = json.loads(scripts[0].read_text(encoding="utf-8"))
    config = script.get("config", {})
    style = config.get("style", "动画")
    director_style = config.get("director_style", "")
    style_extra = config.get("style_extra", "")
    aspect_ratio = config.get("aspect_ratio", "16:9")

    chars = script.get("characters", [])
    char_brief = "\n".join(
        f"- {c.get('name', '')}：{c.get('description', '')}" for c in chars
    ) or "（剧本未提供角色）"

    scenes = script.get("scenes", [])
    n_scenes = len(scenes)
    if config.get("target_total"):
        est = max(3, min(max_shots, round(int(config["target_total"]) / seconds)))
    else:
        est = min(max_shots, n_scenes * 4)

    prompt = f"""项目名: {project}
画面: {aspect_ratio} | 视觉风格: {style}{(' + ' + style_extra) if style_extra else ''}{(' | 导演风格: ' + director_style) if director_style else ''}
每镜时长: {seconds} 秒 | 总镜头数上限: {est}（不超过 {max_shots}）

角色外形基准（frame 中必须一致沿用）：
{char_brief}

资产上下文（可融入 frame 的环境/光线）：
{asset_brief(script) or "（无）"}

剧本场次（JSON）：
{json.dumps(scenes, ensure_ascii=False, indent=1)}

请输出完整 shotlist JSON（director_notes + shots + total_seconds）。"""

    print(f"🎬 总导演展开: {project}（{n_scenes} 场 → ≤{est} 镜，每镜 {seconds}s）...")
    shotlist = None
    last_raw = ""
    for attempt in range(2):
        raw = call_agnes(prompt, model=model)
        last_raw = raw
        shotlist = extract_json(raw)
        if shotlist:
            break
        print(f"   ⚠️  第 {attempt+1} 次返回的 JSON 无法解析，重试...")
    if not shotlist:
        print("[ERROR] 模型未返回有效 JSON:\n" + last_raw[:500], file=sys.stderr)
        sys.exit(1)

    # 连号校验/修正 + 截断
    shots = shotlist.get("shots", [])
    for idx, s in enumerate(shots, 1):
        s["shot"] = idx
    shotlist["shots"] = shots[:max_shots]
    shotlist["project"] = project
    shotlist["model"] = model
    shotlist["seconds_default"] = seconds
    shotlist["stats"] = {
        "n_scenes": n_scenes,
        "n_shots": len(shotlist["shots"]),
        "total_seconds": sum(int(s.get("seconds", seconds)) for s in shotlist["shots"]),
    }
    shotlist["generated_at"] = datetime.now(timezone.utc).isoformat()

    out = proj_dir / "scripts" / f"{project}-shotlist.json"
    out.write_text(json.dumps(shotlist, ensure_ascii=False, indent=2), encoding="utf-8")
    track_file(project, "script", str(out), "总导演 shotlist",
               f"镜数={shotlist['stats']['n_shots']},每镜={seconds}s")

    print(f"✅ shotlist 已保存: {out}")
    print(f"   {shotlist['stats']['n_shots']} 镜 | 总时长 {shotlist['stats']['total_seconds']}s")
    print(f"   导演阐述: {str(shotlist.get('director_notes', ''))[:80]}...")
    print("\n下一步：")
    print(f"  [1] 逐镜出图 → python storyboard-gen/examples/gen-storyboard.py \"{project}\" --shotlist")
    print(f"  [2] 逐镜出视频 → python video-composer/examples/gen-video.py \"{project}\" --shotlist")
    print(f"  [3] 查看/修改 → 直接编辑 {out.name}")


if __name__ == "__main__":
    main()
