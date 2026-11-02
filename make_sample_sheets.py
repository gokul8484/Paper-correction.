"""Creates fake 'handwritten-style' answer sheet images in sample_data/ (no real student data)."""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "sample_data")


def make(name, lines):
    img = Image.new("RGB", (1000, 120 + 70 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Oblique.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        d.text((40, 50 + 70 * i), line, fill=(20, 20, 90), font=font)
    img.save(os.path.join(OUT, name))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make("sample_sheet_1.png", [
        "Q1. Photosynthesis uses sunlight, water and carbon dioxide.",
        "Q2. CPU is the brain. It has ALU and control unit.",
        "Q3. Windows and Linux are operating systems."])
    print("Sample sheet images created in sample_data/")
