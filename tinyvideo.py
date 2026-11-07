#!/usr/bin/env python3
"""Tiny Japanese video generator: story script (.txt) -> 1080x1920 MP4.

Free stack: edge-tts (Japanese neural voices), Pillow (drawn characters + subtitles),
ffmpeg (encode). Runs on GitHub Actions, nothing to install locally.
"""
import time, argparse, asyncio, functools, glob, inspect, math, os, random, re, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, SR = 1080, 1920, 30, 24000
CHAR_SCALE, CHAR_Y = 0.9, 300
TABLE_TOP, CARD_Y = 885, 1040

# ---------- characters ----------
# Two slots on screen: "Mika" = left, "Alex" = right. Which character stands in a slot comes from `cast: left, right` in the story.
CHAR_DEFAULTS = dict(hair_style="short", eye=(55, 35, 42), pupil=False, outfit="plain", acc=(), acc_col=(226, 92, 92), mark=None, brow=None,
                     trim=(250, 250, 250), pitch=None, tag="", arm=None, group="Everyday")
F_VOICE, M_VOICE = "ja-JP-NanamiNeural", "ja-JP-KeitaNeural"


def char(label, **kw):
    c = dict(CHAR_DEFAULTS, label=label); c.update(kw)
    return c


ROSTER = {
    "mika": char("Mika", voice=F_VOICE, hair=(74, 45, 38), skin=(255, 224, 205), top=(244, 168, 184), accent=(222, 110, 134), hair_style="long", acc=("flower",), tag="Cheerful"),
    "alex": char("Alex", voice=M_VOICE, hair=(139, 98, 64), skin=(250, 214, 190), top=(142, 178, 150), accent=(96, 150, 112), hair_style="short", tag="Friendly"),
    "haru": char("Haru", voice=M_VOICE, pitch="+12Hz", hair=(36, 50, 92), skin=(250, 216, 190), top=(232, 98, 80), accent=(214, 82, 64), hair_style="spiky",
                 eye=(80, 176, 130), pupil=True, outfit="hoodie", mark="freckles", tag="Energetic"),
    "sora": char("Sora", voice=M_VOICE, pitch="-8Hz", hair=(204, 210, 224), skin=(248, 222, 204), top=(46, 62, 112), accent=(70, 90, 150), hair_style="short",
                 eye=(120, 150, 214), pupil=True, outfit="blazer", acc_col=(200, 70, 70), brow="sharp", tag="Cool"),
    "rin": char("Rin", voice=F_VOICE, pitch="+22Hz", hair=(244, 148, 190), skin=(255, 226, 210), top=(250, 250, 252), accent=(60, 80, 150), hair_style="twintails",
                eye=(206, 76, 128), pupil=True, outfit="sailor", acc=("ribbon",), acc_col=(230, 70, 90), tag="Playful"),
    "yuki": char("Yuki", voice=F_VOICE, pitch="-10Hz", hair=(212, 230, 250), skin=(255, 230, 220), top=(142, 184, 226), accent=(110, 160, 220), hair_style="hime",
                 eye=(110, 170, 230), pupil=True, outfit="kimono", acc_col=(236, 120, 150), tag="Calm"),
    "kenji": char("Kenji", voice=M_VOICE, pitch="-2Hz", hair=(30, 30, 40), skin=(250, 218, 196), top=(74, 88, 104), accent=(80, 110, 140), hair_style="short",
                  eye=(70, 60, 60), pupil=True, outfit="blazer", acc=("glasses",), acc_col=(200, 70, 70), tag="Bookish"),
    "hana": char("Hana", voice=F_VOICE, pitch="+8Hz", hair=(170, 60, 70), skin=(255, 224, 205), top=(236, 140, 70), accent=(226, 120, 60), hair_style="bun",
                 eye=(150, 60, 50), pupil=True, outfit="kimono", acc_col=(250, 226, 150), tag="Festival"),
    "ryu": char("Ryu", voice=M_VOICE, pitch="-14Hz", hair=(28, 26, 30), skin=(246, 210, 184), top=(244, 244, 240), accent=(80, 80, 98), hair_style="spiky",
                eye=(40, 30, 30), pupil=True, outfit="gi", acc=("headband",), acc_col=(210, 60, 60), mark="bandaid", brow="sharp", tag="Fighter"),
    "kai": char("Kai", voice=M_VOICE, pitch="+6Hz", hair=(226, 184, 106), skin=(250, 214, 190), top=(40, 150, 170), accent=(36, 130, 150), hair_style="spiky",
                eye=(120, 80, 50), pupil=True, outfit="jacket", acc=("goggles",), mark="freckles", tag="Explorer"),
    "aoi": char("Aoi", voice=F_VOICE, pitch="+10Hz", hair=(70, 130, 220), skin=(252, 222, 202), top=(72, 120, 200), accent=(60, 110, 190), hair_style="ponytail",
                eye=(50, 170, 170), pupil=True, outfit="jacket", acc_col=(250, 200, 60), tag="Sporty"),
    "emi": char("Emi", voice=F_VOICE, pitch="+26Hz", hair=(252, 216, 120), skin=(255, 228, 212), top=(186, 160, 230), accent=(160, 130, 214), hair_style="bob",
                eye=(230, 150, 70), pupil=True, outfit="hoodie", acc=("catears",), acc_col=(250, 170, 190), tag="Cute"),
    "taro": char("Taro", voice=M_VOICE, pitch="-4Hz", hair=(92, 60, 44), skin=(248, 212, 186), top=(250, 250, 252), accent=(214, 84, 70), hair_style="short",
                 outfit="chef", acc=("chefhat",), acc_col=(214, 84, 70), tag="Chef"),
    "sakuya": char("Sakuya", voice=F_VOICE, pitch="-14Hz", hair=(62, 42, 96), skin=(255, 232, 222), top=(92, 58, 130), accent=(150, 90, 190), hair_style="hime",
                   eye=(140, 96, 190), pupil=True, outfit="kimono", acc_col=(236, 200, 120), mark="mole", tag="Elegant"),
    "daichi": char("Daichi", voice=M_VOICE, pitch="-22Hz", hair=(112, 78, 58), skin=(240, 202, 174), top=(120, 140, 128), accent=(90, 120, 104), hair_style="short",
                   outfit="hoodie", acc=("headphones",), acc_col=(50, 50, 60), mark="stubble", tag="Chill"),
    "kage": char("Kage", voice=M_VOICE, pitch="-6Hz", hair=(24, 28, 48), skin=(246, 212, 186), top=(44, 48, 72), accent=(60, 70, 110), hair_style="short",
                 eye=(220, 190, 60), pupil=True, outfit="ninja", acc=("headband", "scarf"), acc_col=(196, 60, 60), brow="sharp", tag="Shadow"),
    "sayo": char("Sayo", voice=F_VOICE, pitch="+6Hz", hair=(70, 40, 100), skin=(255, 228, 212), top=(66, 50, 96), accent=(130, 80, 170), hair_style="ponytail",
                 eye=(190, 70, 150), pupil=True, outfit="ninja", acc=("headband", "scarf"), acc_col=(236, 130, 170), brow="sharp", tag="Swift"),
    "rex": char("Rex", voice=M_VOICE, pitch="-12Hz", hair=(34, 30, 36), skin=(240, 204, 176), top=(250, 246, 236), accent=(176, 44, 56), hair_style="short",
                eye=(60, 90, 140), pupil=True, outfit="pirate", acc=("piratehat", "cape"), acc_col=(232, 190, 80), mark="scar", tag="Captain"),
    "marin": char("Marin", voice=F_VOICE, pitch="+14Hz", hair=(70, 196, 200), skin=(255, 226, 208), top=(250, 246, 236), accent=(40, 150, 170), hair_style="bob",
                  eye=(40, 140, 170), pupil=True, outfit="pirate", acc=("bandana",), acc_col=(250, 200, 70), tag="Navigator"),
    "bolt": char("Bolt", voice=M_VOICE, pitch="+2Hz", hair=(92, 166, 92), skin=(244, 206, 178), top=(70, 110, 170), accent=(60, 100, 160), hair_style="short",
                 outfit="overalls", trim=(250, 210, 70), arm=(250, 210, 70), acc=("bandana",), acc_col=(220, 80, 70), mark="freckles", tag="Mechanic"),
    "takeru": char("Takeru", voice=M_VOICE, pitch="-16Hz", hair=(26, 24, 30), skin=(244, 208, 182), top=(36, 48, 86), accent=(60, 76, 130), hair_style="topknot",
                   eye=(50, 40, 40), pupil=True, outfit="samurai", acc_col=(200, 60, 60), mark="scar", brow="sharp", tag="Samurai"),
    "tomoe": char("Tomoe", voice=F_VOICE, pitch="-6Hz", hair=(36, 44, 86), skin=(255, 230, 216), top=(128, 40, 64), accent=(190, 70, 100), hair_style="braid",
                  eye=(200, 60, 70), pupil=True, outfit="samurai", acc_col=(240, 230, 220), brow="sharp", tag="Blade"),
    "luna": char("Luna", voice=F_VOICE, pitch="+18Hz", hair=(160, 160, 250), skin=(255, 230, 218), top=(250, 196, 226), accent=(190, 120, 220), hair_style="long",
                 eye=(120, 110, 230), pupil=True, outfit="magical", acc=("bigbow", "wand"), acc_col=(110, 150, 240), tag="Star"),
    "hoshi": char("Hoshi", voice=F_VOICE, pitch="+24Hz", hair=(255, 210, 90), skin=(255, 228, 212), top=(255, 244, 170), accent=(240, 170, 40), hair_style="twintails",
                  eye=(240, 150, 50), pupil=True, outfit="magical", acc=("starclip", "wand"), acc_col=(250, 120, 160), tag="Sparkle"),
    "eldo": char("Eldo", voice=M_VOICE, pitch="-30Hz", hair=(236, 236, 242), skin=(246, 214, 190), top=(80, 64, 150), accent=(100, 80, 180), hair_style="short",
                 eye=(90, 90, 140), pupil=True, outfit="robe", acc=("wizardhat", "mustache"), acc_col=(240, 200, 90), tag="Wizard"),
    "mia": char("Mia", voice=F_VOICE, pitch="+16Hz", hair=(46, 34, 74), skin=(255, 230, 218), top=(60, 46, 110), accent=(90, 60, 150), hair_style="bob",
                eye=(160, 100, 230), pupil=True, outfit="robe", acc=("wizardhat",), acc_col=(250, 210, 100), tag="Witch"),
    "noa": char("Noa", voice=F_VOICE, pitch="+12Hz", hair=(120, 222, 232), skin=(255, 230, 216), top=(250, 250, 255), accent=(60, 190, 210), hair_style="long",
                eye=(60, 170, 200), pupil=True, outfit="stage", acc=("headset", "starclip"), acc_col=(250, 100, 170), tag="Idol"),
    "rei": char("Rei", voice=M_VOICE, pitch="-4Hz", hair=(58, 46, 44), skin=(248, 214, 190), top=(162, 128, 92), accent=(110, 86, 64), hair_style="short",
                eye=(70, 60, 50), pupil=True, outfit="trench", acc=("flatcap",), acc_col=(150, 50, 56), tag="Detective"),
    "mei": char("Mei", voice=F_VOICE, pitch="-2Hz", hair=(88, 58, 50), skin=(252, 222, 204), top=(250, 250, 252), accent=(60, 170, 170), hair_style="bun",
                eye=(70, 100, 90), pupil=True, outfit="labcoat", trim=(60, 170, 170), acc=("glasses",), acc_col=(60, 170, 170), tag="Scientist"),
    "gen": char("Gen", voice=M_VOICE, pitch="-30Hz", hair=(232, 232, 236), skin=(240, 206, 180), top=(110, 84, 60), accent=(130, 100, 70), hair_style="topknot",
                eye=(60, 50, 50), pupil=True, outfit="kimono", acc=("mustache",), acc_col=(60, 50, 44), tag="Sensei"),
    "zed": char("Zed", voice=M_VOICE, pitch="+4Hz", hair=(70, 232, 150), skin=(246, 212, 188), top=(40, 40, 48), accent=(230, 60, 150), hair_style="spiky",
                eye=(230, 60, 150), pupil=True, outfit="jacket", trim=(240, 240, 246), acc=("headphones",), acc_col=(230, 60, 150), brow="sharp", tag="Rocker"),
    "sari": char("Sari", voice=F_VOICE, hair=(44, 30, 28), skin=(174, 112, 77), top=(113, 55, 63), accent=(181, 104, 77), hair_style="bun", outfit="batik", acc_col=(230, 185, 111), tag="Batik-inspired"),
    "bagas": char("Bagas", voice=M_VOICE, hair=(36, 28, 27), skin=(150, 94, 65), top=(71, 56, 48), accent=(116, 86, 60), hair_style="short", outfit="batik", acc=("blangkon",), acc_col=(205, 166, 98), tag="Batik-inspired"),
}
GROUPS = {"Traditional": ("yuki", "hana", "sakuya", "ryu", "takeru", "tomoe", "gen"), "Nusantara": ("sari", "bagas"), "Ninja": ("kage", "sayo"), "Pirate": ("rex", "marin", "bolt", "kai"),
          "Magic": ("luna", "hoshi", "eldo", "mia"), "Other": ("noa", "zed", "rei", "mei")}
for _g, _ids in GROUPS.items():
    for _i in _ids:
        ROSTER[_i]["group"] = _g
for _k, _v in ROSTER.items():
    _v["id"] = _k
CHARS = {"Mika": dict(ROSTER["mika"], x=16), "Alex": dict(ROSTER["alex"], x=W - 16 - int(560 * CHAR_SCALE))}


def cast_ids(meta):
    toks = [t for t in re.split(r"[\s,&/|+]+|\band\b", (meta.get("cast") or "").lower()) if t]
    if not toks:
        return "mika", "alex"
    ids = (toks + ["alex" if toks[0] != "alex" else "mika"])[:2]
    for x in ids:
        if x not in ROSTER:
            sys.exit(f"Unknown character '{x}' in cast. Choose from: {', '.join(ROSTER)}")
    if ids[0] == ids[1]:
        sys.exit("cast: pick two different characters")
    return ids[0], ids[1]


def apply_cast(meta):
    """Put the chosen characters into the left (Mika) and right (Alex) slots."""
    for slot, cid in zip(("Mika", "Alex"), cast_ids(meta)):
        CHARS[slot].update(ROSTER[cid])
    return CHARS["Mika"]["id"], CHARS["Alex"]["id"]


