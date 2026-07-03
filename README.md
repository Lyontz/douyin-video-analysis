# 🎬 抖音视频内容分析工具

从抖音分享链接中提取视频，通过关键帧视觉分析 + 音频转写，自动总结视频内容。

## ✨ 功能

- 🔗 解析抖音短链，提取视频 ID
- 📥 下载公开视频文件（绕过 PC 端反爬）
- 🎞️ ffmpeg 抽取关键帧（每 N 秒一帧）
- 🔊 ffmpeg 提取音频
- 👁️ 视觉模型识别画面中的中文文字（OCR）
- 🎙️ Whisper 语音转写（可选）
- 📝 自动合并总结视频内容

## 📋 前置条件

- **Python 3.8+**
- **ffmpeg**：https://ffmpeg.org/download.html
- **curl**：通常系统自带
- **（可选）openai-whisper**：音频转写

```bash
pip install openai-whisper   # 可选：音频转写
```

## 🚀 使用方法

### 基本用法

```bash
python analyze.py "https://v.douyin.com/XXXXX/"
```

### 完整参数

```bash
python analyze.py "https://v.douyin.com/XXXXX/" \
  --interval 10 \          # 抽帧间隔（秒），默认 10
  --output ./output \       # 输出目录，默认 ./output
  --whisper \               # 启用 Whisper 音频转写
  --whisper-model medium    # Whisper 模型，默认 medium
```

### 输出

```
output/
├── video.mp4           # 下载的原始视频
├── audio.mp3           # 提取的音频
├── frames/             # 关键帧图片
│   ├── frame_001.jpg
│   ├── frame_002.jpg
│   └── ...
└── summary.md          # 内容总结
```

## 🔧 工作原理

```
抖音短链 → 视频ID → 移动端页面 → play_addr → 下载视频
                                              ↓
                              ffmpeg 抽帧 + 提取音频
                                    ↓           ↓
                              视觉OCR识别    Whisper转写
                                    ↓           ↓
                                    └── 合并总结 ──┘
```

### 关键技术点

1. **绕过反爬**：抖音 PC 端有 jsvmprt 虚拟机级别的反爬，必须用移动端 UA 请求 `iesdouyin.com`
2. **提取 SSR 数据**：移动端页面的 HTML 中直接包含 `play_addr` 和视频描述
3. **ffmpeg 处理**：抽取关键帧 + 提取音频为 mp3

## 📖 Hermes Agent 技能

本工具也可以作为 [Hermes Agent](https://hermes-agent.nousresearch.com) 的技能使用。

将 `SKILL.md` 复制到 `~/.hermes/skills/media/douyin-video-analysis/SKILL.md` 即可。

## ⚠️ 注意事项

- 仅支持公开视频的分析
- 视频下载链接有时效性，解析后请尽快下载
- 请遵守抖音的使用条款，仅供个人学习使用
- 不支持需要登录才能查看的私密视频

## 📄 License

MIT
