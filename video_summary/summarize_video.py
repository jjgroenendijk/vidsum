import argparse # Still needed for type hints in function signatures
import os
import time
import shutil
import google.genai as genai
from google.genai import types
from video_summary.gemini_utils import (
    PROMPT_TEXT, 
    upload_video_chunk_and_wait, 
    generate_summary_for_resource,
    refine_summary_text # Added import for refine_summary_text
)
from video_summary.video_processing_utils import (
    get_video_duration,
    create_video_chunks,
    merge_chunk_summaries,
    discover_video_files,
)
from video_summary.cli import (
    parse_arguments,
    initialize_gemini,
    BASE_TEMP_CHUNK_DIR # Base name for the temporary directory for chunks
)

# Note: Constants like DEFAULT_MODEL, API_KEY_FILE_PATH etc., are now in cli.py
# Note: Helper functions like get_video_duration, create_video_chunks (formerly _create_video_chunks)
#       and merge_chunk_summaries (formerly _merge_chunk_summaries) are now in video_processing_utils.py
# Note: Argument parsing and Gemini initialization are now in cli.py
# Note: Video file discovery is now in video_processing_utils.py

def _upload_chunks_to_gemini(
    gemini_client: "genai.Client", # Added gemini_client parameter
    chunk_details_list: list[tuple[str, float, float]],
    video_basename_no_ext: str,
) -> list[types.File]: 
    """Uploads all video chunks to Google Gemini using the client.

    Iterates through the list of chunk details, uploads each chunk, and
    waits for it to become active on the Gemini service.

    Args:
        gemini_client: The initialized Gemini Client instance.
        chunk_details_list: A list of tuples, where each tuple contains
                            (local_path_to_chunk, start_time, end_time).
        video_basename_no_ext: The base name of the original video file,
                               used for creating display names for uploaded chunks.

    Returns:
        A list of `types.File` objects representing the successfully uploaded
        and active files on Gemini. Returns an empty list if all uploads fail.
    """
    uploaded_file_objects = []
    for i, (local_path, _, _) in enumerate(chunk_details_list):
        print(f"Uploading chunk {i + 1}/{len(chunk_details_list)} for {video_basename_no_ext}: {local_path}")
        # Pass gemini_client to upload_video_chunk_and_wait (display_name parameter removed)
        file_object = upload_video_chunk_and_wait(gemini_client, local_path)
        if file_object:
            uploaded_file_objects.append(file_object)
        else:
            print(f"Upload failed for {local_path}.")
        # Add a small delay between uploads to be respectful to the API.
        if i < len(chunk_details_list) - 1:
            time.sleep(4) # This delay could be made configurable.
    return uploaded_file_objects

def _generate_individual_summaries(
    uploaded_file_objects: list[types.File], # Explicitly type hinting
    gemini_client: "genai.Client", # Changed from gemini_model_instance
    video_temp_dir: str,
    args: argparse.Namespace # args contains args.model (model name string) and args.timeout_per_chunk
) -> list[str]:
    """Generates a text summary for each uploaded video chunk.

    Saves each summary as a separate Markdown (.md) file in the video_temp_dir.
    Includes delays between API calls based on the model type to manage rate limits.

    Args:
        uploaded_file_objects: A list of `types.File` objects for which
                               summaries need to be generated.
        gemini_client: The initialized Gemini Client instance.
        video_temp_dir: The directory where individual summary Markdown files will be saved.
        args: Command-line arguments, containing `timeout_per_chunk` and `model` name.

    Returns:
        A list of file paths to the successfully created summary Markdown files.
    """
    individual_summary_file_paths = []
    for i, file_object in enumerate(uploaded_file_objects):
        # Using file_object.name for logging as display_name is None
        print(f"Generating summary for {file_object.name} using model {args.model}...")
        summary_text = generate_summary_for_resource(
            video_file_resource=file_object, 
            gemini_client=gemini_client, 
            model_name_str=args.model, # Pass the model name string
            prompt=PROMPT_TEXT, 
            timeout=args.timeout_per_chunk
        )

        if summary_text:
            # Always use file_object.name (files/xxxx) for the filename part
            name_part = file_object.name.split('/')[-1] if file_object.name else f"unknown_chunk_{i}"
            
            summary_md_filename = f"summary_{name_part}.md"
            summary_md_path = os.path.join(video_temp_dir, summary_md_filename)
            try:
                with open(summary_md_path, 'w', encoding='utf-8') as f:
                    f.write(summary_text)
                individual_summary_file_paths.append(summary_md_path)
                print(f"Summary saved: {summary_md_path}")
            except IOError as e:
                print(f"Error writing summary {summary_md_path}: {e}")
        else:
            # Using file_object.name for logging
            print(f"No summary generated for {file_object.name}.")

        # Delay between summary generation calls.
        if i < len(uploaded_file_objects) - 1:
            # Shorter delay for "flash" models, longer for others (e.g., "pro").
            delay_seconds = 4 if "flash" in args.model.lower() else 12
            print(f"Waiting {delay_seconds}s (model: {args.model})...")
            time.sleep(delay_seconds)
    return individual_summary_file_paths