SCENES = {
    "cafe": dict(top=(255, 246, 232), bot=(250, 228, 210), floor=(204, 160, 120), table=(228, 184, 140), edge=(176, 130, 92)),
    "station": dict(top=(196, 224, 246), bot=(236, 246, 252), floor=(150, 150, 164), table=(238, 204, 96), edge=(120, 120, 134)),
    "sakura": dict(top=(255, 228, 236), bot=(255, 246, 242), floor=(160, 204, 148), table=(176, 218, 156), edge=(120, 170, 108)),
    "restaurant": dict(top=(255, 236, 214), bot=(250, 214, 186), floor=(150, 96, 74), table=(196, 140, 104), edge=(140, 92, 66)),
    "store": dict(top=(232, 246, 255), bot=(246, 252, 255), floor=(214, 218, 226), table=(120, 196, 170), edge=(84, 150, 128)),
    "bookstore": dict(top=(246, 230, 206), bot=(238, 214, 184), floor=(166, 122, 90), table=(204, 160, 118), edge=(150, 108, 76)),
    "classroom": dict(top=(240, 248, 236), bot=(250, 252, 244), floor=(206, 176, 136), table=(226, 196, 150), edge=(176, 142, 102)),
    "home": dict(top=(255, 242, 226), bot=(252, 226, 204), floor=(196, 150, 112), table=(236, 206, 170), edge=(190, 150, 112)),
    "airport": dict(top=(204, 228, 250), bot=(240, 248, 255), floor=(178, 184, 198), table=(150, 170, 210), edge=(110, 128, 170)),
    "street": dict(top=(46, 52, 98), bot=(120, 90, 130), floor=(84, 84, 104), table=(186, 90, 90), edge=(130, 60, 66)),
    "park": dict(top=(190, 228, 252), bot=(236, 248, 238), floor=(140, 200, 120), table=(190, 152, 110), edge=(146, 112, 78)),
    "beach": dict(top=(150, 214, 244), bot=(224, 244, 252), floor=(240, 220, 170), table=(240, 130, 110), edge=(200, 96, 80)),
    "hospital": dict(top=(236, 248, 250), bot=(248, 252, 252), floor=(200, 222, 224), table=(170, 214, 216), edge=(120, 176, 180)),
    "ramen": dict(top=(255, 226, 190), bot=(244, 198, 152), floor=(120, 78, 56), table=(170, 114, 78), edge=(112, 72, 50)),
    "shrine": dict(top=(255, 236, 214), bot=(255, 247, 238), floor=(196, 188, 176), table=(204, 62, 54), edge=(142, 40, 40)),
    "fuji": dict(top=(150, 206, 246), bot=(240, 248, 252), floor=(120, 184, 140), table=(236, 208, 160), edge=(180, 148, 104)),
    "matsuri": dict(top=(30, 28, 70), bot=(150, 70, 110), floor=(104, 82, 96), table=(240, 170, 70), edge=(190, 120, 40)),
    "arcade": dict(top=(40, 30, 90), bot=(104, 52, 144), floor=(58, 48, 98), table=(60, 200, 220), edge=(30, 140, 170)),
    "aquarium": dict(top=(24, 96, 156), bot=(84, 172, 212), floor=(40, 80, 112), table=(120, 220, 230), edge=(60, 160, 180)),
    "onsen": dict(top=(208, 230, 240), bot=(240, 246, 248), floor=(176, 150, 122), table=(150, 206, 222), edge=(100, 150, 170)),
    "snow": dict(top=(176, 200, 232), bot=(244, 248, 255), floor=(236, 242, 250), table=(190, 150, 110), edge=(140, 106, 76)),
    "bakery": dict(top=(255, 240, 218), bot=(252, 222, 192), floor=(214, 170, 130), table=(240, 200, 150), edge=(190, 140, 96)),
    "rainy": dict(top=(120, 136, 164), bot=(190, 200, 216), floor=(110, 116, 134), table=(90, 120, 170), edge=(60, 86, 134)),
    "karaoke": dict(top=(36, 24, 70), bot=(150, 56, 120), floor=(70, 40, 84), table=(250, 120, 170), edge=(190, 70, 120)),
    "rooftop": dict(top=(168, 208, 246), bot=(250, 236, 224), floor=(150, 154, 166), table=(190, 196, 208), edge=(140, 146, 160)),
    "izakaya": dict(top=(120, 72, 52), bot=(176, 106, 70), floor=(84, 56, 44), table=(150, 96, 64), edge=(96, 60, 42)),
    "commute": dict(top=(226, 232, 240), bot=(240, 244, 250), floor=(126, 134, 150), table=(80, 150, 200), edge=(50, 110, 160)),
    "sushi": dict(top=(255, 240, 226), bot=(250, 222, 200), floor=(160, 110, 80), table=(196, 150, 110), edge=(150, 104, 72)),
    "bamboo": dict(top=(200, 236, 206), bot=(236, 248, 230), floor=(150, 170, 120), table=(176, 150, 100), edge=(130, 106, 70)),
    "autumn": dict(top=(255, 220, 170), bot=(255, 238, 214), floor=(190, 130, 80), table=(214, 150, 90), edge=(160, 100, 60)),
    "castle": dict(top=(150, 206, 246), bot=(238, 248, 252), floor=(196, 190, 176), table=(170, 134, 96), edge=(124, 94, 64)),
    "sunset": dict(top=(250, 150, 110), bot=(255, 220, 170), floor=(126, 150, 106), table=(176, 150, 110), edge=(130, 106, 76)),
    "flowers": dict(top=(150, 214, 250), bot=(236, 248, 252), floor=(130, 196, 104), table=(240, 200, 100), edge=(190, 150, 60)),
}
# keywords used to pick a background automatically from the story's title + dialogue
SCENE_KEYWORDS = {
    "station": ["えき", "でんしゃ", "電車", "駅", "きっぷ", "ホーム", "バス", "station", "train", "bus stop", "ticket"],
    "airport": ["くうこう", "空港", "ひこうき", "飛行機", "パスポート", "airport", "flight", "passport", "luggage"],
    "bookstore": ["ほんや", "本屋", "しょてん", "ほん", "本", "book", "library", "としょかん", "図書館"],
    "restaurant": ["レストラン", "メニュー", "ちゅうもん", "注文", "おなか", "ごはん", "restaurant", "menu", "order", "hungry", "food"],
    "cafe": ["カフェ", "コーヒー", "こうちゃ", "ケーキ", "のみもの", "cafe", "café", "coffee", "tea", "name", "meet", "first time", "はじめまして"],
    "store": ["スーパー", "supermarket", "コンビニ", "みせ", "店", "いくら", "かいもの", "買い物", "ぜんぶで", "shop", "store", "buy", "how much", "price", "convenience"],
    "classroom": ["がっこう", "学校", "せんせい", "先生", "じゅぎょう", "しゅくだい", "きょうしつ", "school", "class", "teacher", "homework", "student"],
    "hospital": ["びょういん", "病院", "くすり", "いしゃ", "医者", "ねつ", "あたま", "いたい", "hospital", "doctor", "medicine", "sick", "fever", "pain"],
    "home": ["いえ", "家", "うち", "へや", "部屋", "かぞく", "ただいま", "いってきます", "home", "house", "room", "family", "kitchen"],
    "beach": ["うみ", "海", "なつ", "夏", "およぐ", "ビーチ", "sea", "beach", "swim", "summer"],
    "street": ["よる", "夜", "こんばんは", "みち", "道", "night", "evening", "street", "way to"],
    "park": ["こうえん", "公園", "さんぽ", "てんき", "天気", "はれ", "park", "walk", "weather", "sunny"],
    "sakura": ["さくら", "桜", "はなみ", "花見", "はる", "春", "sakura", "cherry", "blossom", "spring"],
    "ramen": ["ラーメン", "らーめん", "ramen", "noodle", "麺", "とんこつ", "broth", "ぎょうざ", "餃子"],
    "shrine": ["じんじゃ", "神社", "おまいり", "お参り", "おみくじ", "鳥居", "寺", "shrine", "temple", "pray", "fortune", "torii"],
    "fuji": ["ふじさん", "富士", "山", "とざん", "登山", "mountain", "hiking", "hike", "fuji"],
    "matsuri": ["まつり", "祭", "はなび", "花火", "やたい", "屋台", "ゆかた", "浴衣", "festival", "fireworks", "yukata", "stall"],
    "arcade": ["ゲーム", "げーむ", "ゲーセン", "プリクラ", "arcade", "game", "claw machine"],
    "aquarium": ["すいぞくかん", "水族館", "くらげ", "クラゲ", "イルカ", "aquarium", "shark", "jellyfish", "dolphin"],
    "onsen": ["おんせん", "温泉", "おふろ", "お風呂", "りょかん", "旅館", "onsen", "hot spring", "ryokan", "bathhouse", "hot bath"],
    "snow": ["ゆき", "雪", "ふゆ", "冬", "スキー", "snow", "winter", "skiing"],
    "bakery": ["パンや", "パン屋", "ベーカリー", "メロンパン", "クロワッサン", "bakery", "bread", "croissant"],
    "rainy": ["雨", "あめ", "傘", "rain", "umbrella"],
    "karaoke": ["カラオケ", "からおけ", "歌", "karaoke", "sing"],
    "rooftop": ["おくじょう", "屋上", "rooftop", "roof"],
    "izakaya": ["いざかや", "居酒屋", "ビール", "やきとり", "焼き鳥", "かんぱい", "乾杯", "izakaya", "beer", "yakitori", "cheers"],
    "commute": ["つうきん", "通勤", "しゃない", "車内", "commute", "on the train", "train ride"],
    "sushi": ["すし", "寿司", "かいてん", "回転", "sushi", "conveyor"],
    "bamboo": ["竹", "たけやぶ", "嵐山", "bamboo", "arashiyama"],
    "autumn": ["もみじ", "紅葉", "秋", "autumn", "momiji", "maple"],
    "castle": ["お城", "おしろ", "城", "castle", "himeji"],
    "sunset": ["ゆうやけ", "夕焼け", "ゆうひ", "夕日", "川", "sunset", "river", "riverside"],
    "flowers": ["花畑", "はなばたけ", "ひまわり", "向日葵", "sunflower", "flower field", "flowers"],
}
SCENE_ALIASES = {"supermarket": "store", "market": "store", "shop": "store", "shopping": "store", "convenience": "store",
                 "school": "classroom", "library": "bookstore", "house": "home", "kitchen": "home", "room": "home",
                 "night": "street", "city": "street", "festival": "matsuri", "fireworks": "matsuri", "sea": "beach", "ocean": "beach",
                 "garden": "park", "train": "station", "bus": "station", "clinic": "hospital", "coffee": "cafe", "noodles": "ramen", "temple": "shrine", "torii": "shrine", "mountain": "fuji", "mt fuji": "fuji",
                 "game": "arcade", "game center": "arcade", "gamecenter": "arcade", "fish": "aquarium", "hot spring": "onsen", "bath": "onsen",
                 "winter": "snow", "bread": "bakery", "rain": "rainy", "umbrella": "rainy",
                 "school roof": "rooftop", "roof": "rooftop", "pub": "izakaya", "subway": "commute", "train interior": "commute", "train car": "commute",
                 "kaiten": "sushi", "conveyor sushi": "sushi", "bamboo forest": "bamboo", "momiji": "autumn", "koyo": "autumn", "maple": "autumn",
                 "himeji": "castle", "riverside": "sunset", "river": "sunset", "dusk": "sunset", "sunflower": "flowers", "flower": "flowers",
                 "sing": "karaoke"}
SCENE_ORDER = ["cafe", "station", "sakura", "restaurant", "store", "bookstore", "classroom", "home", "airport", "street", "park", "beach", "hospital",
               "ramen", "shrine", "fuji", "matsuri", "arcade", "aquarium", "onsen", "snow", "bakery", "rainy",
               "karaoke", "rooftop", "izakaya", "commute", "sushi", "bamboo", "autumn", "castle", "sunset", "flowers"]


def kw_count(text, kw):
    """Count a keyword; ASCII words must start at a word boundary (so 'rain' does not match 'train')."""
    kw = kw.lower()
    return len(re.findall(r"\b" + re.escape(kw), text)) if kw.isascii() and kw[:1].isalnum() else text.count(kw)


def pick_scene(meta, lines):
    """Explicit `scene:` wins when it is a known one; otherwise choose from the story text."""
    sc = (meta.get("scene") or "auto").strip().lower()
    sc = SCENE_ALIASES.get(sc, sc)
    if sc in SCENES:
        return sc
    for key, val in list(SCENE_ALIASES.items()) + [(k, k) for k in SCENES]:  # e.g. "train station" -> station
        if sc != "auto" and key in sc:
            return val
    text = (meta.get("title", "") + " " + " ".join(l["jp"] + " " + l["en"] for l in lines)).lower()
    title = meta.get("title", "").lower()
    best, score = None, 0
    for name, kws in SCENE_KEYWORDS.items():
        n = sum(kw_count(text, k) + 3 * kw_count(title, k) for k in kws)
        if n > score:
            best, score = name, n
    if best:
        return best
    return SCENE_ORDER[sum(map(ord, meta.get("title", ""))) % len(SCENE_ORDER)]
BRAND = (222, 110, 134)


# ---------- fonts / text ----------
@functools.lru_cache(None)
def font(size, bold=True):
    w = "Bold" if bold else "Regular"
    for pat in (f"/usr/share/fonts/**/NotoSansCJK-{w}.ttc", f"/usr/share/fonts/**/NotoSansCJKjp-{w}.otf",
                "/usr/share/fonts/**/NotoSansCJK*.ttc", "/usr/share/fonts/**/*CJK*.tt*", "/usr/share/fonts/**/DejaVuSans.ttf",
                f"/System/Library/Fonts/Supplemental/Arial {'Bold' if bold else 'Unicode'}.ttf"):
        g = sorted(glob.glob(pat, recursive=True))
        if g:
            try:
                return ImageFont.truetype(g[0], size)
            except Exception:
                pass
    return ImageFont.load_default()


def wrap(text, f, maxw):
    if not text:
        return []
    sep = " " if " " in text else ""
    toks = text.split(" ") if sep else list(text)
    out, cur = [], ""
    for t in toks:
        trial = cur + sep + t if cur else t
        if f.getlength(trial) > maxw and cur:
            out.append(cur)
            cur = t
        else:
            cur = trial
    out.append(cur)
    return out


def to_romaji(t):
    try:
        import pykakasi
        r = pykakasi.kakasi().convert(t)
        s = " ".join(x["hepburn"] for x in r if x["hepburn"].strip())
        s = re.sub(r"\s+([!?,.。！？、])", r"\1", s)
        return s[:1].upper() + s[1:]
    except Exception:
        return ""


# ---------- script parsing ----------
def parse_story(path):
    meta, lines, vocab = {"title": "Tiny Story", "scene": "auto", "episode": ""}, [], []
    for raw in open(path, encoding="utf-8"):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^(title|scene|episode|weather|cast|language|brand)\s*:\s*(.+)$", s, re.I)
        if m:
            meta[m[1].lower()] = m[2].strip()
            continue
        m = re.match(r"^vocab\s*:\s*(.+)$", s, re.I)
        if m:
            p = [x.strip() for x in m[1].split("|")]
            if len(p) == 2:
                p = [p[0], to_romaji(p[0]), p[1]]
            if len(p) == 3:
                vocab.append(dict(jp=p[0], romaji=p[1], en=p[2]))
            continue
        m = re.match(r"^([A-Za-z]+)\s*[:：]\s*(.+)$", s)
        if m and m[1].lower() in ROSTER:
            p = [x.strip() for x in m[2].split("|")]
            lines.append(dict(speaker=m[1].lower(), jp=p[0], en=p[1] if len(p) > 1 else "",
                              romaji=p[2] if len(p) > 2 else (to_romaji(p[0]) if meta.get("language", "ja") == "ja" else "")))
            continue
        sys.exit(f"Cannot parse line (speakers: Mika / Alex = left / right, or a cast character's name): {s}")
    if not lines:
        sys.exit("No dialogue lines found.")
    order = []
    for l in lines:
        if l["speaker"] not in order:
            order.append(l["speaker"])
    if len(order) > 2:
        sys.exit("A story can only have two speakers (left and right); this one has " + str(len(order)) + ".")
    if not meta.get("cast") and any(s not in ("mika", "alex") for s in order):
        meta["cast"] = ", ".join(order)          # script written with real character names and no cast line: use them in speaking order
    left, right = cast_ids(meta)
    if all(s in ("mika", "alex") for s in order):
        slots = {"mika": "Mika", "alex": "Alex"}    # classic Mika:/Alex: script = left/right, whoever was picked
    else:
        slots = {"mika": "Mika", "alex": "Alex", left: "Mika", right: "Alex"}
    used = {slots[s] for s in order if s in slots}
    for s in order:
        if s not in slots:                          # a speaker who isn't in the cast: use a free slot instead of failing
            free = [x for x in ("Mika", "Alex") if x not in used]
            slots[s] = free[0]; used.add(free[0])
            print(f"Note: '{s}' is not in the cast, so the {slots[s]} slot speaks their lines.")
    for l in lines:
        l["speaker"] = slots[l["speaker"]]
    apply_cast(meta)
    return meta, lines, vocab


