import os
import math
import ffmpeg
import shutil
import argparse # For type hinting Namespace

# --- Constants ---
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
"""Set of supported video file extensions."""

MIN_CHUNK_PROCESSING_THRESHOLD_SECONDS = 1.0
"""Minimum duration in seconds for a video chunk to be considered for processing."""

# --- Helper Functions ---

def get_video_duration(video_path: str) -> float | None:
    """Probes a video file to determine its duration in seconds.

    Uses ffmpeg to get video metadata.

    Args:
        video_path: The absolute or relative path to the video file.

    Returns:
        The duration of the video in seconds as a float, or None if
        the duration cannot be determined or an error occurs.
    """
    try:
        print(f"Probing: {video_path}...")
        probe = ffmpeg.probe(video_path)
        # Find the video stream from the probe output.
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_stream or 'duration' not in video_stream:
            print(f"Error: No video stream or duration in metadata for {video_path}.")
            return None
        duration = float(video_stream['duration'])
        print(f"Duration: {duration:.2f}s.")
        return duration
    except ffmpeg.Error as e:
        # Handle errors specific to ffmpeg.
        print(f"ffmpeg probe error for {video_path}: {e.stderr.decode('utf-8') if e.stderr else str(e)}")
        return None
    except Exception as e:
        # Handle any other unexpected errors during probing.
        print(f"Unexpected probe error for {video_path}: {e}")
        return None

