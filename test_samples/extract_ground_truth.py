"""Extrahuje plain-text z první 3 minuty .vtt titulků pro porovnání s Whisper přepisem."""
import re
import sys
from pathlib import Path

MAX_SECONDS = 180  # první 3 min


def vtt_time_to_seconds(t: str) -> float:
    # 00:00:05.000 nebo 00:05.000
    parts = t.strip().split(":")
    if len(parts) == 3:
        h, m, rest = parts
        s = float(rest)
        return int(h) * 3600 + int(m) * 60 + s
    if len(parts) == 2:
        m, rest = parts
        return int(m) * 60 + float(rest)
    return float(parts[0])


def main(vtt_path: Path) -> None:
    text = vtt_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    output: list[str] = []
    cue_active = False
    cue_start = 0.0
    skip_cue = False

    for raw in lines:
        line = raw.strip()
        if "-->" in line:
            # 00:00:05.000 --> 00:00:08.000 align...
            m = re.match(r"(\d{1,2}:[\d:.]+)\s*-->\s*(\d{1,2}:[\d:.]+)", line)
            if m:
                cue_start = vtt_time_to_seconds(m.group(1))
                cue_active = True
                skip_cue = cue_start > MAX_SECONDS
            continue
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("Kind:") or line.startswith("Language:"):
            cue_active = False
            continue
        if cue_active and not skip_cue:
            # Odstranit inline tagy <c>, <00:00:05.000> apod.
            clean = re.sub(r"<[^>]+>", "", line)
            clean = clean.strip()
            if clean and clean not in ("[Hudba]", "[Music]"):
                output.append(clean)

    # Dedupe sousedních řádků (VTT často duplikuje pro karaoke)
    deduped: list[str] = []
    for s in output:
        if not deduped or deduped[-1] != s:
            deduped.append(s)

    text_out = " ".join(deduped)
    print(text_out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: extract_ground_truth.py <file.vtt>", file=sys.stderr)
        sys.exit(2)
    main(Path(sys.argv[1]))