# ---------- audio ----------
def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def sh(cmd):
    subprocess.run(cmd, check=True)


FALLBACK_USED = False


def synth(text, speaker, out_wav, rate, dummy=False, voice=None, lang="ja"):
    if dummy:
        n = int(max(1.0, len(text) * 0.11) * SR); t = np.arange(n) / SR
        write_wav(out_wav, 0.4 * np.sin(2 * np.pi * 220 * t) * np.abs(np.sin(2 * np.pi * 3.5 * t)) ** 0.7)
        return
    global FALLBACK_USED
    mp3, af = out_wav + ".mp3", []
    ok, last = False, None
    for attempt in range(1, 6):          # Microsoft's endpoint sometimes answers 403 for a while; retry before downgrading
        try:
            import edge_tts
            kw = {}
            if not voice and CHARS.get(speaker, {}).get("pitch") and "pitch" in inspect.signature(edge_tts.Communicate.__init__).parameters:
                kw["pitch"] = CHARS[speaker]["pitch"]
            asyncio.run(edge_tts.Communicate(text, voice or CHARS[speaker]["voice"], rate=rate, **kw).save(mp3))
            ok = True
            break
        except Exception as e:
            last = e
            print(f"edge-tts attempt {attempt}/5 failed ({e})", file=sys.stderr)
            if attempt < 5:
                time.sleep(4 * attempt)
    if not ok:
        if os.environ.get("STRICT_VOICE") == "1":
            sys.exit("::error::The natural (edge-tts) voice is unavailable right now, so this render was stopped instead of "
                     "using the lower-quality fallback voice. Re-run it in a little while.")
        FALLBACK_USED = True
        print(f"::warning::edge-tts unavailable ({last}); using the lower-quality gTTS fallback voice", file=sys.stderr)
        from gtts import gTTS
        gTTS(text, lang=lang.split("-")[0]).save(mp3)
        if CHARS.get(speaker, {}).get("voice") == M_VOICE and lang == "ja":
            af = ["-af", f"asetrate={int(SR * 0.86)},aresample={SR}"]
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, *af, "-ar", str(SR), "-ac", "1", out_wav])


def mouth_levels(audio, n):
    spf = SR / FPS
    rms = np.array([np.sqrt(np.mean(audio[int(i * spf):int((i + 1) * spf)] ** 2) + 1e-12)
                    if int(i * spf) < len(audio) else 0 for i in range(n)])
    ref = np.percentile(rms[rms > 1e-3], 90) if (rms > 1e-3).any() else 1
    lv = np.clip(rms / ref, 0, 1.2)
    sm = lv.copy(); sm[1:-1] = 0.5 * lv[1:-1] + 0.25 * (lv[:-2] + lv[2:])
    return np.where(sm < 0.15, 0, np.where(sm < 0.55, 1, 2))


