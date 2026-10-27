#!/usr/bin/env python3
"""Generate short video clips from storyboard.

Uses image reference mode when URLs are available (from gen-storyboard.py).
Falls back to text mode if no URLs stored.

Audio reference (optional): if AGNES_TTS_GITHUB_REPO is configured in .env,
local TTS lines (videos/audio/line-*.mp3 from gen-tts.py) are uploaded to
that PUBLIC GitHub repo and passed as `audios` reference — the model then
animates speaking mouths roughly in sync with the line audio. Without it,
videos are generated image-only (mouths not synced to dialogue).

Multi-key parallel (optional): set AGNESAI_API_KEYS in .env to generate clips
in parallel — one worker thread per key, each keeping its own 65s submit
rhythm. Entries accept an optional per-key platform override:

    AGNESAI_API_KEYS=sk-domestic,sk-intl@https://apihub.agnes-ai.com/v1
                     ^^^^^^^^^ default AGNESAI_BASE_URL   ^^^^^^^^^^^^^
                     ^^^^^^^^^^^^^ explicit base URL (international platform)

Without AGNESAI_API_KEYS, generation is serial on AGNESAI_API_KEY.
Note: the server-side video queue is global PER PLATFORM; extra keys speed up
the serial 65s chain and mix platforms (domestic + international in parallel),
but cannot exceed each platform's own queue cap.

Rate limit (agnes-video-2.5-flash):
  - 1 次/分钟（每次提交间隔 >= 65s，按 key 独立计算）
  - 图片参考最多 5 张
  - 音频参考最多 3 段
  - 不支持视频参考
  - size 固定 720P
  - 时长 4-12s

Batch status (breakpoint resume): each round writes
scripts/<project>-video-status.json with per-slot status {success,
error(+reason), pending}; rerun with --retry-failed to only redo
failed slots.

Shotlist mode (总导演): with --shotlist, work per SHOT from
scripts/<project>-shotlist.json (gen-shotlist.py): clips are named
scene-<shot>.mp4 so merge-videos.py and the image-URL refs
(scene-<shot> from gen-storyboard.py --shotlist) keep working.

Usage:
    python gen-video.py "项目名" [--scene N] [--duration 5]
    python gen-video.py "项目名" --shotlist
    python gen-video.py "项目名" --retry-failed
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_env import API_KEY, API_BASE_URL, PROJECT_ROOT
from track import track_file

VIDEO_INTERVAL_SEC = 65


def _video_submit_url(base: str) -> str:
    """POST endpoint for creating video tasks (base is the /v1 OpenAI-style root)."""
    return base.rstrip("/") + "/videos"


def _video_poll_url(base: str) -> str:
    """Task-poll endpoint: sibling of /v1 on the same host (e.g. .../agnesapi)."""
    host = base.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3]
    return host.rstrip("/") + "/agnesapi"


def validate_duration(seconds: str) -> str:
    s = int(seconds)
    if s < 4:
        print(f"⚠️  时长 {s}s < 4s，自动调整为 4s")
        return "4"
    if s > 12:
        print(f"⚠️  时长 {s}s > 12s，自动调整为 12s")
        return "12"
    return str(s)


def load_image_urls(project: str) -> dict:
    """Load stored image URLs from gen-storyboard output."""
    urls_file = PROJECT_ROOT / project / "scripts" / f"{project}-image-urls.json"
    if urls_file.exists():
        return json.loads(urls_file.read_text(encoding="utf-8"))
    return {}


def load_video_status(project: str) -> dict:
    """Load per-slot status ledger written by a previous gen-video run."""
    f = PROJECT_ROOT / project / "scripts" / f"{project}-video-status.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("slots", {})
        except Exception:
            return {}
    return {}


def _git(args: list, cwd=None, timeout=180) -> subprocess.CompletedProcess:
    """Run git: try the direct route first (explicitly clearing any stale
    system/registry proxy, which may point at a dead proxy), then fall back
    to the optional AGNES_GIT_PROXY / AGNES_GIT_SSL settings."""
    plain = subprocess.run(["git", "-c", "http.proxy=", "-c", "https.proxy="] + args,
                           cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if plain.returncode == 0:
        return plain
    proxy = os.environ.get("AGNES_GIT_PROXY", "").strip()
    ssl_backend = os.environ.get("AGNES_GIT_SSL", "").strip()
    if proxy or ssl_backend:
        cmd = ["git"]
        if proxy:
            cmd += ["-c", f"http.proxy={proxy}", "-c", f"https.proxy={proxy}"]
        if ssl_backend:
            cmd += ["-c", f"http.sslBackend={ssl_backend}"]
        cmd += args
        fallback = subprocess.run(cmd, cwd=cwd, capture_output=True,
                                  text=True, timeout=timeout)
        if fallback.returncode == 0:
            return fallback
    return plain


def upload_tts_audio(project: str, audio_files: list) -> dict:
    """Upload TTS mp3s to the configured public GitHub repo, return {name: raw_url}.

    Config (.env / env vars):
      AGNES_TTS_GITHUB_REPO  owner/repo  (public repo Agnes servers can fetch)
      AGNES_TTS_REPO_BRANCH  default "main"
      AGNES_GIT_PROXY        optional http proxy for git operations
      AGNES_GIT_SSL          optional git ssl backend (e.g. "openssl")

    Without AGNES_TTS_GITHUB_REPO this is a no-op (image-only references).
    On any failure it prints a warning and returns {} so video generation
    still proceeds with image references.
    """
    repo = os.environ.get("AGNES_TTS_GITHUB_REPO", "").strip()
    if not repo or "/" not in repo:
        return {}
    branch = os.environ.get("AGNES_TTS_REPO_BRANCH", "main").strip() or "main"
    cache = PROJECT_ROOT / "_tts-repo"

    if cache.exists():
        _git(["pull", "-q"], cwd=cache)  # best effort
    else:
        r = _git(["clone", "--depth", "1", "-b", branch,
                  f"https://github.com/{repo}.git", str(cache)])
        if r.returncode != 0:
            print(f"   ⚠️  TTS 仓库克隆失败（{r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '未知错误'}），本次仅用图片参考")
            return {}

    repo_proj_dir = cache / project
    repo_proj_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    for a in audio_files:
        dest = repo_proj_dir / a.name
        if not dest.exists() or dest.stat().st_size != a.stat().st_size:
            shutil.copy2(a, dest)
            changed = True
    if changed:
        _git(["add", "-A"], cwd=cache)
        r = _git(["diff", "--cached", "--quiet"], cwd=cache)
        if r.returncode != 0:  # staged changes exist
            _git(["-c", "user.name=manju-studio", "-c", "user.email=manju-studio@local",
                  "commit", "-q", "-m", f"{project}: update TTS audio references"], cwd=cache)
            p = _git(["push", "-q", "origin", branch], cwd=cache, timeout=300)
            if p.returncode != 0:
                print(f"   ⚠️  TTS 推送失败（{p.stderr.strip().splitlines()[-1] if p.stderr.strip() else '未知错误'}），本次仅用图片参考")
                return {}
        print(f"   📤  已上传 {len(audio_files)} 段 TTS → github.com/{repo}/{project}/")

    base = f"https://raw.githubusercontent.com/{repo}/{branch}/{project}/"
    urls = {a.name: base + a.name for a in audio_files}

    # Agnes rejects video tasks with HTTP 400 when an `audios` URL is not
    # fetchable; GitHub raw can lag a push by 30-60s. Verify reachability
    # before handing URLs to the model, fall back to image-only otherwise.
    proxy = os.environ.get("AGNES_GIT_PROXY", "").strip()
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request
    broken = []
    for u in urls.values():
        ok = False
        for _ in range(3):
            try:
                with opener.open(u, timeout=30) as r:
                    ok = (r.status == 200)
                if ok:
                    break
            except Exception:
                time.sleep(20)
        if not ok:
            broken.append(u)
    if broken:
        print(f"   ⚠️  {len(broken)} 个 TTS raw URL 暂不可达（GitHub 传播延迟/网络），本次仅用图片参考")
        for u in broken[:3]:
            print(f"      - {u}")
        return {}
    return urls


def submit_video(prompt: str, image_refs: list = None,
                 seconds: str = "5", aspect_ratio: str = "16:9",
                 audios: list = None, api_key: str = None,
                 base_url: str = None) -> str:
    """Submit video task. Uses reference mode if image_refs/audios provided.

    audios: up to 3 public URLs (e.g. TTS lines) passed as `audios` reference;
    reference them in the prompt with <Audio 1>, <Audio 2>, ...
    api_key / base_url: override the default AGNESAI_API_KEY / AGNESAI_BASE_URL
    (multi-key multi-platform mode, see load_api_pairs).
    """
    key = api_key or API_KEY
    base = (base_url or API_BASE_URL).rstrip("/")
    # Validate: max 5 image refs, max 3 audio refs
    refs = (image_refs or [])[:5]
    auds = (audios or [])[:3]

    body = {
        "model": "agnes-video-2.5-flash",
        "prompt": prompt,
        "seconds": seconds,
        "size": "720P",
        "aspect_ratio": aspect_ratio,
    }

    if refs or auds:
        body["mode"] = "reference"
        if refs:
            body["images"] = refs
        if auds:
            body["audios"] = auds
    else:
        body["mode"] = "text"

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        _video_submit_url(base), data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=120).read()
    return json.loads(resp)["video_id"]


def poll_video(video_id: str, timeout=600, interval=30, api_key: str = None,
               base_url: str = None) -> str:
    key = api_key or API_KEY
    base = (base_url or API_BASE_URL).rstrip("/")
    elapsed = 0
    while elapsed < timeout:
        url = f"{_video_poll_url(base)}?video_id={video_id}&model_name=agnes-video-2.5-flash"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        resp = urllib.request.urlopen(req, timeout=60).read()
        result = json.loads(resp)
        status = result.get("status", "")
        progress = result.get("progress", 0)
        print(f"     status={status} progress={progress}%")
        if status == "completed":
            return result.get("url", "")
        if status == "failed":
            raise RuntimeError(f"Video failed: {result.get('error')}")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Video {video_id} not ready after {timeout}s")


def retry_api(func, max_retries=4):
    """Retry a submit on 429 (rate limit) and 503 (video_queue_full) with backoff.

    The Agnes video queue is shared and fills quickly at peak hours; waiting
    a few in-script retries (65s, 130s, 195s) usually beats the queue surge.
    If all retries fail the HTTPError is re-raised and the caller decides
    (main() fast-fails with exit code 3 so an outer runner can re-run later —
    completed scenes are skipped, so re-running is idempotent).
    """
    for attempt in range(max_retries):
        try:
            return func()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries - 1:
                wait = 65 * (attempt + 1)
                reason = "429 限流" if e.code == 429 else "503 视频队列已满"
                print(f"     ⏱  {reason}，等待 {wait}s 后重试 ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise


def load_api_pairs() -> list:
    """API key/platform pairs for video generation.

    AGNESAI_API_KEYS entries (comma-separated): "sk-..." or "sk-...@baseURL".
    An entry without @ uses the default AGNESAI_BASE_URL (domestic platform).
    This lets one run mix domestic + international keys/platforms in parallel.
    Without AGNESAI_API_KEYS: a single pair (AGNESAI_API_KEY, AGNESAI_BASE_URL).
    """
    raw = os.environ.get("AGNESAI_API_KEYS", "").strip()
    pairs = []
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if "@" in entry:
                key, base = entry.split("@", 1)
                pairs.append((key.strip(), base.strip().rstrip("/")))
            else:
                pairs.append((entry, API_BASE_URL))
    if not pairs:
        pairs = [(API_KEY, API_BASE_URL)] if API_KEY else []
    return pairs


def _run_serial(pair, work_items, project, duration, aspect_ratio, slots=None):
    """Single-key path: process scenes one by one (65s apart).
    pair = (api_key, base_url). If slots is provided, each slot's final
    status is recorded there (success / error+reason / pending)."""
    api_key, base_url = pair
    if slots is None:
        slots = {}
    total = len(work_items)
    stopped = False
    for i, item in enumerate(work_items):
        sid = item["sid"]
        out_file = item["out_file"]
        refs, prompt, scene_audios = item["refs"], item["prompt"], item["audios"]
        slot = slots.setdefault(str(sid), {"status": "pending"})

        print(f"  🎥 [{i+1}/{total}] scene-{sid}: {item['title'][:30]}...")
        try:
            video_id = retry_api(
                lambda: submit_video(prompt, refs, duration, aspect_ratio,
                                     scene_audios, api_key, base_url)
            )
            print(f"     submitted: {video_id} ({len(refs)} refs, {len(scene_audios)} audio)")
            video_url = poll_video(video_id, api_key=api_key, base_url=base_url)
            mp4_data = urllib.request.urlopen(video_url).read()
            out_file.write_bytes(mp4_data)
            track_file(project, "video", str(out_file), f"视频 scene-{sid}", f"duration={duration}s")
            slot.update({"status": "success", "file": out_file.name})
            print(f"     ✅ {out_file.name} ({len(mp4_data)//1024}KB)")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                reason = "429 限流 / 503 视频队列已满，重试后仍失败"
                slot.update({"status": "error", "reason": reason})
                print(f"     ❌ scene-{sid} 提交失败 (HTTP {e.code})，{reason}")
                print("⚠️  Agnes 视频队列已满，本轮停止。稍后重新运行本脚本即可续跑（已完成的片段会自动跳过）。")
                stopped = True
                break
            if e.code == 400:
                body = e.read().decode("utf-8", "replace")[:300]
                slot.update({"status": "error", "reason": f"HTTP 400: {body}"})
                print(f"     ❌ scene-{sid} 提交被拒 (HTTP 400): {body}")
                print("⚠️  400 是永久性参数/参考校验失败（常见：分镜图或 TTS 的参考 URL 不可达），本轮停止。修正参考源后重跑。")
                stopped = True
                break
            reason = f"HTTP {e.code}: {e.reason}"
            slot.update({"status": "error", "reason": reason})
            print(f"     ❌ 提交失败 (HTTP {e.code}): {e.reason}（记录后继续下一段）")
        except OSError as e:
            slot.update({"status": "error", "reason": f"网络瞬时故障: {str(e)[:60] or '连接中断'}"})
            print(f"     ⏱  网络瞬时故障（{str(e)[:60] or '连接中断'}），本轮停止")
            print("⚠️  网络不稳或队列繁忙。稍后重新运行本脚本即可续跑（已完成的片段会自动跳过）。")
            stopped = True
            break
        except Exception as e:
            slot.update({"status": "error", "reason": str(e)[:300]})
            print(f"     ❌ 失败: {e}（记录后继续下一段）")

        if stopped:
            break
        if i < total - 1:
            print(f"     ⏱  等待 {VIDEO_INTERVAL_SEC}s (剩余 {total - i - 1} 个)...")
            time.sleep(VIDEO_INTERVAL_SEC)
    return stopped


def _run_parallel(api_pairs, work_items, project, duration, aspect_ratio, slots=None):
    """One worker thread per key/platform pair; shared scene queue, per-key
    65s pacing. Works across platforms (domestic + international keys mix).

    A scene that hits a persistent 429/503 or a network error is released
    back to the queue and the worker cools down 90s while other workers
    keep moving. A 25-minute no-progress watchdog exits the round (exit 3)
    so an outer retry loop can restart it.
    If slots is provided, per-slot final status is recorded there."""
    if slots is None:
        slots = {}
    lock = threading.Lock()
    state = {"claimed": {}, "done": 0, "last_progress": time.time(), "fatal": False}
    for w in work_items:
        state["claimed"][id(w)] = False

    def _rec(item, status, reason=None, file_=None):
        slot = slots.setdefault(str(item["sid"]), {"status": "pending"})
        slot["status"] = status
        if reason:
            slot["reason"] = reason
        if file_:
            slot["file"] = file_

    def worker(idx, pair):
        key, base_url = pair
        last_submit = 0.0
        while True:
            with lock:
                item = next((w for w in work_items
                             if not w["out_file"].exists()
                             and not state["claimed"][id(w)]), None)
                if item is None:
                    return
                state["claimed"][id(item)] = True
            sid = item["sid"]
            tag = f"[W{idx}] scene-{sid}"

            wait = last_submit + VIDEO_INTERVAL_SEC - time.time()
            if wait > 0:
                time.sleep(wait)
            last_submit = time.time()

            print(f"  🎥 {tag} 开始 ({len(item['refs'])} refs, {len(item['audios'])} audio) {base_url}")
            try:
                video_id = retry_api(
                    lambda: submit_video(item["prompt"], item["refs"], duration,
                                         aspect_ratio, item["audios"], key, base_url)
                )
                print(f"     submitted: {video_id} ({len(item['refs'])} refs)")
                video_url = poll_video(video_id, api_key=key, base_url=base_url)
                mp4_data = urllib.request.urlopen(video_url).read()
                item["out_file"].write_bytes(mp4_data)
                with lock:
                    track_file(project, "video", str(item["out_file"]),
                               f"视频 scene-{sid}", f"duration={duration}s")
                    state["done"] += 1
                    state["last_progress"] = time.time()
                    _rec(item, "success", file_=item["out_file"].name)
                print(f"     ✅ {tag} {item['out_file'].name} ({len(mp4_data)//1024}KB)")
            except urllib.error.HTTPError as e:
                with lock:
                    state["claimed"][id(item)] = False
                if e.code in (429, 503):
                    print(f"     ⏱ {tag} 重试后仍 HTTP {e.code}，worker 稍后再试")
                    time.sleep(90)
                elif e.code == 400:
                    body = e.read().decode("utf-8", "replace")[:300]
                    print(f"     ❌ {tag} 提交被拒 (HTTP 400): {body}")
                    print("⚠️  400 为永久性错误（参考 URL 不可达/参数校验失败），停止本轮。"
                          "修正参考源后重跑。")
                    with lock:
                        state["fatal"] = True
                        _rec(item, "error", reason=f"HTTP 400: {body}")
                    return
                else:
                    with lock:
                        _rec(item, "error", reason=f"HTTP {e.code}: {e.reason}")
                    print(f"     ❌ {tag} 提交失败 (HTTP {e.code}): {e.reason}（记录后稍后再试）")
                    time.sleep(30)
            except OSError as e:
                with lock:
                    state["claimed"][id(item)] = False
                    _rec(item, "error", reason=f"网络瞬时故障: {str(e)[:60] or '连接中断'}")
                print(f"     ⏱ {tag} 网络瞬时故障（{str(e)[:60] or '连接中断'}），worker 稍后再试")
                time.sleep(90)
            except Exception as e:
                with lock:
                    state["claimed"][id(item)] = False
                    _rec(item, "error", reason=str(e)[:300])
                print(f"     ❌ {tag} 失败: {e}（记录后稍后再试）")
                time.sleep(30)

    threads = []
    for i in range(len(api_pairs)):
        t = threading.Thread(target=worker, args=(i, api_pairs[i]),
                             name=f"video-worker-{i}")
        t.daemon = True
        t.start()
        threads.append(t)
        time.sleep(1)  # stagger starts so first submits don't pile into one second

    while any(t.is_alive() for t in threads):
        time.sleep(10)
        with lock:
            stall = time.time() - state["last_progress"]
            done = state["done"]
            fatal = state["fatal"]
        if fatal:
            missing = sum(1 for w in work_items if not w["out_file"].exists())
            print(f"⚠️  检测到永久性提交失败 (400)，本轮停止。剩余 {missing} 段。")
            break
        if stall > 1500:
            missing = sum(1 for w in work_items if not w["out_file"].exists())
            print(f"⚠️  全部 worker 已停滞 {int(stall//60)} 分钟（队列满/网络），"
                  f"本轮停止。剩余 {missing} 段，稍后重新运行本脚本即可续跑。")
            break
    _ = done


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    project = sys.argv[1]
    scene_filter = None
    duration = None
    use_shotlist = False
    retry_failed = False
    if "--scene" in sys.argv:
        scene_filter = int(sys.argv[sys.argv.index("--scene") + 1])
    if "--duration" in sys.argv:
        duration = validate_duration(sys.argv[sys.argv.index("--duration") + 1])
    if "--shotlist" in sys.argv:
        use_shotlist = True
    if "--retry-failed" in sys.argv:
        retry_failed = True

    proj_dir = PROJECT_ROOT / project
    video_dir = proj_dir / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    img_dir = proj_dir / "images"
    script_dir = proj_dir / "scripts"

    scripts = list(script_dir.glob(f"{project}-script.json"))
    script = json.loads(scripts[0].read_text(encoding="utf-8")) if scripts else {}
    scenes = script.get("scenes", [])
    config = script.get("config", {})

    # ---- shotlist mode: work per SHOT (gen-shotlist.py output) ----
    shotlist = None
    if use_shotlist:
        sl_file = script_dir / f"{project}-shotlist.json"
        if not sl_file.exists():
            print(f"[ERROR] 未找到 shotlist: {sl_file}", file=sys.stderr)
            print(f"       先运行 → python script-writer/examples/gen-shotlist.py \"{project}\"")
            sys.exit(1)
        shotlist = json.loads(sl_file.read_text(encoding="utf-8"))
        shots = shotlist.get("shots", [])
        if scene_filter:
            shots = [s for s in shots if s.get("shot") == scene_filter]
        notes = str(shotlist.get("director_notes", ""))[:120]
        scenes = []
        for s in shots:
            desc = f"{s.get('frame', '')}. Camera: {s.get('camera', '')}"
            if notes:
                desc += f" Continuity: {notes}"
            scenes.append({"scene_id": s.get("shot", 0), "title": s.get("title", ""),
                           "description": desc,
                           "description_zh": f"{s.get('title', '')} | {s.get('camera', '')}",
                           "seconds": s.get("seconds")})
        if duration is None:
            duration = validate_duration(str(shotlist.get("seconds_default",
                              config.get("video_duration", "5"))))

    if duration is None:
        duration = validate_duration(str(config.get("video_duration", "5")))
    aspect_ratio = config.get("aspect_ratio", "16:9")

    # Load stored image URLs (for reference mode)
    image_urls = load_image_urls(project)
    has_urls = len(image_urls) > 0
    mode_label = "reference (图生视频)" if has_urls else "text (文生视频)"

    # TTS audio references: upload local TTS lines (if AGNES_TTS_GITHUB_REPO
    # is configured) and let the model generate speaking mouths in sync with them
    audio_dir = video_dir / "audio"
    tts_audio_files = sorted(audio_dir.glob("line-*.mp3"))
    tts_urls = upload_tts_audio(project, tts_audio_files) if tts_audio_files else {}
    if tts_audio_files and not tts_urls:
        mode_label += " + 配音(未上传，仅图片参考)"
    elif tts_urls:
        mode_label += f" + {len(tts_urls)} 段配音参考"

    if scene_filter and not use_shotlist:
        scenes = [s for s in scenes if s.get("scene_id") == scene_filter]
    if not scenes:
        scene_files = sorted(img_dir.glob("scene-*.png"))
        scenes = [{"scene_id": int(f.stem.split("-")[1]), "title": f.stem,
                   "description": f.stem, "description_zh": f.stem} for f in scene_files]

    # ---- breakpoint resume: --retry-failed only redoes failed slots ----
    status_file = script_dir / f"{project}-video-status.json"
    if retry_failed:
        prev_slots = load_video_status(project)
        bad = {k for k, v in prev_slots.items() if v.get("status") != "success"}
        kept = [s for s in scenes
                if str(s.get("scene_id")) in bad
                or not (video_dir / f"scene-{s.get('scene_id')}.mp4").exists()]
        if not kept:
            print("✅ status 中无失败槽（或视频均已生成），无需重跑。")
            sys.exit(0)
        scenes = kept
        print(f"🔁 --retry-failed: 仅重做 {len(kept)} 个失败/缺失槽")

    total = len(scenes)
    api_pairs = load_api_pairs()
    n_keys = len(api_pairs)
    mode_label += " | shotlist 镜级模式" if use_shotlist else ""
    print(f"🎬 生成 {total} 个视频片段")
    print(f"   模式: {mode_label}")
    print(f"   Key: {n_keys} 个（{'并行' if n_keys > 1 else '串行'}）")
    print(f"   时长: {duration}s/段 | 间隔: {VIDEO_INTERVAL_SEC}s")
    est_min = max(1, total // max(1, n_keys)) * 5
    print(f"   预计总耗时: ~{est_min} 分钟\n")

    # ---- build per-scene work items (refs / prompt / audio refs) ----
    work_items = []
    slots = {}
    for scene in scenes:
        sid = scene.get("scene_id", 0)
        out_file = video_dir / f"scene-{sid}.mp4"
        if out_file.exists():
            slots[str(sid)] = {"status": "success", "file": out_file.name}
            print(f"  ⏭  scene-{sid} 已存在，跳过")
            continue

        refs = []
        if has_urls:
            scene_key = f"scene-{sid}"
            if scene_key in image_urls:
                refs.append(image_urls[scene_key])
            char_refs = [v for k, v in image_urls.items() if k.startswith("char-")]
            refs.extend(char_refs[:4])  # Keep total <= 5
            refs = refs[:5]

        desc_en = scene.get("description", "")
        desc_zh = scene.get("description_zh", "")
        style = config.get("style", "动画")
        style_word = {"动画": "anime", "写实": "cinematic", "水墨": "ink wash",
                      "赛博朋克": "cyberpunk", "二次元": "2D anime"}.get(style, "anime")
        prompt = f"{style_word} style, smooth animation. {desc_en}. {desc_zh[:60]}"

        scene_audios = [tts_urls[f"line-{sid}-{n}.mp3"]
                        for n in range(1, 4) if f"line-{sid}-{n}.mp3" in tts_urls]
        if scene_audios:
            markers = " ".join(f"<Audio {k+1}>" for k in range(len(scene_audios)))
            prompt += (f" The character is speaking; the mouth moves naturally, "
                       f"in sync with the reference audio {markers}.")

        work_items.append({"sid": sid, "out_file": out_file, "refs": refs,
                          "prompt": prompt, "audios": scene_audios,
                          "title": scene.get("title", "")})
        slots[str(sid)] = {"status": "pending"}

    if not work_items:
        print(f"\n✅ 所有 {total} 个片段已存在，无需生成。")
        print(f"\n✅ 视频目录: {video_dir}/")
        print("\n下一步：")
        print(f"  [1] 拼接完整视频 → python merge-videos.py \"{project}\"")
        print(f"  [2] 重新生成某场景 → python gen-video.py \"{project}\" --scene N")
        print(f"  [3] 完成 🎬")
        return

    # ---- dispatch: serial (single key) or parallel (multi-key/multi-platform) ----
    api_pairs = load_api_pairs()
    if not api_pairs:
        print("\n[ERROR] 没有可用的 API Key：请在 .env 中配置 AGNESAI_API_KEY（参考 .env.example）", file=sys.stderr)
        sys.exit(1)
    if len(api_pairs) <= 1:
        print(f"\n开始串行生成 {len(work_items)} 个片段（单 key）...\n")
        _run_serial(api_pairs[0] if api_pairs else None, work_items,
                    project, duration, aspect_ratio, slots)
    else:
        platforms = sorted({b for _, b in api_pairs})
        plat_label = "、".join(p.split("/")[2] for p in platforms)
        print(f"\n开始并行生成 {len(work_items)} 个片段（{len(api_pairs)} 个 key，"
              f"平台: {plat_label}，每个 worker 间隔 {VIDEO_INTERVAL_SEC}s）...\n")
        _run_parallel(api_pairs, work_items, project, duration, aspect_ratio, slots)

    # ---- write batch status ledger (merge with previous rounds) ----
    prev = load_video_status(project)
    merged = {**prev, **slots}
    status = {
        "project": project,
        "artifact": "scene-{sid}.mp4",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "slots": merged,
    }
    status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    missing = [w["sid"] for w in work_items if not w["out_file"].exists()]
    if missing:
        n_err = sum(1 for v in slots.values() if v["status"] == "error")
        print(f"\n⚠️  本轮结束，仍缺 {len(missing)} 段: scene-{', scene-'.join(map(str, missing))}（{n_err} 槽已记录失败原因）")
        print(f"⚠️  稍后重新运行并加 --retry-failed 即可只补失败项：")
        print(f"   python gen-video.py \"{project}\" --retry-failed")
        sys.exit(3)

    print(f"\n✅ 视频生成完成，保存在 {video_dir}/")
    print("\n下一步：")
    print(f"  [1] 拼接完整视频 → python merge-videos.py \"{project}\"")
    print(f"  [2] 重新生成某场景 → python gen-video.py \"{project}\" --scene N")
    print(f"  [3] 完成 🎬")


if __name__ == "__main__":
    main()
