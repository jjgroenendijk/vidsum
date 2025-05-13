# 🎬 Video Summarizer Pro (with Gemini AI) ✨

Quickly generate text summaries from your video files or all video files within a directory using the power of Google's Gemini API! This tool implements a robust batch processing workflow: it first splits long videos into manageable, evenly-sized chunks, uploads all chunks, then generates summaries for each, and finally merges them into a comprehensive document.

## 🚀 Features

*   **AI-Powered Summaries**: Leverages Google Gemini for high-quality text generation.
*   **Flexible Input**: Process a single video file or an entire directory of videos.
*   **Two-Stage Summarization Output**:
    *   **Initial Merged Summary**: Combines summaries from individual video chunks.
    *   **Refined Summary (`_v2.md`)**: The initial summary is further processed by Gemini to:
        *   Generate a main title (H1) and subtitle (H2).
        *   Improve overall formatting and readability.
        *   Ensure consistent Markdown and correct LaTeX rendering.
*   **Improved LaTeX Handling**: Prompts are optimized to prevent backticks around LaTeX expressions.
*   **Robust Chunk Summarization**: Implements a retry mechanism (1 retry after 10s delay) if generating a summary for an individual chunk fails.
*   **Batch Processing Workflow**:
    1.  **Smart Chunking**:
        *   Videos are divided into chunks with a configurable total overlap (`--overlap_duration`).
        *   Chunks are stored locally in a video-specific subdirectory within `.tmp_chunks/` (e.g., `.tmp_chunks/my_video_name/chunk_1.mp4`).
    2.  **Sequential Upload**: All chunks for a video are uploaded to Gemini.
    3.  **Individual Summarization**: Summaries are requested for each chunk. Each chunk's summary is saved locally (e.g., `.tmp_chunks/my_video_name/summary_GEMINI_FILE_ID.md`).
    4.  **Merged Output**: Individual summaries are combined into `{video_filename}_summary.md`.
    5.  **Refinement**: The merged summary is then refined by Gemini, producing `{video_filename}_summary_v2.md`.
*   **Overlap Control**: Maintains context between chunks with configurable overlap.
*   **Flexible Model Choice**: Defaults to `gemini-2.0-flash`.
*   **Configurable Output**: Saves final summaries to `.md` files in your chosen directory.
*   **Temporary File Management**: Option to keep temporary files.
*   **FFmpeg Powered**: Uses FFmpeg for video processing.

## 📋 Prerequisites

*   Python 3.7+ (Python 3.9+ recommended for `argparse.Namespace` type hinting if developing)
*   A Google Gemini API Key
*   FFmpeg installed and accessible in your system's PATH. ([Download FFmpeg](https://ffmpeg.org/download.html))

## 🛠️ Setup Guide

1.  **Project Directory**:
    Make sure you have this `video-summary` project folder.

2.  **API Key Configuration**:
    *   Create a file named `gemini-api-key.txt`.
    *   Place this file in the directory *above* the `video-summary` folder (e.g., if `video-summary` is in `MyProjects/video-summary/`, the key file should be at `MyProjects/gemini-api-key.txt`).
    *   Paste your Google Gemini API key into this file and save it.

