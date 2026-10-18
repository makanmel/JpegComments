# JpegComments

Batch tool that reads hidden JPEG comments (the legacy `COM` / `0xFFFE` marker
written by e.g. FastStone Image Viewer's "JPEG Comment" feature) and burns the text
onto a white caption bar appended below each photo.

FastStone writes comments in the local ANSI code page (Windows-1251 on Cyrillic
systems), which is why Android galleries like Aves show garbled text. This tool
decodes UTF-8 and Windows-1251 correctly.

## Setup

```bat
pip install -r requirements.txt
```

## Usage

Preview the extracted comments without writing any files:

```bat
python jpeg_comments.py "C:\Users\User\Pictures\Scans" --list
```

Process the folder (writes copies into `Scans\captioned`, originals untouched):

```bat
python jpeg_comments.py "C:\Users\User\Pictures\Scans"
```

## Options

- `-o`, `--output` - custom output folder (default: `<folder>/captioned`)
- `--font` - path to a `.ttf` file (default: Arial)
- `--font-size` - caption size in pixels (default: auto, scales with image width)
- `--quality` - JPEG quality, 1-100 (default: 95)
- `--list` - print comments only, do not write images

Existing EXIF data, ICC profile and the original hidden comment are preserved
in the output files.
