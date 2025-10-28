#!/usr/bin/env python3
"""
Merge AIFF tags from an arbitrary list of sub‑folders so Plex sees a single album.

Features
--------
* Flags for artist, date, venue, location.
* `--dirs` – comma‑separated list of directories to aggregate (order matters).
* `--tracklist` – optional text file (one line per track) that supplies exact titles.
* Consecutive track numbers across all supplied folders.
* Disc numbers (TPOS) correspond to the position of each folder in the list.
* All tags are written using ID3 frames (mutagen).

Usage example
-------------
python merge_aiff_tags.py \
    --root "/Users/me/Music/Live/GreatShow" \
    --album "Great Show – Live" \
    --artist "The Example Band" \
    --date "2024-09-15" \
    --venue "Red Rocks Amphitheatre" \
    --location "Boulder, CO" \
    --dirs cd1,cd2,bonus \
    --tracklist "/Users/me/track_names.txt"
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from mutagen.aiff import AIFF
from mutagen.id3 import (
    ID3,
    TIT2,
    TALB,
    TPE1,
    TRCK,
    TPOS,
    TDRC,
    TXXX,
    TCON,
)


# ----------------------------------------------------------------------
# Helper: write tags for a single AIFF file
# ----------------------------------------------------------------------
def write_tags(
    aiff_path: Path,
    album: str,
    artist: str,
    date_iso: str,
    venue: Optional[str],
    location: Optional[str],
    track_number: int,
    disc_number: int,
    title: str,
) -> None:
    """Overwrite (or create) ID3 tags on an AIFF file."""
    audio = AIFF(aiff_path)

    # Ensure an ID3 container exists
    if audio.tags is None:
        audio.add_tags()
    id3: ID3 = audio.tags

    # Core metadata
    id3[TPE1] = TPE1(encoding=3, text=artist)  # Artist
    id3[TALB] = TALB(encoding=3, text=album)  # Album
    id3[TDRC] = TDRC(encoding=3, text=date_iso)  # Full date
    id3[TRCK] = TRCK(encoding=3, text=str(track_number))  # Track number (no total)
    id3[TPOS] = TPOS(encoding=3, text=str(disc_number))  # Disc number

    # Optional custom text frames
    if venue:
        id3.add(TXXX(encoding=3, desc="Venue", text=venue))
    if location:
        id3.add(TXXX(encoding=3, desc="Location", text=location))

    # Title – either from supplied list or fallback to filename stem
    id3[TIT2] = TIT2(encoding=3, text=title)

    # Empty genre placeholder (you can expose a flag later if desired)
    id3[TCON] = TCON(encoding=3, text="")

    # Persist changes
    audio.save()


# ----------------------------------------------------------------------
# Load optional track‑list file (one line per track)
# ----------------------------------------------------------------------
def load_tracklist(path: Path) -> List[str]:
    """Read a UTF‑8 text file, stripping trailing newlines."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        # Remove empty lines but keep order
        return [ln.strip() for ln in lines if ln.strip()]
    except Exception as exc:
        print(f"[ERROR] Could not read tracklist file '{path}': {exc}")
        sys.exit(1)


# ----------------------------------------------------------------------
# Main processing routine
# ----------------------------------------------------------------------
def process_directories(
    root: Path,
    dirs: List[str],
    album: str,
    artist: str,
    date_iso: str,
    venue: Optional[str],
    location: Optional[str],
    track_titles: List[str],
) -> None:
    """
    Walk each supplied sub‑folder in order, rewrite tags, and keep a global
    track counter so Plex sees a single, consecutive list.
    """
    global_counter = 1  # overall track number across all folders
    track_title_idx = 0  # pointer into the optional track‑list array

    for disc_idx, subdir in enumerate(dirs, start=1):
        folder = root / subdir
        if not folder.is_dir():
            print(f"[WARN] Skipping non‑existent folder: {folder}")
            continue

        # Gather AIFF files sorted alphabetically (adjust if you need a different order)
        aiff_files = sorted(folder.glob("*.aiff"))
        if not aiff_files:
            print(f"[INFO] No AIFF files found in {folder}")
            continue

        print(
            f"[INFO] Processing {len(aiff_files)} files in {folder} (Disc {disc_idx})"
        )
        for aiff_path in aiff_files:
            # Determine title: use supplied list if available, otherwise filename stem
            if track_title_idx < len(track_titles):
                title = track_titles[track_title_idx]
                track_title_idx += 1
            else:
                title = aiff_path.stem  # fallback

            write_tags(
                aiff_path=aiff_path,
                album=album,
                artist=artist,
                date_iso=date_iso,
                venue=venue,
                location=location,
                track_number=global_counter,
                disc_number=disc_idx,
                title=title,
            )
            print(f"  • {aiff_path.name} → Track {global_counter}, Title: {title}")
            global_counter += 1


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Aggregate multiple AIFF directories into a single Plex album "
        "by rewriting ID3 tags (artist, date, venue, location, titles, etc.)."
    )
    p.add_argument(
        "--root",
        required=True,
        help="Root directory that contains the sub‑folders to aggregate.",
    )
    p.add_argument(
        "--album",
        required=True,
        help="Unified album title that Plex will display.",
    )
    p.add_argument(
        "--artist",
        required=True,
        help="Artist name to write into every file.",
    )
    p.add_argument(
        "--date",
        required=True,
        help="Full ISO date (YYYY‑MM‑DD) for the recording/release.",
    )
    p.add_argument(
        "--venue",
        default=None,
        help="Venue name (optional).",
    )
    p.add_argument(
        "--location",
        default=None,
        help="Location (city, state, country) – optional.",
    )
    p.add_argument(
        "--dirs",
        required=True,
        help=(
            "Comma‑separated list of sub‑folder names to merge, in the order you "
            "want them treated as discs (e.g. 'cd1,cd2,bonus')."
        ),
    )
    p.add_argument(
        "--tracklist",
        default=None,
        help=(
            "Path to a plain‑text file containing one track title per line. "
            "If fewer titles than total tracks are supplied, remaining tracks fall "
            "back to their original filenames."
        ),
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    root_path = Path(args.root).expanduser().resolve()
    if not root_path.is_dir():
        print(f"[ERROR] Root path does not exist or is not a directory: {root_path}")
        sys.exit(1)

    # Parse the comma‑separated list of directories
    dir_list = [d.strip() for d in args.dirs.split(",") if d.strip()]
    if not dir_list:
        print("[ERROR] No valid directories supplied via --dirs")
        sys.exit(1)

    # Load optional track‑list file
    track_titles: List[str] = []
    if args.tracklist:
        tracklist_path = Path(args.tracklist).expanduser().resolve()
        if not tracklist_path.is_file():
            print(f"[ERROR] Tracklist file not found: {tracklist_path}")
            sys.exit(1)
        track_titles = load_tracklist(tracklist_path)

    # Run the processing loop
    process_directories(
        root=root_path,
        dirs=dir_list,
        album=args.album,
        artist=args.artist,
        date_iso=args.date,
        venue=args.venue,
        location=args.location,
        track_titles=track_titles,
    )

    print(
        "\n✅ All tags have been rewritten. Refresh Plex (or trigger a manual scan) "
        "to see the single combined album with consecutive tracks."
    )


if __name__ == "__main__":
    main()
