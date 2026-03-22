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
DEFAULT_THUMB_WIDTH = 300
DEFAULT_MARGIN = 5

# Updated Font Sizes
FONT_SIZE = 16
TITLE_FONT_SIZE = 22

# Updated Dark Theme Colors
TEXT_COLOR = (240, 240, 240)         # Off-white text
BG_COLOR = (30, 30, 30)              # Dark gray for header background
GRID_BG_COLOR = (15, 15, 15)         # Almost black for the thumbnail grid background
TIMESTAMP_BG_COLOR = (0, 0, 0, 180)  # Darker semi-transparent black for timestamps
TIMESTAMP_TEXT_COLOR = (255, 255, 255) # White

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".mpeg", "webm")

possible_fonts = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]

SELECTED_FONT_PATH = next((f for f in possible_fonts if os.path.exists(f)), None)

# --- Helper Functions ---

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
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
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

        # Duration calculation
        duration_s = metadata.get("format", {}).get("duration")
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
        file_size_bytes = int(metadata.get("format", {}).get("size", 0))
        file_size_mb = file_size_bytes / (1024 * 1024)

        if file_size_mb > 0:
            size_str = f"{file_size_mb:.0f} MB"
        else:
            size_str = "N/A"

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
                aspect_ratio = f"{width//gcd}:{height//gcd}"

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