def _cleanup_processing_resources(
    gemini_client: "genai.Client", # Added gemini_client parameter
    uploaded_file_objects: list[types.File], 
    video_temp_dir: str,
    video_basename_no_ext: str, 
    args: argparse.Namespace
) -> None:
    """Cleans up resources after processing a video using the client.

    This includes deleting uploaded files from Google Gemini and removing
    the local temporary directory for chunks and summaries, unless
    `args.keep_temp_files` is specified.

    Args:
        gemini_client: The initialized Gemini Client instance.
        uploaded_file_objects: List of `types.File` objects to delete from Gemini.
        video_temp_dir: Path to the local temporary directory to be removed.
        video_basename_no_ext: Base name of the video, for logging.
        args: Command-line arguments, specifically to check `keep_temp_files`.
    """
    print(f"\n--- Phase 5: Cleaning Up for {video_basename_no_ext} ---")
    if uploaded_file_objects:
        print("Deleting remote files from Gemini storage...")
        for file_object in uploaded_file_objects:
            # Always use file_object.name for logging as display_name is None
            try:
                print(f"Deleting remote: {file_object.name}")
                gemini_client.files.delete(name=file_object.name) # Use client for deletion
            except Exception as e:
                print(f"Warning: Could not delete remote file {file_object.name}: {e}")
    
    if os.path.exists(video_temp_dir) and not args.keep_temp_files:
        print(f"Deleting local temporary directory: {video_temp_dir}")
        try:
            shutil.rmtree(video_temp_dir)
        except OSError as e:
            print(f"Error deleting temporary directory {video_temp_dir}: {e}")
    elif args.keep_temp_files:
        print(f"Temporary files and summaries kept at: {video_temp_dir}")

