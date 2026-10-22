import argparse
import datetime
import json
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def make_test_card(test_id: str, timestamp: str, font_path: Path) -> Image.Image:
    image = Image.new("L", (1280, 720), 255)
    draw = ImageDraw.Draw(image)
    large = ImageFont.truetype(str(font_path), 88)
    medium = ImageFont.truetype(str(font_path), 72)
    small = ImageFont.truetype(str(font_path), 34)
    tiny = ImageFont.truetype(str(font_path), 24)
    draw.rectangle((0, 0, 1279, 199), fill=0)
    draw.text((640, 100), "SENT FROM MAC", font=large, fill=255, anchor="mm")
    draw.text((640, 295), test_id, font=medium, fill=0, anchor="mm")
    draw.text((640, 390), "CUSTOM FULL-SCREEN IMAGE", font=small, fill=0, anchor="mm")
    for level in range(16):
        left = 40 + level * 75
        draw.rectangle((left, 475, left + 74, 554), fill=level * 17)
        draw.text((left + 37, 579), str(level), font=tiny, fill=0, anchor="mm")
    draw.rectangle((40, 475, 1239, 554), outline=0, width=2)
    draw.text((640, 623), timestamp, font=tiny, fill=0, anchor="mm")
    draw.text(
        (640, 663),
        "All four corner labels should be visible.",
        font=tiny,
        fill=0,
        anchor="mm",
    )
    draw.text((10, 7), "TL", font=small, fill=255)
    draw.text((1270, 7), "TR", font=small, fill=255, anchor="ra")
    draw.text((10, 706), "BL", font=small, fill=0, anchor="ld")
    draw.text((1270, 706), "BR", font=small, fill=0, anchor="rd")
    draw.rectangle((0, 0, 1279, 719), outline=0, width=4)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a visibly distinct Dory upload test")
    parser.add_argument("--output", type=Path, default=Path("private/mac-test.png"))
    parser.add_argument(
        "--font",
        type=Path,
        default=Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    )
    arguments = parser.parse_args()
    test_id = f"MAC-{uuid.uuid4().hex[:6].upper()}"
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    image = make_test_card(test_id, timestamp, arguments.font)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(arguments.output)
    arguments.output.with_suffix(".json").write_text(
        json.dumps({"test_id": test_id, "created_at": timestamp}, indent=2) + "\n"
    )
    print(f"Created {arguments.output}: SENT FROM MAC / {test_id}")


if __name__ == "__main__":
    main()