# ---------- characters ----------
def render_char(c, mouth, blink):
    S = 2 * CHAR_SCALE
    w, h = int(560 * S), int(760 * S)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    P = lambda *v: [int(x * S) for x in v]
    ell = lambda box, fill: d.ellipse(P(*box), fill=fill)
    shade = lambda col, f: tuple(int(v * f) for v in col)
    line = lambda pts, fill, wd: d.line(P(*pts), fill=fill, width=max(1, int(wd * S)))
    lite = lambda col, f: tuple(min(255, int(v * f)) for v in col)
    star = lambda cx, cy, r: [v for i in range(10) for v in (cx + (r if i % 2 == 0 else r * 0.45) * math.cos(math.radians(-90 + 36 * i)),
                                                              cy + (r if i % 2 == 0 else r * 0.45) * math.sin(math.radians(-90 + 36 * i)))]
    ink, hair, skin, top, acc, det = (70, 45, 48), c["hair"], c["skin"], c["top"], c["accent"], c["acc_col"]
    hs, outfit, accs, white = c["hair_style"], c["outfit"], set(c["acc"]), (255, 255, 255)
    # hair that sits behind the body
    if hs in ("long", "hime"):
        d.rounded_rectangle(P(110, 170, 450, 590), radius=int(110 * S), fill=hair)
    elif hs == "twintails":
        ell((50, 240, 170, 650), hair); ell((390, 240, 510, 650), hair)
    elif hs == "ponytail":
        ell((372, 170, 522, 570), hair)
    elif hs == "bob":
        d.rounded_rectangle(P(112, 170, 448, 440), radius=int(70 * S), fill=hair)
    elif hs == "braid":
        d.rounded_rectangle(P(130, 170, 430, 470), radius=int(70 * S), fill=hair)
    if "cape" in accs:
        d.polygon(P(150, 466, 410, 466, 458, 716, 102, 716), fill=shade(acc, 0.7))
    # body + outfit
    if outfit == "hoodie":
        ell((198, 428, 362, 522), shade(top, 0.8))
    d.rounded_rectangle(P(185, 450, 375, 690), radius=int(60 * S), fill=top)
    if outfit == "hoodie":
        d.rounded_rectangle(P(225, 600, 335, 672), radius=int(24 * S), fill=shade(top, 0.86))
    if outfit == "sailor":
        d.polygon(P(185, 462, 280, 552, 375, 462, 375, 506, 280, 602, 185, 506), fill=acc)
        line((190, 484, 280, 574), white, 4); line((370, 484, 280, 574), white, 4)
    if outfit == "blazer":
        d.polygon(P(247, 452, 280, 590, 313, 452), fill=white); d.polygon(P(262, 452, 280, 488, 298, 452), fill=skin)
        d.polygon(P(274, 500, 286, 500, 291, 585, 280, 604, 269, 585), fill=det)
        line((247, 452, 224, 566), shade(top, 0.7), 5); line((313, 452, 336, 566), shade(top, 0.7), 5)
    elif outfit == "jacket":
        d.rectangle(P(256, 452, 304, 690), fill=c["trim"]); d.polygon(P(262, 452, 280, 486, 298, 452), fill=skin)
        line((256, 452, 256, 690), shade(top, 0.7), 5); line((304, 452, 304, 690), shade(top, 0.7), 5)
        d.polygon(P(236, 446, 258, 452, 258, 506), fill=shade(top, 0.82)); d.polygon(P(324, 446, 302, 452, 302, 506), fill=shade(top, 0.82))
    elif outfit == "chef":
        d.polygon(P(245, 452, 280, 505, 315, 452), fill=skin)
        for by in (530, 574, 618):
            ell((248, by - 8, 264, by + 8), (190, 190, 200)); ell((296, by - 8, 312, by + 8), (190, 190, 200))
        d.polygon(P(236, 452, 324, 452, 280, 524), fill=det)
    elif outfit == "ninja":
        d.polygon(P(256, 452, 280, 490, 304, 452), fill=skin)
        line((200, 468, 360, 676), lite(top, 1.7), 9); line((360, 468, 200, 676), lite(top, 1.7), 9)
        d.rectangle(P(185, 612, 375, 640), fill=det)
    elif outfit == "pirate":
        d.polygon(P(190, 466, 246, 452, 262, 690, 196, 690), fill=acc); d.polygon(P(370, 466, 314, 452, 298, 690, 364, 690), fill=acc)
        d.polygon(P(250, 452, 280, 522, 310, 452), fill=skin)
        d.rectangle(P(185, 612, 375, 640), fill=det); ell((340, 606, 366, 646), shade(det, 0.8))
    elif outfit == "magical":
        d.polygon(P(262, 452, 280, 486, 298, 452), fill=skin)
        for x in range(205, 360, 30):
            ell((x - 18, 440, x + 18, 480), (255, 255, 255))
        d.polygon(P(280, 548, 226, 520, 226, 576), fill=det); d.polygon(P(280, 548, 334, 520, 334, 576), fill=det); ell((264, 532, 296, 564), shade(det, 0.85))
        d.rectangle(P(192, 652, 368, 690), fill=(255, 255, 255))
    elif outfit == "robe":
        d.polygon(P(256, 452, 280, 506, 304, 452), fill=skin)
        line((246, 452, 276, 650), det, 9); line((314, 452, 284, 650), det, 9)
        for sx, sy in ((214, 540), (344, 522), (236, 626), (326, 640), (290, 570)):
            ell((sx - 6, sy - 6, sx + 6, sy + 6), (255, 236, 150))
        d.rectangle(P(185, 604, 375, 622), fill=det)
    elif outfit == "trench":
        d.polygon(P(256, 452, 280, 548, 304, 452), fill=(250, 250, 246)); d.polygon(P(264, 452, 280, 486, 296, 452), fill=skin)
        d.polygon(P(274, 490, 286, 490, 289, 560, 280, 574, 271, 560), fill=det)
        d.polygon(P(222, 440, 258, 452, 248, 530), fill=shade(top, 0.78)); d.polygon(P(338, 440, 302, 452, 312, 530), fill=shade(top, 0.78))
        d.rectangle(P(185, 604, 375, 630), fill=shade(top, 0.65)); d.rectangle(P(268, 602, 292, 632), fill=(236, 200, 100))
        ell((236, 560, 248, 572), (110, 86, 64)); ell((312, 560, 324, 572), (110, 86, 64))
    elif outfit == "overalls":
        d.polygon(P(190, 452, 370, 452, 370, 524, 190, 524), fill=c["trim"])
        d.polygon(P(236, 452, 262, 452, 258, 536, 230, 536), fill=top); d.polygon(P(324, 452, 298, 452, 302, 536, 330, 536), fill=top)
        d.polygon(P(262, 452, 280, 482, 298, 452), fill=skin)
        d.rounded_rectangle(P(240, 580, 320, 640), radius=int(10 * S), fill=shade(top, 0.82))
        ell((236, 520, 252, 536), (240, 200, 70)); ell((308, 520, 324, 536), (240, 200, 70))
    elif outfit == "labcoat":
        d.polygon(P(250, 452, 310, 452, 300, 690, 260, 690), fill=c["trim"]); d.polygon(P(264, 452, 280, 486, 296, 452), fill=skin)
        d.polygon(P(224, 444, 256, 452, 262, 548), fill=shade(top, 0.92)); d.polygon(P(336, 444, 304, 452, 298, 548), fill=shade(top, 0.92))
        line((256, 452, 262, 690), (208, 208, 218), 4); line((304, 452, 298, 690), (208, 208, 218), 4)
        d.rectangle(P(206, 610, 250, 660), outline=(208, 208, 218), width=max(1, int(3 * S))); line((222, 596, 222, 626), det, 6)
    elif outfit == "stage":
        d.polygon(P(262, 452, 280, 500, 298, 452), fill=skin)
        line((190, 560, 300, 462), det, 9); line((190, 640, 372, 462), det, 9); line((260, 690, 372, 560), det, 9)
        d.polygon(P(280, 474, 244, 452, 244, 496), fill=det); d.polygon(P(280, 474, 316, 452, 316, 496), fill=det); ell((268, 460, 292, 488), shade(det, 0.8))
        for sx, sy in ((228, 620), (332, 600), (306, 660)):
            d.polygon(P(*star(sx, sy, 12)), fill=(255, 236, 150))
    elif outfit == "batik":
        d.polygon(P(252, 452, 280, 500, 308, 452), fill=skin)
        for yy in (520, 570, 620, 670):
            for xx in (220, 270, 320):
                d.polygon(P(xx, yy-12, xx+14, yy, xx, yy+12, xx-14, yy), fill=det)
                ell((xx-4, yy-4, xx+4, yy+4), shade(top, 0.75))
    elif outfit == "samurai":
        d.polygon(P(250, 452, 280, 506, 310, 452), fill=skin)
        line((246, 452, 296, 580), (250, 244, 236), 10); line((314, 452, 264, 580), (250, 244, 236), 10)
        line((196, 470, 372, 640), det, 14)
        d.rectangle(P(185, 626, 375, 654), fill=shade(top, 0.6)); ell((262, 618, 298, 662), det)
    else:
        d.polygon(P(245, 452, 280, 505, 315, 452), fill=skin)                          # neckline
        if outfit == "kimono":
            line((250, 452, 300, 612), (250, 244, 236), 12); line((310, 452, 262, 612), (250, 244, 236), 12)
            d.rounded_rectangle(P(185, 588, 375, 650), radius=int(14 * S), fill=det); ell((296, 596, 364, 644), shade(det, 0.85))
        elif outfit == "gi":
            line((250, 452, 296, 606), (200, 200, 196), 8); line((310, 452, 264, 606), (200, 200, 196), 8)
            d.rectangle(P(185, 606, 375, 636), fill=(40, 40, 48)); ell((258, 600, 302, 648), (40, 40, 48))
            d.polygon(P(280, 632, 262, 692, 278, 692), fill=(40, 40, 48)); d.polygon(P(280, 632, 302, 692, 286, 692), fill=(40, 40, 48))
        elif outfit == "sailor":
            d.polygon(P(280, 548, 236, 526, 236, 572), fill=det); d.polygon(P(280, 548, 324, 526, 324, 572), fill=det); ell((264, 534, 296, 562), shade(det, 0.85))
        elif outfit == "hoodie":
            line((262, 505, 258, 565), (250, 250, 250), 5); line((298, 505, 302, 565), (250, 250, 250), 5)
    arm = c["arm"] or top
    ell((140, 500, 210, 650), arm); ell((350, 500, 420, 650), arm)                     # arms
    ell((148, 625, 205, 675), skin); ell((355, 625, 412, 675), skin)                   # hands
    if outfit == "samurai":
        d.rounded_rectangle(P(122, 468, 212, 538), radius=int(22 * S), fill=shade(det, 0.92)); d.rounded_rectangle(P(348, 468, 438, 538), radius=int(22 * S), fill=shade(det, 0.92))
        for yy in (488, 508):
            line((130, yy, 204, yy), shade(top, 0.8), 4); line((356, yy, 430, yy), shade(top, 0.8), 4)
    if "scarf" in accs:
        d.rounded_rectangle(P(196, 438, 364, 486), radius=int(24 * S), fill=det); d.polygon(P(326, 470, 372, 482, 362, 614, 322, 602), fill=shade(det, 0.88))
    ell((125, 145, 435, 455), skin)                                                    # head
    d.pieslice(P(118, 136, 442, 460), 180, 360, fill=hair)                             # hair cap
    # front hair
    if hs == "long":
        for x in range(150, 420, 48):
            ell((x - 34, 225, x + 34, 300 + (12 if (x // 48) % 2 else 0)), hair)
        ell((112, 280, 168, 520), hair); ell((392, 280, 448, 520), hair)
    elif hs == "short":
        for x in range(135, 420, 58):
            d.polygon(P(x, 225, x + 58, 225, x + 29, 305), fill=hair)
        d.polygon(P(262, 120, 300, 120, 282, 165), fill=hair)
    elif hs == "spiky":
        for ang, tr in ((200, 230), (228, 262), (256, 240), (284, 276), (312, 246), (340, 226)):
            tip = (280 + tr * math.cos(math.radians(ang)), 300 + tr * math.sin(math.radians(ang)))
            b1 = (280 + 160 * math.cos(math.radians(ang - 16)), 300 + 160 * math.sin(math.radians(ang - 16)))
            b2 = (280 + 160 * math.cos(math.radians(ang + 16)), 300 + 160 * math.sin(math.radians(ang + 16)))
            d.polygon(P(b1[0], b1[1], tip[0], tip[1], b2[0], b2[1]), fill=hair)
        for x in range(128, 430, 50):
            d.polygon(P(x, 215, x + 50, 215, x + 25, 302 + (14 if (x // 50) % 2 else 0)), fill=hair)
        d.polygon(P(122, 262, 92, 336, 152, 322), fill=hair); d.polygon(P(438, 262, 468, 336, 408, 322), fill=hair)
    elif hs == "topknot":
        ell((240, 52, 320, 136), hair); d.rectangle(P(256, 120, 304, 138), fill=det)
        for x in range(135, 420, 58):
            d.polygon(P(x, 225, x + 58, 225, x + 29, 268), fill=hair)
        ell((112, 250, 152, 350), hair); ell((408, 250, 448, 350), hair)
    else:                                                                              # hime, twintails, bun, ponytail, bob, braid: blunt bangs
        d.rounded_rectangle(P(132, 200, 428, 302), radius=int(26 * S), fill=hair)
        if hs == "hime":
            ell((108, 250, 170, 570), hair); ell((390, 250, 452, 570), hair)
        elif hs == "twintails":
            ell((92, 232, 152, 288), det); ell((408, 232, 468, 288), det)
        elif hs == "bun":
            ell((118, 80, 232, 194), hair); ell((328, 80, 442, 194), hair); ell((156, 168, 196, 198), det); ell((364, 168, 404, 198), det)
        elif hs == "ponytail":
            ell((112, 230, 160, 380), hair); ell((372, 196, 424, 248), det)
        elif hs == "bob":
            ell((112, 250, 170, 440), hair); ell((390, 250, 448, 440), hair)
        elif hs == "braid":
            for k in range(7):
                ell((384 - k * 3, 300 + k * 52, 448 - k * 3, 366 + k * 52), hair)
            ell((372, 640, 424, 690), det)
    for ex in (222, 338):                                                              # eyes
        if blink:
            d.arc(P(ex - 26, 335, ex + 26, 375), 200, 340, fill=ink, width=int(6 * S))
        else:
            y0, y1 = (324, 376) if c["brow"] == "sharp" else (318, 382)
            ell((ex - 24, y0, ex + 24, y1), c["eye"])
            if c["pupil"]:
                ell((ex - 13, y0 + 12, ex + 13, y1 - 10), (35, 25, 34))
            ell((ex - 15, 330, ex + 3, 350), (255, 255, 255)); ell((ex + 6, 358, ex + 16, 368), (255, 255, 255))
    ell((168, 388, 215, 412), (250, 172, 170)); ell((345, 388, 392, 412), (250, 172, 170))  # blush
    mk = c["mark"]
    if mk == "freckles":
        for fx, fy in ((176, 372), (192, 380), (208, 372), (352, 372), (368, 380), (384, 372)):
            ell((fx - 4, fy - 4, fx + 4, fy + 4), (196, 120, 100))
    elif mk == "bandaid":
        d.rounded_rectangle(P(150, 386, 206, 406), radius=int(8 * S), fill=(246, 222, 176)); ell((172, 394, 178, 400), (222, 190, 140)); ell((184, 394, 190, 400), (222, 190, 140))
    elif mk == "scar":
        line((168, 350, 206, 420), (196, 110, 110), 6); line((176, 372, 200, 366), (196, 110, 110), 4); line((184, 394, 210, 386), (196, 110, 110), 4)
    elif mk == "mole":
        ell((366, 398, 376, 408), (90, 60, 60))
    elif mk == "stubble":
        for i in range(-5, 6):
            for yy in (432, 444):
                ell((280 + i * 17 - 2, yy - abs(i) * 3 - 2, 280 + i * 17 + 2, yy - abs(i) * 3 + 2), (126, 100, 90))
    if c["brow"] == "sharp":
        line((186, 296, 248, 312), shade(hair, 0.7), 8); line((374, 296, 312, 312), shade(hair, 0.7), 8)
    if mouth == 0:
        d.arc(P(262, 400, 298, 430), 20, 160, fill=ink, width=int(5 * S))
    elif mouth == 1:
        ell((268, 408, 292, 430), (120, 40, 52))
    else:
        ell((258, 405, 302, 442), (120, 40, 52)); ell((266, 424, 294, 440), (236, 120, 132))
    # accessories
    if "flower" in accs:
        ell((340, 165, 392, 215), acc); ell((355, 180, 377, 200), (255, 240, 200))
    if "headband" in accs:
        d.rectangle(P(121, 212, 439, 244), fill=det)
        d.polygon(P(430, 214, 490, 226, 472, 250, 430, 244), fill=det); d.polygon(P(430, 232, 484, 266, 458, 280, 428, 250), fill=shade(det, 0.85))
    if "goggles" in accs:
        line((122, 210, 438, 210), (60, 62, 72), 22)
        ell((196, 142, 274, 216), (60, 62, 72)); ell((206, 152, 264, 206), (140, 224, 244)); ell((286, 142, 364, 216), (60, 62, 72)); ell((296, 152, 354, 206), (140, 224, 244))
    if "glasses" in accs:
        for ex in (222, 338):
            d.ellipse(P(ex - 44, 306, ex + 44, 394), outline=(60, 50, 60), width=max(2, int(6 * S)))
        line((266, 348, 294, 348), (60, 50, 60), 6)
    if "catears" in accs:
        d.polygon(P(150, 190, 168, 84, 246, 150), fill=hair); d.polygon(P(410, 190, 392, 84, 314, 150), fill=hair)
        d.polygon(P(168, 160, 176, 112, 214, 148), fill=det); d.polygon(P(392, 160, 384, 112, 346, 148), fill=det)
    if "ribbon" in accs:
        d.polygon(P(366, 176, 322, 148, 322, 204), fill=det); d.polygon(P(366, 176, 410, 148, 410, 204), fill=det); ell((352, 162, 380, 190), shade(det, 0.8))
    if "chefhat" in accs:
        rim = (214, 214, 222)
        for bx in ((158, 36, 266, 138), (226, 6, 334, 116), (294, 36, 402, 138)):
            d.ellipse(P(*bx), fill=(252, 252, 252), outline=rim)
        d.rectangle(P(186, 112, 374, 160), fill=(252, 252, 252)); d.line(P(186, 160, 374, 160), fill=rim, width=max(1, int(3 * S)))
    if "headphones" in accs:
        d.arc(P(112, 118, 448, 440), 200, 340, fill=det, width=int(18 * S))
        ell((96, 268, 164, 372), det); ell((396, 268, 464, 372), det); ell((108, 284, 152, 356), acc); ell((408, 284, 452, 356), acc)
    if "piratehat" in accs:
        d.polygon(P(112, 200, 152, 120, 280, 66, 408, 120, 448, 200, 360, 170, 280, 152, 200, 170), fill=(34, 32, 38))
        d.line(P(112, 200, 200, 170, 280, 152, 360, 170, 448, 200), fill=(232, 190, 80), width=max(1, int(6 * S)))
        d.polygon(P(404, 116, 482, 36, 464, 114), fill=acc)
    if "bandana" in accs:
        d.pieslice(P(120, 134, 440, 358), 180, 360, fill=det); d.rectangle(P(121, 226, 439, 250), fill=shade(det, 0.82))
        for bx, by in ((190, 190), (250, 166), (310, 172), (370, 196), (222, 236)):
            ell((bx - 7, by - 7, bx + 7, by + 7), (255, 255, 255))
        ell((418, 218, 470, 262), det); d.polygon(P(452, 232, 496, 274, 472, 282, 440, 252), fill=det)
    if "eyepatch" in accs:
        line((126, 296, 194, 330), (30, 28, 34), 5); line((250, 330, 436, 290), (30, 28, 34), 5); ell((190, 312, 254, 390), (30, 28, 34))
    if "wizardhat" in accs:
        d.polygon(P(150, 184, 300, 14, 412, 184), fill=acc); ell((96, 150, 464, 214), shade(acc, 0.82))
        d.polygon(P(195.9, 132, 377.7, 132, 396.2, 160, 171.2, 160), fill=det); d.polygon(P(*star(290, 100, 18)), fill=(255, 236, 150))
    if "flatcap" in accs:
        d.pieslice(P(126, 120, 434, 330), 180, 360, fill=acc); ell((170, 196, 420, 238), shade(acc, 0.8)); ell((268, 118, 292, 138), shade(acc, 0.8))
    if "blangkon" in accs:
        d.pieslice(P(120, 100, 440, 336), 180, 360, fill=acc)
        d.polygon(P(126, 226, 280, 196, 434, 226, 434, 258, 280, 242, 126, 258), fill=shade(acc, 0.8))
        for xx in (178, 238, 298, 358):
            d.polygon(P(xx, 211, xx+14, 224, xx, 237, xx-14, 224), fill=det)
    if "bigbow" in accs:
        d.polygon(P(330, 152, 262, 108, 262, 196), fill=det); d.polygon(P(330, 152, 398, 108, 398, 196), fill=det); ell((314, 134, 346, 170), shade(det, 0.8))
    if "starclip" in accs:
        d.polygon(P(*star(150, 196, 26)), fill=(255, 230, 120)); d.polygon(P(*star(410, 196, 26)), fill=(255, 230, 120))
    if "headset" in accs:
        line((132, 312, 150, 420), (50, 50, 60), 6); line((150, 420, 196, 424), (50, 50, 60), 6); ell((190, 412, 214, 436), (50, 50, 60))
    if "mustache" in accs:
        ell((236, 384, 282, 402), hair); ell((278, 384, 324, 402), hair)
    if "wand" in accs:
        line((386, 652, 432, 540), (200, 160, 70), 8); d.polygon(P(*star(436, 516, 36)), fill=(255, 226, 110))
    return im.resize((int(560 * CHAR_SCALE), int(760 * CHAR_SCALE)), Image.LANCZOS)


@functools.lru_cache(None)
def _sprite(cid, mouth, blink):
    return render_char(ROSTER[cid], mouth, blink)


def sprite(name, mouth, blink):
    return _sprite(CHARS[name]["id"], mouth, blink)


def pill(text, fill, fg=(255, 255, 255)):
    f = font(32); tw = int(f.getlength(text)) + 56
    im = Image.new("RGBA", (tw, 58), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, tw - 1, 57), radius=29, fill=fill)
    d.text((tw / 2, 29), text, font=f, fill=fg, anchor="mm")
    return im


# ---------- scenes ----------
PETAL_COLS = ((255, 200, 214), (255, 214, 224), (250, 184, 202))
LEAF_COLS = ((232, 110, 60), (240, 170, 60), (210, 70, 50), (190, 120, 50))
GROUND_DECOR = {"sakura": PETAL_COLS, "fuji": PETAL_COLS, "castle": PETAL_COLS, "shrine": LEAF_COLS, "autumn": LEAF_COLS}


def vgrad(w, h, a, b):
    arr = np.zeros((h, w, 3), np.uint8)
    for i in range(3):
        arr[:, :, i] = np.linspace(a[i], b[i], h)[:, None]
    return Image.fromarray(arr).convert("RGBA")


def blossoms(d, rng, box, n):
    cols = ((255, 200, 214), (255, 214, 224), (250, 184, 202))
    for _ in range(n):
        x, y, r = rng.randint(box[0], box[2]), rng.randint(box[1], box[3]), rng.randint(8, 18)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice(cols))


def paper_lantern(d, x, y, r, col, text=None, f=None):
    """Hanging chochin lantern: x = centre, y = top of the lantern body."""
    hh = int(r * 1.35); dark = (70, 50, 44)
    d.line([(x, y - 40), (x, y)], fill=dark, width=4)
    d.ellipse((x - r, y, x + r, y + hh), fill=col)
    d.rectangle((x - int(r * 0.55), y - 6, x + int(r * 0.55), y + 6), fill=dark)
    d.rectangle((x - int(r * 0.55), y + hh - 6, x + int(r * 0.55), y + hh + 4), fill=dark)
    for k in (0.38, 0.62):
        d.line([(x - r + 10, y + int(hh * k)), (x + r - 10, y + int(hh * k))], fill=tuple(int(v * 0.8) for v in col), width=2)
    if text:
        d.text((x, y + hh // 2), text, font=f, fill=(255, 240, 210), anchor="mm")


def steam(d, x, y, n=3, col=(255, 255, 255), w=5):
    for i in range(n):
        xx = x + (i - n // 2) * 28
        d.arc((xx - 16, y - 70 - i * 6, xx + 16, y - 30 - i * 6), 90, 270, fill=col, width=w)
        d.arc((xx - 16, y - 110 - i * 6, xx + 16, y - 70 - i * 6), 270, 450, fill=col, width=w)


def ramen_bowl(d, x, y):
    """Bowl whose foot sits at about y + 80."""
    d.rounded_rectangle((x - 54, y + 62, x + 54, y + 80), radius=6, fill=(196, 56, 52))
    d.pieslice((x - 110, y - 110, x + 110, y + 70), 0, 180, fill=(250, 250, 246), outline=(196, 56, 52), width=6)
    d.ellipse((x - 106, y - 40, x + 106, y), fill=(222, 156, 76), outline=(250, 250, 246), width=6)
    for k in range(-2, 3):
        d.arc((x + k * 34 - 30, y - 34, x + k * 34 + 30, y - 6), 190, 350, fill=(252, 232, 160), width=5)
    d.ellipse((x - 76, y - 34, x - 26, y - 8), fill=(255, 255, 255)); d.ellipse((x - 60, y - 28, x - 42, y - 14), fill=(246, 168, 56))
    d.ellipse((x + 18, y - 34, x + 64, y - 8), fill=(255, 255, 255)); d.ellipse((x + 33, y - 27, x + 49, y - 15), fill=(240, 130, 150))
    d.rectangle((x + 66, y - 62, x + 84, y - 12), fill=(30, 62, 46))
    for sx in (-8, 6, 22, -22):
        d.ellipse((x + sx - 5, y - 22, x + sx + 5, y - 14), fill=(110, 190, 90))
    steam(d, x, y - 36)


def fish(d, x, y, col, s=1.0, flip=False):
    w, h = int(80 * s), int(38 * s); t = int(26 * s)
    if flip:
        d.polygon([(x + w, y + h // 2), (x + w + t, y), (x + w + t, y + h)], fill=col)
        d.ellipse((x, y, x + w, y + h), fill=col); ex = x + int(w * 0.2)
    else:
        d.polygon([(x, y + h // 2), (x - t, y), (x - t, y + h)], fill=col)
        d.ellipse((x, y, x + w, y + h), fill=col); ex = x + int(w * 0.76)
    d.ellipse((ex - 4, y + h // 3 - 4, ex + 4, y + h // 3 + 4), fill=(255, 255, 255)); d.ellipse((ex - 2, y + h // 3 - 2, ex + 2, y + h // 3 + 2), fill=(30, 40, 60))


def jellyfish(d, x, y, col):
    d.pieslice((x - 44, y - 44, x + 44, y + 44), 180, 360, fill=col)
    for k in range(-3, 4):
        d.line([(x + k * 12, y), (x + k * 12 + (7 if k % 2 else -7), y + 30), (x + k * 12, y + 58)], fill=col, width=4)


def sunflower(d, x, y, s):
    d.line([(x, y), (x, y + s * 5)], fill=(70, 150, 80), width=max(4, s // 4))
    d.ellipse((x + 2, y + s * 2, x + s * 2, y + s * 2 + s // 2), fill=(90, 170, 90)); d.ellipse((x - s * 2, y + s * 3, x - 2, y + s * 3 + s // 2), fill=(90, 170, 90))
    for a in range(0, 360, 30):
        px, py = x + int(1.35 * s * math.cos(math.radians(a))), y + int(1.35 * s * math.sin(math.radians(a)))
        d.ellipse((px - s // 2, py - s // 2, px + s // 2, py + s // 2), fill=(250, 206, 50))
    d.ellipse((x - int(s * 0.85), y - int(s * 0.85), x + int(s * 0.85), y + int(s * 0.85)), fill=(112, 72, 42))


def make_scene(scene, meta, header=True):
    sc = SCENES.get(scene, SCENES["cafe"]); rng = random.Random(7)
    bg = vgrad(W, H, sc["top"], sc["bot"]); d = ImageDraw.Draw(bg)
    if scene == "restaurant":
        for x in (150, 540, 930):
            d.line([(x, 0), (x, 250)], fill=(120, 90, 80), width=5)
            d.ellipse((x - 60, 230, x + 60, 300), fill=(255, 214, 120)); d.ellipse((x - 150, 200, x + 150, 420), fill=(255, 226, 150, 40))
        d.rounded_rectangle((120, 380, 960, 560), radius=20, fill=(110, 70, 56))
        d.text((540, 470), "らーめん  ・  すし  ・  どん", font=font(54), fill=(255, 236, 200), anchor="mm")
        for x in range(160, 960, 120):
            d.rounded_rectangle((x, 600, x + 70, 760), radius=14, fill=(214, 70, 70)); d.rectangle((x + 20, 580, x + 50, 600), fill=(250, 220, 120))
    elif scene == "store":
        d.rectangle((0, 300, W, 340), fill=(52, 160, 120)); d.rectangle((0, 340, W, 372), fill=(244, 244, 250))
        d.text((540, 322), "コンビニ  OPEN 24h", font=font(40), fill="white", anchor="mm")
        cols = [(250, 120, 110), (250, 200, 90), (110, 190, 240), (140, 210, 150), (200, 150, 230)]
        for row, y in enumerate((430, 600, 770)):
            d.rectangle((60, y + 70, W - 60, y + 86), fill=(150, 150, 164))
            for k, x in enumerate(range(80, W - 120, 70)):
                c = cols[(k * 3 + row) % 5]; hh = 40 + (k * 7 + row * 5) % 30
                d.rounded_rectangle((x, y + 70 - hh, x + 52, y + 70), radius=8, fill=c)
    elif scene == "bookstore":
        d.rectangle((60, 280, W - 60, 840), fill=(150, 104, 72))
        for y in (280, 460, 640):
            d.rectangle((70, y + 150, W - 70, y + 170), fill=(116, 78, 54)); x = 80
            while x < W - 120:
                w = rng.randint(34, 62); hh = rng.randint(100, 145)
                d.rectangle((x, y + 150 - hh, x + w, y + 150), fill=rng.choice([(210, 100, 96), (96, 150, 200), (230, 190, 96), (110, 170, 130), (170, 120, 190), (240, 230, 214)])); x += w + 4
    elif scene == "classroom":
        d.rounded_rectangle((120, 290, 960, 690), radius=18, fill=(150, 112, 78)); d.rounded_rectangle((140, 310, 940, 670), radius=10, fill=(52, 98, 80))
        d.text((540, 420), "にほんご", font=font(110), fill=(244, 244, 236), anchor="mm"); d.text((540, 560), "あ い う え お", font=font(80), fill=(244, 230, 140), anchor="mm")
        d.ellipse((860, 740, 940, 820), fill=(250, 250, 250), outline=(60, 60, 70), width=6); d.line([(900, 780), (900, 750)], fill=(60, 60, 70), width=5); d.line([(900, 780), (922, 790)], fill=(60, 60, 70), width=5)
    elif scene == "home":
        d.rounded_rectangle((90, 290, 470, 690), radius=24, fill=(255, 255, 255)); d.rounded_rectangle((108, 308, 452, 672), radius=16, fill=(205, 232, 244))
        d.line([(280, 308), (280, 672)], fill=(255, 255, 255), width=8)
        d.rounded_rectangle((590, 330, 990, 520), radius=16, fill=(255, 240, 220), outline=(190, 150, 112), width=8)
        d.ellipse((650, 370, 750, 470), fill=(255, 200, 150)); d.polygon([(780, 480), (860, 380), (940, 480)], fill=(150, 200, 140))
        d.rounded_rectangle((560, 640, 1020, 840), radius=34, fill=(224, 140, 140)); d.rounded_rectangle((560, 600, 1020, 700), radius=30, fill=(236, 160, 160))
    elif scene == "airport":
        d.rectangle((0, 280, W, 760), fill=(176, 212, 244)); d.polygon([(0, 760), (W, 560), (W, 760)], fill=(160, 200, 236))
        d.polygon([(250, 500), (640, 470), (700, 430), (730, 440), (690, 500), (800, 520), (790, 540), (260, 540)], fill=(250, 250, 255))
        d.rounded_rectangle((60, 290, 1020, 380), radius=18, fill=(40, 52, 80)); d.text((540, 335), "くうこう  Airport", font=font(48), fill=(250, 220, 110), anchor="mm")
        d.rounded_rectangle((100, 700, 260, 860), radius=20, fill=(230, 120, 100)); d.rounded_rectangle((820, 720, 960, 860), radius=18, fill=(100, 150, 200))
    elif scene == "street":
        d.ellipse((780, 220, 920, 360), fill=(255, 244, 200))
        for _ in range(60):
            x, y = rng.randint(0, W), rng.randint(0, 420); d.ellipse((x, y, x + 5, y + 5), fill=(255, 255, 255))
        for x in range(-30, W, 170):
            hh = rng.randint(260, 520); d.rectangle((x, TABLE_TOP - hh, x + 150, TABLE_TOP), fill=(36, 40, 72))
            for wy in range(TABLE_TOP - hh + 24, TABLE_TOP - 30, 54):
                for wx in (x + 20, x + 80):
                    if rng.random() < 0.65: d.rectangle((wx, wy, wx + 34, wy + 30), fill=(255, 218, 120))
        for x in (120, 360, 600, 840):
            d.line([(x, 560), (x, 620)], fill=(120, 80, 70), width=3); d.ellipse((x - 42, 600, x + 42, 720), fill=(236, 80, 70)); d.rectangle((x - 30, 650, x + 30, 662), fill=(255, 220, 160))
    elif scene == "park":
        d.ellipse((120, 300, 300, 480), fill=(250, 232, 140))
        for x in (760, 940):
            d.rectangle((x - 18, 520, x + 18, 800), fill=(122, 88, 66)); d.ellipse((x - 150, 300, x + 150, 600), fill=(96, 176, 108)); d.ellipse((x - 90, 340, x + 40, 450), fill=(120, 196, 128))
        for cx, cy in ((420, 360), (560, 300), (640, 420)):
            d.ellipse((cx - 70, cy - 30, cx + 70, cy + 30), fill=(255, 255, 255)); d.ellipse((cx - 30, cy - 55, cx + 50, cy + 10), fill=(255, 255, 255))
    elif scene == "beach":
        d.ellipse((780, 250, 920, 390), fill=(255, 226, 120))
        d.rectangle((0, 520, W, 885), fill=(70, 170, 220))
        for y in range(560, 880, 60):
            for x in range(-40, W, 140):
                d.arc((x + (y % 120), y, x + 100 + (y % 120), y + 40), 200, 340, fill=(220, 244, 255), width=5)
        d.rectangle((140, 560, 150, 840), fill=(150, 110, 80)); d.pieslice((40, 450, 260, 640), 180, 360, fill=(240, 100, 90)); d.pieslice((40, 450, 150, 640), 180, 360, fill=(255, 250, 250))
    elif scene == "hospital":
        d.rectangle((60, 290, W - 60, 800), fill=(226, 242, 244))
        d.rounded_rectangle((60, 290, W - 60, 380), radius=16, fill=(90, 170, 180)); d.text((540, 335), "びょういん  Hospital", font=font(50), fill="white", anchor="mm")
        d.rectangle((480, 440, 600, 480), fill=(236, 86, 96)); d.rectangle((520, 400, 560, 520), fill=(236, 86, 96))
        d.rounded_rectangle((120, 600, 330, 800), radius=12, fill=(250, 250, 252), outline=(160, 200, 206), width=6); d.rounded_rectangle((750, 600, 960, 800), radius=12, fill=(250, 250, 252), outline=(160, 200, 206), width=6)
    elif scene == "station":
        for x in range(-40, W, 150):
            hh = rng.randint(180, 380); d.rectangle((x, TABLE_TOP - hh, x + 130, TABLE_TOP), fill=(206, 218, 234))
        d.rounded_rectangle((330, 290, 750, 400), radius=24, fill=(60, 80, 120))
        d.text((540, 345), "えき  Station", font=font(52), fill="white", anchor="mm")
    elif scene == "sakura":
        d.line([(0, 330), (300, 280), (600, 340), (1080, 240)], fill=(122, 84, 72), width=20)
        blossoms(d, rng, (0, 170, W, 520), 150)
        blossoms(d, rng, (0, 520, W, 880), 40)
    elif scene == "ramen":
        d.rectangle((0, 280, W, 302), fill=(96, 62, 46))
        for i, x in enumerate(range(60, 1020, 192)):  # noren curtain
            d.rounded_rectangle((x, 302, x + 174, 520), radius=10, fill=(196, 52, 52))
            d.text((x + 87, 412), "らーめんや"[i], font=font(88), fill=(255, 244, 228), anchor="mm")
        paper_lantern(d, 90, 560, 52, (226, 60, 56), "麺", font(52)); paper_lantern(d, 990, 560, 52, (226, 60, 56), "麺", font(52))
        d.rounded_rectangle((350, 580, 730, 690), radius=14, fill=(112, 76, 54), outline=(80, 54, 40), width=6)
        d.text((540, 635), "きょうの おすすめ", font=font(44), fill=(255, 236, 200), anchor="mm")
        ramen_bowl(d, 250, 800); ramen_bowl(d, 830, 800)
    elif scene == "shrine":
        for x in (70, 200, 880, 1010):  # pines
            d.rectangle((x - 12, 640, x + 12, 840), fill=(104, 76, 60))
            for k, y in enumerate((470, 540, 610)):
                d.polygon([(x - 92 + k * 12, y + 100), (x, y - 20), (x + 92 - k * 12, y + 100)], fill=(84, 150, 102))
        for _ in range(60):  # autumn leaves
            x, y, r = rng.randint(0, W), rng.randint(200, 620), rng.randint(6, 12)
            d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice([(232, 110, 60), (240, 170, 60), (210, 70, 50)]))
        d.rectangle((350, 380, 392, 880), fill=(206, 56, 50)); d.rectangle((688, 380, 730, 880), fill=(206, 56, 50))  # torii
        d.polygon([(206, 300), (874, 300), (842, 332), (238, 332)], fill=(40, 36, 40))
        d.rectangle((262, 332, 818, 374), fill=(206, 56, 50)); d.rectangle((326, 462, 754, 500), fill=(206, 56, 50))
        d.rectangle((516, 374, 564, 462), fill=(240, 200, 90), outline=(120, 40, 36), width=4)
        d.rectangle((336, 856, 406, 885), fill=(60, 56, 60)); d.rectangle((674, 856, 744, 885), fill=(60, 56, 60))
    elif scene == "fuji":
        for cx, cy in ((190, 360), (860, 330), (520, 300)):
            d.ellipse((cx - 80, cy - 26, cx + 80, cy + 26), fill=(255, 255, 255)); d.ellipse((cx - 36, cy - 48, cx + 40, cy + 8), fill=(255, 255, 255))
        d.polygon([(40, 800), (440, 380), (640, 380), (1040, 800)], fill=(104, 120, 180))
        d.polygon([(440, 380), (640, 380), (684, 470), (630, 445), (590, 500), (545, 455), (500, 505), (455, 450), (396, 470)], fill=(248, 250, 255))
        d.rectangle((0, 760, W, 885), fill=(100, 172, 226))
        for y in range(790, 880, 44):
            for x in range(-40, W, 150):
                d.arc((x + (y % 100), y, x + 100 + (y % 100), y + 30), 200, 340, fill=(220, 244, 255), width=4)
        blossoms(d, rng, (0, 300, 260, 600), 34); blossoms(d, rng, (820, 300, W, 600), 34)
        d.rectangle((90, 520, 104, 780), fill=(122, 84, 72)); d.rectangle((980, 520, 994, 780), fill=(122, 84, 72))
    elif scene == "matsuri":
        for _ in range(45):
            x, y = rng.randint(0, W), rng.randint(130, 520); d.ellipse((x, y, x + 4, y + 4), fill=(255, 255, 255))
        for cx, cy, col in ((250, 470, (255, 214, 90)), (830, 440, (255, 130, 180)), (540, 400, (120, 220, 255))):  # fireworks
            for a in range(0, 360, 30):
                ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
                d.line([(cx + int(34 * ca), cy + int(34 * sa)), (cx + int(90 * ca), cy + int(90 * sa))], fill=col, width=5)
                d.ellipse((cx + int(104 * ca) - 6, cy + int(104 * sa) - 6, cx + int(104 * ca) + 6, cy + int(104 * sa) + 6), fill=col)
        pts = [(x, 300 + int(36 * math.sin(x / 170))) for x in range(0, W + 20, 20)]
        d.line(pts, fill=(60, 44, 50), width=3)
        for x in range(60, W, 120):
            y0 = 300 + int(36 * math.sin(x / 170)) + 4
            d.ellipse((x - 30, y0, x + 30, y0 + 74), fill=rng.choice([(236, 70, 64), (250, 170, 60)])); d.rectangle((x - 12, y0 - 4, x + 12, y0 + 4), fill=(60, 44, 50))
        for sx, name, awn in ((30, "きんぎょ", (236, 70, 64)), (700, "やきそば", (70, 150, 230))):  # food stalls
            d.rectangle((sx, 650, sx + 350, 885), fill=(80, 56, 56))
            for i in range(7):
                col = awn if i % 2 == 0 else (255, 250, 246)
                d.rectangle((sx + i * 50, 620, sx + (i + 1) * 50, 690), fill=col); d.pieslice((sx + i * 50, 660, sx + (i + 1) * 50, 720), 0, 180, fill=col)
            d.text((sx + 175, 775), name, font=font(60), fill=(255, 236, 190), anchor="mm")
    elif scene == "arcade":
        for _ in range(70):
            x, y = rng.randint(0, W), rng.randint(130, 420); d.rectangle((x, y, x + 4, y + 4), fill=rng.choice([(255, 255, 255), (140, 200, 255), (255, 150, 220)]))
        d.rounded_rectangle((90, 285, 990, 375), radius=22, fill=(24, 20, 60), outline=(255, 90, 200), width=8)
        d.text((540, 330), "ゲームセンター", font=font(56), fill=(255, 230, 90), anchor="mm")
        for x, col in ((40, (255, 90, 160)), (300, (80, 220, 240)), (560, (250, 210, 80)), (820, (160, 120, 255))):
            d.rounded_rectangle((x, 430, x + 220, 885), radius=18, fill=(34, 30, 78), outline=col, width=6)
            d.rectangle((x + 16, 448, x + 204, 500), fill=col)
            d.rounded_rectangle((x + 24, 520, x + 196, 660), radius=10, fill=(14, 16, 40), outline=(120, 120, 160), width=4)
            for k in range(6):
                oy = 540 + (k * 37) % 70; d.rectangle((x + 40 + k * 24, oy, x + 58 + k * 24, oy + 16), fill=col)
            d.line([(x + 70, 745), (x + 70, 710)], fill=(200, 200, 210), width=8); d.ellipse((x + 54, 686, x + 86, 718), fill=(236, 64, 64))
            d.ellipse((x + 120, 722, x + 148, 750), fill=(80, 220, 120)); d.ellipse((x + 158, 700, x + 186, 728), fill=(250, 210, 80))
    elif scene == "aquarium":
        d.rounded_rectangle((330, 282, 750, 342), radius=18, fill=(20, 60, 110)); d.text((540, 312), "すいぞくかん", font=font(38), fill=(220, 240, 250), anchor="mm")
        d.rounded_rectangle((60, 352, 1020, 840), radius=40, fill=(24, 116, 184), outline=(214, 236, 246), width=14)
        d.polygon([(180, 366), (280, 366), (420, 826), (300, 826)], fill=(36, 134, 200)); d.polygon([(560, 366), (680, 366), (800, 826), (680, 826)], fill=(36, 134, 200))
        d.ellipse((250, 540, 760, 680), fill=(96, 126, 170)); d.ellipse((260, 620, 750, 682), fill=(190, 208, 230))
        d.polygon([(740, 610), (840, 540), (862, 566), (800, 620), (862, 676), (836, 700)], fill=(96, 126, 170))
        d.polygon([(450, 666), (520, 744), (546, 672)], fill=(96, 126, 170)); d.ellipse((312, 598, 328, 614), fill=(20, 30, 50))
        fish(d, 120, 420, (250, 160, 60), 0.9); fish(d, 860, 450, (255, 120, 150), 0.8, True); fish(d, 170, 740, (250, 220, 90), 0.7); fish(d, 800, 770, (120, 230, 200), 0.8, True)
        jellyfish(d, 540, 440, (250, 170, 220)); jellyfish(d, 930, 640, (190, 170, 250))
        for bx, by, br in ((100, 600, 10), (120, 560, 7), (960, 500, 9), (940, 460, 6), (610, 400, 8)):
            d.ellipse((bx - br, by - br, bx + br, by + br), outline=(214, 240, 252), width=3)
        for x in (110, 190, 890, 970):
            d.line([(x + (12 if (y // 30) % 2 else -12), y) for y in range(826, 690, -30)], fill=(60, 170, 110), width=10)
    elif scene == "onsen":
        for i, x in enumerate(range(60, 1020, 60)):  # wooden fence
            d.rectangle((x, 306, x + 54, 640), fill=(150, 104, 72) if i % 2 == 0 else (132, 90, 62))
        d.rectangle((40, 284, 1040, 312), fill=(100, 66, 48)); d.rectangle((40, 630, 1040, 660), fill=(100, 66, 48))
        d.rounded_rectangle((440, 330, 640, 560), radius=8, fill=(52, 96, 170)); d.text((540, 445), "ゆ", font=font(150), fill=(255, 255, 255), anchor="mm")
        d.ellipse((40, 670, 1040, 940), fill=(132, 206, 226))
        for t in range(180, 361, 8):
            sx, sy = 540 + int(500 * math.cos(math.radians(t))), 805 + int(135 * math.sin(math.radians(t))); r = rng.randint(18, 30)
            d.ellipse((sx - r, sy - r, sx + r, sy + r), fill=rng.choice([(170, 166, 160), (150, 146, 142), (186, 182, 176)]))
        for x in (210, 430, 680, 880):
            steam(d, x, 700, 3, (246, 250, 252), 7)
        for lx, ly in ((300, 800), (700, 830), (860, 780)):
            d.ellipse((lx - 16, ly - 9, lx + 16, ly + 9), fill=(214, 84, 56))
    elif scene == "snow":
        d.polygon([(0, 560), (230, 390), (470, 560)], fill=(200, 214, 238)); d.polygon([(380, 560), (700, 360), (1000, 560)], fill=(186, 204, 232)); d.polygon([(720, 560), (940, 420), (1080, 520), (1080, 560)], fill=(206, 218, 240))
        d.polygon([(190, 430), (230, 390), (270, 430), (240, 420), (220, 440)], fill=(255, 255, 255)); d.polygon([(630, 420), (700, 360), (770, 420), (720, 408), (690, 440)], fill=(255, 255, 255))
        d.ellipse((-200, 700, 700, 1000), fill=(250, 252, 255)); d.ellipse((400, 720, 1300, 1000), fill=(250, 252, 255))
        for hx in (90, 820):
            d.rectangle((hx, 640, hx + 170, 800), fill=(176, 120, 88)); d.polygon([(hx - 16, 646), (hx + 85, 556), (hx + 186, 646)], fill=(250, 252, 255), outline=(200, 210, 226))
            d.rectangle((hx + 20, 690, hx + 70, 740), fill=(255, 222, 130)); d.rectangle((hx + 110, 700, hx + 150, 800), fill=(110, 74, 56))
        for x in (350, 730):
            d.rectangle((x - 10, 700, x + 10, 800), fill=(104, 76, 60))
            for k, y in enumerate((560, 620, 680)):
                d.polygon([(x - 80 + k * 10, y + 90), (x, y - 20), (x + 80 - k * 10, y + 90)], fill=(70, 130, 96)); d.polygon([(x - 36, y + 20), (x, y - 20), (x + 36, y + 20)], fill=(250, 252, 255))
        d.ellipse((490, 750, 590, 850), fill=(255, 255, 255), outline=(196, 206, 222), width=3); d.ellipse((510, 690, 570, 750), fill=(255, 255, 255), outline=(196, 206, 222), width=3)
        d.ellipse((528, 710, 536, 718), fill=(40, 40, 50)); d.ellipse((546, 710, 554, 718), fill=(40, 40, 50)); d.polygon([(540, 722), (578, 728), (540, 734)], fill=(246, 130, 50))
        d.rectangle((514, 744, 566, 756), fill=(226, 70, 70))
        for _ in range(120):
            x, y, r = rng.randint(0, W), rng.randint(170, 880), rng.randint(3, 7); d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255))
    elif scene == "bakery":
        for i in range(10):  # striped awning
            col = (240, 150, 170) if i % 2 == 0 else (255, 250, 246)
            d.rectangle((40 + i * 100, 280, 40 + (i + 1) * 100, 330), fill=col); d.pieslice((40 + i * 100, 300, 40 + (i + 1) * 100, 360), 0, 180, fill=col)
        d.rounded_rectangle((340, 390, 740, 480), radius=20, fill=(120, 76, 52)); d.text((540, 435), "パンや", font=font(64), fill=(255, 236, 200), anchor="mm")
        d.rectangle((60, 540, 1020, 850), fill=(246, 226, 196))
        for y in (690, 830):
            d.rectangle((60, y, 1020, y + 16), fill=(150, 104, 72))
            for i, x in enumerate(range(90, 960, 120)):
                k = (i + (y // 100)) % 3
                if k == 0:
                    d.rounded_rectangle((x, y - 60, x + 90, y), radius=30, fill=(222, 160, 84))
                    for s in (24, 44, 64): d.line([(x + s, y - 46), (x + s - 8, y - 18)], fill=(170, 110, 52), width=4)
                elif k == 1:
                    d.rounded_rectangle((x, y - 34, x + 110, y), radius=17, fill=(226, 176, 96))
                    for s in (22, 50, 78): d.line([(x + s, y - 28), (x + s - 6, y - 6)], fill=(170, 110, 52), width=4)
                else:
                    d.pieslice((x, y - 70, x + 90, y + 20), 180, 360, fill=(232, 170, 80))
                    for s in (24, 45, 66): d.line([(x + s, y - 66), (x + s, y - 4)], fill=(176, 116, 54), width=4)
    elif scene == "rainy":
        for x in range(-30, W, 170):
            hh = rng.randint(220, 480); d.rectangle((x, TABLE_TOP - hh, x + 150, TABLE_TOP), fill=(84, 94, 124))
            for wy in range(TABLE_TOP - hh + 24, TABLE_TOP - 30, 54):
                for wx in (x + 20, x + 80):
                    d.rectangle((wx, wy, wx + 34, wy + 30), fill=(250, 226, 150) if rng.random() < 0.4 else (150, 164, 196))
        for _ in range(260):
            x, y = rng.randint(0, W), rng.randint(170, 880); d.line([(x, y), (x - 10, y + 34)], fill=(214, 226, 246), width=2)
        d.line([(980, 420), (980, 880)], fill=(60, 64, 80), width=14); d.ellipse((940, 380, 1020, 450), fill=(255, 236, 170))
        d.pieslice((300, 300, 780, 620), 180, 360, fill=(236, 96, 110))
        for i in range(4):
            d.pieslice((300 + i * 120, 430, 420 + i * 120, 490), 0, 180, fill=(236, 96, 110))
        for k in range(1, 4):
            d.line([(540, 300), (300 + k * 120, 462)], fill=(196, 64, 80), width=3)
        d.line([(540, 300), (540, 600)], fill=(70, 50, 56), width=10); d.arc((510, 570, 570, 630), 0, 180, fill=(70, 50, 56), width=10)
        for px, py in ((180, 840), (700, 850)):
            d.ellipse((px - 110, py - 14, px + 110, py + 22), fill=(150, 168, 204)); d.ellipse((px - 50, py - 6, px + 50, py + 14), outline=(220, 232, 250), width=3)
    elif scene == "karaoke":
        for pts, col in (([(540, 340), (150, 880), (330, 880)], (96, 52, 132)), ([(540, 340), (460, 880), (640, 880)], (124, 58, 132)), ([(540, 340), (750, 880), (930, 880)], (96, 52, 132))):
            d.polygon(pts, fill=col)
        d.rounded_rectangle((130, 450, 950, 700), radius=20, fill=(12, 14, 40), outline=(255, 255, 255), width=8)
        d.text((540, 510), "カラオケ", font=font(70), fill=(255, 230, 90), anchor="mm")
        d.rectangle((200, 580, 880, 600), fill=(255, 150, 210)); d.rectangle((200, 624, 640, 644), fill=(255, 255, 255)); d.rectangle((200, 624, 430, 644), fill=(255, 230, 90))
        d.line([(540, 252), (540, 300)], fill=(200, 204, 224), width=4); d.ellipse((496, 300, 584, 388), fill=(200, 204, 224))
        for k in (322, 344, 366): d.line([(500, k), (580, k)], fill=(150, 154, 180), width=2)
        for k in range(-1, 2): d.line([(540 + k * 22, 302), (540 + k * 22, 386)], fill=(150, 154, 180), width=2)
        for _ in range(26):
            x, y = rng.randint(60, 1020), rng.randint(280, 440); d.rectangle((x, y, x + 5, y + 5), fill=rng.choice([(255, 255, 255), (255, 200, 120), (140, 230, 255)]))
        d.rounded_rectangle((60, 740, 1020, 870), radius=40, fill=(190, 60, 110)); d.rounded_rectangle((60, 790, 1020, 880), radius=30, fill=(214, 78, 130))
        for x in (360, 720): d.line([(x, 800), (x, 876)], fill=(160, 44, 90), width=4)
    elif scene == "rooftop":
        d.ellipse((120, 330, 330, 400), fill=(255, 255, 255)); d.ellipse((190, 300, 320, 370), fill=(255, 255, 255)); d.ellipse((720, 360, 940, 430), fill=(255, 255, 255))
        for x in range(-30, W, 120):
            hh = rng.randint(120, 330); d.rectangle((x, 740 - hh, x + 100, 740), fill=(128, 150, 192))
            for wy in range(740 - hh + 16, 720, 36):
                d.rectangle((x + 18, wy, x + 34, wy + 16), fill=(232, 240, 252)); d.rectangle((x + 60, wy, x + 76, wy + 16), fill=(232, 240, 252))
        d.rectangle((790, 420, 960, 560), fill=(170, 176, 190)); d.polygon([(776, 424), (875, 360), (974, 424)], fill=(120, 126, 142))
        for x in (800, 940): d.rectangle((x, 560, x + 10, 740), fill=(120, 126, 142))
        for x in range(40, 1060, 50): d.line([(x, 430), (x, 800)], fill=(92, 102, 122), width=3)
        for y in range(430, 801, 50): d.line([(40, y), (1040, y)], fill=(92, 102, 122), width=3)
        d.rectangle((30, 412, 1050, 430), fill=(70, 80, 100)); d.rectangle((30, 796, 1050, 812), fill=(70, 80, 100))
        for x in (30, 330, 630, 930): d.rectangle((x, 412, x + 16, 812), fill=(70, 80, 100))
    elif scene == "izakaya":
        for x in range(0, W, 90): d.line([(x, 280), (x, 800)], fill=(100, 62, 44), width=4)
        for x in (140, 540, 940): paper_lantern(d, x, 300, 46, (226, 60, 56), "酒", font(48))
        for i, name in enumerate(("やきとり", "ビール", "からあげ", "おでん", "えだまめ")):
            x = 60 + i * 190; d.rectangle((x, 430, x + 170, 520), fill=(250, 238, 214), outline=(150, 100, 70), width=3)
            d.text((x + 85, 475), name, font=font(34), fill=(120, 40, 36), anchor="mm")
        d.rectangle((40, 660, 1040, 680), fill=(84, 54, 40))
        for i, x in enumerate(range(80, 1000, 90)):
            col = ((70, 130, 100), (200, 150, 60), (90, 110, 170), (160, 80, 70))[i % 4]
            d.rounded_rectangle((x, 580, x + 44, 660), radius=8, fill=col); d.rectangle((x + 15, 548, x + 29, 584), fill=col)
    elif scene == "commute":
        d.rectangle((0, 280, W, 885), fill=(226, 232, 240))
        for x in (60, 390, 720):
            d.rounded_rectangle((x, 340, x + 300, 640), radius=16, fill=(150, 208, 250), outline=(150, 160, 176), width=10)
            d.rectangle((x + 10, 570, x + 290, 630), fill=(120, 186, 120)); d.ellipse((x + 210, 370, x + 262, 422), fill=(255, 240, 160)); d.ellipse((x + 40, 380, x + 140, 420), fill=(255, 255, 255))
        d.rectangle((0, 296, W, 310), fill=(190, 196, 208))
        for x in range(90, 1040, 120):
            d.line([(x, 310), (x, 372)], fill=(200, 200, 210), width=4); d.ellipse((x - 24, 360, x + 24, 408), outline=(250, 250, 250), width=7)
        d.rounded_rectangle((20, 700, 1060, 870), radius=30, fill=(70, 140, 196))
        for x in (360, 720): d.line([(x, 710), (x, 860)], fill=(50, 110, 160), width=4)
    elif scene == "sushi":
        d.rounded_rectangle((190, 290, 890, 400), radius=18, fill=(196, 52, 52)); d.text((540, 345), "かいてんずし", font=font(62), fill=(255, 244, 228), anchor="mm")
        for x in (90, 990): paper_lantern(d, x, 430, 40, (236, 70, 64), "寿", font(44))
        d.rectangle((0, 720, W, 800), fill=(214, 216, 224)); d.rectangle((0, 800, W, 830), fill=(150, 154, 166))
        tops = ((250, 140, 110), (220, 70, 84), (250, 222, 110), (246, 160, 90), (240, 240, 236))
        for i, x in enumerate(range(40, 1060, 150)):
            d.ellipse((x, 742, x + 120, 786), fill=(255, 255, 255), outline=((220, 60, 60), (70, 130, 210), (240, 190, 60))[i % 3], width=5)
            d.rounded_rectangle((x + 22, 722, x + 98, 752), radius=14, fill=(250, 250, 246)); d.rounded_rectangle((x + 16, 706, x + 104, 738), radius=14, fill=tops[i % 5])
    elif scene == "bamboo":
        for pts in ([(200, 150), (300, 150), (520, 885), (380, 885)], [(640, 150), (720, 150), (900, 885), (800, 885)]):
            d.polygon(pts, fill=(244, 250, 232))
        for cols, wr, n in (((150, 200, 140), (30, 44), 9), ((110, 176, 104), (40, 60), 7)):
            for k in range(n):
                x = rng.randint(-20, W); w = rng.randint(*wr)
                d.rectangle((x, 170, x + w, TABLE_TOP), fill=cols)
                for y in range(260 + (k * 37) % 80, TABLE_TOP, 120):
                    d.rectangle((x - 2, y, x + w + 2, y + 10), fill=tuple(int(v * 0.78) for v in cols))
        for _ in range(60):
            x, y = rng.randint(0, W), rng.randint(160, 420)
            d.polygon([(x, y), (x + 34, y + 8), (x + 4, y + 16)], fill=rng.choice([(120, 184, 100), (150, 206, 120), (90, 160, 90)]))
    elif scene == "autumn":
        d.ellipse((-300, 560, 500, 1000), fill=(222, 150, 90)); d.ellipse((300, 600, 1300, 1050), fill=(210, 120, 70))
        for tx in (100, 330, 760, 980):
            d.rectangle((tx - 14, 520, tx + 14, 860), fill=(104, 72, 56))
            for ox, oy, rr, col in ((0, -40, 110, (220, 80, 50)), (-80, 20, 80, (240, 150, 50)), (80, 20, 86, (206, 66, 46)), (0, 60, 70, (246, 176, 60))):
                d.ellipse((tx + ox - rr, 420 + oy - rr, tx + ox + rr, 420 + oy + rr), fill=col)
    elif scene == "castle":
        for cx, cy in ((190, 360), (880, 330)):
            d.ellipse((cx - 80, cy - 26, cx + 80, cy + 26), fill=(255, 255, 255)); d.ellipse((cx - 36, cy - 48, cx + 40, cy + 8), fill=(255, 255, 255))
        d.rectangle((0, 790, W, 885), fill=(100, 172, 226))
        for y in range(810, 880, 36):
            for x in range(-40, W, 150): d.arc((x + (y % 90), y, x + 100 + (y % 90), y + 26), 200, 340, fill=(220, 244, 255), width=4)
        d.polygon([(260, 800), (330, 690), (750, 690), (820, 800)], fill=(150, 150, 156))
        for w, y in ((440, 600), (320, 500), (200, 410)):
            d.rectangle((540 - w // 2, y, 540 + w // 2, y + 90), fill=(250, 250, 250), outline=(200, 200, 208), width=3)
            for wx in range(540 - w // 2 + 40, 540 + w // 2 - 30, 70): d.rectangle((wx, y + 30, wx + 22, y + 62), fill=(70, 76, 92))
            d.polygon([(540 - w // 2 - 50, y + 8), (540, y - 52), (540 + w // 2 + 50, y + 8)], fill=(84, 92, 110))
        for x in (90, 990):
            d.rectangle((x - 10, 660, x + 10, 800), fill=(104, 76, 60))
            for k, y in enumerate((520, 580, 640)): d.polygon([(x - 80 + k * 10, y + 90), (x, y - 20), (x + 80 - k * 10, y + 90)], fill=(84, 150, 102))
    elif scene == "sunset":
        d.ellipse((420, 430, 660, 670), fill=(255, 236, 160))
        for cx, cy in ((200, 380), (860, 340)):
            d.ellipse((cx - 90, cy - 24, cx + 90, cy + 24), fill=(255, 200, 170)); d.ellipse((cx - 40, cy - 46, cx + 40, cy + 6), fill=(255, 200, 170))
        d.polygon([(0, 650), (200, 540), (420, 650)], fill=(150, 100, 130)); d.polygon([(600, 650), (860, 520), (1080, 650)], fill=(140, 96, 126))
        d.rectangle((0, 640, W, 885), fill=(240, 150, 120))
        for k, y in enumerate(range(660, 880, 24)):
            half = max(20, 110 - k * 7); d.rectangle((540 - half, y, 540 + half, y + 8), fill=(255, 214, 150))
        d.polygon([(700, 790), (860, 790), (830, 822), (730, 822)], fill=(86, 66, 96)); d.polygon([(780, 700), (780, 788), (850, 788)], fill=(86, 66, 96))
        for bx, by in ((300, 420), (350, 390), (410, 430)):
            d.arc((bx, by, bx + 30, by + 16), 200, 340, fill=(86, 66, 96), width=3); d.arc((bx + 28, by, bx + 58, by + 16), 200, 340, fill=(86, 66, 96), width=3)
    elif scene == "flowers":
        d.ellipse((780, 270, 920, 410), fill=(255, 232, 130))
        for cx, cy in ((260, 340), (560, 300)):
            d.ellipse((cx - 80, cy - 26, cx + 80, cy + 26), fill=(255, 255, 255)); d.ellipse((cx - 36, cy - 48, cx + 40, cy + 8), fill=(255, 255, 255))
        d.ellipse((-300, 560, 600, 1000), fill=(150, 210, 120)); d.ellipse((400, 600, 1400, 1050), fill=(130, 196, 104))
        for y, s, step in ((640, 18, 90), (720, 24, 110), (810, 32, 140)):
            for x in range(40 + (y % 50), W, step): sunflower(d, x, y, s)
    else:
        d.rounded_rectangle((290, 280, 790, 730), radius=36, fill=(255, 255, 255))
        d.rounded_rectangle((310, 300, 770, 710), radius=26, fill=(205, 232, 244))
        d.line([(540, 300), (540, 710)], fill=(255, 255, 255), width=10); d.line([(310, 505), (770, 505)], fill=(255, 255, 255), width=10)
        blossoms(d, rng, (330, 320, 750, 480), 22)
        for x in (110, 970):
            d.line([(x, 0), (x, 190)], fill=(120, 90, 80), width=6)
            d.pieslice((x - 62, 170, x + 62, 300), 180, 360, fill=(240, 170, 120))
    d.rectangle((0, TABLE_TOP, W, H), fill=sc["floor"])
    for y in range(TABLE_TOP + 140, H, 96):
        d.line([(0, y), (W, y)], fill=tuple(int(v * 0.93) for v in sc["floor"]), width=3)
    gcols = GROUND_DECOR.get(scene)
    if gcols:  # fallen petals / leaves on the ground
        gr = random.Random(5)
        for _ in range(90):
            x, y, r = gr.randint(0, W), gr.randint(TABLE_TOP + 130, H - 20), gr.randint(7, 14)
            d.ellipse((x - r, y - r // 2, x + r, y + r // 2), fill=gr.choice(gcols))
    if header:
        ep = f"Ep.{meta['episode']}  ·  " if meta.get("episode") else ""
        d.rounded_rectangle((60, 118, 1020, 252), radius=54, fill=(255, 255, 255, 238))
        d.text((100, 142), meta.get("brand", "TINY JAPANESE")[:28].upper(), font=font(30), fill=BRAND)
        size = 48
        while size > 28 and font(size).getlength(ep + meta["title"]) > 880:
            size -= 2
        d.text((100, 184), ep + meta["title"], font=font(size), fill=(60, 45, 48))
    fg = Image.new("RGBA", (W, 175), (0, 0, 0, 0)); g = ImageDraw.Draw(fg)
    g.rectangle((0, 55, W, 125), fill=sc["table"]); g.rectangle((0, 125, W, 175), fill=sc["edge"])
    if scene in ("cafe", "restaurant"):
        for x in (180, 820):
            g.rounded_rectangle((x, 8, x + 84, 62), radius=14, fill=(255, 255, 255)); g.ellipse((x + 70, 20, x + 110, 50), outline=(255, 255, 255), width=8)
    return bg, fg


# ---------- cards ----------
def card_image(tag, tag_color, parts, min_h=380):
    body = sum(p[3] for p in parts); h = max(min_h, body + 150); cw = 960
    size = (cw + 80, h + 80)
    m = Image.new("L", size, 0); ImageDraw.Draw(m).rounded_rectangle((40, 52, 40 + cw, 52 + h), radius=56, fill=90)
    sh_ = Image.new("RGBA", size, (120, 80, 70, 0)); sh_.putalpha(m.filter(ImageFilter.GaussianBlur(16)))
    d_img = Image.new("RGBA", size, (0, 0, 0, 0)); d_img = Image.alpha_composite(d_img, sh_)
    d = ImageDraw.Draw(d_img); d.rounded_rectangle((40, 40, 40 + cw, 40 + h), radius=56, fill=(255, 253, 250, 245))
    y = 40 + 56 + (h - 56 - 36 - body) / 2
    for text, f, color, adv in parts:
        if f:
            d.text((40 + cw / 2, y), text, font=f, fill=color, anchor="ma")
        y += adv
    p = pill(tag, tag_color); d_img.paste(p, (84, 14), p)
    return d_img


def balanced(text, f, maxw):
    lines = wrap(text, f, maxw)
    if len(lines) == 2 and " " not in text:
        n, best = len(text), None
        for i in range(n // 3, 2 * n // 3 + 1):
            if text[i] in "。、！？，.!?" or text[i - 1] in "（「":
                continue
            sc = abs(f.getlength(text[:i]) - f.getlength(text[i:]))
            if f.getlength(text[:i]) <= maxw and f.getlength(text[i:]) <= maxw and (best is None or sc < best[0]):
                best = (sc, i)
        if best:
            return [text[:best[1]], text[best[1]:]]
    return lines


def line_card(ln):
    maxw = 840
    jp = next((font(s) for s in (62, 56, 50) if font(s).getlength(ln["jp"]) <= maxw), font(56))
    ro, en = font(36, False), font(40, False)
    parts = [(t, jp, (52, 40, 44), 82) for t in balanced(ln["jp"], jp, maxw)] + [("", None, None, 14)]
    parts += [(t, ro, (176, 110, 128), 49) for t in wrap(ln["romaji"], ro, maxw)] + [("", None, None, 18)]
    parts += [(t, en, (90, 78, 80), 54) for t in wrap(ln["en"], en, maxw)]
    return card_image(CHARS[ln["speaker"]]["label"], CHARS[ln["speaker"]]["accent"], parts)


def vocab_card(vocab, active=None):
    parts = []
    for i, v in enumerate(vocab[:5]):
        if active is None:
            jc, sc = (52, 40, 44), (120, 98, 104)
        elif i == active:
            jc, sc = BRAND, (90, 70, 78)
        else:
            jc, sc = (140, 124, 130), (170, 156, 162)
        parts.append((v["jp"], font(50), jc, 64))
        parts.append((f'{v["romaji"]}  –  {v["en"]}', font(31, False), sc, 58))
    return card_image("Today's tiny words", BRAND, parts, min_h=420)


# ---------- weather: animated particles drawn over the scene ----------
WX_Y0, WX_Y1 = 130, TABLE_TOP + 30
WX_BAND = {"bubbles": (370, 830)}  # bubbles stay inside the aquarium tank
WEATHER_KINDS = ("petals", "leaves", "snow", "rain", "wind", "bubbles", "sparks")
WEATHER_ALIASES = {"sakura": "petals", "blossoms": "petals", "petal": "petals", "cherry": "petals", "spring": "petals",
                   "autumn": "leaves", "fall": "leaves", "leaf": "leaves", "momiji": "leaves", "windy": "wind", "breeze": "wind", "gust": "wind",
                   "snowing": "snow", "snowy": "snow", "raining": "rain", "rainy": "rain", "storm": "rain", "fireflies": "sparks",
                   "embers": "sparks", "fireworks": "sparks", "none": "none", "off": "none", "clear": "none", "sunny": "none", "no": "none"}
WEATHER_KEYWORDS = {
    "petals": ["さくら", "桜", "はなみ", "花見", "はる", "春", "sakura", "cherry", "blossom", "petal", "spring"],
    "snow": ["ゆき", "雪", "ふゆ", "冬", "snow", "winter", "blizzard"],
    "rain": ["雨", "あめ", "かさ", "傘", "rain", "umbrella", "drizzle", "storm"],
    "wind": ["かぜ", "風", "wind", "breeze", "gust"],
    "leaves": ["もみじ", "紅葉", "あき", "秋", "autumn", "momiji", "leaves"],
}
WEATHER_BY_SCENE = {"sakura": "petals", "fuji": "petals", "castle": "petals", "shrine": "leaves", "autumn": "leaves", "bamboo": "leaves",
                    "snow": "snow", "rainy": "rain", "park": "wind", "beach": "wind", "station": "wind", "sunset": "wind", "rooftop": "wind",
                    "flowers": "wind", "airport": "wind", "aquarium": "bubbles", "matsuri": "sparks"}
WEATHER_OUTDOOR = {"sakura", "station", "street", "park", "beach", "fuji", "shrine", "snow", "rainy", "matsuri", "sunset", "rooftop",
                   "bamboo", "autumn", "castle", "flowers", "airport"}


def pick_weather(meta, lines, scene):
    """`weather:` in the story wins (petals leaves snow rain wind none ...); otherwise weather words in an outdoor story; otherwise the scene's own."""
    w = (meta.get("weather") or "auto").strip().lower(); w = WEATHER_ALIASES.get(w, w)
    if w == "none":
        return None
    if w in WEATHER_KINDS:
        return w
    if scene in WEATHER_OUTDOOR:
        text = (meta.get("title", "") + " " + " ".join(l["jp"] + " " + l["en"] for l in lines)).lower(); title = meta.get("title", "").lower()
        best, score = None, 0
        for kind, kws in WEATHER_KEYWORDS.items():
            n = sum(kw_count(text, k) + 3 * kw_count(title, k) for k in kws)
            if n > score:
                best, score = kind, n
        if best:
            return best
    return WEATHER_BY_SCENE.get(scene)


def make_weather(kind, scene):
    rng = random.Random(3)
    n, front = dict(petals=(70, 0.22), leaves=(44, 0.2), snow=(130, 0.2), rain=(170, 0.15), wind=(24, 0.15), bubbles=(40, 0.0), sparks=(50, 0.15))[kind]
    leaf_cols = [(130, 190, 100, 240), (170, 214, 120, 240), (110, 170, 90, 240)] if scene == "bamboo" else [c + (240,) for c in LEAF_COLS]
    P = []
    for _ in range(n):
        p = dict(x=rng.uniform(0, W + 120), y=rng.uniform(0, 4000), ph=rng.uniform(0, 6.28), front=rng.random() < front,
                 v=0.0, sw=0.0, f=1.0, r=4.0, drift=0.0, spin=0.0, col=(255, 255, 255, 255), streak=False)
        s = 1.25 if p["front"] else 1.0
        if kind == "petals":
            p.update(v=rng.uniform(55, 110), sw=rng.uniform(30, 80), f=rng.uniform(0.8, 1.8), r=rng.uniform(9, 16) * s, drift=rng.uniform(15, 50), spin=rng.uniform(-3, 3), col=rng.choice(PETAL_COLS) + (235,))
        elif kind == "leaves":
            p.update(v=rng.uniform(60, 120), sw=rng.uniform(40, 90), f=rng.uniform(0.7, 1.5), r=rng.uniform(12, 20) * s, drift=rng.uniform(20, 70), spin=rng.uniform(-4, 4), col=rng.choice(leaf_cols))
        elif kind == "snow":
            r = rng.uniform(2.5, 8) * s; p.update(v=30 + r * 9, sw=rng.uniform(10, 34), f=rng.uniform(0.6, 1.4), r=r, drift=rng.uniform(-8, 8), col=(255, 255, 255, 235))
        elif kind == "rain":
            p.update(v=rng.uniform(1300, 1900), r=rng.uniform(40, 70) * s, col=(214, 226, 246, 210))
        elif kind == "wind":
            if rng.random() < 0.45:
                p.update(streak=True, drift=rng.uniform(500, 900), r=rng.uniform(120, 260), y=rng.uniform(150, 800))
            else:
                p.update(v=rng.uniform(25, 70), sw=rng.uniform(20, 50), f=rng.uniform(1.5, 3), r=rng.uniform(7, 12) * s, drift=rng.uniform(320, 620), spin=rng.uniform(-6, 6),
                         col=rng.choice([(176, 214, 130, 235), (210, 226, 150, 235), (255, 255, 255, 235)]))
        elif kind == "bubbles":
            p.update(x=rng.uniform(170, 1030), v=-rng.uniform(50, 110), sw=rng.uniform(6, 16), f=rng.uniform(1, 2.2), r=rng.uniform(4, 14))  # x - 60 -> 110..970
        elif kind == "sparks":
            p.update(v=-rng.uniform(40, 90), sw=rng.uniform(10, 40), f=rng.uniform(0.8, 1.6), r=rng.uniform(2, 5))
        P.append(p)
    return P


def wx_layer(kind, P, tt, front):
    y0, y1 = WX_BAND.get(kind, (WX_Y0, WX_Y1)); span = y1 - y0
    ov = Image.new("RGBA", (W, WX_Y1 - WX_Y0), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for p in P:
        if p["front"] != front:
            continue
        y = y0 + (p["y"] + p["v"] * tt) % span - WX_Y0
        x = (p["x"] + p["drift"] * tt + p["sw"] * math.sin(tt * p["f"] + p["ph"])) % (W + 120) - 60
        r = p["r"]
        if kind in ("petals", "leaves") or (kind == "wind" and not p["streak"]):
            a = p["ph"] + tt * p["spin"]; ca, sa = math.cos(a), math.sin(a); wd = 0.55 if kind == "petals" else 0.7
            d.polygon([(x + ca * r, y + sa * r), (x - sa * r * wd, y + ca * r * wd), (x - ca * r, y - sa * r), (x + sa * r * wd, y - ca * r * wd)], fill=p["col"])
        elif kind == "wind":
            pts = [(x - r + r * k / 8, y + 7 * math.sin(k * 0.9 + tt * 3 + p["ph"])) for k in range(9)]
            d.line(pts, fill=(255, 255, 255, 150), width=3)
        elif kind == "snow":
            d.ellipse((x - r, y - r, x + r, y + r), fill=p["col"])
        elif kind == "rain":
            d.line([(x, y), (x - 0.18 * r, y + r)], fill=p["col"], width=3 if front else 2)
        elif kind == "bubbles":
            d.ellipse((x - r, y - r, x + r, y + r), outline=(224, 246, 255, 210), width=2); d.ellipse((x - r * 0.5, y - r * 0.55, x - r * 0.15, y - r * 0.2), fill=(255, 255, 255, 220))
        elif kind == "sparks":
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 206, 110, int(150 + 100 * math.sin(tt * 6 + p["ph"]))))
    if kind == "rain" and not front:  # splashes where the rain hits the ground
        for k in range(10):
            u = (tt * 1.5 + k * 0.37) % 1; rr = 6 + 30 * u; sx = (k * 197 + 90) % W; sy = WX_Y1 - WX_Y0 - 22 - (k % 3) * 8
            d.ellipse((sx - rr, sy - rr * 0.3, sx + rr, sy + rr * 0.3), outline=(230, 238, 250, int(210 * (1 - u))), width=2)
    return ov


def draw_wedang_demo(fr, tt, stage):
    """Small looping ginger-tea illustration for the Javanese demo's lower band."""
    d = ImageDraw.Draw(fr)
    bob = int(5 * math.sin(tt * 2.4))
    # Ginger roots sit beside a warm cup; steam rises continuously.
    for x, y, angle in ((278, 1720 + bob, -1), (786, 1750 - bob, 1)):
        d.line((x, y, x + angle * 82, y - 30, x + angle * 118, y - 4), fill=(167, 112, 58), width=30, joint="curve")
        d.ellipse((x - 24, y - 16, x + 23, y + 16), fill=(196, 145, 79))
        d.ellipse((x + angle * 65 - 10, y - 40, x + angle * 65 + 10, y - 20), fill=(196, 145, 79))
    # Cup appears as the recipe reaches serving; its handle rocks slightly.
    if stage >= 1:
        cx, cy = 540, 1740 + bob
        d.ellipse((cx - 145, cy - 66, cx + 145, cy + 156), fill=(255, 250, 237), outline=(142, 91, 61), width=8)
        d.ellipse((cx - 112, cy - 58, cx + 112, cy - 22), fill=(133, 79, 43), outline=(142, 91, 61), width=6)
        d.arc((cx + 115, cy - 35, cx + 230, cy + 90), -85, 85, fill=(142, 91, 61), width=16)
        d.arc((cx + 130, cy - 18, cx + 214, cy + 72), -85, 85, fill=(255, 250, 237), width=8)
        if stage == 1:
            d.arc((cx - 45, cy + 28, cx + 45, cy + 98), int(tt * 110) % 180, int(tt * 110) % 180 + 140, fill=(232, 181, 87), width=9)
        for i, x in enumerate((cx - 48, cx, cx + 48)):
            sway = int(14 * math.sin(tt * 3 + i * 1.8))
            d.arc((x - 18 + sway, cy - 156 - i * 12, x + 18 + sway, cy - 88 - i * 12), 190, 345, fill=(255, 255, 255), width=8)


# ---------- main ----------
def build(story, rate, dummy, tmp):
    meta, lines, vocab = parse_story(story)
    context = (meta.get("title", "") + " " + " ".join(line["jp"] + " " + line["en"] for line in lines)).lower()
    if meta.get("language") == "jv" and "jahe" in context:
        meta["context_animation"] = "ginger-tea"
    voices = {"ja": (F_VOICE, M_VOICE), "en": ("en-US-AriaNeural", "en-US-GuyNeural"), "en-GB": ("en-GB-SoniaNeural", "en-GB-RyanNeural"), "id": ("id-ID-GadisNeural", "id-ID-ArdiNeural"), "jv": ("jv-ID-SitiNeural", "jv-ID-DimasNeural")}
    if meta.get("language", "ja") not in voices:
        sys.exit("Unsupported language. Choose ja, en, en-GB, id, or jv.")
    if meta.get("language", "ja") == "en":
        # English voices follow the character's gender, not the slot: the
        # right-hand slot used to always get the male Guy voice, so a woman
        # cast there sounded male. Distinct voices per gender so two women
        # (or two men) still sound different from each other.
        en_voices = {"female": ["en-US-AriaNeural", "en-US-JennyNeural"],
                     "male": ["en-US-GuyNeural", "en-US-EricNeural"]}
        seen = {"female": 0, "male": 0}
        for slot in ("Mika", "Alex"):
            v = CHARS[slot].get("voice")
            gender = "female" if v == F_VOICE else "male" if v == M_VOICE else None
            if gender is None:
                # unknown voice: keep the slot default for this language
                CHARS[slot]["voice"] = voices["en"][0 if slot == "Mika" else 1]
            else:
                options = en_voices[gender]
                CHARS[slot]["voice"] = options[min(seen[gender], len(options) - 1)]
                seen[gender] += 1
    else:
        for slot, voice in zip(("Mika", "Alex"), voices[meta.get("language", "ja")]):
            CHARS[slot]["voice"] = voice
    chunks, t = [np.zeros(int(0.6 * SR), np.float32)], 0.6
    for i, ln in enumerate(lines):
        wav = os.path.join(tmp, f"l{i}.wav"); synth(ln["jp"], ln["speaker"], wav, rate, dummy, lang=meta.get("language", "ja"))
        x = read_wav(wav); ln["start"], ln["end"] = t, t + len(x) / SR
        chunks += [x, np.zeros(int(0.5 * SR), np.float32)]; t = ln["end"] + 0.5
    # Key words: say each one out loud (Japanese, then its English meaning, then Japanese again).
    vocab = vocab[:5]
    vstart, talk = t, list(lines)
    for j, v in enumerate(vocab):
        jp_say = re.sub(r"[〜~]+", "、", v["jp"]).strip("、 ") or v["jp"]
        en_say = "means " + v["en"].replace("~", "something")
        steps = [(jp_say, "jp"), (en_say, "en"), (jp_say, "jp")]
        v["start"] = t
        for k, (txt, kind) in enumerate(steps):
            wav = os.path.join(tmp, f"v{j}_{k}.wav")
            if kind == "jp":
                synth(txt, "Mika", wav, "-25%", dummy)
            else:
                synth(txt, "Narrator", wav, "+0%", dummy, voice="en-US-AriaNeural", lang="en")
            x = read_wav(wav)
            if kind == "jp":
                talk.append(dict(speaker="Mika", start=t, end=t + len(x) / SR))
            gap = 0.45 if k < 2 else 0.9
            chunks += [x, np.zeros(int(gap * SR), np.float32)]; t += len(x) / SR + gap
        v["end"] = t
    total = t + (0.6 if vocab else 1.2)
    chunks.append(np.zeros(int((total - t) * SR) + SR, np.float32))
    audio = np.concatenate(chunks); audio = audio / max(0.01, np.abs(audio).max()) * 0.9
    n = int(total * FPS); mouth = mouth_levels(audio, n)
    meta["scene"] = pick_scene(meta, lines)
    print("Scene:", meta["scene"])
    bg, fg = make_scene(meta["scene"], meta)
    wx = pick_weather(meta, lines, meta["scene"]); print("Weather:", wx or "none")
    wxp = make_weather(wx, meta["scene"]) if wx else None
    cards = [line_card(l) for l in lines]; vcards = [vocab_card(vocab, j) for j in range(len(vocab))]
    pills = {(nm, a): pill(CHARS[nm]["label"], CHARS[nm]["accent"] if a else (226, 214, 206), (255, 255, 255) if a else (130, 112, 108))
             for nm in CHARS for a in (0, 1)}

    def frame(i):
        tt = i / FPS; fr = bg.copy()
        if wx:
            fr.alpha_composite(wx_layer(wx, wxp, tt, False), (0, WX_Y0))
        cur = next((k for k, l in enumerate(talk) if l["start"] - 0.02 <= tt <= l["end"] + 0.1), None)
        for nm, c in CHARS.items():
            sp = cur is not None and talk[cur]["speaker"] == nm
            bob = 6 * abs(math.sin(tt * 7)) if sp and mouth[i] else 2 * math.sin(tt * 2 + (0 if nm == "Mika" else 1.7))
            blink = ((i + (0 if nm == "Mika" else 41)) % 97) < 4
            s = sprite(nm, int(mouth[i]) if sp else 0, blink)
            fr.paste(s, (c["x"], int(CHAR_Y - bob)), s)
            p = pills[(nm, int(sp))]; fr.paste(p, (c["x"] + s.width // 2 - p.width // 2, 330), p)
        fr.paste(fg, (0, TABLE_TOP - 55), fg)
        if wx:
            fr.alpha_composite(wx_layer(wx, wxp, tt, True), (0, WX_Y0))
        card, t0 = None, 0
        if tt >= vstart and vcards:
            j = max((j for j, v in enumerate(vocab) if tt >= v["start"]), default=0)
            card, t0 = vcards[j], vstart
        else:
            k = max((k for k, l in enumerate(lines) if tt >= l["start"] - 0.02), default=None)
            if k is not None:
                card, t0 = cards[k], lines[k]["start"]
        if card:
            f = min(1, (tt - t0) / 0.2); dy = int(24 * (1 - f))
            if f < 1:
                card = card.copy(); card.putalpha(card.getchannel("A").point(lambda v: int(v * f)))
            fr.paste(card, (20, CARD_Y - 40 + dy), card)
        if meta.get("context_animation") == "ginger-tea":
            stage = next((k for k, line in enumerate(lines) if tt <= line["end"] + 0.5), len(lines) - 1)
            draw_wedang_demo(fr, tt, min(2, stage))
        return fr.convert("RGB")

    return meta, lines, audio, n, frame


def landscape_frame(portrait, meta, lines, t):
    """Keep the illustrated scene at left and redraw the active dialogue at right."""
    image = Image.new("RGB", (1920, 1080), (244, 236, 228))
    image.paste(portrait.crop((0, 0, W, 1000)).resize((1080, 1080), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(image)
    d.rectangle((1080, 0, 1094, 1080), fill=BRAND)
    d.text((1150, 74), meta.get("brand", "STORY STUDIO").upper()[:28], font=font(34), fill=BRAND)
    title = meta["title"]
    size = 62
    while size > 36 and font(size).getlength(title) > 700:
        size -= 2
    d.text((1150, 132), title, font=font(size), fill=(52, 40, 44))
    d.rounded_rectangle((1135, 260, 1870, 900), radius=48, fill=(255, 253, 250))
    line = next((line for line in reversed(lines) if t >= line["start"] - 0.02), None)
    if line:
        name = CHARS[line["speaker"]]["label"]
        color = CHARS[line["speaker"]]["accent"]
        d.rounded_rectangle((1185, 295, 1185 + int(font(34).getlength(name)) + 60, 355), radius=30, fill=color)
        d.text((1215, 306), name, font=font(34), fill=(255, 255, 255))
        size = 62
        while size > 28:
            face = font(size)
            rows = wrap(line["jp"], face, 630)
            if len(rows) * (size + 16) <= 340:
                break
            size -= 2
        y = 420 + max(0, (340 - len(rows) * (size + 16)) // 2)
        for row in rows:
            d.text((1502, y), row, font=face, fill=(52, 40, 44), anchor="ma")
            y += size + 16
        if line["en"]:
            for row in wrap(line["en"], font(32, False), 640)[:2]:
                d.text((1502, y + 24), row, font=font(32, False), fill=(130, 105, 112), anchor="ma")
                y += 45
    return image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story"); ap.add_argument("-o", "--out", default="output/video.mp4")
    ap.add_argument("--rate", default="-12%", help="speech speed, e.g. -12%% (slower) or +0%%")
    ap.add_argument("--dummy-audio", action="store_true", help="skip TTS (for testing)")
    ap.add_argument("--preview", help="save one PNG frame and exit")
    ap.add_argument("--srt", help="write timed dialogue subtitles")
    ap.add_argument("--layout", choices=("portrait", "landscape"), default="portrait")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        meta, lines, audio, n, frame = build(a.story, a.rate, a.dummy_audio, tmp)
        if a.srt:
            def stamp(t):
                ms = round(t * 1000); h, rem = divmod(ms, 3600000); m, rem = divmod(rem, 60000); s, ms = divmod(rem, 1000)
                return f"{h:02}:{m:02}:{s:02},{ms:03}"
            with open(a.srt, "w", encoding="utf-8") as subtitles:
                for i, line in enumerate(lines, 1):
                    subtitles.write(f"{i}\n{stamp(line['start'])} --> {stamp(line['end'])}\n{line['jp']}\n\n")
        if a.preview:
            l = lines[min(1, len(lines) - 1)]; tt = l["start"] + 0.5
            image = frame(int(tt * FPS))
            (landscape_frame(image, meta, lines, tt) if a.layout == "landscape" else image).save(a.preview)
            return
        wav = os.path.join(tmp, "final.wav"); write_wav(wav, audio)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        size = "1920x1080" if a.layout == "landscape" else f"{W}x{H}"
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size,
                              "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", a.out],
                             stdin=subprocess.PIPE)
        for i in range(n):
            image = frame(i)
            p.stdin.write((landscape_frame(image, meta, lines, i / FPS) if a.layout == "landscape" else image).tobytes())
        p.stdin.close(); p.wait()
        print(f"Wrote {a.out} ({n / FPS:.1f}s)")


if __name__ == "__main__":
    main()
