"""Build a captioned draft from real browser captures; never synthesize website frames."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CAPTIONS = [
    "个人材料：从账户菜单进入；本轮未上传新材料。",
    "已保存项目版本：查看实际提取的文件，不执行上传代码。",
    "静态原文与行号：不代表运行结果或本人贡献已核验。",
    "报告列表：读取已保存结果，本轮不调用网站模型。",
    "规则证据报告：描述材料支持程度，不是能力认证。",
    "按需展开来源：查看文件、行号和原文，其余来源仍收起。",
    "切换状态分组：本轮未创建补证任务或投递。",
    "合成热力图：三位虚构候选人，状态与分数均预设。",
    "选择候选人与要求：同步切换对照面板。",
    "证据联动雷达：缺少材料，不等于没有能力。",
    "查看雷达全图；零与不可评状态都须结合说明阅读。",
]
BOUNDARY = "分段网页实录 · 低帧率初稿 · 无配音 · 未录完整上传／新报告／企业／撤回链路"


def run(args, cwd, log):
    with log.open("xb") as handle:
        subprocess.run(args, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, check=True)


def card(path, title, lines, font):
    image = Image.new("RGB", (1920, 1080), "#f6f8fc")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 72, 1848, 1008), radius=36, fill="white", outline="#dce2f1")
    draw.text((140, 132), "职证 CareerProof · 演示初稿", fill="#4f46e5",
              font=ImageFont.truetype(str(font), 42))
    draw.text((140, 260), title, fill="#0f172a", font=ImageFont.truetype(str(font), 64))
    body = ImageFont.truetype(str(font), 38)
    for number, line in enumerate(lines):
        if draw.textlength(line, font=body) > 1630:
            raise ValueError("Title-card line exceeds the visible canvas")
        draw.text((140, 420 + number * 94), line, fill="#475569", font=body)
    image.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/msyh.ttc"))
    args = parser.parse_args()
    output, work = args.output.resolve(), args.work_dir.resolve()
    captures, font = args.capture_dir.resolve(), args.font.resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing video")
    work.mkdir(parents=True, exist_ok=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    index = json.loads((captures / "index.json").read_text(encoding="utf-8"))
    if len(index) != len(CAPTIONS):
        raise ValueError("This draft requires all observed browser clips")
    manifest = {"kind": "segmented real-browser draft", "native_fps": "see frame timestamps",
                "encoded_format": "1920x1080, H.264, 25fps, no audio",
                "clips": [], "limitations": BOUNDARY}
    common = ["-an", "-r", "25", "-c:v", "libx264", "-preset", "fast",
              "-crf", "20", "-pix_fmt", "yuv420p"]
    segments = []
    title_cards = [
        ("intro", "从材料到可核对的证据", [
            "正常本地网站的真实操作片段 · 2026-10-16",
            "演示学生、既有合成材料、已保存的规则报告",
            "热力图为预设示例；本轮不调用模型、不创建投递",
            "分段低帧率录制 · 本稿没有配音"], 5),
        ("outro", "本稿覆盖与待补录范围", [
            "已录：账户入口、材料原文、保存报告、证据联动",
            "待录：上传 → 新报告 → 企业回复 → 撤回与重投",
            "首次独立用户、真实 AI 语义与最终赛事格式仍待核对",
            "当前为分段初稿，不代表完整端到端演示已交付"], 8),
    ]
    for name, title, lines, duration in title_cards:
        card(work / f"{name}.png", title, lines, font)
        run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", "-loop", "1",
             "-i", f"{name}.png", "-t", str(duration), *common, f"{name}.mp4"],
            work, work / f"{name}.raw.out")
    segments.append("intro.mp4")
    font_filter = font.as_posix().replace(":", r"\:")
    (work / "boundary.txt").write_text(BOUNDARY, encoding="utf-8")
    for number, (item, caption) in enumerate(zip(index, CAPTIONS, strict=True), 1):
        data = json.loads((captures / item["name"] / "capture.json").read_text(encoding="utf-8"))
        frames = data["frames"]
        if len(frames) < 2 or any(b["ms"] <= a["ms"] for a, b in zip(frames, frames[1:])):
            raise ValueError("A real multi-frame capture with increasing timestamps is required")
        filename = f"clip-{number:02}"
        lines = ["ffconcat version 1.0"]
        for i, frame in enumerate(frames):
            source = captures / item["name"] / frame["file"]
            next_ms = frames[i + 1]["ms"] if i + 1 < len(frames) else data["durationMs"]
            lines += [f"file '{source.as_posix()}'", f"duration {(next_ms-frame['ms'])/1000:.6f}"]
        lines.append(f"file '{source.as_posix()}'")
        (work / f"{filename}.ffconcat").write_text("\n".join(lines)+"\n", encoding="utf-8")
        caption_font = ImageFont.truetype(str(font), 32)
        if caption_font.getlength(caption) > 1792:
            raise ValueError("Caption exceeds visible width")
        (work / f"{filename}.txt").write_text(caption, encoding="utf-8")
        filters = (
            "scale=1920:944:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1920:1080:(ow-iw)/2:0:color=0xf6f8fc,"
            "drawbox=x=0:y=944:w=1920:h=136:color=0x10172a:t=fill,"
            f"drawtext=fontfile='{font_filter}':textfile='{filename}.txt':"
            "fontsize=32:fontcolor=white:x=64:y=972,"
            f"drawtext=fontfile='{font_filter}':textfile='boundary.txt':"
            "fontsize=24:fontcolor=0xcbd5e1:x=64:y=1025"
        )
        run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", "-f", "concat",
             "-safe", "0", "-i", f"{filename}.ffconcat", "-vf", filters,
             "-t", str(data["durationMs"]/1000), *common, f"{filename}.mp4"],
            work, work / f"{filename}.raw.out")
        manifest["clips"].append({"name": item["name"], "caption": caption,
                                  "frame_count": len(frames), "duration_ms": data["durationMs"],
                                  "capture_sha256": hashlib.sha256(
                                      (captures/item["name"]/"capture.json").read_bytes()).hexdigest()})
        segments.append(f"{filename}.mp4")
        print(filename, "encoded", flush=True)
    segments.append("outro.mp4")
    (work / "segments.ffconcat").write_text(
        "ffconcat version 1.0\n"+"\n".join(f"file '{name}'" for name in segments)+"\n",
        encoding="utf-8")
    run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", "-f", "concat", "-safe",
         "0", "-i", "segments.ffconcat", "-c", "copy", "-movflags", "+faststart", str(output)],
        work, work / "assemble.raw.out")
    manifest["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest["bytes"] = output.stat().st_size
    (work / "build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n",
                                     encoding="utf-8")
    print("Draft video assembled", flush=True)


if __name__ == "__main__":
    main()
