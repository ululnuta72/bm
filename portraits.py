#!/usr/bin/env python3
"""Draw a portrait for every character: python portraits.py  ->  docs/characters/<id>.png, roster.json and docs/characters.jpg"""
import json, os
from PIL import Image, ImageDraw
import tinyvideo as T

OUT = os.path.join("docs", "characters")


def lighten(c, f):
    return tuple(int(v + (255 - v) * f) for v in c)


def portrait(c, size=320):
    s = T.render_char(c, 1, False)
    w, h = s.size
    crop = s.crop((0, 0, w, int(h * 0.80)))
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=44, fill=lighten(c["accent"], 0.72))
    k = size / crop.height
    crop = crop.resize((int(crop.width * k), size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=44, fill=255)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0)); layer.paste(crop, ((size - crop.width) // 2, 0), crop)
    im.paste(layer, (0, 0), Image.composite(layer.split()[3], Image.new("L", (size, size), 0), mask))
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    roster, tiles = [], []
    for cid, c in T.ROSTER.items():
        p = portrait(c); p.save(os.path.join(OUT, cid + ".png"), optimize=True); tiles.append((c["label"], p))
        roster.append(dict(id=cid, name=c["label"], tag=c["tag"], group=c["group"], voice="male" if c["voice"] == T.M_VOICE else "female"))
    with open(os.path.join(OUT, "roster.json"), "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=1)
    cols, tw, pad = 5, 240, 16
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (tw + 64 + pad) + pad), (30, 26, 34)); d = ImageDraw.Draw(sheet)
    for i, (name, p) in enumerate(tiles):
        x, y = pad + (i % cols) * (tw + pad), pad + (i // cols) * (tw + 64 + pad)
        sheet.paste(p.resize((tw, tw), Image.LANCZOS), (x, y), p.resize((tw, tw), Image.LANCZOS))
        d.text((x + tw / 2, y + tw + 28), name, font=T.font(34), fill=(244, 234, 237), anchor="mm")
    sheet.save(os.path.join("docs", "characters.jpg"), quality=85)
    print(f"{len(tiles)} portraits written to {OUT}")


if __name__ == "__main__":
    main()
