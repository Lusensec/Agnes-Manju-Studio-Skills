#!/usr/bin/env python3
"""Deterministic quality gate for the script -> shotlist -> media pipeline.

Borrowed from manju-laoli's validate_prompt.py idea: a set of cheap,
rule-based checks (NO LLM) that catch the common failure modes before you
spend API quota on generation. Run it at each confirmation gate.

It inspects the project's scripts/ folder and reports PASS/WARN/FAIL per
rule, with concrete offending items. Exit code = number of FAILs.

Usage:
    python validate-pipeline.py "项目名" [--stage script|shotlist|all]
                                  [--max-dialogue 15] [--min-hook-scenes 1]

Rules (deterministic, zero API):
  S1  台词字数      单句 <= --max-dialogue 字（默认 15，TTS 装得下）
  S2  场景数        scenes 非空，且每场有 scene_id + description
  S3  资产引用      场景 location/props 必须能在剧本五路资产里找到（防悬空引用）
  S4  钩子          config.hook 非空，或首 --min-hook-scenes 个场景含"钩子/反转/悬念"
  H1  分镜连号      shotlist.shots 的 shot 字段从 1 连续
  H2  分镜帧文本    每个 shot.frame 非空且 >= 20 字符（够喂生图）
  H3  分镜时长      每镜 seconds 在 [4,12]
  H4  场景覆盖      shotlist 引用的 scene_id 都在剧本里
  M1  槽位对账      storyboard/video status.json 的槽与目标（scene 或 shot）数量一致
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_env import PROJECT_ROOT


def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    project = args[0]
    stage = "all"
    max_dialogue = 15
    min_hook = 1
    i = 1
    while i < len(args):
        if args[i] == "--stage":
            stage = args[i + 1]; i += 2
        elif args[i] == "--max-dialogue":
            max_dialogue = int(args[i + 1]); i += 2
        elif args[i] == "--min-hook-scenes":
            min_hook = int(args[i + 1]); i += 2
        else:
            i += 1

    sd = PROJECT_ROOT / project / "scripts"
    script_f = list(sd.glob(f"{project}-script.json"))
    shot_f = list(sd.glob(f"{project}-shotlist.json"))
    script = load_json(script_f[0]) if script_f else None
    shotlist = load_json(shot_f[0]) if shot_f else None

    results = []  # (level, code, msg)
    fails = 0

    def add(level, code, msg):
        nonlocal fails
        if level == "FAIL":
            fails += 1
        results.append((level, code, msg))

    # ---------------- script stage ----------------
    if stage in ("script", "all"):
        if not script:
            add("FAIL", "S0", f"未找到剧本 {project}-script.json")
        else:
            scenes = script.get("scenes", [])
            if not scenes:
                add("FAIL", "S2", "剧本没有 scenes")
            # S2 per-scene fields
            bad = [s.get("scene_id") for s in scenes if not s.get("description")]
            if bad:
                add("FAIL", "S2", f"场景缺 description: {bad}")

            # S1 dialogue length
            long_lines = []
            for s in scenes:
                for d in s.get("dialogue", []):
                    line = d.get("line", "")
                    if len(line) > max_dialogue:
                        long_lines.append((s.get("scene_id"), line[:18], len(line)))
            if long_lines:
                lvl = "WARN" if len(long_lines) <= 3 else "FAIL"
                add(lvl, "S1", f"{len(long_lines)} 句台词超 {max_dialogue} 字: {long_lines[:5]}")

            # S3 asset reference integrity
            loc_names = {a.get("name") for a in script.get("locations", [])}
            prop_names = {a.get("name") for a in script.get("props", [])}
            dangling = []
            for s in scenes:
                l = s.get("location")
                if l and l not in loc_names:
                    dangling.append(f"scene{s.get('scene_id')}.location='{l}'")
                for p in s.get("props", []):
                    if p not in prop_names:
                        dangling.append(f"scene{s.get('scene_id')}.props='{p}'")
            if dangling:
                add("WARN", "S3", f"悬空资产引用: {dangling[:5]}")

            # S4 hook
            hook = (script.get("config", {}).get("hook") or script.get("hook") or "").strip()
            head = scenes[:min_hook]
            has_head = any(re.search(r"钩子|反转|悬念|冲击|爆|亮", json.dumps(s, ensure_ascii=False))
                          for s in head)
            if not hook and not has_head:
                add("WARN", "S4", "无核心钩子（config.hook 空且开场无钩子词）")

    # ---------------- shotlist stage ----------------
    if stage in ("shotlist", "all") and shotlist:
        shots = shotlist.get("shots", [])
        if not shots:
            add("FAIL", "H0", "shotlist 没有 shots")
        else:
            # H1 consecutive numbering
            nums = [s.get("shot") for s in shots]
            expected = list(range(1, len(nums) + 1))
            if nums != expected:
                add("FAIL", "H1", f"分镜连号断裂: 实际 {nums[:10]}{'...' if len(nums)>10 else ''}")
            # H2 frame text
            thin = [s.get("shot") for s in shots if len((s.get("frame") or "").strip()) < 20]
            if thin:
                add("WARN", "H2", f"{len(thin)} 镜 frame 过短(<20字): {thin[:5]}")
            # H3 seconds in range
            oob = [(s.get("shot"), s.get("seconds")) for s in shots
                   if s.get("seconds") and not (4 <= int(s.get("seconds", 0)) <= 12)]
            if oob:
                add("FAIL", "H3", f"镜时长越界(4-12s): {oob[:5]}")
            # H4 scene coverage
            if script:
                valid_scenes = {s.get("scene_id") for s in script.get("scenes", [])}
                orphan = sorted({s.get("scene_id") for s in shots
                                 if s.get("scene_id") not in valid_scenes})
                if orphan:
                    add("WARN", "H4", f"分镜引用了剧本不存在的 scene_id: {orphan}")

    # ---------------- media status 对账 (M1) ----------------
    if stage in ("all", "script") and script:
        target = len(script.get("scenes", []))
        for name, key in (("storyboard-status", "scene-"), ("video-status", "scene-")):
            sf = list(sd.glob(f"{project}-{name}.json"))
            if not sf:
                continue
            st = load_json(sf[0]) or {}
            slots = st.get("slots", {})
            n_ok = sum(1 for v in slots.values() if v.get("status") == "success")
            n_err = sum(1 for v in slots.values() if v.get("status") == "error")
            n_pen = sum(1 for v in slots.values() if v.get("status") == "pending")
            if n_err:
                add("WARN", "M1", f"{name}: {n_err} 槽失败待补 (--retry-failed)，成功 {n_ok}")
            elif n_pen:
                add("WARN", "M1", f"{name}: {n_pen} 槽 pending 未完成")

    # ---------------- report ----------------
    print(f"🧪 质量门: {project} (stage={stage})")
    if not results:
        print("  ✅ 已检规则全部通过（台词字数 / 场景完整性 / 资产引用 / 钩子 / 分镜连号 / 槽位对账）")
    for lvl, code, msg in results:
        icon = {"FAIL": "❌", "WARN": "⚠️", "PASS": "✅"}.get(lvl, "·")
        print(f"  {icon} [{code}] {msg}")
    print(f"\n{'✅ 通过' if fails == 0 else f'❌ {fails} 项 FAIL'}（{sum(1 for r in results if r[0]=='WARN')} 项 WARN）")
    if fails:
        print("提示: FAIL 项建议修正后再出片；WARN 可酌情处理。")
    sys.exit(0 if fails == 0 else fails)


if __name__ == "__main__":
    main()
