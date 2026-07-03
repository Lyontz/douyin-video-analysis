#!/usr/bin/env python3
"""
抖音视频内容分析工具
从抖音分享链接中提取视频，通过关键帧视觉分析 + 音频转写，总结视频内容。

用法:
    python analyze.py "https://v.douyin.com/XXXXX/"
    python analyze.py "https://v.douyin.com/XXXXX/" --interval 5 --whisper
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


# ── 常量 ──────────────────────────────────────────────

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
    "Mobile/15E148 Safari/604.1"
)

DOUYIN_SHARE_URL = "https://www.iesdouyin.com/share/video/{video_id}"


# ── Step 1: 解析短链，获取视频 ID ─────────────────────

def extract_video_id(url: str) -> str:
    """从抖音分享链接中提取视频 ID"""
    # 直接是纯数字 ID
    if url.strip().isdigit():
        return url.strip()

    # 短链格式: https://v.douyin.com/XXXXX/
    # 先解析短链拿到真实 URL
    if "v.douyin.com" in url or "vm.tiktok.com" in url:
        try:
            result = subprocess.run(
                ["curl", "-sIL", "-o", "/dev/null", "-w", "%{url_effective}", url],
                capture_output=True, text=True, timeout=15
            )
            real_url = result.stdout.strip()
            if real_url:
                url = real_url
        except Exception:
            pass

    # 从 URL 中提取数字 ID
    patterns = [
        r'/video/(\d+)',
        r'/note/(\d+)',
        r'modal_id=(\d+)',
        r'/(\d{15,})',  # 抖音 ID 通常是 15+ 位数字
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"无法从 URL 中提取视频 ID: {url}")


# ── Step 2: 请求移动端页面，提取视频信息 ──────────────

def fetch_video_info(video_id: str) -> dict:
    """从抖音移动端页面提取视频信息"""
    import tempfile

    url = DOUYIN_SHARE_URL.format(video_id=video_id)
    tmp_file = os.path.join(tempfile.gettempdir(), "dy_page.html")

    subprocess.run(
        ["curl", "-sL", "-H", f"User-Agent: {MOBILE_UA}", url, "-o", tmp_file],
        timeout=30
    )

    with open(tmp_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    info = {"video_id": video_id}

    # 提取 play_addr
    play_match = re.search(r'"play_addr":\{[^}]+\}', content)
    if play_match:
        play_text = play_match.group(0)
        # 提取 URL
        url_match = re.search(r'"url_list":\["([^"]+)"', play_text)
        if url_match:
            video_url = url_match.group(1).replace("\\u002F", "/")
            info["play_url"] = video_url

        # 提取 uri
        uri_match = re.search(r'"uri":"([^"]+)"', play_text)
        if uri_match:
            info["video_uri"] = uri_match.group(1)

    # 提取描述
    desc_match = re.search(r'"desc":"([^"]*)"', content)
    if desc_match:
        info["desc"] = desc_match.group(1)

    # 提取作者
    author_match = re.search(r'"nickname":"([^"]*)"', content)
    if author_match:
        info["author"] = author_match.group(1)

    # 提取统计数据
    for stat in ["digg_count", "comment_count", "share_count", "collect_count"]:
        stat_match = re.search(rf'"{stat}":(\d+)', content)
        if stat_match:
            info[stat] = int(stat_match.group(1))

    return info


# ── Step 3: 下载视频 ────────────────────────────────

def download_video(play_url: str, output_path: str) -> str:
    """下载视频文件"""
    subprocess.run(
        ["curl", "-sL", "-H", f"User-Agent: {MOBILE_UA}", play_url, "-o", output_path],
        timeout=120
    )

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError("视频下载失败")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ 视频下载完成: {output_path} ({size_mb:.1f} MB)")
    return output_path


# ── Step 4: ffmpeg 抽帧 + 提取音频 ───────────────────

def extract_frames(video_path: str, frames_dir: str, interval: int = 10) -> list:
    """用 ffmpeg 抽取关键帧"""
    os.makedirs(frames_dir, exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps=1/{interval}",
         "-q:v", "2", os.path.join(frames_dir, "frame_%03d.jpg")],
        capture_output=True, timeout=300
    )

    frames = sorted(Path(frames_dir).glob("frame_*.jpg"))
    print(f"✅ 抽取 {len(frames)} 帧（间隔 {interval}s）")
    return [str(f) for f in frames]


def extract_audio(video_path: str, audio_path: str) -> str:
    """用 ffmpeg 提取音频"""
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame",
         "-q:a", "2", audio_path],
        capture_output=True, timeout=300
    )

    if os.path.exists(audio_path):
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"✅ 音频提取完成: {audio_path} ({size_mb:.1f} MB)")
    return audio_path


# ── Step 5: Whisper 音频转写（可选）───────────────────

def transcribe_audio(audio_path: str, model: str = "medium") -> str:
    """用 Whisper 转写音频"""
    try:
        import whisper
    except ImportError:
        print("⚠️  未安装 whisper，跳过音频转写")
        print("   安装命令: pip install openai-whisper")
        return ""

    print(f"🎙️  Whisper 转写中（模型: {model}）...")
    m = whisper.load_model(model)
    result = m.transcribe(audio_path, language="zh")

    transcript = result.get("text", "")
    print(f"✅ 转写完成，共 {len(transcript)} 字")
    return transcript


# ── Step 6: 生成总结 ─────────────────────────────────

def generate_summary(info: dict, frames: list, transcript: str, output_dir: str):
    """生成内容总结文件"""
    summary_path = os.path.join(output_dir, "summary.md")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# 视频分析总结\n\n")
        f.write(f"**视频 ID**: {info.get('video_id', 'N/A')}\n")
        f.write(f"**作者**: {info.get('author', 'N/A')}\n")
        f.write(f"**描述**: {info.get('desc', 'N/A')}\n\n")

        # 互动数据
        f.write("## 📊 互动数据\n\n")
        stats = {
            "digg_count": "点赞",
            "comment_count": "评论",
            "share_count": "分享",
            "collect_count": "收藏",
        }
        for key, label in stats.items():
            if key in info:
                f.write(f"- **{label}**: {info[key]:,}\n")
        f.write("\n")

        # 关键帧
        f.write(f"## 🎞️ 关键帧（共 {len(frames)} 帧）\n\n")
        f.write("关键帧已保存到 `frames/` 目录。\n")
        f.write("建议使用 AI 视觉模型（如 GPT-4o、Claude）逐帧分析画面文字。\n\n")

        # 音频转写
        if transcript:
            f.write("## 🎙️ 音频转写\n\n")
            f.write(f"共 {len(transcript)} 字\n\n")
            f.write("```\n")
            f.write(transcript[:5000])
            if len(transcript) > 5000:
                f.write("\n... (截断，完整转写见 transcript.txt)")
            f.write("\n```\n\n")

            # 保存完整转写
            with open(os.path.join(output_dir, "transcript.txt"), "w", encoding="utf-8") as tf:
                tf.write(transcript)

        f.write("---\n\n")
        f.write("*本文件由 douyin-video-analysis 自动生成*\n")

    print(f"✅ 总结已保存: {summary_path}")


# ── Main ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="抖音视频内容分析工具")
    parser.add_argument("url", help="抖音分享链接或视频 ID")
    parser.add_argument("--interval", type=int, default=10, help="抽帧间隔（秒），默认 10")
    parser.add_argument("--output", "-o", default="./output", help="输出目录，默认 ./output")
    parser.add_argument("--whisper", action="store_true", help="启用 Whisper 音频转写")
    parser.add_argument("--whisper-model", default="medium", help="Whisper 模型，默认 medium")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载（使用已有视频文件）")
    parser.add_argument("--video", help="直接指定本地视频文件路径")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 解析视频 ID
    print("🔗 Step 1: 解析视频链接...")
    video_id = extract_video_id(args.url)
    print(f"   视频 ID: {video_id}")

    # Step 2: 获取视频信息
    print("📡 Step 2: 获取视频信息...")
    info = fetch_video_info(video_id)
    print(f"   作者: {info.get('author', 'N/A')}")
    print(f"   描述: {info.get('desc', 'N/A')[:60]}...")

    # Step 3: 下载视频
    if args.video:
        video_path = args.video
        print(f"📁 使用本地视频: {video_path}")
    elif not args.skip_download:
        print("📥 Step 3: 下载视频...")
        video_path = os.path.join(output_dir, "video.mp4")
        download_video(info["play_url"], video_path)
    else:
        video_path = os.path.join(output_dir, "video.mp4")
        print(f"⏭️  跳过下载，使用: {video_path}")

    # Step 4: 抽帧 + 提取音频
    print("🎞️  Step 4: 抽取关键帧...")
    frames_dir = os.path.join(output_dir, "frames")
    frames = extract_frames(video_path, frames_dir, args.interval)

    print("🔊 Step 5: 提取音频...")
    audio_path = os.path.join(output_dir, "audio.mp3")
    extract_audio(video_path, audio_path)

    # Step 5: 音频转写（可选）
    transcript = ""
    if args.whisper:
        print("🎙️  Step 6: Whisper 音频转写...")
        transcript = transcribe_audio(audio_path, args.whisper_model)

    # Step 6: 生成总结
    print("📝 Step 7: 生成总结...")
    generate_summary(info, frames, transcript, output_dir)

    print(f"\n🎉 分析完成！输出目录: {output_dir}")


if __name__ == "__main__":
    main()