# --- Main Processing Function for a Single Video ---
def process_single_video(
    video_file_path: str,
    gemini_client: "genai.Client", # Changed from gemini_model_instance
    args: argparse.Namespace,
    base_script_dir: str
) -> None:
    """Orchestrates the entire summarization process for a single video file.

    This involves:
    1. Setting up a temporary directory for the video.
    2. Getting video duration.
    3. Creating video chunks.
    4. Uploading chunks to Gemini.
    5. Generating summaries for each chunk.
    6. Merging individual summaries into a final file.
    7. Cleaning up temporary local and remote resources.

    Args:
        video_file_path: The path to the video file to be processed.
        gemini_client: The initialized Gemini Client instance.
        args: Parsed command-line arguments.
        base_script_dir: The directory where the main script is located, used for
                         constructing paths to temporary directories.
    """
    print(f"\n{'='*20} Processing Video: {video_file_path} {'='*20}")

    video_basename_no_ext = os.path.splitext(os.path.basename(video_file_path))[0]
    # Create a specific temporary directory for this video's chunks and summaries.
    video_temp_dir = os.path.join(base_script_dir, BASE_TEMP_CHUNK_DIR, video_basename_no_ext)

    # Ensure a clean temporary directory for the current video.
    if os.path.exists(video_temp_dir):
        print(f"Removing existing temporary directory for this video: {video_temp_dir}")
        shutil.rmtree(video_temp_dir)
    os.makedirs(video_temp_dir, exist_ok=True)
    print(f"Created temporary directory for this video: {video_temp_dir}")

    video_duration = get_video_duration(video_file_path)
    if video_duration is None:
        print(f"Could not get duration for {video_file_path}. Skipping.")
        return # Stop processing this video if duration can't be found.

    # Initialize lists to store details of processing stages.
    uploaded_file_objects: list[types.File] = []
    chunk_details_list: list[tuple[str, float, float]] = []
    individual_summary_file_paths: list[str] = []

    try:
        print("\n--- Phase 1: Creating Video Chunks ---")
        chunk_details_list = create_video_chunks(
            video_file_path, video_basename_no_ext, video_temp_dir, video_duration, args
        )
        if not chunk_details_list:
            print(f"No video chunks were created for {video_file_path}. Skipping further processing for this video.")
            return

        print("\n--- Phase 2: Uploading Video Chunks to Gemini ---")
        uploaded_file_objects.extend(_upload_chunks_to_gemini(
            gemini_client, chunk_details_list, video_basename_no_ext # Pass gemini_client
        ))
        if not uploaded_file_objects:
            print(f"No video chunks were successfully uploaded for {video_basename_no_ext}. Skipping further processing.")
            return

        print("\n--- Phase 3: Generating Individual Summaries for Each Chunk ---")
        individual_summary_file_paths.extend(_generate_individual_summaries(
            uploaded_file_objects, gemini_client, video_temp_dir, args
        ))
        if not individual_summary_file_paths:
            print(f"No individual summaries were generated for {video_basename_no_ext}. Skipping merge.")
            # Cleanup will still occur in the finally block.
            return

        print("\n--- Phase 4: Merging Individual Summaries ---")
        merge_chunk_summaries(
            uploaded_file_objects,
            individual_summary_file_paths,
            chunk_details_list,
            video_temp_dir,
            video_basename_no_ext,
            base_script_dir, # Used as default output dir if args.output_dir is None
            args
        )

        # --- Phase 4.5: Refine the merged summary ---
        print("\n--- Phase 4.5: Refining Merged Summary ---")
        # Determine the path of the initially merged summary
        initial_summary_filename = f"{video_basename_no_ext}_summary.md"
        output_directory = args.output_dir if args.output_dir else base_script_dir
        initial_summary_path = os.path.join(output_directory, initial_summary_filename)

        if os.path.exists(initial_summary_path):
            try:
                with open(initial_summary_path, 'r', encoding='utf-8') as f:
                    original_merged_content = f.read()
                
                refined_summary_content = refine_summary_text(
                    original_summary_text=original_merged_content,
                    gemini_client=gemini_client,
                    model_name_str=args.model, # Use the same model for refinement
                    timeout=args.timeout_per_chunk # Reuse timeout setting
                )

                if refined_summary_content:
                    refined_summary_filename = f"{video_basename_no_ext}_summary_v2.md"
                    refined_output_path = os.path.join(output_directory, refined_summary_filename)
                    with open(refined_output_path, 'w', encoding='utf-8') as f_v2:
                        f_v2.write(refined_summary_content)
                    print(f"🎉 Refined summary saved: {refined_output_path}")
                else:
                    print(f"Failed to refine summary for {video_basename_no_ext}.")

            except Exception as refine_e:
                print(f"Error during summary refinement for {video_basename_no_ext}: {refine_e}")
        else:
            print(f"Initial merged summary {initial_summary_path} not found. Skipping refinement.")

    except Exception as e:
        # Catch any unexpected errors during the processing of this video.
        print(f"An unhandled error occurred while processing {video_file_path}: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging.
    finally:
        # Ensure cleanup happens regardless of success or failure within the try block.
        _cleanup_processing_resources(
            gemini_client, uploaded_file_objects, video_temp_dir, video_basename_no_ext, args # Pass gemini_client
        )
    print(f"\n{'='*20} Finished Processing Video: {video_file_path} {'='*20}")

# --- Main Orchestration Function ---
def main() -> None:
    """The main entry point for the video summarization script.

    Parses arguments, initializes the Gemini model, discovers video files,
    and then processes each video file.
    """
    args = parse_arguments()
    # Get the directory where this script (summarize_video.py) is located.
    script_dir = os.path.dirname(os.path.abspath(__file__))

    gemini_client = initialize_gemini() # No longer takes args.model
    if not gemini_client:
        print("Failed to initialize Gemini Client. Exiting.")
        return

    videos_to_process = discover_video_files(args.input_path)
    if not videos_to_process:
        print("No video files found to process based on the input path. Exiting.")
        return

    print(f"Found {len(videos_to_process)} video(s) to process: {videos_to_process}")
    for video_file in videos_to_process:
        process_single_video(video_file, gemini_client, args, script_dir)
    
    print("\nAll video processing complete.")

if __name__ == "__main__":
    main()
