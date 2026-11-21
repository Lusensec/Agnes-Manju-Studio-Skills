"""Style-bible lock (borrowed from manju-laoli I-lock / director-param-library).

Turn a named director-style into a parameterized prompt block instead of a bare
adjective. Delivery layer stays human-name-free: the user picks a style by its
Chinese label, we emit a machine-friendly 参数块 (lighting/color/medium/lens/
motion/prohibited) that gets appended to image/video prompts.

Pick one by name (see list_styles). Returns a dict with:
  - "label"     中文风格名（展示用）
  - "block_en"  英文提示词块（直接拼进 frame / [SHOT]）
  - "block_zh"  中文说明（写进剧本 config，供人看）
  - "forbidden" 针对性禁项（写入提示词末尾的 "avoid:" 行）
"""

STYLES = {
    "新派武侠": {
        "label": "新派武侠（高反差硬光·冷蓝主调·实体化法术）",
        "block_en": ("new-school wuxia, high-contrast hard light, cool-blue key tone, "
                     "volumetric mist with visible light shafts, wide-angle low camera, "
                     "slight barrel distortion, solid materialized spell effects with weight, "
                     "60-120fps slow-mo mixed with fast cuts"),
        "block_zh": "高反差硬光、冷蓝主调、体积雾光柱、广角低机位、实体化法术、升格慢镜与快切交替",
        "forbidden": "avoid plastic 3D-render look, avoid even soft beauty lighting, avoid Q-version distortion",
    },
    "都市抽帧": {
        "label": "都市抽帧（霓虹暖黄·残影·狭窄空间贴身手持）",
        "block_en": ("urban noir, 24p drop-frame ghosting, neon pink and warm amber interplay, "
                     "tight narrow space with close handheld, foreground occlusion, "
                     "long-shutter motion blur, shallow depth of field"),
        "block_zh": "抽帧残影、霓虹粉与暖黄交错、狭窄空间贴身手持、前景遮挡、慢门拖影",
        "forbidden": "avoid clean wide open space, avoid flat even lighting, avoid static tripod feel",
    },
    "水墨写意": {
        "label": "水墨写意（留白·墨分五色·气韵流动）",
        "block_en": ("Chinese ink-wash painting, generous negative space, five shades of ink, "
                     "flowing qi-brush motion, muted mineral palette, paper grain, "
                     "no heavy outlines, atmospheric washes bleeding at edges"),
        "block_zh": "留白、墨分五色、气韵流动、矿物淡彩、宣纸肌理、无重描边、边缘晕染",
        "forbidden": "avoid saturated digital colors, avoid hard cel-shading, avoid realistic PBR textures",
    },
    "赛博夜城": {
        "label": "赛博夜城（霓虹冷紫·雨面反光·高科技低生活）",
        "block_en": ("cyberpunk night city, neon purple and cyan on wet asphalt, "
                     "high-tech low-life, reflective puddles, holo-ads, dense vertical megablocks, "
                     "practical neon key light, anamorphic flare"),
        "block_zh": "霓虹紫青、湿路面反光、高科技低生活、全息广告、高密度垂直街区、实用霓虹主光",
        "forbidden": "avoid daylight exteriors, avoid clean matte surfaces, avoid warm pastel palette",
    },
    "国漫高燃": {
        "label": "国漫高燃（高饱和·大透视·法术粒子重量感）",
        "block_en": ("Chinese high-burn anime, high saturation, extreme foreshortening, "
                     "heavy spell particle effects with physical weight, dynamic speed lines, "
                     "epic scale battles, vivid color grading"),
        "block_zh": "高饱和、大透视、法术粒子重量感、速度线、史诗级大战、鲜艳调色",
        "forbidden": "avoid muted muted palette, avoid flat 2D no-effects, avoid small-scale domestic",
    },
    "治愈日常": {
        "label": "治愈日常（柔光·低饱和·生活质感）",
        "block_en": ("healing slice-of-life, soft diffused light, low saturation warm palette, "
                     "cozy domestic detail, gentle camera, natural window light, "
                     "tender character acting, muted background blur"),
        "block_zh": "柔光、低饱和暖调、生活质感细节、温柔运镜、自然窗光、柔和背景虚化",
        "forbidden": "avoid harsh contrast, avoid violent action framing, avoid high-saturation neon",
    },
    "悬疑冷调": {
        "label": "悬疑冷调（低照度·长阴影·信息留白）",
        "block_en": ("suspense cold-tone, low-key lighting, long directional shadows, "
                     "cool desaturated palette, negative space holding clues, "
                     "restricted camera, unsettling stillness, practical single light source"),
        "block_zh": "低照度、长向阴影、冷调低饱和、留白藏线索、受限运镜、不安静止、单光源",
        "forbidden": "avoid bright even lighting, avoid warm cozy palette, avoid fully revealing composition",
    },
    "史诗历史": {
        "label": "史诗历史（大地色·体积光·宏大场面·胶片颗粒）",
        "block_en": ("epic historical, earthy palette, volumatic god-rays, "
                     "grand-scale crowd battles, film grain, wide establishing shots, "
                     "weighty practical cloth and metal, muted heroic tones"),
        "block_zh": "大地色系、体积光、宏大群战、胶片颗粒、大远景、厚重实用布料金属、克制英雄色调",
        "forbidden": "avoid modern neon, avoid cartoonish proportions, avoid hyper-saturated digital look",
    },
}


def list_styles() -> list:
    return [f"{k}  ({v['label']})" for k, v in STYLES.items()]


def get(name: str) -> dict:
    """Lookup a style by key (case-insensitive, also accepts the label prefix).
    Raises KeyError with available names if not found."""
    key = (name or "").strip()
    for k, v in STYLES.items():
        if key.lower() == k.lower() or key in v["label"]:
            return dict(v, key=k)
    raise KeyError(f"未知风格 '{name}'，可选: {list(STYLES.keys())}")


def block(name: str) -> str:
    """Return the English prompt block (+ forbidden tail) for embedding in a prompt."""
    s = get(name)
    return f"{s['block_en']}; {s['forbidden']}"


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:
        try:
            s = get(sys.argv[1])
            print(json.dumps({k: s.get(k) for k in ("label", "block_en", "block_zh", "forbidden")},
                             ensure_ascii=False, indent=2))
        except KeyError as e:
            print(f"[ERROR] {e}", file=__import__("sys").stderr)
            print("可用风格: " + " / ".join(STYLES.keys()))
            sys.exit(1)
    else:
        print("画风锁参数库（--style-bible 可选值）：")
        for line in list_styles():
            print("  " + line)
        print(f"\n用法: python style-lock.py <风格名>")
