"""程序化像素分析：从截图提取 LED 颜色/曲线/文字渲染的客观证据。"""
import sys
from pathlib import Path
from PIL import Image

SHOTS = Path("/home/jayden/can_monitor/data/shots")


def analyze(path: str):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    red = green = blue = bright = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            r, g, b = px[x, y]
            if r > 150 and g < 110 and b < 110:
                red += 1
            elif g > 150 and r < 110 and b < 110:
                green += 1
            elif b > 160 and r < 130 and g < 130:
                blue += 1
            if r > 180 and g > 180 and b > 180:
                bright += 1
    total = (w // 3) * (h // 3)
    return dict(red=red / total, green=green / total, blue=blue / total,
                bright=bright / total, w=w, h=h)


def main():
    pairs = [
        ("tab_0_overview.png", "tab_0_overview_fault.png"),
        ("tab_1_camera.png", "tab_1_camera_fault.png"),
        ("tab_2_io.png", "tab_2_io_fault.png"),
    ]
    for norm, fault in pairs:
        n, f = analyze(SHOTS / norm), analyze(SHOTS / fault)
        print(f"{norm}: red={n['red']:.4f} green={n['green']:.4f} blue={n['blue']:.4f} bright={n['bright']:.4f}")
        print(f"{fault}: red={f['red']:.4f} green={f['green']:.4f} blue={f['blue']:.4f} bright={f['bright']:.4f}")
        print(f"  red delta={f['red']-n['red']:+.4f}  (故障态红色像素占比应显著上升)")

    for name in ("tab_3_curves.png", "tab_4_log.png"):
        a = analyze(SHOTS / name)
        print(f"{name}: red={a['red']:.4f} green={a['green']:.4f} blue={a['blue']:.4f} bright={a['bright']:.4f}")


if __name__ == "__main__":
    main()