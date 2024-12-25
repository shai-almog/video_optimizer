import os
import subprocess
import shutil
import platform
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
                "-show_entries",
                "stream=bit_rate:stream_tags=rotate",
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
        rotation = int(stats['streams'][0].get('tags', {}).get('rotate', 0))

        return bitrate, size, duration, rotation
    except Exception as e:
        print(f"Error getting stats for {file_path}: {e}")
        return None, None, None, 0


def convert_video(input_path, output_path, target_bitrate, duration, rotation, verbose=False):
    """Convert the video using FFmpeg with specified bitrate and rotation."""
    try:
        # Ensure output file has the correct extension
        if not output_path.endswith(".mp4"):
            output_path = os.path.splitext(output_path)[0] + ".mp4"

        # Detect if running on Apple Silicon for hardware acceleration
        is_arm_mac = platform.system() == "Darwin" and platform.processor() == "arm"

        # Use hardware acceleration if on Apple Silicon
        video_codec = "hevc_videotoolbox" if is_arm_mac else "libx265"

        command = [
            "ffmpeg",
            "-i",
            input_path,
            "-c:v",
            video_codec,
            "-b:v",
            target_bitrate,
            "-c:a",
            "aac",
            "-y",
            output_path,
        ]

        if rotation != 0:
            transpose_map = {
                90: 1,
                180: 2,
                270: 3
            }
            transpose = transpose_map.get(rotation, 0)
            if transpose:
                command.extend(["-vf", f"transpose={transpose}"])

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
                        if 0 < progress_percentage < 100:
                            print(f"File Progress: {progress_percentage:.2f}%", end="\r")
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
    reasonable_threshold = 1.15  # Allow a 15% margin over the target bitrate

    # Gather all files and calculate total size upfront
    video_files = []
    failed_files = []
    size_increase_files = []
    total_size = 0
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)

            # Skip non-video files
            if not file.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".m4v", ".wmv")):
                continue

            bitrate, size, _, _ = get_video_stats(file_path)
            if size:
                video_files.append((file_path, size))
                total_size += size

    total_files = len(video_files)
    processed_size = 0
    converted_files = 0
    converted_size_before = 0
    converted_size_after = 0

    for index, (file_path, size) in enumerate(video_files, start=1):
        overall_progress = (processed_size / total_size) * 100 if total_size > 0 else 0
        print(f"Processing {file_path} ({index} of {total_files}, overall progress: {overall_progress:.2f}%)...")

        bitrate, _, duration, rotation = get_video_stats(file_path)

        if bitrate is None or duration is None:
            print(f"Skipping {file_path} due to missing stats.")
            processed_size += size
            continue

        print(f"Original bitrate: {bitrate // 1000}kbps")
        if (file_path.lower().endswith(".wmv") or size > max_size_bytes) and bitrate > (max_bitrate_kbps * 1000 * reasonable_threshold):
            output_path = os.path.splitext(file_path)[0] + ".temp.mp4"
            print(f"File {file_path} ({size // (1024 * 1024)}MB) exceeds thresholds. Starting conversion...")

            if convert_video(file_path, output_path, target_bitrate, duration, rotation, verbose):
                try:
                    new_size = os.path.getsize(output_path)
                    if new_size > size:
                        os.remove(output_path)
                        print(f"Conversion failed for {file_path}. Size increased from {size // (1024 * 1024)}MB to {new_size // (1024 * 1024)}MB.")
                        size_increase_files.append(output_path)
                    else:
                        new_bitrate, _, _, _ = get_video_stats(output_path)
                        final_path = os.path.splitext(file_path)[0] + ".mp4"
                        print(f"Conversion successful for {file_path}. Size reduced from {size // (1024 * 1024)}MB to {new_size // (1024 * 1024)}MB.")
                        print(f"New bitrate: {new_bitrate // 1000}kbps")
                        os.remove(file_path)
                        shutil.move(output_path, final_path)

                        converted_files += 1
                        converted_size_before += size
                        converted_size_after += new_size
                except FileNotFoundError:
                    failed_files.append(file_path)
                    print(f"Conversion failed for {file_path}. Output file not found.")
            else:
                failed_files.append(file_path)
                print(f"Failed to convert {file_path}.")
        else:
            print(f"Skipped {file_path} due to bitrate ({bitrate // 1000}kbps) or size ({size // (1024 * 1024)}MB) being within limits.")

        processed_size += size

    total_size_gb = total_size / (1024 ** 3)
    converted_size_before_gb = converted_size_before / (1024 ** 3)
    converted_size_after_gb = converted_size_after / (1024 ** 3)
    saved_space_gb = converted_size_before_gb - converted_size_after_gb

    if len(failed_files) > 0:
        print(f"Processing of the following files failed: {failed_files}\n")

    if len(size_increase_files) > 0:
        print(f"The following files increased in size after conversion and were not converted: {size_increase_files}\n")

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
