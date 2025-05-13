import argparse
import os
import google.genai as genai
from typing import Optional

# --- Constants ---
DEFAULT_MODEL = "gemini-2.0-flash"  # Default model for Gemini API.
API_KEY_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "gemini-api-key.txt")  # Path to the API key file.
DEFAULT_TARGET_CHUNK_DURATION_SECONDS = 900  # Default target duration for video chunks (15 minutes).
DEFAULT_OVERLAP_DURATION_SECONDS = 60    # Default overlap duration between chunks (1 minute).
DEFAULT_TIMEOUT_PER_CHUNK_SECONDS = 1200 # Default timeout for API summary call per chunk (20 minutes).
BASE_TEMP_CHUNK_DIR = ".tmp_chunks"  # Base directory for temporary video-specific subdirectories.

# --- Argument Parsing ---
def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments for the video summarization script."""
    parser = argparse.ArgumentParser(
        description="Summarize video(s) using Google Gemini API. "
                    "Accepts a single video file or a directory of videos. "
                    "Splits long videos into chunks, processes them sequentially."
    )
    parser.add_argument(
        "input_path",
        help="Path to the video file or directory containing video files to summarize."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to use (default: {DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--max_chunk_duration",
        type=int,
        default=DEFAULT_TARGET_CHUNK_DURATION_SECONDS,
        help=f"Target duration for video chunks in seconds (default: {DEFAULT_TARGET_CHUNK_DURATION_SECONDS}s)."
    )
    parser.add_argument(
        "--overlap_duration",
        type=int,
        default=DEFAULT_OVERLAP_DURATION_SECONDS,
        help=f"Overlap duration between chunks in seconds (default: {DEFAULT_OVERLAP_DURATION_SECONDS}s)."
    )
    parser.add_argument(
        "--timeout_per_chunk",
        type=int,
        default=DEFAULT_TIMEOUT_PER_CHUNK_SECONDS,
        help=f"Timeout in seconds for API summary call per chunk (default: {DEFAULT_TIMEOUT_PER_CHUNK_SECONDS}s)."
    )
    parser.add_argument(
        "--output_dir",
        default=None,
        help="Directory to save the final summary file(s) (default: script's directory)."
    )
    parser.add_argument(
        "--keep_temp_files",
        action="store_true",
        help="Keep temporary chunk files and individual summaries after processing."
    )
    args = parser.parse_args()

    # Validate and adjust overlap duration if necessary.
    if args.max_chunk_duration > 0 and args.overlap_duration >= args.max_chunk_duration:
        print(f"Error: Overlap ({args.overlap_duration}s) must be less than chunk duration ({args.max_chunk_duration}s).")
        args.overlap_duration = max(0, args.max_chunk_duration - 1) # Ensure overlap is at least 0 and less than chunk duration.
        print(f"Adjusted overlap to: {args.overlap_duration}s")
    return args

# --- Gemini Initialization ---
def initialize_gemini() -> Optional["genai.Client"]: # model_name is no longer needed here
    """Initializes and returns a Gemini Client instance.
    
    Reads the API key from API_KEY_FILE_PATH and creates a genai.Client.
    The actual model will be specified when making API calls.
    """
    try:
        with open(API_KEY_FILE_PATH, 'r') as f:
            api_key = f.read().strip()
        if not api_key:
            print(f"Error: API key file at {API_KEY_FILE_PATH} is empty.")
            return None
    except FileNotFoundError:
        print(f"Error: API key file not found at {API_KEY_FILE_PATH}")
        return None
    except Exception as e:
        print(f"Error reading API key file: {e}")
        return None

    # print(f"DEBUG: genai module: {genai}") # Removed debug print
    # print(f"DEBUG: genai module path: {genai.__file__}") # Removed debug print
    # print(f"DEBUG: genai module attributes: {dir(genai)}") # Removed debug print
    
    try:
        # The new SDK uses a Client object for authentication and interaction.
        client = genai.Client(api_key=api_key)
        # print(f"DEBUG: Successfully created genai.Client instance.") # Removed debug print
        return client
    except Exception as e:
        print(f"Error initializing Gemini Client: {e}")
        return None
