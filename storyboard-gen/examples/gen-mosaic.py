#!/usr/bin/env python3
"""Build a contact-sheet (mosaic) overview of generated images.

Takes a grid (default 2 columns) of scene/character images and produces
ONE overview image for the human-review step ("展示图片请确认" — one image
instead of scrolling dozens). Pure ffmpeg, no new dependencies.

Cell order = numeric scene id order (scene-1, scene-2, ...).

Usage:
    python gen-mosaic.py "项目名" [--kind scene|char|all] [--cols 2]
                         [--cell 720x405] [--out 路径]
    --kind  scene: images/scene-*.png (默认) | char: character-*.png | all: 两者
    --cell  单格尺寸 WxH（默认 720x405 = 16:9；竖屏项目用 405x720）
    --out   默认 images/<项目>-overview.jpg
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_env import PROJECT_ROOT
from track import track_file

BLACK_IMG_LIMIT = 10 * 1024  # 小于 10KB 的 PNG 基本是黑图占位


def _num(f: Path) -> int:
    m = re.search(r"(\d+)", f.stem)
    return int(m.group(1)) if m else 0


def collect(img_dir: Path, kind: str):
    """Return (files sorted by numeric id, black/placeholder files skipped)."""
    if kind == "char":
        raw = list(img_dir.glob("character-*.png"))
    elif kind == "all":
        raw = list(img_dir.glob("character-*.png")) + list(img_dir.glob("scene-*.png"))
    else:
        raw = list(img_dir.glob("scene-*.png"))
    files = [f for f in raw if f.stat().st_size >= BLACK_IMG_LIMIT]
    skipped = sorted((f for f in raw if f not in files), key=_num)
    return sorted(files, key=_num), skipped


def _stack(parts, labels, op, pfx):
    """Chain 2-input hstack/vstack filters over a label list.

    ffmpeg's hstack/vstack accept at most 2 inputs each, so labels are
    combined pairwise into intermediate outputs (named pfx0, pfx1, ...
    to stay unique across calls). Returns the final label.
    """
    if len(labels) == 1:
        return labels[0]
    acc = []
    i = 0
    while i < len(labels):
        if i + 1 < len(labels):
            out = f"[{pfx}{i // 2}]"
            parts.append(f"{labels[i]}{labels[i+1]}{op}={out}")
            acc.append(out)
            i += 2
        else:
            acc.append(labels[i])  # odd tail passes through
            i += 1
    if len(acc) == 1:
        return acc[0]
    last = acc[0]
    for j in range(1, len(acc)):
        out = f"[{pfx}{j + 100}]"
        parts.append(f"{last}{acc[j]}{op}={out}")
        last = out
    return last


def build_filter(n: int, cols: int, cell: str) -> tuple:
    """Build the ffmpeg filter_complex for an n-input, cols-wide grid.

    Rows are hstacks of their cells; the row outputs are vstacked into the
    final grid. The last row (if shorter than `cols`) is padded with black
    cells so every row has identical width (vstack requirement).
    Returns (filter_complex, final_label).
    """
    w, h = (int(x) for x in cell.split("x"))
    parts = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:({w}-iw)/2:({h}-ih)/2,setsar=1[v{i}]"
        )
    row_labels = []
    r = 0
    for start in range(0, n, cols):
        count = min(cols, n - start)
        if count < cols:
            # pad the short last row with black cells to full width
            labels = [f"[v{start + j}]" for j in range(count)]
            for k in range(cols - count):
                parts.append(f"color=c=black:s={w}x{h}:d=1[b{r}{k}]")
                labels.append(f"[b{r}{k}]")
            row_label = _stack(parts, labels, "hstack", pfx=f"h{r}")
        elif count == 1:
            row_label = f"[v{start}]"
        else:
            chunk = [f"[v{start + j}]" for j in range(count)]
            row_label = _stack(parts, chunk, "hstack", pfx=f"h{r}")
        row_labels.append(row_label)
        r += 1
    if len(row_labels) == 1:
        return ";".join(parts), row_labels[0]
    final = _stack(parts, row_labels, "vstack", pfx="f")
    return ";".join(parts), final


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    project = sys.argv[1]
    kind, cols, cell, out = "scene", 2, "720x405", None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--kind":
            kind = args[i + 1]; i += 2
        elif args[i] == "--cols":
            cols = int(args[i + 1]); i += 2
        elif args[i] == "--cell":
            cell = args[i + 1]; i += 2
        elif args[i] == "--out":
            out = args[i + 1]; i += 2
        else:
            i += 1

    if shutil.which("ffmpeg") is None:
        print("[ERROR] 未找到 ffmpeg（mosaic 需要）。安装: https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    img_dir = PROJECT_ROOT / project / "images"
    files, skipped = collect(img_dir, kind)
    if not files:
        print(f"[ERROR] {img_dir} 中没有可用图片（kind={kind}）", file=sys.stderr)
        sys.exit(1)
    if skipped:
        print(f"⚠️  跳过 {len(skipped)} 张疑似黑图占位: "
              f"{', '.join(f.name for f in skipped)}")

    out = Path(out) if out else img_dir / f"{project}-overview.jpg"

    filter_complex, out_label = build_filter(len(files), cols, cell)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for f in files:
        cmd += ["-i", str(f)]
    cmd += ["-filter_complex", filter_complex,
            "-map", out_label, "-frames:v", "1", "-q:v", "2", str(out)]

    print(f"🧩 总览拼图: {len(files)} 张 → {out.name}（{cols} 列, 单格 {cell}）")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERROR] ffmpeg 失败:\n{r.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    track_file(project, "image", str(out), "总览拼图",
               f"kind={kind},n={len(files)},cols={cols}")
    print(f"✅ 总览已保存: {out}")
    print("\n请确认画面质量与角色一致性：")
    print(f"  [1] 通过 → 生成视频 → python video-composer/examples/gen-video.py \"{project}\"")
    print(f"  [2] 某镜不行 → python gen-storyboard.py \"{project}\" --scene N 重做该槽")


if __name__ == "__main__":
    main()
