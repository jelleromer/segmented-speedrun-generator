#!/bin/python3
# dependencies: ffmpeg, wget
import csv, collections, os, json, yt_dlp
from itertools import islice
Segment = collections.namedtuple("Segment", ["i", "name", "url", "time", "split_time", "player", "date", "notes", "start", "end"])

# preset should be "veryfast" during testing, then set to "slow" when done testing to render in higher quality
ffmpeg_preset = "slow"

def main():
    os.makedirs("cache", exist_ok=True)
    os.chdir("cache")
    sheet_id = "1n7gSPuIKCQB6p7HVNKRhNPaIxLcVLA7R3j1Ms28wJ7A"
    download_sheet(sheet_id, "DG%20Segmented")
    final_time, segments = parse_segments_tsv("data.tsv", 19)
    try:
        changed_segments = read_cache(segments)
        no_cache = False
    except FileNotFoundError:
        changed_segments = []
        no_cache = True
    download_videos(segments, changed_segments, no_cache)
    render_full_speedrun(segments, changed_segments, no_cache)
    generate_description(segments, changed_segments, sheet_id, final_time)
    write_cache(segments)

def download_sheet(sheet_id: str, sheet_name: str):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=tsv&sheet={sheet_name}"
    os.system(f"wget -nv '{url}' -O data.tsv")

# pandas doesn't seem to like rows with merged cells so it seems less rebust :/
# def parse_segments_tsv(filename: str, amount_of_segments: int) -> tuple[str, list[Segment]]:
#     with open(filename, "r") as f:
#         df = pd.read_csv(f, delimiter="\t")
#         df.fillna("", inplace=True) # replace NaN with ""
#         rows = df.iloc[3:3+amount_of_segments].values.tolist()
#         final_time = df.iloc[amount_of_segments + 2, 1]
#         return final_time, [Segment(i, *row[:9]) for i, row in enumerate(rows)]

