from datetime import time
from pydub import AudioSegment
import argparse
import music_tag
import os
import re
from typing import List, Optional

# Goal: split mp3 file by simple copy/paste config I can get from YT timestamps
# Given a file name and location of this conf file we split the original mp3 into
# the sections defined in the timestamp
#
# Optionally we can add extra metadata into the file with the added args

# Regex used for reading in config
# Capture groups: 1 for number, 3 for section title, 5 for time
CONFIG_PATTERN = r'#{0,1}(\d+)( [-\|]){0,1} (.*?)( [-\|]){0,1} ((\d{2}\:{0,1})+)'

# Capture groups: 1 for time, 4 for section title.
# Assume index for track #
ALT_CONFIG_PATTERN = r'((\d{2}\:{0,1})+)( [-\|]){0,1} (.*?)$'


class TrackInfo:
    """A class to hold track information."""

    def __init__(
        self,
        name: str,
        track_number: int,
        track_start: int,
        track_end: Optional[int],
        album: str,
        artist: Optional[str] = None,
        composer: Optional[str] = None,
        total_discs: Optional[int] = None,
        disc_number: Optional[int] = None
    ):
        self.name = name
        self.track_number = track_number
        self.track_start = track_start
        self.track_end = track_end
        self.album = album
        self.composer = composer
        self.total_discs = total_discs
        self.disc_number = disc_number
        self.artist = artist

    def set_track_end(self, time_end: int):
        """Sets the end time of the track."""
        self.track_end = time_end


def main():
    """Main function to parse arguments and split the audio file."""
    parser = argparse.ArgumentParser(description="Split an MP3 file based on a timestamp configuration.")
    parser.add_argument('-f', '--file', required=True, help="Location of the mp3 file to be split")
    parser.add_argument('-c', '--config', required=True, help="Location of config file")
    parser.add_argument('-o', '--output', help="Output location for file/s (optional)")
    parser.add_argument('-a', '--album', help="Album name (optional)")
    parser.add_argument('-art', '--artist', help="Add contributing artist (optional)")
    parser.add_argument('-comp', '--composer', help="Composer name (optional)")
    parser.add_argument('-tdisc', '--total_discs', type=int, help="Total number of discs (optional)")
    parser.add_argument('-disc', '--disc', type=int, help="Disc number (optional)")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: The file '{args.file}' is not a valid file.")
        return

    try:
        audio = AudioSegment.from_mp3(args.file)
        print('Successfully processed audio file...')
    except Exception as e:
        print(f"Error processing audio file: {e}")
        return

    total_length = len(audio) // 1000
    album_name = args.album if args.album else os.path.splitext(os.path.basename(args.file))[0]

    try:
        tracks = process_conf(
            args.config,
            album=album_name,
            duration=total_length,
            composer=args.composer,
            total_discs=args.total_discs,
            disc_number=args.disc,
            artist=args.artist
        )
        print('Successfully processed config file...')
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{args.config}'")
        return
    except ValueError as e:
        print(f"Error processing config file: {e}")
        return

    output_path = args.output if args.output else os.path.dirname(args.file)
    os.makedirs(output_path, exist_ok=True)
    
    process_tracks(tracks, audio, output_path)


def process_tracks(tracks: List[TrackInfo], audio: AudioSegment, output_path: str):
    """Processes and exports each track."""
    total_tracks = len(tracks)
    for i, track in enumerate(tracks, 1):
        print(f"\rProcessing track {i}/{total_tracks}...", end="")
        start_ms = track.track_start * 1000
        end_ms = track.track_end * 1000 if track.track_end is not None else len(audio)
        
        segment = audio[start_ms:end_ms]
        
        sanitized_track_name = re.sub(r'[\\/*?:"<>|]',"", track.name)
        file_path = os.path.join(output_path, f"{sanitized_track_name}.mp3")
        
        segment.export(file_path, format="mp3")

        # Set metadata tags
        f = music_tag.load_file(file_path)
        f['album'] = track.album
        if track.composer:
            f['composer'] = track.composer
        if track.disc_number:
            f['discnumber'] = track.disc_number
        if track.total_discs:
            f['totaldiscs'] = track.total_discs
        f['tracknumber'] = track.track_number
        f['tracktitle'] = track.name
        if track.artist:
            f['artist'] = track.artist
        f.save()
    print(f"\nProcessed {total_tracks} track/s!")


def process_conf(
    file_path: str,
    album: str,
    duration: Optional[int] = None,
    composer: Optional[str] = None,
    total_discs: Optional[int] = None,
    disc_number: Optional[int] = None,
    artist: Optional[str] = None
) -> List[TrackInfo]:
    """Parses the configuration file to extract track information."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f'Configuration path is not a file: {file_path}')

    tracks = []
    with open(file_path, 'r') as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            match = re.search(CONFIG_PATTERN, line) or re.search(ALT_CONFIG_PATTERN, line)

            if not match:
                raise ValueError(f'Failed to parse config: line #{line_number} - {line}')

            if re.search(CONFIG_PATTERN, line):
                track_num = int(match.group(1))
                track_name = match.group(3)
                time_stamp_str = match.group(5)
            else: # ALT_CONFIG_PATTERN
                track_num = line_number
                track_name = match.group(4)
                time_stamp_str = match.group(1)

            time_stamp_sec = time_stamp_to_seconds(time_stamp_str)

            if tracks:
                tracks[-1].set_track_end(time_stamp_sec)
            
            track = TrackInfo(
                name=track_name.strip(),
                album=album,
                track_number=track_num,
                track_start=time_stamp_sec,
                track_end=None,
                composer=composer,
                total_discs=total_discs,
                disc_number=disc_number,
                artist=artist
            )
            tracks.append(track)

    if tracks:
        tracks[-1].set_track_end(duration)
    
    return tracks


def time_stamp_to_seconds(time_stamp: str) -> int:
    """Converts a timestamp string (e.g., HH:MM:SS) to seconds."""
    parts = list(map(int, time_stamp.split(':')))
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 4:
        return parts[0] * 86400 + parts[1] * 3600 + parts[2] * 60 + parts[3]
    
    raise ValueError(f"Unsupported timestamp format: {time_stamp}")


if __name__ == '__main__':
    main()