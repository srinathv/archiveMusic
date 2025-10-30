#!/usr/bin/env python3
"""
Aggregate multiple AIFF directories into a single Plex album.

New feature:
    • If --album is NOT supplied, the script builds an album title from
      artist, date, venue, and location (e.g. "The Example Band – 2024-09-15 –
      Red Rocks Amphitheatre – Boulder, CO").

Other capabilities (unchanged):
    • Optional cover art (APIC)
    • Optional genre (TCON)
    • Total‑track count in TRCK (e.g. 5/27)
    • Custom sorting inside each folder (alpha / numeric)
    • Comma‑separated list of directories (--dirs) → disc numbers
    • Optional track‑list file (one title per line)
"""

import argparse
import sys
import re
from pathlib import Path
from typing import List, Optional, Callable

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
    APIC,
)


# ----------------------------------------------------------------------
# Helpers for sorting
# ----------------------------------------------------------------------
def _numeric_key(p: Path) -> tuple:
    """Sort by leading integer (if any) then alphabetically."""
    m = re.match(r"^\D*(\d+)", p.stem)
    if m:
        return (int(m.group(1)), p.name.lower())
    else:
        return (float("inf"), p.name.lower())


def _alpha_key(p: Path) -> str:
    return p.name.lower()


SORTERS = {"numeric": _numeric_key, "alpha": _alpha_key}


# ----------------------------------------------------------------------
# Build an album title from the supplied pieces when the user omits --album
# ----------------------------------------------------------------------
def build_album_title(
    artist: str,
    date_iso: str,
    venue: Optional[str],
    location: Optional[str],
) -> str:
    parts = [artist, date_iso]
    if venue:
        parts.append(venue)
    if location:
        parts.append(location)
    # Join with an en‑dash surrounded by spaces for readability
    return " – ".join(parts)


# ----------------------------------------------------------------------
# Write tags for a single AIFF file
# ----------------------------------------------------------------------
def write_tags(
    aiff_path: Path,
    album: str,
    artist: str,
    date_iso: str,
    venue: Optional[str],
    location: Optional[str],
    track_number: int,
    total_tracks: int,
    disc_number: int,
    title: str,
    genre: Optional[str],
    cover_bytes: Optional[bytes],
    cover_mime: Optional[str],
) -> None:
    audio = AIFF(aiff_path)

    if audio.tags is None:
        audio.add_tags()
    id3: ID3 = audio.tags

    # Core metadata
    id3[TPE1] = TPE1(encoding=3, text=artist)  # Artist
    id3[TALB] = TALB(encoding=3, text=album)  # Album
    id3[TDRC] = TDRC(encoding=3, text=date_iso)  # Full date
    id3[TRCK] = TRCK(encoding=3, text=f"{track_number}/{total_tracks}")  # Track/total
    id3[TPOS] = TPOS(encoding=3, text=str(disc_number))  # Disc number

    # Optional custom text frames
    if venue:
        id3.add(TXXX(encoding=3, desc="Venue", text=venue))
    if location:
        id3.add(TXXX(encoding=3, desc="Location", text=location))

    # Title
    id3[TIT2] = TIT2(encoding=3, text=title)

    # Genre (may be empty)
    id3[TCON] = TCON(encoding=3, text=genre or "")

    # Cover art (APIC) – replace any existing picture
    if cover_bytes and cover_mime:
        id3.delall("APIC")
        id3.add(
            APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_bytes)
        )

    audio.save()


