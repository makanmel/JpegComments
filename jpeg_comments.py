"""Burn JPEG COM-marker comments (e.g. legacy FastStone "JPEG Comment" text)
onto a white caption bar appended below each photo in a folder.

FastStone stores comments in the JPEG COM (0xFFFE) segment using the local
ANSI code page - Windows-1251 on Cyrillic systems. Android galleries expect
UTF-8, which is why they show garbage. This script decodes both variants.
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

COM_MARKER = b"\xff\xfe"  # JPEG comment segment
SOS_MARKER = b"\xff\xda"  # Start of Scan - comments always live before it

DEFAULT_FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
MIN_FONT_SIZE = 12
JPEG_EXTENSIONS = (".jpg", ".jpeg")


def find_comment_blocks(data):
    """Return raw byte contents of every JPEG COM segment before SOS."""
    sos = data.find(SOS_MARKER)
    area = data if sos == -1 else data[:sos]
    blocks = []
    index = 0
    while True:
        index = area.find(COM_MARKER, index)
        if index == -1 or index + 4 > len(area):
            return blocks
        length = int.from_bytes(area[index + 2:index + 4], "big")
        blocks.append(area[index + 4:index + 2 + length])
        index += 2 + max(length, 2)


def decode_comment(raw):
    """Prefer UTF-8; fall back to Windows-1251 (FastStone ANSI comments)."""
    text = raw.decode("utf-8", errors="surrogateescape")
    if any("\udc80" <= ch <= "\udcff" for ch in text):
        text = raw.decode("cp1251", errors="replace")
    return text.strip("\x00").strip()


def get_jpeg_comment(path):
    with open(path, "rb") as handle:
        data = handle.read()
    parts = [decode_comment(block) for block in find_comment_blocks(data)]
    return "\n".join(part for part in parts if part)


def load_font(font_path, size):
    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    if os.path.exists(DEFAULT_FONT_PATH):
        return ImageFont.truetype(DEFAULT_FONT_PATH, size)
    return ImageFont.load_default()


def wrap_lines(draw, text, font, max_width):
    """Word-wrap text so every line fits inside max_width pixels."""
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = current + " " + word
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_text(draw, text, font_path, max_width, start_size):
    """Shrink the font until the wrapped text fits the available width."""
    size = start_size
    while size > MIN_FONT_SIZE:
        font = load_font(font_path, size)
        lines = wrap_lines(draw, text, font, max_width)
        widest = max(draw.textlength(line, font=font) for line in lines)
        if widest <= max_width:
            return font, lines
        size -= 4
    font = load_font(font_path, MIN_FONT_SIZE)
    return font, wrap_lines(draw, text, font, max_width)


def burn_comment(img, text, font_path, font_size):
    """Return a new image with a white caption bar containing the comment."""
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    max_width = int(img.width * 0.92)
    start_size = font_size if font_size > 0 else max(MIN_FONT_SIZE, img.width // 45)
    font, lines = fit_text(draw, text, font_path, max_width, start_size)

    spacing = max(4, getattr(font, "size", 12) // 4)
    joined = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), joined, font=font, spacing=spacing)
    text_height = bbox[3] - bbox[1]
    padding = max(10, text_height // 3)
    bar_height = text_height + padding * 2

    out = Image.new("RGB", (img.width, img.height + bar_height), "white")
    out.paste(img, (0, 0))
    out_draw = ImageDraw.Draw(out)
    out_draw.multiline_text(
        (img.width / 2, img.height + padding),
        joined,
        font=font,
        fill="black",
        anchor="ma",
        align="center",
        spacing=spacing,
    )
    return out


def process_folder(folder, output_dir, font_path, font_size, quality, list_only):
    if not list_only:
        os.makedirs(output_dir, exist_ok=True)

    processed = 0
    skipped = 0
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or not name.lower().endswith(JPEG_EXTENSIONS):
            continue
        comment = get_jpeg_comment(path)
        if not comment:
            print(f"  [skip] {name} (no comment)")
            skipped += 1
            continue
        if list_only:
            print(f"{name}: {comment}")
            processed += 1
            continue

        with Image.open(path) as src:
            info = dict(src.info)
            out = burn_comment(src, comment, font_path, font_size)
        save_kwargs = {"quality": quality}
        if "exif" in info:
            save_kwargs["exif"] = info["exif"]
        if "icc_profile" in info:
            save_kwargs["icc_profile"] = info["icc_profile"]
        if "comment" in info:
            save_kwargs["comment"] = info["comment"]
        out.save(os.path.join(output_dir, name), "JPEG", **save_kwargs)
        print(f"  [ok] {name}")
        processed += 1

    print(f"Done: {processed} processed, {skipped} skipped -> {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Burn JPEG COM-marker comments onto a caption bar below each photo."
    )
    parser.add_argument("folder", help="Folder containing the JPEG files")
    parser.add_argument(
        "-o", "--output",
        help="Output folder (default: <folder>/captioned)",
        default=None,
    )
    parser.add_argument("--font", help="Path to a .ttf font file", default=None)
    parser.add_argument(
        "--font-size", type=int, default=0,
        help="Font size in pixels (default: auto, based on image width)",
    )
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality (default: 95)")
    parser.add_argument(
        "--list", action="store_true",
        help="Only print extracted comments, do not write images",
    )
    args = parser.parse_args()

    output_dir = args.output or os.path.join(args.folder, "captioned")
    process_folder(args.folder, output_dir, args.font, args.font_size, args.quality, args.list)


if __name__ == "__main__":
    main()
