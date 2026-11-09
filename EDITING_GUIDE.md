# OpenShorts Automated Video Engine & Custom Editing Guide

This repository (`D:\youtube\Automate`) has been set up with the **OpenShorts** pipeline and extended with a custom **Anti-Copyright & Video Transformation Engine**.

---

## 🌟 1. Core Workflow: YouTube URL to Viral Shorts

1. **Input**: Any YouTube video URL (podcasts, tutorials, interviews, vlogs, etc.).
2. **Download & Transcribe**: Uses `yt-dlp` and `faster-whisper` to generate high-accuracy transcripts with word-level timestamps.
3. **Viral Moment Detection**: Scene boundary detection via `PySceneDetect` + LLM virality scoring (Gemini or local Ollama) to extract the 3–15 best 15–60s highlight moments with hooks and viral scores.
4. **Smart 9:16 Re-framing**:
   - `TRACK` mode: MediaPipe + YOLOv8 face tracking keeps the active speaker centered.
   - `GENERAL` mode: Centers the video over a blurred, enlarged background.
   - `SPLIT` mode: Vertically stacks two speakers (podcast view) and places subtitles along the middle seam.
   - `SCREENCAST` mode: Places the presenter as picture-in-picture over a shared screen.
5. **Dynamic Subtitles**: Word-by-word synced, colored subtitles (TikTok / Shorts style) burned with ASS / FFmpeg.
6. **Hook Text**: Attention-grabbing hook text overlays generated for the opening seconds.

---

## 🛠️ 2. Newly Added Feature: Custom Editor & Anti-Copyright Engine

We built and integrated **`custom_editor.py`** and added the **`POST /api/clip/custom-edit`** endpoint to allow flexible video editing and copyright evasion.

### Why Videos Get Copyright Claims & How Our Engine Protects You:
Automated Content ID systems (like YouTube, TikTok, and Meta) scan for exact matches across three vectors:
1. **Audio Fingerprints (Waveform & Frequency Spectrogram):**
   - *Our Solution*: Micro-speed acceleration (1.02x–1.05x) shifts temporal audio cadence. Micro-pitch detune (`asetrate=44100*1.012`) and equalizer shift disrupt automated waveform matchers without sounding unnatural to human ears.
2. **Visual Hashes (Perceptual Frame Hashes & Pixel Alignment):**
   - *Our Solution*: Subtle dynamic micro-zoom (3–4%), color histogram shifting (contrast +4%, saturation +6%, gamma +2%), vignette edge shading, and optional horizontal flipping (`hflip`) ensure no frame matches the source video pixel-for-pixel.
3. **Container Metadata:**
   - *Our Solution*: Automatic metadata wiping (`METADATA_SCRUB`) strips original camera tags, Google/YouTube stream handler tags, and encoder traces.

---

## 🚀 3. How to Use the Custom Editing Features

### A. Via Python CLI:
Run on any video or generated short:
```bash
# Apply full anti-copyright transformation with blurred 9:16 background:
python custom_editor.py --input "input_clip.mp4" --output "output_clip.mp4" --speed 1.03 --bg blur

# Apply solid dark background framing with a mirror flip:
python custom_editor.py --input "input_clip.mp4" --output "output_clip.mp4" --bg solid --bg-color "#121212" --flip

# Burn custom subtitles (.ass) and watermark text:
python custom_editor.py --input "input_clip.mp4" --output "output_clip.mp4" --subtitles "subs.ass" --watermark "@MyChannel"
```

#### CLI Options:
- `--speed`: Playback speed factor (e.g. `1.02` to `1.05`, default `1.03`).
- `--bg`: Background style (`keep`, `blur`, `solid`).
- `--bg-color`: Color for solid matte background (default `black`).
- `--flip`: Enables horizontal mirroring.
- `--no-pitch`: Disables audio pitch shift (enabled by default).
- `--no-color`: Disables color histogram adjustments (enabled by default).
- `--no-zoom`: Disables micro-zoom (enabled by default).
- `--subtitles`: Path to `.ass` subtitle file to burn.
- `--watermark`: Text overlay to stamp on the video.

---

### B. Via Backend REST API:
You can call the newly added endpoint on `http://localhost:8000/api/clip/custom-edit`:

```bash
curl -X POST "http://localhost:8000/api/clip/custom-edit" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "<job_id>",
    "clip_index": 0,
    "speed": 1.03,
    "pitch_shift": true,
    "color_shift": true,
    "micro_zoom": true,
    "flip_horizontal": false,
    "background_style": "blur",
    "bg_color": "black",
    "watermark_text": "@MyShorts"
  }'
```

---

## 🖥️ 4. Running the Entire Application

### Option 1: Docker Compose (Full Stack - Recommended)
1. Open Docker Desktop on Windows.
2. In `D:\youtube\Automate`, run:
   ```bash
   docker compose up --build
   ```
3. Open your browser:
   - **Frontend Dashboard:** [http://localhost:5175](http://localhost:5175)
   - **Backend API & Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Option 2: Local Development Mode (Without Docker)
1. **Start the Frontend Dashboard:**
   ```bash
   cd D:\youtube\Automate\dashboard
   npm run dev
   ```
   (Opens on [http://localhost:5173](http://localhost:5173))
2. **Start the Backend API:**
   ```bash
   cd D:\youtube\Automate
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

### Option 3: Direct Pipeline CLI
To generate shorts directly from a YouTube URL without opening the browser:
```bash
cd D:\youtube\Automate
python main.py -u "https://www.youtube.com/watch?v=VIDEO_ID" -o output/my_run
```
