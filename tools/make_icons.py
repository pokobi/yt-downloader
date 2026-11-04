"""アプリと拡張機能のアイコンを生成するスクリプト（Pillow が必要）。

使い方:  python tools/make_icons.py
生成物:  src/ytdl/assets/app.ico, app.png
         extension/icons/icon16.png ... icon128.png
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "ytdl" / "assets"
EXT_ICONS = ROOT / "extension" / "icons"

# 単色（強調色の「録音中の赤」 #d2364a）。グラデーションは使わない
TOP = BOTTOM = (210, 54, 74)


def render(size: int) -> Image.Image:
    s = size * 8  # 高解像度で描いて縮小（アンチエイリアス）
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 角丸四角（TOP と BOTTOM が同じなので単色になる）
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        c = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (s, y)], fill=c)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    cx = s / 2
    # 下向き矢印
    shaft_w = s * 0.14
    d.rectangle([cx - shaft_w / 2, s * 0.20, cx + shaft_w / 2, s * 0.52], fill=white)
    d.polygon([(cx - s * 0.25, s * 0.46), (cx + s * 0.25, s * 0.46), (cx, s * 0.70)], fill=white)
    # 受け皿
    bar_h = s * 0.085
    d.rounded_rectangle([s * 0.24, s * 0.76, s * 0.76, s * 0.76 + bar_h], radius=bar_h / 2, fill=white)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    EXT_ICONS.mkdir(parents=True, exist_ok=True)

    big = render(256)
    big.save(ASSETS / "app.png")
    big.save(ASSETS / "app.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    for n in (16, 32, 48, 128):
        render(n).save(EXT_ICONS / f"icon{n}.png")
    print("icons generated")


if __name__ == "__main__":
    main()