def parse_segments_tsv(filename: str, amount_of_segments: int) -> tuple[str, list[Segment]]:
    with open(filename, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        rows = islice(reader, 2, 2 + amount_of_segments) # skip first two rows, get rows 3 through 21
        segments = [Segment(i, *row[:9]) for i, row in enumerate(rows)]
        next(reader) # skip one row
        final_time = list(next(reader))[1]
        return final_time, segments


def download_videos(segments: list[Segment], changed_segments: list[tuple[Segment, Segment]], no_cache: bool):
    if no_cache:
        segments_to_do = segments
    else:
        segments_to_do = [x for x, y in changed_segments if x.url != y.url]
    for s in segments_to_do:
        # os.system(f"rm {find_filename(s.i)}")
        try:
            os.remove(find_filename(s.i))
        except:
            pass
    download_videos_direct(segments_to_do)

def download_videos_direct(segments):
    for s in segments:
        # os.system(f"yt-dlp {s.url} -o {s.i}")
        with yt_dlp.YoutubeDL({"outtmpl": str(s.i)}) as ydl:
            ydl.download([s.url])


def render_full_speedrun(segments: list[Segment], changed_segments: list[tuple[Segment, Segment]], no_cache: bool):
    if no_cache:
        segments_to_do = segments
    else:
        segments_to_do = [x for x, _ in changed_segments]
    for s in segments_to_do:
        try:
            os.remove(f"trimmed_{s.i}.mp4")
        except:
            pass
    render_segments(segments_to_do)

    file_list = '\n'.join([f"file 'trimmed_{i}.mp4'" for i in range(len(segments))])
    with open("filelist.txt", "w") as f:
        f.write(file_list)
    # maybe?
    # -fflags +genpts -fflags +igndts
    os.system("ffmpeg -f concat -i filelist.txt -c copy -y notimer.mp4")
    ffmpeg_overlay_cmd = f'ffmpeg \
        -i notimer.mp4 \
        -i ../timer.mov \
        -filter_complex "[1:v]format=rgba[overlay];[0:v][overlay]overlay=0:0" \
        -preset {ffmpeg_preset} \
        -y \
        ../output.mp4'
    os.system(ffmpeg_overlay_cmd)


# returns segments where url, start or end changed
def read_cache(segments: list[Segment]) -> list[tuple[Segment, Segment]]:
    ComparisonSegment = collections.namedtuple("ComparisonSegment", ["i", "url", "start", "end"])
    def to_cmp(x: Segment):
        return ComparisonSegment(x.i, x.url, x.start, x.end)
    with open("cache.json", "r") as f:
        cache = [Segment(*x) for x in json.load(f)]
        return [(x, y) for x, y in zip(segments, cache) if to_cmp(x) != to_cmp(y)]

def write_cache(segments: list[Segment]):
    with open("cache.json", "w") as f:
        json.dump(segments, f)

def generate_description(segments: list[Segment], changed_segments: list[tuple[Segment, Segment]], sheet_id: str, final_time: str):
    desc = f"Ocarina of Time: Defeat Ganon in {final_time} (Segmented)\n"
    if changed_segments != []:
        if len(changed_segments) > 1:
            s = "s"
        else:
            s = ""
        updated = [f"{round(float(y.time)-float(x.time), 2)} ({x.time} → {y.time}) at {x.name.replace('->', '→')}" for x, y in changed_segments]
        desc += "\n".join([f"Updated segment{s}:"] + updated + ["\n"])
    else:
        desc += ""
    desc += "\n".join([f"{s.i+1}: {s.time} by {s.player} on {s.date} ({s.name.replace('->', '→')})" for s in segments])
    desc += f"\n\nDocument: https://docs.google.com/spreadsheets/d/{sheet_id}/\nLeaderboards: https://www.speedrun.com/oot#Defeat_Ganon"
    with open("desc.txt", "w") as f:
        f.write(desc)

# finds the first file whose filename matches (excluding file extension)
def find_filename(i: int) -> str:
    for file in os.listdir("."):
        if os.path.isfile(file):
            file_base, _ = os.path.splitext(file)
            if file_base == str(i):
                return file
    raise FileNotFoundError(f"can't find {i}")

# ffmpeg concat -f does not like videos that aren't uniform.
# So don't only trim the segments, render them into files that are as uniform as possible.
# The goal with the encoding is to approach this at high quality:
# https://support.google.com/youtube/answer/1722171

# RENDERING QUALITY
# preset should be set to "slow" when done testing to render in higher quality
# crf: lower crf means better quality, higher file size

# UNIFORMITY
# libx264, yuv420p, aac and its 44.1KHz bitrate are chosen because they match with youtube
# -map_metadata -1 removes all metadata from files. idk if it helps
# -video_track_timescale 18000
# -fflags +genpts
# -fflags +igndts
# The last three are failed attempts to solve the following warning I keep getting, idk how to fix it:
# [mov,mp4,m4a,3gp,3g2,mj2 @ 0x7fdafc01b2c0] Auto-inserting h264_mp4toannexb bitstream filterA
# [mp4 @ 0x55ba7662aa40] Non-monotonous DTS in output stream 0:1; previous: 77846, current: 77836; changing to 77847. This may result in incorrect timestamps in the output file.
# https://stackoverflow.com/questions/55914754/how-to-fix-non-monotonous-dts-in-output-stream-01-when-using-ffmpeg
# 
# This probably warned about the mismatched timecodes in the concatenated file. mpv will show the timecode skipping way more than 1 frame on cuts, and uploading the video to youtube will make it fill in the blanks with a bunch of duplicated frames. Fortunately, overlaying a timer with ffmpeg fixes this.
def render_segments(segments):
    for s in segments:
        fn = find_filename(s.i)
        ffmpeg_cmd = f"ffmpeg -ss {s.start} -to {s.end} "
        if s.start == "" and s.end == "":
            ffmpeg_cmd = "ffmpeg "
        ffmpeg_cmd += f'-i "{fn}" \
-s 1920x1080 \
-r 60 \
-preset {ffmpeg_preset} \
-c:v libx264 \
-crf 17 \
-pix_fmt yuv420p \
-video_track_timescale 18000 \
-c:a aac \
-ar 44100 \
-map_metadata -1 \
"trimmed_{s.i}.mp4"'
        os.system(ffmpeg_cmd)

# -fflags +igndts \
# -fflags +genpts \

if __name__ == "__main__":
    main()
