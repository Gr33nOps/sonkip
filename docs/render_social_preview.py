"""Render the deterministic Open Graph preview used by the Sonkip website."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 630
PAPER = "#f3f0e8"
INK = "#111111"
ORANGE = "#ee4700"
ACID = "#e8ff00"
MUTED = "#6e6b64"


def font(name: str, size: int):
    windows_fonts = Path("C:/Windows/Fonts")
    path = windows_fonts / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def render(output: Path):
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 22, HEIGHT), fill=ORANGE)
    draw.line((72, 64, 1128, 64), fill=INK, width=2)
    draw.text((72, 86), "FREE  ·  OPEN SOURCE  ·  LOCAL LIBRARY", font=font("consola.ttf", 20), fill=MUTED)
    draw.text((66, 150), "sonkip.", font=font("arialbd.ttf", 94), fill=INK)
    draw.text((67, 265), "MUSIC", font=font("arialbd.ttf", 112), fill=INK, stroke_width=1)
    draw.text((67, 365), "DOWNLOADER", font=font("arialbd.ttf", 86), fill=ORANGE)
    draw.text((72, 500), "ANDROID  ·  WINDOWS  ·  MACOS  ·  LINUX", font=font("consolab.ttf", 21), fill=INK)
    draw.text((72, 548), "Find it. Save it. Play it — on your device.", font=font("arial.ttf", 26), fill=MUTED)

    center_x, center_y = 972, 316
    draw.ellipse((center_x - 170, center_y - 170, center_x + 170, center_y + 170), fill=ORANGE)
    center_x -= 14
    center_y -= 14
    draw.ellipse((center_x - 170, center_y - 170, center_x + 170, center_y + 170), fill=INK)
    for radius in range(158, 55, -16):
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            outline="#383832",
            width=3,
        )
    draw.ellipse((center_x - 62, center_y - 62, center_x + 62, center_y + 62), fill=ACID)
    label = "SK"
    label_font = font("arialbd.ttf", 49)
    box = draw.textbbox((0, 0), label, font=label_font)
    draw.text(
        (center_x - (box[2] - box[0]) / 2, center_y - (box[3] - box[1]) / 2 - 5),
        label,
        font=label_font,
        fill=INK,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


if __name__ == "__main__":
    render(Path(__file__).parents[1] / "static" / "sonkip-social.png")
