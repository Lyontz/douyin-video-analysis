---
name: douyin-video-analysis
description: 分析抖音（Douyin/TikTok）视频内容——解析短链、下载视频、抽帧+音频、视觉识别画面文字、总结内容
tags: [douyin, tiktok, video, analysis, ffmpeg, vision, ocr]
triggers:
  - 抖音视频分析
  - douyin video analysis
  - 分析抖音
  - 抖音链接
---

# 抖音视频内容分析

从抖音分享链接中提取视频，通过关键帧视觉分析 + 音频转写，总结视频内容。

## 前置条件

- **ffmpeg**：用于抽帧和提取音频（`which ffmpeg` 验证）
- **curl**：下载视频文件
- **vision_analyze**：Hermes 内置视觉分析工具
- **Windows 注意**：vision_analyze 需要 Windows 原生路径（如 `C:/Users/...`），不支持 MSYS 的 `/tmp/` 路径

## 完整流程

### Step 1: 解析短链，获取视频 ID

```bash
# 从分享链接中提取视频ID，格式通常为：
# https://v.douyin.com/XXXXX/
# 或直接是数字 ID：7657994105967938822
VIDEO_ID="7657994105967938822"
```

### Step 2: 请求移动端页面，提取视频地址

抖音 PC 页面有强反爬（jsvmprt 虚拟机混淆），**必须用移动端 UA**：

```bash
curl -sL \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1" \
  "https://www.iesdouyin.com/share/video/${VIDEO_ID}" \
  -o /tmp/dy_page.html
```

提取视频播放地址和描述：

```bash
# 提取 play_addr（含视频播放URL）
grep -oP '"play_addr":\{[^}]+\}' /tmp/dy_page.html

# 提取视频描述/标题
grep -oP '"desc":"[^"]*"' /tmp/dy_page.html
```

play_addr 中的 URL 需要反转义 `\u002F` → `/`。

### Step 3: 下载视频

```bash
VIDEO_URL="https://aweme.snssdk.com/aweme/v1/playwm/?video_id=xxx&ratio=720p&line=0"
curl -sL -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)" \
  "$VIDEO_URL" -o /tmp/douyin_video.mp4
```

### Step 4: 用 ffmpeg 抽取关键帧和音频

```bash
# 抽关键帧（每10秒一帧，约3分钟视频得~21帧）
mkdir -p /tmp/dy_frames
ffmpeg -y -i /tmp/douyin_video.mp4 -vf "fps=1/10" -q:v 2 /tmp/dy_frames/frame_%03d.jpg

# 提取音频（为后续 Whisper 转写准备）
ffmpeg -y -i /tmp/douyin_video.mp4 -vn -acodec libmp3lame -q:a 2 /tmp/douyin_audio.mp3
```

### Step 5: 用 vision_analyze 分析关键帧

**⚠️ Windows 关键点**：vision_analyze 不识别 MSYS 的 `/tmp/` 路径，需要用 Windows 原生路径：

```python
# /tmp 在 Windows 上通常是 C:/Users/<user>/AppData/Local/Temp/
# 用 realpath 确认：realpath /tmp/dy_frames/frame_001.jpg
```

对关键帧逐一分析，提取画面中的中文文字（排行列表、技能名称、数值等）：

```python
vision_analyze(
    image_url="C:/Users/yq/AppData/Local/Temp/dy_frames/frame_001.jpg",
    question="这是游戏视频截图。请仔细读取画面中所有中文文字，特别是排行列表、技能名称、数值等内容。"
)
```

**优化策略**：
- 先分析第1帧了解视频大致内容
- 批量分析（每4帧一批并行调用）提高效率
- 根据首帧内容调整后续帧的分析问题

### Step 6: 音频转写（可选）

如果关键帧信息不足以覆盖视频全部内容，用 Whisper 转写音频：

```bash
# 需要安装：pip install openai-whisper
whisper /tmp/douyin_audio.mp3 --language zh --model medium --output_format txt
```

或用 Vosk 等本地模型。

### Step 7: 合并总结

将关键帧文字识别结果 + 音频转写文本合并，生成结构化的内容总结。

## 常见坑

1. **PC 页面反爬**：抖音 PC 端有 jsvmprt 虚拟机级别的反爬，curl 拿到的只是混淆 JS，必须用移动端页面
2. **vision_analyze 路径**：Windows 上 MSYS 的 `/tmp/` 不被识别，要用 `C:/Users/<user>/AppData/Local/Temp/` 格式
3. **视频下载有时效**：play_addr 中的 URL 有时效性，解析后应尽快下载
4. **帧间隔选择**：10秒/帧适合大多数视频，快节奏视频可缩短到5秒
5. **批量并行**：vision_analyze 支持批量并行调用，4个一批效率最高
