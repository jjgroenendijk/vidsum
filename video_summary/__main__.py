# This file allows the package to be run as a script using "python -m video_summary"
# For example: python -m video_summary path/to/video_or_dir

if __name__ == "__main__":
    # We use a local import here to avoid potential circular dependencies
    # or issues if this __main__.py is imported elsewhere (though unlikely for __main__).
    # The summarize_video.py script already handles argument parsing and calling its own main.
    # So, we effectively delegate to it.
    #
    # An alternative, more direct way if summarize_video.py's main() was designed
    # to be imported and called without its own if __name__ == "__main__": guard
    # (or if we wanted to bypass that guard for package execution) would be:
    #
    # from .summarize_video import main as summarize_main
    # summarize_main()
    #
    # However, since summarize_video.py is already set up to be the primary executable
    # logic with its own argument parsing, we can just "run" it.
    #
    # The most robust way to do this when summarize_video.py has its own
    # `if __name__ == "__main__": main()` is to simulate how Python would run it
    # if it were the top-level script, but ensuring its context is within the package.
    #
    # For this specific structure where summarize_video.py is the main script:
    from .summarize_video import main
    main()