# ----------------------------------------------------------------------
# Load optional track‑list file (one line per track)
# ----------------------------------------------------------------------
def load_tracklist(path: Path) -> List[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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
    genre: Optional[str],
    cover_path: Optional[Path],
    sort_mode: str,
    track_titles: List[str],
) -> None:
    """
    Walk each supplied sub‑folder in order, rewrite tags, and keep a global
    track counter so Plex sees a single, consecutive list.
    """

    # ------------------------------------------------------------------
    # 1️⃣ Gather *all* AIFF files first so we know the total count.
    # ------------------------------------------------------------------
    all_files: List[tuple[Path, int]] = []  # (file_path, disc_number)
    for disc_idx, subdir in enumerate(dirs, start=1):
        folder = root / subdir
        if not folder.is_dir():
            print(f"[WARN] Skipping missing folder: {folder}")
            continue

        sorter: Callable[[Path], any] = SORTERS.get(sort_mode, _alpha_key)
        files = sorted(folder.glob("*.aiff"), key=sorter)
        for f in files:
            all_files.append((f, disc_idx))

    total_tracks = len(all_files)
    if total_tracks == 0:
        print("[ERROR] No AIFF files found in any of the supplied directories.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2️⃣ Load cover art (if supplied) once.
    # ------------------------------------------------------------------
    cover_bytes: Optional[bytes] = None
    cover_mime: Optional[str] = None
    if cover_path:
        if not cover_path.is_file():
            print(f"[ERROR] Cover image not found: {cover_path}")
            sys.exit(1)
        cover_bytes = cover_path.read_bytes()
        ext = cover_path.suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            cover_mime = "image/jpeg"
        elif ext == ".png":
            cover_mime = "image/png"
        else:
            print("[WARN] Unknown cover image type; defaulting to image/jpeg")
            cover_mime = "image/jpeg"

    # ------------------------------------------------------------------
    # 3️⃣ Iterate over the collected list, assign numbers, write tags.
    # ------------------------------------------------------------------
    global_counter = 1
    title_idx = 0

    for file_path, disc_number in all_files:
        # Choose title from tracklist if available, else fallback to filename stem
        if title_idx < len(track_titles):
            title = track_titles[title_idx]
            title_idx += 1
        else:
            title = file_path.stem

        write_tags(
            aiff_path=file_path,
            album=album,
            artist=artist,
            date_iso=date_iso,
            venue=venue,
            location=location,
            track_number=global_counter,
            total_tracks=total_tracks,
            disc_number=disc_number,
            title=title,
            genre=genre,
            cover_bytes=cover_bytes,
            cover_mime=cover_mime,
        )
        print(
            f"  • {file_path.name} → Track {global_counter}/{total_tracks}, "
            f"Disc {disc_number}, Title: {title}"
        )
        global_counter += 1


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate multiple AIFF directories into a single Plex album. "
            "If --album is omitted, the title is built from artist, date, venue, "
            "and location."
        )
    )
    p.add_argument(
        "--root", required=True, help="Root directory containing the sub‑folders."
    )
    p.add_argument(
        "--album",
        required=False,
        default=None,
        help=(
            "Unified album title. If omitted, the script creates one from "
            "artist, date, venue, and location."
        ),
    )
    p.add_argument("--artist", required=True, help="Artist name.")
    p.add_argument("--date", required=True, help="Full ISO date (YYYY‑MM‑DD).")
    p.add_argument("--venue", default=None, help="Venue name (optional).")
    p.add_argument(
        "--location", default=None, help="Location (city/state/country) (optional)."
    )
    p.add_argument("--genre", default=None, help="Genre string (optional).")
    p.add_argument(
        "--cover",
        default=None,
        help="Path to a JPEG/PNG image to embed as album artwork (optional).",
    )
    p.add_argument(
        "--dirs",
        required=True,
        help=(
            "Comma‑separated list of sub‑folder names to merge, in order "
            "(e.g. cd1,cd2,bonus). The order determines disc numbers."
        ),
    )
    p.add_argument(
        "--tracklist",
        default=None,
        help="Plain‑text file with one track title per line (optional).",
    )
    p.add_argument(
        "--sort",
        choices=["alpha", "numeric"],
        default="alpha",
        help="How to sort files inside each folder (default: alpha).",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    root_path = Path(args.root).expanduser().resolve()
    if not root_path.is_dir():
        print(f"[ERROR] Root path does not exist or is not a directory: {root_path}")
        sys.exit(1)

    dir_list = [d.strip() for d in args.dirs.split(",") if d.strip()]
    if not dir_list:
        print("[ERROR] No valid directories supplied via --dirs")
        sys.exit(1)

    # Load optional track‑list
    track_titles: List[str] = []
    if args.tracklist:
        tracklist_path = Path(args.tracklist).expanduser().resolve()
        if not tracklist_path.is_file():
            print(f"[ERROR] Tracklist file not found: {tracklist_path}")
            sys.exit(1)
        track_titles = load_tracklist(tracklist_path)

    # Resolve optional cover path
    cover_path: Optional[Path] = None
    if args.cover:
        cover_path = Path(args.cover).expanduser().resolve()

    # ------------------------------------------------------------------
    # Determine the final album title (user‑supplied or auto‑generated)
    # ------------------------------------------------------------------
    final_album = (
        args.album
        if args.album
        else build_album_title(
            artist=args.artist,
            date_iso=args.date,
            venue=args.venue,
            location=args.location,
        )
    )
    print(f"[INFO] Using album title: {final_album}")

    # ------------------------------------------------------------------
    # Run the processing pipeline
    # ------------------------------------------------------------------
    process_directories(
        root=root_path,
        dirs=dir_list,
        album=final_album,
        artist=args.artist,
        date_iso=args.date,
        venue=args.venue,
        location=args.location,
        genre=args.genre,
        cover_path=cover_path,
        sort_mode=args.sort,
        track_titles=track_titles,
    )

    print(
        "\n✅ Tagging complete! Refresh Plex (or trigger a manual library scan) "
        "to see the single combined album with consecutive tracks, genre, and artwork."
    )


if __name__ == "__main__":
    main()
