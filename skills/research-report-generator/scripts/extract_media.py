#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_media.py — 调研素材预处理（视频/音频）

用法:
  python extract_media.py <input> <output_dir> [--interval 5] [--max-frames 240]

输入:
  - 视频: mp4/mov/mkv/webm/flv...（有画面可抽帧）
  - 音频: mp3/wav/m4a/aac/flac...（仅提取音频，无抽帧）

输出:
  <output_dir>/meta.json           ffprobe 元数据（时长/分辨率/fps/编码/帧清单）
  <output_dir>/frames/f_001.jpg    视频每 interval 秒抽一帧（仅视频输入）
  <output_dir>/audio.wav           提取的 16kHz 单声道音频（供 ASR 转写）

依赖: 需要 ffmpeg / ffprobe 在 PATH 中（macOS: brew install ffmpeg）
"""

import argparse
import fractions
import json
import os
import shutil
import subprocess
import sys


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("命令失败: %s\n%s" % (" ".join(cmd), r.stderr[:800]))
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_format", "-show_streams", path])
    return json.loads(out)


def hms(sec):
    sec = int(sec)
    return "%dh%02dm%02ds" % (sec // 3600, sec % 3600 // 60, sec % 60)


def main():
    ap = argparse.ArgumentParser(description="调研素材预处理：抽帧 + 提音频 + 元数据")
    ap.add_argument("input", help="视频或音频文件路径")
    ap.add_argument("output_dir", help="输出目录（不存在则自动创建）")
    ap.add_argument("--interval", type=float, default=5.0, help="抽帧间隔秒数（默认 5）")
    ap.add_argument("--max-frames", type=int, default=240, help="最大抽帧数（默认 240）")
    args = ap.parse_args()

    src = os.path.abspath(args.input)
    if not os.path.isfile(src):
        sys.exit("文件不存在: %s" % src)
    for tool in ("ffprobe", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit("缺少 %s，请先安装 ffmpeg（macOS: brew install ffmpeg）" % tool)

    out = os.path.abspath(args.output_dir)
    os.makedirs(out, exist_ok=True)

    meta = probe(src)
    fmt = meta.get("format", {})
    duration = float(fmt.get("duration", 0) or 0)
    streams = meta.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
    astream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    info = {
        "source": src,
        "filename": os.path.basename(src),
        "duration_sec": round(duration, 1),
        "duration_hms": hms(duration),
        "video": None,
        "audio": None,
    }
    if vstream:
        fps = None
        if vstream.get("r_frame_rate"):
            try:
                fps = float(fractions.Fraction(vstream["r_frame_rate"]))
            except (ValueError, ZeroDivisionError):
                fps = None
        info["video"] = {
            "codec": vstream.get("codec_name"),
            "width": vstream.get("width"),
            "height": vstream.get("height"),
            "fps": round(fps, 2) if fps else None,
        }
    if astream:
        info["audio"] = {
            "codec": astream.get("codec_name"),
            "channels": astream.get("channels"),
            "sample_rate": astream.get("sample_rate"),
        }

    frames = []
    if vstream:
        frames_dir = os.path.join(out, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        pattern = os.path.join(frames_dir, "f_%03d.jpg")
        run(["ffmpeg", "-y", "-i", src, "-vf",
             "fps=1/%s" % args.interval, "-q:v", "2", pattern])
        frames = sorted(f for f in os.listdir(frames_dir) if f.endswith(".jpg"))
        frames = frames[: args.max_frames]
        info["frames"] = [{"file": f, "path": os.path.join(frames_dir, f)} for f in frames]
        info["frame_count"] = len(frames)
        info["frame_interval_sec"] = args.interval

    if astream:
        wav = os.path.join(out, "audio.wav")
        run(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", wav])
        info["audio_wav"] = wav
        info["asr_hint"] = ("已提取 16kHz 单声道音频，可调用本地 ASR/whisper 或云转写服务生成逐字稿；"
                            "若无可用转写工具，向用户索取逐字稿或让其确认仅做帧级视觉分析")

    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("\n[OK] 元数据: %s" % os.path.join(out, "meta.json"))
    if frames:
        print("[OK] 抽帧 %d 张 -> %s" % (len(frames), frames_dir))
    if info.get("audio_wav"):
        print("[OK] 音频提取 -> %s" % wav)
    if not vstream and not astream:
        print("[WARN] 未检测到音视频流，请确认文件格式")


if __name__ == "__main__":
    main()