def create_video_chunks(
    video_file_path: str,
    video_basename_no_ext: str,
    video_temp_dir: str,
    video_duration: float,
    args: argparse.Namespace
) -> list[tuple[str, float, float]]:
    """Splits a video file into smaller chunks based on specified durations and overlaps.

    This function uses ffmpeg to create chunks. If the video is shorter than
    the `max_chunk_duration` or if chunking is disabled (max_chunk_duration is 0),
    the original video is copied as a single chunk. Otherwise, the video is
    divided into segments, with overlap between adjacent segments to maintain context.

    Args:
        video_file_path: Path to the original video file.
        video_basename_no_ext: The base name of the video file without its extension.
        video_temp_dir: Directory where temporary video chunks will be stored.
        video_duration: Total duration of the video in seconds.
        args: Command-line arguments, containing settings like `max_chunk_duration`
              and `overlap_duration`.

    Returns:
        A list of tuples. Each tuple contains:
        - chunk_path (str): The file path to the created video chunk.
        - start_time (float): The start time of this chunk in the original video (seconds).
        - end_time (float): The end time of this chunk in the original video (seconds).
    """
    chunk_details_list = []
    _, orig_ext = os.path.splitext(video_file_path)
    if not orig_ext:
        orig_ext = ".mp4"  # Default to .mp4 if original extension is missing.

    # Check if chunking is needed based on video duration and max_chunk_duration setting.
    if args.max_chunk_duration > 0 and video_duration > args.max_chunk_duration:
        total_overlap_duration = float(args.overlap_duration)
        overlap_padding = total_overlap_duration / 2.0 # Padding for each side of a chunk.
        target_ffmpeg_duration_middle_chunks = float(args.max_chunk_duration)
        # Calculate the length of the unique content part of each chunk.
        base_content_length = target_ffmpeg_duration_middle_chunks - total_overlap_duration

        if base_content_length <= 0:
            # If overlap is too large for the chunk duration, process as a single segment.
            print(f"Error: Invalid chunk/overlap. base_content_length ({base_content_length:.2f}s) <= 0. Processing as single segment.")
            temp_chunk_path = os.path.join(video_temp_dir, f"{video_basename_no_ext}_chunk_1{orig_ext}")
            shutil.copy(video_file_path, temp_chunk_path) # Copy original video as one chunk.
            chunk_details_list.append((temp_chunk_path, 0, video_duration))
        else:
            # Calculate the number of base segments needed.
            num_base_segments = math.ceil(video_duration / base_content_length)
            if num_base_segments == 0: # Should not happen if video_duration > 0
                num_base_segments = 1
            print(f"Video: {video_duration:.2f}s, Target chunk: {target_ffmpeg_duration_middle_chunks:.2f}s, Overlap: {total_overlap_duration:.2f}s, Base content: {base_content_length:.2f}s, Segments: {num_base_segments}")

            for k in range(num_base_segments):
                # Calculate start and end times for the core content of the current segment.
                base_segment_start_time = k * base_content_length
                base_segment_end_time = min((k + 1) * base_content_length, video_duration)

                # Stop if we've processed the entire video.
                if base_segment_start_time >= video_duration or base_segment_start_time >= base_segment_end_time:
                    break

                # Calculate the actual start and end points for ffmpeg, including overlap padding.
                ffmpeg_final_ss = max(0.0, base_segment_start_time - overlap_padding)
                ffmpeg_final_end_point = min(video_duration, base_segment_end_time + overlap_padding)
                ffmpeg_final_t = ffmpeg_final_end_point - ffmpeg_final_ss # Duration of the ffmpeg chunk.

                # Skip creating the chunk if its duration is below the minimum threshold.
                if ffmpeg_final_t < MIN_CHUNK_PROCESSING_THRESHOLD_SECONDS:
                    print(f"Skipping segment {k + 1}: duration {ffmpeg_final_t:.2f}s < threshold.")
                    continue

                current_chunk_number = len(chunk_details_list) + 1
                temp_chunk_filename = f"chunk_{current_chunk_number}{orig_ext}"
                temp_chunk_path = os.path.join(video_temp_dir, temp_chunk_filename)
                print(f"Creating chunk {current_chunk_number}: {temp_chunk_path} (ss={ffmpeg_final_ss:.2f}s, t={ffmpeg_final_t:.2f}s)")

                try:
                    # Use ffmpeg to create the chunk.
                    # 'ss' is start time, 't' is duration for the output.
                    # 'vcodec' and 'acodec' 'copy' means no re-encoding, which is faster.
                    (ffmpeg.input(video_file_path, ss=ffmpeg_final_ss, t=ffmpeg_final_t)
                     .output(temp_chunk_path, vcodec='copy', acodec='copy', format=orig_ext.lstrip('.'))
                     .overwrite_output().run(capture_stdout=True, capture_stderr=True))
                    chunk_details_list.append((temp_chunk_path, ffmpeg_final_ss, ffmpeg_final_ss + ffmpeg_final_t))
                except ffmpeg.Error as e:
                    print(f"ffmpeg error creating {temp_chunk_path}: {e.stderr.decode('utf-8') if e.stderr else str(e)}")
    else:
        # If video is short or chunking is disabled, copy the whole video as one chunk.
        print("Processing as single segment (video shorter than max_chunk_duration or splitting disabled).")
        temp_chunk_path = os.path.join(video_temp_dir, f"{video_basename_no_ext}_chunk_1{orig_ext}")
        shutil.copy(video_file_path, temp_chunk_path)
        chunk_details_list.append((temp_chunk_path, 0, video_duration))
    return chunk_details_list