3.  **Virtual Environment (Recommended)**:
    Navigate to the `video-summary` directory in your terminal:
    ```bash
    cd path/to/your/video-summary
    ```
    Create and activate a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Linux/macOS
    # .venv\Scripts\activate    # On Windows
    ```

4.  **Install Dependencies**:
    With the virtual environment active:
    ```bash
    pip install -r requirements.txt
    ```

## 🎮 How to Use

Ensure your virtual environment is active and you are in the `video-summary` directory.

**Basic Command (single video):**
```bash
python summarize_video.py path/to/your/video.mp4
```

**Basic Command (directory of videos):**
```bash
python summarize_video.py path/to/your/video_directory/
```

**Example with a specific video:**
```bash
python summarize_video.py ../input_videos/my_lecture.mp4
```
*(Adjust the path to your video file or directory accordingly.)*

### ⚙️ Command-Line Options:

*   `input_path`: (Required) Path to the video file or directory containing video files to summarize.
*   `--model MODEL_NAME`: Specify the Gemini model.
    *   **Default**: `gemini-2.0-flash` (Offers a good balance of capability and generous free tier limits).
    *   Example: `python summarize_video.py video.mp4 --model gemini-1.5-pro-latest`
*   `--max_chunk_duration SECONDS`: Target duration for the ffmpeg-generated video chunks (especially middle chunks). This duration includes the specified overlap.
    *   Default: `900` (15 minutes).
    *   The first and last chunks might be shorter depending on video boundaries and overlap settings.
    *   Set to `0` to disable splitting (video processed as a single segment).
    *   Example: `python summarize_video.py long_video.mp4 --max_chunk_duration 1200` (targets ~20-minute chunks for middle segments)
*   `--overlap_duration SECONDS`: Total desired overlap duration between the content of adjacent ffmpeg-generated chunks. Half of this duration (`overlap_padding`) is applied to each side of a core content segment when creating a chunk.
    *   Default: `60` (1 minute). This means an `overlap_padding` of 30 seconds on each side.
*   `--timeout_per_chunk SECONDS`: API call timeout for generating the summary of each chunk.
    *   Default: `1200` (20 minutes).
*   `--output_dir DIRECTORY_PATH`: Specify where to save the final summary `.md` file(s).
    *   Default: Saves in the current `video-summary/` directory (i.e., the script's directory).
    *   Example: `python summarize_video.py video.mp4 --output_dir ../summaries_output`
*   `--keep_temp_files`: If specified, temporary video chunks and individual summary Markdown files in the video-specific subdirectories within `.tmp_chunks/` will not be deleted after processing. Useful for debugging.
    *   Example: `python summarize_video.py video.mp4 --keep_temp_files`

## 💡 Important Notes

*   **Workflow & Temporary Files**:
    1.  For each video, the script first creates all necessary video chunks (e.g., `chunk_1.mp4`, `chunk_2.mp4`) in a dedicated subdirectory named after the video (e.g., `.tmp_chunks/my_lecture/`) within the `video-summary/` folder.
    2.  All these chunks for the current video are then uploaded to the Gemini API.
    3.  Summaries are generated for each uploaded chunk. Each individual summary is saved as a Markdown file named after the Gemini file ID (e.g., `summary_files_xxxxxxx.md`) in the same video-specific temporary subdirectory.
    4.  These individual Markdown summaries are merged into a single `.md` file for that video (e.g., `my_lecture_summary.md`). The headers that previously indicated time segments for each chunk have been removed for a cleaner merge, relying on the `---` separator between chunk summaries.
    5.  This merged summary (`my_lecture_summary.md`) is then sent back to Gemini for a refinement pass, which generates a title, subtitle, and improves formatting. This refined version is saved as `my_lecture_summary_v2.md`.
    6.  By default, the video-specific subdirectory in `.tmp_chunks/` and its contents (video chunks, individual summaries) are deleted after successful completion for that video. Use `--keep_temp_files` to retain them.
*   **Output**:
    *   The initial merged summary for each video is saved as `{video_filename}_summary.md`.
    *   The **final, refined summary** (recommended for use) is saved as `{video_filename}_summary_v2.md`.
    *   Both are saved in the directory specified by `--output_dir` (or the script's directory by default).
*   **API Rate Limits & Costs**:
    *   The `gemini-2.0-flash` model is generally recommended for its higher free tier limits (check official documentation for current limits).
    *   Other models (e.g., "Pro" versions) typically have much lower free limits.
    *   The script includes a 4-second delay between each chunk upload and a model-dependent delay (4s for flash, 12s for others) between each summary generation API call to help respect these limits.
    *   Always check the [official Google Gemini API rate limits documentation](https://ai.google.dev/gemini-api/docs/rate-limits) for the latest details.
    *   Uploaded video files (chunks) are automatically deleted from Gemini's storage after processing for each video.
*   **Supported Formats**: `ffmpeg` handles a wide array of video formats. For API compatibility, common formats like MP4, MOV, WEBM, MKV, AVI etc., are generally supported. Check Gemini's documentation for specifics.

---

Happy Summarizing! 📝
