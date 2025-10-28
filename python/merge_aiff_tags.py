i  #!/usr/bin/env python3
"""
Combine AIFF tags from two CD folders so Plex sees them as one album.

Folder layout (example):
    /music/Artist/Album/
        cd1/
            01 Track One.aiff
            02 Track Two.aiff
            ...
        cd2/
            01 Track Eleven.aiff
            02 Track Twelve.aiff
            ...

Usage:
    python merge_aiff_tags.py /path/to/Album cd1 cd2 "Combined Album Title"
"""

import sys
from pathlib import Path
from mutagen.aiff import AIFF
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TRCK, TPOS, TYER, TCON, TDRC


def update_aiff_tags(
    file_path: Path,
    album_title: str,
    artist: str,
    year: str,
    start_track: int,
    disc_number: int,
) -> None:
    """
    Overwrite AIFF tags with unified album info.

    Parameters
    ----------
    file_path : Path
        Path to the .aiff file.
    album_title : str
        Desired album name (the same for all tracks).
    artist : str
        Artist name.
    year : str
        Release year (as a four‑digit string).
    start_track : int
        The track number that this file should receive.
    disc_number : int
        Disc number (1 for cd1, 2 for cd2, …).
    """
    # Load the AIFF file – Mutagen treats AIFF metadata as ID3 frames.
    audio = AIFF(file_path)

    # Ensure there is an ID3 tag container; create if missing.
    if audio.tags is None:
        audio.add_tags()
    id3 = audio.tags

    # Set common fields.
    id3[TPE1] = TPE1(encoding=3, text=artist)  # Artist
    id3[TALB] = TALB(encoding=3, text=album_title)  # Album
    id3[TDRC] = TDRC(encoding=3, text=year)  # Year / Date
    id3[TCON] = TCON(encoding=3, text="")  # Genre (blank – you can fill)

    # Per‑track fields.
    id3[TIT2] = TIT2(
        encoding=3, text=file_path.stem
    )  # Title = filename (you can customize)
    id3[TRCK] = TRCK(encoding=3, text=str(start_track))  # Track number
    id3[TPOS] = TPOS(encoding=3, text=str(disc_number))  # Disc number

    # Write changes back to disk.
    audio.save()


def process_folder(
    base_dir: Path,
    subfolder: str,
    album_title: str,
    artist: str,
    year: str,
    start_index: int,
    disc_number: int,
) -> int:
    """
    Process all AIFF files in a given subfolder.

    Returns the next track index after processing this folder.
    """
    folder_path = base_dir / subfolder
    if not folder_path.is_dir():
        print(f"[WARN] Folder {folder_path} does not exist – skipping.")
        return start_index

    aiff_files = sorted(folder_path.glob("*.aiff"))
    if not aiff_files:
        print(f"[INFO] No AIFF files found in {folder_path}.")
        return start_index

    print(f"[INFO] Updating {len(aiff_files)} files in {folder_path} ...")
    for i, aiff_path in enumerate(aiff_files, start=start_index):
        update_aiff_tags(
            file_path=aiff_path,
            album_title=album_title,
            artist=artist,
            year=year,
            start_track=i,
            disc_number=disc_number,
        )
        print(f"  • {aiff_path.name} → track {i}")

    return start_index + len(aiff_files)


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    root_dir = Path(sys.argv[1]).expanduser().resolve()
    cd_folders = [sys.argv[2], sys.argv[3]]  # e.g. ["cd1", "cd2"]
    combined_album = sys.argv[4]  # Desired album title

    # You can hard‑code these or pull them from an existing file/metadata source.
    # Here we simply guess from the parent directory name.
    artist = root_dir.parent.name or "Unknown Artist"
    year = "2024"  # Change as needed

    next_track = 1
    for idx, cd in enumerate(cd_folders, start=1):
        next_track = process_folder(
            base_dir=root_dir,
            subfolder=cd,
            album_title=combined_album,
            artist=artist,
            year=year,
            start_index=next_track,
            disc_number=idx,
        )

    print("\n✅ Tag update complete! Plex should now see a single album.")


if __name__ == "__main__":
    main()
