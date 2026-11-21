"""Pre-flight lock checklist (borrowed from manju-laoli's 五道前置锁 idea).

Before generating a script/shotlist, the key creative decisions should be
explicit rather than defaulted. This module provides:

  - LOCKS: the lock definitions (id, prompt, options, default, why)
  - render_locks(): human-readable checklist text
  - check_strict(flags, defaults): in --strict mode, raise/return the list of
    unanswered locks so the caller can stop and ask the user.

Design note: unlike manju-laoli (which hard-stops the whole task), our CLI
scripts are one-shot; the default behaviour is ADVISORY (print the checklist,
fill gaps with sensible defaults, keep going). Pass --strict to make missing
locks fatal. The Agent-facing SKILL.md uses the advisory text to ask the user
before running the script.
"""

LOCKS = [
    {
        "id": "source",
        "label": "素材来源",
        "prompt": "内容来源：1 原创 / 2 改编（有原著）/ 3 对标爆款 / 4 热点速成",
        "options": ["原创", "改编", "对标爆款", "热点速成"],
        "default": "原创",
        "flag": "source",
        "why": "改编/对标需先有原著或情报卡，影响剧本开发路径",
    },
    {
        "id": "model",
        "label": "模型",
        "prompt": "出片模型：agnes-video-2.5-flash（720P/4-12s，已锁定）",
        "options": ["agnes-video-2.5-flash"],
        "default": "agnes-video-2.5-flash",
        "why": "单模型线，无需选择；记录在案即可",
    },
    {
        "id": "aspect",
        "label": "画幅",
        "prompt": "画幅方向：landscape 16:9 / portrait 9:16 / 3:4 / 21:9",
        "options": ["landscape", "portrait"],
        "default": "portrait",
        "flag": "orientation",
        "why": "竖屏 9:16 为抖音/红果主场景；影响生图与视频 ratio",
    },
    {
        "id": "delivery",
        "label": "交付形态",
        "prompt": "交付形态：本套件固定为「脚本直接出图出视频 + 本地落盘」",
        "options": ["脚本直出"],
        "default": "脚本直出",
        "why": "区别于「只交提示词」的套件；记录在案",
    },
    {
        "id": "rhythm",
        "label": "节奏/钩子",
        "prompt": "节奏（快/中/慢）与钩子密度；快=每 1-2 场必出钩子",
        "options": ["快", "中", "慢"],
        "default": "中",
        "flag": "rhythm",
        "why": "决定每场秒数与钩子密度，影响场景数估算",
    },
]


def answered_flags(flags: dict) -> set:
    """Which lock ids are effectively answered by provided flags."""
    answered = set()
    for lk in LOCKS:
        f = lk.get("flag")
        if f and flags.get(f):
            answered.add(lk["id"])
    return answered


def missing(flags: dict) -> list:
    """Locks with no flag value. model/delivery/aspect are informational
    (always defaulted) and not treated as gates; source & rhythm are the real
    pre-flight decisions."""
    ans = answered_flags(flags)
    out = []
    for lk in LOCKS:
        if lk["id"] in ("model", "delivery", "aspect"):
            continue
        if lk["id"] not in ans:
            out.append(lk)
    return out


def render_checklist(flags: dict) -> str:
    """Advisory checklist text for printing / for the Agent to relay to user."""
    lines = ["[前置锁检查] 未指定项将按默认值继续，可加 --strict 强制补全："]
    ans = answered_flags(flags)
    for lk in LOCKS:
        marked = "OK " if (lk["id"] in ans or lk["id"] in ("model", "delivery")) else ".. "
        val = flags.get(lk["flag"], "") if lk.get("flag") else ""
        val = val or lk["default"]
        lines.append(f"  {marked} {lk['label']}: {val}  （{lk['prompt']}）")
    return "\n".join(lines)


def check_strict(flags: dict):
    """Return list of missing lock ids, or None when all answered.
    Caller decides whether to abort."""
    miss = missing(flags)
    if not miss:
        return None
    return [lk["id"] for lk in miss]
