"""Multi-episode continuity ledger (borrowed from manju-laoli 跨集连续性台账).

A 漫剧 serial cannot afford characters/props/locations to "vanish" between
episodes. This module keeps a per-project ledger at:

    <project>/scripts/<project>-series.json

It records, across episodes:
  - characters  每个角色的外形/服装/状态（含"当前集持有道具"）
  - locations   场景空间事实（固定物/光线基调）
  - open_loops  未回收的伏笔（setup → 计划 payoff 集）
  - last_state   每集结尾的接续状态（供下一集首镜承接，配合 --splice）

API:
    ledger_path(project) -> Path
    load(project) -> dict   (empty skeleton if absent)
    save(project, ledger)
    record_episode(project, ep_no, script)   # 从剧本 JSON 更新台账
    handoff_brief(project) -> str            # 给下一集 write-script 注入的上下文
"""
import json
from datetime import datetime, timezone
from pathlib import Path

sys_path_hack = None  # load_env import handled by caller via sys.path


def _ledger_path(project: str) -> Path:
    # resolve PROJECT_ROOT at call time (import lazily to keep module importable
    # for unit tests without a .env)
    from load_env import PROJECT_ROOT
    return PROJECT_ROOT / project / "scripts" / f"{project}-series.json"


def empty_ledger(project: str) -> dict:
    return {
        "project": project,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "episodes": [],
        "characters": {},
        "locations": {},
        "open_loops": [],
        "last_state": {},
    }


def load(project: str) -> dict:
    p = _ledger_path(project)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return empty_ledger(project)


def save(project: str, ledger: dict) -> None:
    p = _ledger_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def record_episode(project: str, ep_no: int, script: dict) -> dict:
    """Update the ledger from a single episode's script JSON.

    - characters: upsert by name, store description/personality + per-episode costume
    - locations: upsert by name, store description
    - open_loops: collect from script["open_loops"] if present (forward-looking setups)
    - last_state: capture the final scene's key entities for handoff
    """
    ledger = load(project)
    for c in script.get("characters", []):
        name = c.get("name")
        if not name:
            continue
        rec = ledger["characters"].setdefault(name, {
            "description": c.get("description", ""),
            "personality": c.get("personality", ""),
            "costumes": [],
        })
        rec["description"] = c.get("description", rec["description"])
        for cs in script.get("costumes", []):
            if cs.get("character") == name and cs.get("name"):
                rec.setdefault("costumes", []).append(cs.get("name"))
    for loc in script.get("locations", []):
        n = loc.get("name")
        if n:
            ledger["locations"].setdefault(n, {"description": loc.get("description", "")})

    # open loops: 本集埋下、计划后续回收
    for loop in script.get("open_loops", []):
        ledger["open_loops"].append({
            "ep_setup": ep_no,
            "desc": loop if isinstance(loop, str) else json.dumps(loop, ensure_ascii=False),
            "payoff_ep": (loop.get("payoff_ep") if isinstance(loop, dict) else None),
        })

    scenes = script.get("scenes", [])
    if scenes:
        last = scenes[-1]
        ledger["last_state"] = {
            "ep": ep_no,
            "scene_id": last.get("scene_id"),
            "title": last.get("title", ""),
            "location": last.get("location", ""),
            "on_screen": [d.get("character") for d in last.get("dialogue", []) if d.get("character")],
        }

    ledger["episodes"].append(ep_no)
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    save(project, ledger)
    return ledger


def handoff_brief(project: str) -> str:
    """Human/LLM-readable brief to prepend to the NEXT episode's write-script
    prompt: who's in what state, what costumes are locked, open loops to pay off,
    and the last-state to splice from."""
    ledger = load(project)
    lines = []
    if ledger.get("characters"):
        lines.append("角色外形基准（跨集锁定，不得改动）：")
        for name, rec in ledger["characters"].items():
            costumes = "、".join(rec.get("costumes", [])) or "（无登记服装）"
            lines.append(f"  - {name}：{rec.get('description','')}（当前服装: {costumes}）")
    if ledger.get("open_loops"):
        lines.append("未回收伏笔（本集需推进或回收）：")
        for lp in ledger["open_loops"][-10:]:
            pay = f" → 计划第{lp['payoff_ep']}集回收" if lp.get("payoff_ep") else ""
            lines.append(f"  - 第{lp['ep_setup']}集埋下: {lp['desc']}{pay}")
    ls = ledger.get("last_state")
    if ls:
        on_screen = "、".join(x for x in ls.get("on_screen", []) if x)
        lines.append(f"上一集（第{ls.get('ep')}集）结尾状态: 场景={ls.get('title')}, "
                     f"在场={on_screen or '（无）'} —— 本集首镜可承接此状态")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    proj = sys.argv[1]
    ledger = load(proj)
    print(f"连载台账: {proj}")
    print(f"  已完成集: {ledger.get('episodes', [])}")
    print(f"  角色({len(ledger.get('characters', {}))}): "
          + ", ".join(ledger.get("characters", {}).keys()))
    print(f"  未回收伏笔({len(ledger.get('open_loops', []))}):")
    for lp in ledger.get("open_loops", []):
        print(f"    - 第{lp.get('ep_setup')}集: {lp.get('desc')}")
    ls = ledger.get("last_state")
    if ls:
        print(f"  上集结尾: 第{ls.get('ep')}集 {ls.get('title')}（在场: "
              f"{', '.join(ls.get('on_screen', []) or [])}）")
