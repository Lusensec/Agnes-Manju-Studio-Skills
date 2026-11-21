"""Seven-segment video prompt builder (borrowed structure from manju-laoli 七段式).

Instead of one free-form sentence, the video prompt is composed of 7 labelled
segments so the model gets explicit 景别/动作/对白/情绪/运镜/声音/转场 cues.
Empty segments are omitted (keeps the prompt tight for Agnes).

Segments:
  [SHOT]   景别/镜头 (shot size + framing)
  [ACTION] 主体动作 (one primary action per clip)
  [DIALOG] 对白/旁白 (optional; TTS-able)
  [MOOD]   情绪/表演 (emotion + performance)
  [CAMERA] 运镜 (camera move)
  [SOUND]  声音 (ambient / SFX cues)
  [CUT]    转场/尾帧 (outro / freeze-last-frame for segment splicing)

The 段缝衔接 (P1-c) writes a CUE into [CUT] so the last second can be
frozen and reused as the next clip's first frame.
"""


def build_seven_segment(desc_en, desc_zh, style_word, dialogues=None,
                        camera=None, mood=None, sound=None,
                        freeze_last=False, combat=False) -> str:
    """Compose the seven-segment prompt. All optional args may be None/empty.
    `dialogues` is either a string or a list of strings; list items are joined
    with ' / ' (a bare string is used verbatim)."""
    segs = []
    # [SHOT] — derive a light framing cue from style
    segs.append(f"[SHOT] {style_word} style, clean composition")
    # [ACTION]
    action = (desc_en or desc_zh or "").strip()
    if combat:
        action = f"{action} | combat: one clear action + one reaction per beat, 2-3s granularity, no sandbag opponents"
    segs.append(f"[ACTION] {action}")
    # [DIALOG]
    if isinstance(dialogues, str):
        lines = dialogues.strip()
    elif dialogues:
        lines = " / ".join(d.strip() for d in dialogues if d and d.strip())
    else:
        lines = ""
    if lines:
        segs.append(f"[DIALOG] {lines}")
    # [MOOD]
    if mood:
        segs.append(f"[MOOD] {mood}")
    # [CAMERA]
    if camera:
        segs.append(f"[CAMERA] {camera}")
    else:
        segs.append("[CAMERA] smooth, single motivated move, no mid-clip cuts")
    # [SOUND]
    if sound:
        segs.append(f"[SOUND] {sound}")
    else:
        segs.append("[SOUND] subtle ambient bed matching the scene; no on-camera SFX unless specified")
    # [CUT]
    if freeze_last:
        segs.append("[CUT] end on a clean last frame: all characters hold pose & blocking, "
                    "action fully still for the final second (freeze-frame friendly), "
                    "so it can be reused as the next clip's first frame")
    else:
        segs.append("[CUT] natural in-clip resolution, no hard cut mid-action")
    return " ".join(segs)
