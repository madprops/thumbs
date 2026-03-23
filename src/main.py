import os
import sys
import argparse
import time
import subprocess
import json
import math
import shutil

import cv2
from PIL import Image, ImageDraw, ImageFont

# --- Configuration & Constants ---
DEFAULT_COLUMNS = 4
DEFAULT_ROWS = 4
DEFAULT_THUMB_WIDTH = 500
DEFAULT_MARGIN = 5

# Updated Dark Theme Colors
TEXT_COLOR = (240, 240, 240)         # Off-white text
BG_COLOR = (30, 30, 30)              # Dark gray for header background
GRID_BG_COLOR = (15, 15, 15)         # Almost black for the thumbnail grid background
TIMESTAMP_BG_COLOR = (0, 0, 0, 180)  # Darker semi-transparent black for timestamps
TIMESTAMP_TEXT_COLOR = (255, 255, 255) # White

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".mpeg", ".webm")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FONT_PATH = os.path.join(SCRIPT_DIR, "RobotoMono-Regular.ttf")

possible_fonts = [
    LOCAL_FONT_PATH,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf"
]

SELECTED_FONT_PATH = next((f for f in possible_fonts if os.path.exists(f)), None)

# --- Helper Functions ---

def resolve_target(target):
    if not target:
        return None
    if os.path.isabs(target):
        return os.path.abspath(target)

    cwd_path = os.path.abspath(target)
    if os.path.exists(cwd_path):
        return cwd_path

    shell_pwd = os.environ.get('PWD')
    if shell_pwd:
        pwd_path = os.path.abspath(os.path.join(shell_pwd, target))
        if os.path.exists(pwd_path):
            return pwd_path

    return cwd_path

def get_unique_filename(base_path, extension):
    directory = os.path.dirname(base_path)
    filename = os.path.basename(base_path)
    name, ext = os.path.splitext(filename)
    final_path = os.path.join(directory, f"{name}{extension}")
    counter = 1

    while os.path.exists(final_path):
        counter += 1
        final_path = os.path.join(directory, f"{name}({counter}){extension}")

    return final_path