def merge_chunk_summaries(
    uploaded_file_objects: list, # List of genai.File objects from Gemini API
    individual_summary_file_paths: list[str],
    chunk_details_list: list[tuple[str, float, float]],
    video_temp_dir: str,
    video_basename_no_ext: str,
    base_script_dir: str,
    args: argparse.Namespace
) -> None:
    """Combines individual summaries from video chunks into a single final summary file.

    Each part of the merged summary is preceded by a header indicating the
    time segment of the original video it corresponds to.

    Args:
        uploaded_file_objects: A list of `genai.File` objects representing the
                               files uploaded to Gemini. Used to match display names.
        individual_summary_file_paths: A list of file paths to the individual
                                       Markdown summary files for each chunk.
        chunk_details_list: A list of tuples containing (chunk_path, start_time, end_time)
                            for each locally created chunk. Used to get time segments.
        video_temp_dir: The temporary directory where individual summaries are stored.
        video_basename_no_ext: Base name of the original video file without extension.
        base_script_dir: The base directory of the script, used as default output if not specified.
        args: Command-line arguments, used to get `output_dir`.
    """
    final_summary_parts = []
    for i, file_object in enumerate(uploaded_file_objects):
        # Reconstruct the expected local summary filename using file_object.name
        name_part = file_object.name.split('/')[-1] if file_object.name else f"unknown_chunk_{i}"
        expected_summary_filename = f"summary_{name_part}.md"
        # Debug print to confirm the expected filename based on file_object.name
        # print(f"Debug: Expecting summary file '{expected_summary_filename}' for Gemini file '{file_object.name}' in merge_chunk_summaries.")
        
        expected_summary_path = os.path.join(video_temp_dir, expected_summary_filename)

        if expected_summary_path in individual_summary_file_paths:
            # Header is already empty as per previous request.
            # We still need to associate the summary content with its original time segment if needed,
            # but the direct header before each chunk's summary text is now "".
            header = "" 
            # The original logic for detailed headers with time segments was:
            # if 0 <= i < len(chunk_details_list):
            #     _, start_time, end_time = chunk_details_list[i]
            #     header = f"## Summary for Chunk {i + 1} (Original Video Time: {start_time:.2f}s - {end_time:.2f}s, File: {file_object.name})\n\n"
            # else:
            #     header = f"## Summary for (Uploaded as: {file_object.name})\n\n" # Using file_object.name as display_name is None

            try:
                with open(expected_summary_path, 'r', encoding='utf-8') as f_sum:
                    final_summary_parts.append(header + f_sum.read()) # header is ""
            except FileNotFoundError:
                 print(f"Error: Summary file {expected_summary_path} not found during merge, though it was expected for {file_object.name}.")
            except Exception as e_read:
                print(f"Error reading summary file {expected_summary_path} for {file_object.name}: {e_read}")
        else:
            # If an expected summary file is missing.
            print(f"Warning: Expected summary {expected_summary_path} not found for Gemini file {file_object.name}")

    if not final_summary_parts:
        print(f"No content to merge for {video_basename_no_ext}.")
    else:
        full_merged_summary = "\n\n---\n\n".join(final_summary_parts)
        final_summary_filename = f"{video_basename_no_ext}_summary.md" # Changed to .md
        # Determine output directory: use specified one or default to script's directory.
        output_directory = args.output_dir if args.output_dir else base_script_dir
        os.makedirs(output_directory, exist_ok=True) # Create output directory if it doesn't exist.
        final_output_path = os.path.join(output_directory, final_summary_filename)
        try:
            with open(final_output_path, 'w', encoding='utf-8') as f:
                f.write(full_merged_summary)
            print(f"\n🎉 Final summary for {video_basename_no_ext} -> {final_output_path}")
        except IOError as e:
            print(f"\nError writing final summary {final_output_path}: {e}")

def discover_video_files(input_path: str) -> list[str]:
    """Finds all supported video files from a given path (can be a file or a directory).

    If `input_path` is a file, it checks if it's a supported video type.
    If `input_path` is a directory, it recursively searches for supported video files.

    Args:
        input_path: The path to a video file or a directory containing video files.

    Returns:
        A sorted list of absolute paths to all discovered video files.
        Returns an empty list if no valid videos are found or if the path is invalid.
    """
    videos_to_process = []
    input_path_abs = os.path.abspath(input_path) # Get the full, absolute path.

    if not os.path.exists(input_path_abs):
        print(f"Error: Input path not found: {input_path_abs}")
        return []

    if os.path.isfile(input_path_abs):
        # If the input is a single file.
        _, ext = os.path.splitext(input_path_abs)
        if ext.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            videos_to_process.append(input_path_abs)
        else:
            print(f"Error: Input file '{input_path_abs}' is not a supported video type ({', '.join(SUPPORTED_VIDEO_EXTENSIONS)}).")
            return []
    elif os.path.isdir(input_path_abs):
        # If the input is a directory, walk through it.
        print(f"Scanning directory for videos: {input_path_abs}")
        for root, _, files in os.walk(input_path_abs):
            for file_in_dir in files:
                _, ext = os.path.splitext(file_in_dir)
                if ext.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                    videos_to_process.append(os.path.join(root, file_in_dir))
        if videos_to_process:
            print(f"Found {len(videos_to_process)} video(s) to process.")
        videos_to_process.sort() # Sort for a consistent processing order.
    else:
        print(f"Error: Input path '{input_path_abs}' is not a valid file or directory.")
        return []
    
    return videos_to_process