def draw_timestamp_on_image(image, text):
    draw = ImageDraw.Draw(image)
    if SELECTED_FONT_PATH:
        try:
            font = ImageFont.truetype(SELECTED_FONT_PATH, FONT_SIZE)
        except OSError:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        text_width, text_height = draw.textsize(text, font=font)

    margin_x = 5
    margin_y = 5
    x = image.width - text_width - margin_x
    y = image.height - text_height - margin_y

    padding = 3
    draw.rectangle(
        [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
        fill=TIMESTAMP_BG_COLOR
    )

    draw.text((x, y), text, font=font, fill=TIMESTAMP_TEXT_COLOR)
    return image

def draw_header(info, width):
    if SELECTED_FONT_PATH:
        try:
            title_font = ImageFont.truetype(SELECTED_FONT_PATH, TITLE_FONT_SIZE)
            text_font = ImageFont.truetype(SELECTED_FONT_PATH, FONT_SIZE)
        except OSError:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
    else:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    margin_top = 10
    margin_left = 10
    title_bottom_margin = 8
    line_spacing = FONT_SIZE + 6
    bottom_margin = 10

    # Calculate Title Height dynamically to make it compact
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    try:
        title_bbox = dummy_draw.textbbox((0, 0), info["filename"], font=title_font)
        title_height = title_bbox[3] - title_bbox[1]
    except AttributeError:
        _, title_height = dummy_draw.textsize(info["filename"], font=title_font)

    # Dynamic compact header height
    header_height = margin_top + title_height + title_bottom_margin + (3 * line_spacing) + bottom_margin
    header_img = Image.new("RGB", (width, header_height), BG_COLOR)
    draw = ImageDraw.Draw(header_img)

    current_y = margin_top

    # Draw Title
    draw.text((margin_left, current_y), info["filename"], font=title_font, fill=TEXT_COLOR)
    current_y += title_height + title_bottom_margin

    # Define Column layout
    col1_x = margin_left
    col2_x = margin_left + int(width * 0.33)
    col3_x = margin_left + int(width * 0.66)

    # Row 1
    draw.text((col1_x, current_y), f"Size: {info["size"]}", font=text_font, fill=TEXT_COLOR)
    draw.text((col2_x, current_y), f"FPS: {info["fps"]}", font=text_font, fill=TEXT_COLOR)
    draw.text((col3_x, current_y), f"Aspect ratio: {info["aspect_ratio"]}", font=text_font, fill=TEXT_COLOR)
    current_y += line_spacing

    # Row 2
    draw.text((col1_x, current_y), f"Resolution: {info["resolution"]}", font=text_font, fill=TEXT_COLOR)
    draw.text((col2_x, current_y), f"Video format: {info["v_format"]}", font=text_font, fill=TEXT_COLOR)
    draw.text((col3_x, current_y), f"Audio rate: {info["a_rate"]}", font=text_font, fill=TEXT_COLOR)
    current_y += line_spacing

    # Row 3
    draw.text((col1_x, current_y), f"Length: {info["length"]}", font=text_font, fill=TEXT_COLOR)
    draw.text((col2_x, current_y), f"Audio format: {info["a_format"]}", font=text_font, fill=TEXT_COLOR)

    return header_img

def process_video_file(video_path, output_arg, cols, rows, thumb_width, skip_at_start, use_jpg):
    print(f"\nProcessing {os.path.basename(video_path)}...")

    info = get_video_info(video_path)
    if not info:
        print(f"Warning: Skipped {os.path.basename(video_path)}: Could not extract metadata.")
        return

    duration = info["duration_s"]
    effective_duration = duration - skip_at_start

    if effective_duration <= 0:
        print(f"Warning: Video too short or start skip too long. Skipped.")
        return

    num_thumbs = cols * rows
    intervals = []

    for i in range(num_thumbs):
        t = skip_at_start + (effective_duration / (num_thumbs + 1)) * (i + 1)
        intervals.append(t)

    thumbnails = []
    for t in intervals:
        total_seconds = int(t)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        thumb_pil = extract_frame_at_time(video_path, t, thumb_width)
        if thumb_pil:
            draw_timestamp_on_image(thumb_pil, time_str)
            thumbnails.append(thumb_pil)
        else:
            placeholder = Image.new("RGB", (thumb_width, int(thumb_width * (9/16))), color=(50, 50, 50))
            draw_timestamp_on_image(placeholder, f"{time_str} (err)")
            thumbnails.append(placeholder)

    if not thumbnails:
        print("Warning: No valid frames found. Skipping.")
        return

    # Calculate grid dimensions
    grid_width = (cols * thumb_width) + ((cols + 1) * DEFAULT_MARGIN)
    grid_height = (rows * thumbnails[0].height) + ((rows + 1) * DEFAULT_MARGIN)

    # Create the header to match the grid width
    header_img = draw_header(info, grid_width)

    # Create the final canvas
    final_canvas_height = header_img.height + grid_height
    final_canvas = Image.new("RGB", (grid_width, final_canvas_height), GRID_BG_COLOR)

    # Paste Header
    final_canvas.paste(header_img, (0, 0))

    # Paste Thumbnails
    current_y_offset = header_img.height
    for idx, thumb in enumerate(thumbnails):
        current_col = idx % cols
        current_row = idx // cols

        x_pos = DEFAULT_MARGIN + (current_col * (thumb_width + DEFAULT_MARGIN))
        y_pos = current_y_offset + DEFAULT_MARGIN + (current_row * (thumb.height + DEFAULT_MARGIN))

        final_canvas.paste(thumb, (x_pos, y_pos))

    ext = ".jpg" if use_jpg else ".png"

    if output_arg:
        if os.path.isdir(output_arg):
            out_base = os.path.join(output_arg, f"{info['filename']}{ext}")
        else:
            out_base_name, _ = os.path.splitext(output_arg)
            out_base = f"{out_base_name}{ext}"
    else:
        out_base = os.path.join(os.path.dirname(video_path), f"{info['filename']}{ext}")

    final_output_path = get_unique_filename(out_base, ext)

    if use_jpg:
        final_canvas.save(final_output_path, quality=95)
    else:
        final_canvas.save(final_output_path)

    print(f"Summary saved at: {final_output_path}")

# --- Main Logic ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a visual summary contact sheet for video files.")

    parser.add_argument("target", nargs="?", help="A single video file or a directory to process (positional)")
    parser.add_argument("--file", help="Specific single video file to process")
    parser.add_argument("--directory", help="Directory to scan for video files")
    parser.add_argument("--output", help="Output file path, directory, or base name. Appends counter if exists.")
    parser.add_argument("--cols", type=int, default=DEFAULT_COLUMNS, help=f"Number of columns. Default: {DEFAULT_COLUMNS}")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help=f"Number of rows. Default: {DEFAULT_ROWS}")
    parser.add_argument("--thumb-width", type=int, default=DEFAULT_THUMB_WIDTH, help=f"Thumbnail width in pixels. Default: {DEFAULT_THUMB_WIDTH}")
    parser.add_argument("--skip-at-start", type=int, default=20, help="Seconds to skip at the beginning. Default: 20")
    parser.add_argument("--jpg", action="store_true", help="Save the output image as JPG instead of PNG")

    args = parser.parse_args()

    # Determine the execution targets based on priority
    video_targets = []

    if args.file:
        if os.path.isfile(args.file):
            video_targets.append(args.file)
        else:
            print(f"Error: The file '{args.file}' does not exist.")
            sys.exit(1)
    elif args.target and os.path.isfile(args.target):
        video_targets.append(args.target)
    else:
        # Determine directory to scan
        if args.directory:
            scan_dir = args.directory
        elif args.target and os.path.isdir(args.target):
            scan_dir = args.target
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
            args.output,
            args.cols,
            args.rows,
            args.thumb_width,
            args.skip_at_start,
            args.jpg,
        )