def get_video_info(video_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("Error: ffmpeg/ffprobe not found. Please install them and ensure they're in your PATH.")
        return None

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error running ffprobe: {stderr.strip()}")
            return None

        metadata = json.loads(stdout)
        format_info = metadata.get("format", {})

        # Duration calculation
        duration_s = format_info.get("duration")

        if not duration_s:
            for stream in metadata.get("streams", []):
                if stream.get("codec_type") == "video" and "duration" in stream:
                    duration_s = stream["duration"]
                    break

        if not duration_s:
            return None

        duration = float(duration_s)
        total_seconds = int(duration)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Size calculation
        file_size_bytes = int(format_info.get("size", 0))
        file_size_mb = file_size_bytes / (1024 * 1024)

        if file_size_mb > 0:
            size_str = f"{file_size_mb:.0f} MB"
        else:
            size_str = "N/A"

        # Bitrate calculation (Overall)
        bitrate_bps = int(format_info.get("bit_rate", 0))

        if bitrate_bps > 0:
            bitrate_kbps = bitrate_bps / 1000
            bitrate_str = f"{bitrate_kbps:.0f} kb/s"
        else:
            bitrate_str = "N/A"

        # Stream specifics
        v_stream = next((s for s in metadata.get("streams", []) if s.get("codec_type") == "video"), {})
        a_stream = next((s for s in metadata.get("streams", []) if s.get("codec_type") == "audio"), {})

        width = v_stream.get("width", 0)
        height = v_stream.get("height", 0)

        if width and height:
            resolution_str = f"{width}x{height}"
        else:
            resolution_str = "N/A"

        # FPS evaluation
        fps_str = v_stream.get("r_frame_rate", "0/1")

        if "/" in fps_str:
            num, den = fps_str.split("/")
            if int(den) != 0:
                fps = round(int(num) / int(den), 3)
            else:
                fps = "N/A"
        else:
            fps = fps_str

        # Aspect Ratio
        aspect_ratio = v_stream.get("display_aspect_ratio", "N/A")

        if aspect_ratio == "N/A" or aspect_ratio == "0:1":
            if width and height:
                gcd = math.gcd(width, height)
                aspect_ratio = f"{width // gcd}:{height // gcd}"

        # Audio formatting
        a_rate = a_stream.get("sample_rate", "N/A")

        if a_rate != "N/A":
            a_rate_str = f"{a_rate} Hz"
        else:
            a_rate_str = "N/A"

        return {
            "filename": os.path.basename(video_path),
            "duration_s": duration,
            "length": duration_str,
            "size": size_str,
            "bitrate": bitrate_str,
            "resolution": resolution_str,
            "fps": str(fps),
            "v_format": v_stream.get("codec_name", "N/A"),
            "a_format": a_stream.get("codec_name", "N/A"),
            "aspect_ratio": aspect_ratio,
            "a_rate": a_rate_str
        }
    except Exception as e:
        print(f"An unexpected error occurred parsing metadata for {video_path}: {e}")
        return None

def extract_frame_at_time(video_path, time_s, target_width):
    cmd = [
        "ffmpeg",
        "-v", "quiet",
        "-ss", str(time_s),
        "-i", video_path,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-"
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return None
        if not stdout:
            return None

        from io import BytesIO

        pil_image = Image.open(BytesIO(stdout)).convert("RGB")
        w_percent = target_width / float(pil_image.size[0])
        h_size = int(float(pil_image.size[1]) * w_percent)

        try:
            pil_image = pil_image.resize((target_width, h_size), Image.Resampling.LANCZOS)
        except AttributeError:
            pil_image = pil_image.resize((target_width, h_size), Image.ANTIALIAS)
        return pil_image
    except Exception:
        return None

def process_video_file(video_path, output_path, cols, rows, thumb_width, skip_at_start, use_jpg, target_width, target_height, font_size, title_font_size, timestamp_font_size, custom_font_path):
    margin = DEFAULT_MARGIN
    info = get_video_info(video_path)

    if not info:
        print(f"Skipping {video_path}: Could not retrieve metadata.")
        return

    print(f"Processing: {info['filename']} ({info['length']})")

    # Calculate Grid
    total_thumbs = cols * rows

    if info["duration_s"] > skip_at_start:
        duration = info["duration_s"] - skip_at_start
    else:
        duration = info["duration_s"]
        skip_at_start = 0

    interval = duration / (total_thumbs + 1)

    # Resolve active font path
    active_font_path = custom_font_path if custom_font_path else SELECTED_FONT_PATH

    # Initialize fonts with fallback warning
    if active_font_path:
        try:
            font = ImageFont.truetype(active_font_path, font_size)
            title_font = ImageFont.truetype(active_font_path, title_font_size)
            ts_font = ImageFont.truetype(active_font_path, timestamp_font_size)
        except Exception as e:
            print(f"Warning: Failed to load font at {active_font_path} ({e}). Falling back to unscalable default font.")
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            ts_font = ImageFont.load_default()
    else:
        print("Warning: No TrueType font found on your system. Falling back to the default unscalable font. Use --font to specify a .ttf file to enable dynamic sizing.")
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        ts_font = ImageFont.load_default()

    # Define Summary Grid Items
    stats = [
        f"Size: {info['size']}", f"Length: {info['length']}", f"Bitrate: {info['bitrate']}",
        f"Video: {info['v_format']}", f"Res: {info['resolution']}", f"FPS: {info['fps']} fps",
        f"Ratio: {info['aspect_ratio']}", f"Audio: {info['a_format']}", f"Rate: {info['a_rate']}"
    ]

    header_padding_x = 20
    header_padding_y = 20
    line_spacing = 15

    # Calculate Heights
    title_text = f"File: {info['filename']}"
    title_bbox = title_font.getbbox(title_text)

    if title_bbox:
        title_h = title_bbox[3] - title_bbox[1]
    else:
        title_h = title_font_size

    stat_bbox = font.getbbox("Mg")

    if stat_bbox:
        stat_h = stat_bbox[3] - stat_bbox[1]
    else:
        stat_h = font_size

    header_height = int(header_padding_y + title_h + (line_spacing * 2) + (3 * (stat_h + line_spacing)) + header_padding_y)

    # Calculate Layout Sizes
    sample_time = skip_at_start + interval
    sample_thumb = extract_frame_at_time(video_path, sample_time, thumb_width)

    if not sample_thumb:
        print(f"Error: Could not extract sample frame from {video_path}")
        return

    thumb_h = sample_thumb.height
    grid_width = (cols * thumb_width) + ((cols + 1) * margin)
    grid_height = (rows * thumb_h) + ((rows + 1) * margin)
    full_height = header_height + grid_height

    # Create Canvas
    canvas = Image.new("RGB", (grid_width, full_height), GRID_BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Draw Header Background
    draw.rectangle([0, 0, grid_width, header_height], fill=BG_COLOR)

    # Draw Metadata Text
    current_y = header_padding_y
    draw.text((header_padding_x, current_y), title_text, font=title_font, fill=TEXT_COLOR)
    current_y += title_h + (line_spacing * 2)

    col_w = (grid_width - (2 * header_padding_x)) / 3

    for i, stat in enumerate(stats):
        col = i % 3
        row = i // 3
        x = header_padding_x + (col * col_w)
        y = current_y + (row * (stat_h + line_spacing))
        draw.text((x, int(y)), stat, font=font, fill=TEXT_COLOR)

    # Process Thumbnails
    for i in range(total_thumbs):
        time_s = skip_at_start + (interval * (i + 1))
        thumb = extract_frame_at_time(video_path, time_s, thumb_width)

        if thumb:
            col = i % cols
            row = i // cols
            x = (col * thumb_width) + ((col + 1) * margin)
            y = header_height + (row * thumb_h) + ((row + 1) * margin)

            canvas.paste(thumb, (x, y))

            # Draw timestamp on thumbnail
            ts_str = time.strftime("%H:%M:%S", time.gmtime(time_s))
            ts_bbox = ts_font.getbbox(ts_str)

            if ts_bbox:
                ts_w = ts_bbox[2] - ts_bbox[0]
                ts_h = ts_bbox[3] - ts_bbox[1]
            else:
                ts_w = timestamp_font_size * 4
                ts_h = timestamp_font_size

            padding = 6
            ts_x = x + thumb_width - ts_w - (padding * 2) - 5
            ts_y = y + thumb_h - ts_h - (padding * 2) - 5

            draw.rectangle(
                [ts_x, ts_y, ts_x + ts_w + (padding * 2), ts_y + ts_h + (padding * 2)],
                fill=TIMESTAMP_BG_COLOR
            )

            draw.text((ts_x + padding, ts_y + padding), ts_str, font=ts_font, fill=TIMESTAMP_TEXT_COLOR)

    # Apply Image Resizing if provided
    if target_width or target_height:
        orig_w, orig_h = canvas.size

        if target_width:
            new_w = target_width
        else:
            new_w = orig_w

        if target_height:
            new_h = target_height
        else:
            new_h = orig_h

        if target_width and not target_height:
            new_h = int(orig_h * (target_width / orig_w))
        elif target_height and not target_width:
            new_w = int(orig_w * (target_height / orig_h))

        try:
            canvas = canvas.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except AttributeError:
            canvas = canvas.resize((new_w, new_h), Image.ANTIALIAS)

    # Save Output
    if use_jpg:
        ext = ".jpg"
    else:
        ext = ".png"

    if not output_path:
        output_path = get_unique_filename(video_path, ext)
    elif os.path.isdir(output_path):
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = get_unique_filename(os.path.join(output_path, base_name), ext)
    else:
        if not output_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            output_path = f"{output_path}{ext}"

    if use_jpg:
        canvas.save(output_path, "JPEG", quality=90)
    else:
        canvas.save(output_path, "PNG")

    print(f"Saved summary to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate a visual summary contact sheet for video files.")

    parser.add_argument("target", nargs="?", help="A single video file or a directory to process (positional)")
    parser.add_argument("--file", help="Specific single video file to process")
    parser.add_argument("--directory", help="Directory to scan for video files")
    parser.add_argument("--output", help="Output file path, directory, or base name. Appends counter if exists.")
    parser.add_argument("--cols", type=int, default=DEFAULT_COLUMNS, help=f"Number of columns. Default: {DEFAULT_COLUMNS}")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help=f"Number of rows. Default: {DEFAULT_ROWS}")
    parser.add_argument("--thumb-width", type=int, default=DEFAULT_THUMB_WIDTH, help=f"Thumbnail width in pixels. Default: {DEFAULT_THUMB_WIDTH}")
    parser.add_argument("--width", type=int, help="Target total max width of the generated image")
    parser.add_argument("--height", type=int, help="Target total max height of the generated image")
    parser.add_argument("--skip-at-start", type=int, default=20, help="Seconds to skip at the beginning. Default: 20")
    parser.add_argument("--jpg", action="store_true", help="Save the output image as JPG instead of PNG")
    parser.add_argument("--font-size", type=int, default=24, help="Font size for the summary stats. Default: 24")
    parser.add_argument("--title-font-size", type=int, default=32, help="Font size for the title. Default: 32")
    parser.add_argument("--timestamp-font-size", type=int, default=24, help="Font size for thumbnail timestamps. Default: 24")
    parser.add_argument("--font", help="Path to a custom .ttf or .ttc font file to use")

    args = parser.parse_args()

    # Resolve inputs to absolute paths taking into account if wrapper script changed directories
    if args.file:
        abs_file = resolve_target(args.file)
    else:
        abs_file = None

    if args.target:
        abs_target = resolve_target(args.target)
    else:
        abs_target = None

    if args.directory:
        abs_dir = resolve_target(args.directory)
    else:
        abs_dir = None

    if args.output:
        abs_out = resolve_target(args.output)
    else:
        abs_out = None

    video_targets = []

    if abs_file:
        if os.path.isfile(abs_file):
            video_targets.append(abs_file)
        else:
            print(f"Error: The file '{abs_file}' does not exist.")
            sys.exit(1)
    elif abs_target and os.path.isfile(abs_target):
        video_targets.append(abs_target)
    else:
        # Determine directory to scan
        if abs_dir:
            scan_dir = abs_dir
        elif abs_target and os.path.isdir(abs_target):
            scan_dir = abs_target
        else:
            shell_pwd = os.environ.get('PWD')

            if shell_pwd:
                scan_dir = shell_pwd
            else:
                scan_dir = os.getcwd()

        if not os.path.isdir(scan_dir):
            print(f"Error: The directory '{scan_dir}' does not exist.")
            sys.exit(1)

        for root, _, files in os.walk(scan_dir):
            for file in files:
                if file.lower().endswith(VIDEO_EXTENSIONS):
                    video_targets.append(os.path.join(root, file))

    if not video_targets:
        print("No valid video files found to process.")
        sys.exit(0)

    for video in video_targets:
        process_video_file(
            video,
            abs_out,
            args.cols,
            args.rows,
            args.thumb_width,
            args.skip_at_start,
            args.jpg,
            args.width,
            args.height,
            args.font_size,
            args.title_font_size,
            args.timestamp_font_size,
            args.font
        )

if __name__ == "__main__":
    main()