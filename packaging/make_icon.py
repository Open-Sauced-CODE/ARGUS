"""Generate a crisp multi-resolution Windows .ico shield icon for ARGUS Desktop."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


def generate_argus_ico(out_path: Path) -> Path:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer peacock shield
    outer = [(128, 12), (228, 48), (216, 142), (128, 244), (40, 142), (28, 48)]
    draw.polygon(outer, fill=(10, 46, 51, 255), outline=(46, 156, 130, 255))

    # Inner emerald shield
    inner = [(128, 42), (198, 68), (188, 138), (128, 210), (68, 138), (58, 68)]
    draw.polygon(inner, fill=(46, 156, 130, 255))

    # Central saffron guardian eye
    draw.ellipse((90, 90, 166, 166), fill=(10, 46, 51, 255))
    draw.ellipse((104, 104, 152, 152), fill=(245, 166, 35, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        out_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return out_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "argus.ico"
    print(f"Generated {generate_argus_ico(target)}")
