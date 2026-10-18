"""Add disclosed local Mandarin speech to existing real capture batches."""

import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

from build_demo_video import card, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.output.resolve()
    if output.exists():
        raise FileExistsError("Existing video preserved")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    parts = manifest["parts"]
    expected = ["intro"] + [f"clip-{i:02}" for i in range(1, 36)] + ["technology", "outro"]
    if [part["name"] for part in parts] != expected:
        raise ValueError("Expected exactly the reviewed 35 clips and three explanatory cards")
    work.mkdir(parents=True, exist_ok=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    source, font = Path(__file__).resolve().parent, Path("C:/Windows/Fonts/msyh.ttc")
    story_path = work / "story.json"
    story_path.write_text(json.dumps(manifest["story"], ensure_ascii=False), encoding="utf-8")
    run([
        "powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(source / "synthesize_demo_narration.ps1"), "-Manifest", str(args.manifest.resolve()),
        "-OutputDirectory", str(work / "speech"),
    ], work, work / "speech.raw.out")
    index = json.loads((args.capture_dir / "index.json").read_text(encoding="utf-8"))
    original = {"intro": 5, "outro": 8, "technology": 0}
    for i, item in enumerate(index, 1):
        capture = json.loads((args.capture_dir / item["name"] / "capture.json").read_text(encoding="utf-8"))
        original[f"clip-{i:02}"] = capture["durationMs"] / 1000
    plan = []
    for part in parts:
        name = part["name"]
        with wave.open(str(work / "speech" / f"{name}.wav"), "rb") as stream:
            spoken = stream.getnframes() / stream.getframerate()
        duration = max(original[name], spoken + 0.75)
        plan.append({"name": name, "text": part["text"], "speechSeconds": spoken,
                     "originalSeconds": original[name], "outputSeconds": duration,
                     "endFrameHoldSeconds": max(0, duration - original[name])})
    total = sum(part["outputSeconds"] for part in plan)
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if not 300 <= total <= 480:
        raise ValueError(f"Natural narration plan is {total:.2f}s; revise content, do not pad to pass")
    run([
        sys.executable, str(source / "build_demo_video.py"), "--capture-dir",
        str(args.capture_dir.resolve()), "--output", str(work / "captioned-source.mp4"),
        "--work-dir", str(work / "source"), "--story", str(story_path),
    ], work, work / "source-build.raw.out")
    card(work / "technology.png", manifest["technology"]["title"],
         manifest["technology"]["lines"], font)
    for part in plan:
        name, duration = part["name"], part["outputSeconds"]
        video = ["-loop", "1", "-i", "technology.png"] if name == "technology" else [
            "-i", f"source/{name}.mp4"
        ]
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", *video,
            "-i", f"speech/{name}.wav", "-vf", f"tpad=stop_mode=clone:stop_duration={duration}",
            "-af", "apad", "-t", str(duration), "-r", "25", "-c:v", "libx264",
            "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-ar", "48000", "-ac", "1", "-b:a", "128k", f"voiced-{name}.mp4",
        ], work, work / f"voiced-{name}.raw.out")
        print(name, "voiced", flush=True)
    (work / "voiced.ffconcat").write_text(
        "ffconcat version 1.0\n" + "\n".join(
            f"file 'voiced-{part['name']}.mp4'" for part in plan
        ) + "\n", encoding="utf-8",
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", "-f", "concat", "-safe",
        "0", "-i", "voiced.ffconcat", "-c", "copy", "-movflags", "+faststart", str(output),
    ], work, work / "assemble.raw.out")
    report = {"kind": "segmented synthetic-data demo with disclosed offline Mandarin TTS",
              "voice": manifest["voice"], "rate": manifest["rate"], "plannedSeconds": total,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
              "bytes": output.stat().st_size, "parts": plan,
              "limitations": ["Not a frozen candidate or continuous recording",
                              "Source screenshots are low frame rate and upscaled",
                              "End-frame holds are listed per segment",
                              "No fresh external AI result; independent human review pending"]}
    (work / "narrated-build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"seconds": total, "bytes": report["bytes"]}), flush=True)


if __name__ == "__main__":
    main()
