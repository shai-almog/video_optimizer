import os
import subprocess
import shutil
from pathlib import Path
import argparse
import json


def get_video_stats(file_path):
    """Get video statistics like bitrate, size, and duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=bit_rate",
                "-show_entries",
                "format=size,duration",
                "-of",
                "json",
                file_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise Exception(result.stderr)

        stats = json.loads(result.stdout)
        bitrate = int(stats['streams'][0].get('bit_rate', 0))
        size = int(stats['format'].get('size', 0))
        duration = float(stats['format'].get('duration', 0))

        return bitrate, size, duration
    except Exception as e:
        print(f"Error getting stats for {file_path}: {e}")
        return None, None, None


def convert_video(input_path, output_path, target_bitrate, duration, verbose=False):
    """Convert the video using FFmpeg with specified bitrate."""
    try:
        command = [
            "ffmpeg",
            "-i",
            input_path,
            "-c:v",
            "libx265",
            "-b:v",
            target_bitrate,
            "-c:a",
            "aac",
            "-y",
            output_path,
        ]

        if verbose:
            subprocess.run(command, check=True)
        else:
            command.extend(["-progress", "pipe:1", "-nostats", "-loglevel", "error"])
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
                for line in process.stdout:
                    if "out_time_ms" in line:
                        time_ms = int(line.split("=")[1].strip())
                        progress_seconds = time_ms / 1_000_000
                        progress_percentage = (progress_seconds / duration) * 100
                        print(f"Progress: {progress_percentage:.2f}%", end="\r")
                process.wait()
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, command)

        return True
    except subprocess.CalledProcessError as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        print(f"Error converting {input_path}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during conversion of {input_path}: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False


def process_videos(directory, max_size_mb=200, max_bitrate_kbps=1000, verbose=False):
    """Process videos in a directory, re-encoding them if necessary."""
    max_size_bytes = max_size_mb * 1024 * 1024
    target_bitrate = f"{max_bitrate_kbps}k"
    reasonable_threshold = 1.1  # Allow a 10% margin over the target bitrate

    total_files = 0
    total_size = 0
    converted_files = 0
    converted_size_before = 0
    converted_size_after = 0

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)

            # Skip non-video files
            if not file.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".m4v", ".wmv")):
                continue

            total_files += 1

            print(f"Processing {file_path}...")
            bitrate, size, duration = get_video_stats(file_path)

            if bitrate is None or size is None or duration is None:
                print(f"Skipping {file_path} due to missing stats.")
                continue

            total_size += size

            print(f"Original bitrate: {bitrate // 1000}kbps")
            if size > max_size_bytes and bitrate > (max_bitrate_kbps * 1000 * reasonable_threshold):
                output_path = file_path + ".temp.mp4"
                print(f"File {file_path} ({size // (1024 * 1024)}MB) exceeds thresholds. Starting conversion...")

                if convert_video(file_path, output_path, target_bitrate, duration, verbose):
                    try:
                        new_size = os.path.getsize(output_path)
                        new_bitrate, _, _ = get_video_stats(output_path)
                        print(f"Conversion successful for {file_path}. Size reduced from {size // (1024 * 1024)}MB to {new_size // (1024 * 1024)}MB.")
                        print(f"New bitrate: {new_bitrate // 1000}kbps")
                        os.remove(file_path)
                        shutil.move(output_path, file_path)

                        converted_files += 1
                        converted_size_before += size
                        converted_size_after += new_size
                    except FileNotFoundError:
                        print(f"Conversion failed for {file_path}. Output file not found.")
                else:
                    print(f"Failed to convert {file_path}.")
            else:
                print(f"Skipped {file_path} due to bitrate ({bitrate // 1000}kbps) or size ({size // (1024 * 1024)}MB) being within limits.")

    total_size_gb = total_size / (1024 ** 3)
    converted_size_before_gb = converted_size_before / (1024 ** 3)
    converted_size_after_gb = converted_size_after / (1024 ** 3)
    saved_space_gb = converted_size_before_gb - converted_size_after_gb

    print("\nProcessing Statistics:")
    print(f"Reviewed {total_files} files totaling {total_size_gb:.2f} GB.")
    print(f"Converted {converted_files} files totaling {converted_size_before_gb:.2f} GB, resulting in {converted_size_after_gb:.2f} GB of final files.")
    print(f"Saved {saved_space_gb:.2f} GB of disk space.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize video files in a directory.")
    parser.add_argument(
        "-d", "--directory", default=".", help="Path to the directory to scan (default: current directory)"
    )
    parser.add_argument(
        "-s", "--max-size", type=int, default=200, help="Maximum file size in MB (default: 200MB)"
    )
    parser.add_argument(
        "-b", "--max-bitrate", type=int, default=1000, help="Maximum bitrate in kbps (default: 1000kbps)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose FFmpeg output"
    )
    args = parser.parse_args()

    process_videos(args.directory, args.max_size, args.max_bitrate, args.verbose)
