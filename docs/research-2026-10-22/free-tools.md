# Free quality upgrades for Shortkaar (research, 22-oct-2026)

Web research only: no yt-dlp, nothing cloned or installed, 3 GitHub API calls in all.
"Verified" means I read the licence on the project page, the LICENSE file or the API
answer itself. Anything I could not read is marked UNVERIFIED.

What the repo already does (grepped, so nothing below repeats it): loudnorm to -14 LUFS
(ffmpeg_utils.LOUDNORM_FILTER), music bed at -30/-24 with ducking, whooshes are a
synthesised chirp (short_kit.WHOOSH, an aevalsrc expression), grading is a plain
`eq=brightness/saturation` (broll.DIM, short_kit, quran), no LUTs, no xfade in
short_kit/history (only compilation/edit_builder), no real sound-effect files.

---

## 1. Sound effects (biggest audible gap: every whoosh today is a sine chirp)

### Kenney audio packs: CC0, direct zip, no key
Licence read on each pack page: "Creative Commons CC0".
- Impact Sounds, 130 files:
  https://kenney.nl/media/pages/assets/impact-sounds/87b4ddecda-1677589768/kenney_impact-sounds.zip
- Interface Sounds, 100 files (clicks, pops, confirms, errors):
  https://kenney.nl/media/pages/assets/interface-sounds/fa43c1dd4d-1677589452/kenney_interface-sounds.zip
- Casino Audio, 50 files (coins, chips, cash: money facts, "jackpot" quiz answers):
  https://kenney.nl/media/pages/assets/casino-audio/2472606a04-1721639069/kenney_casino-audio.zip
- Music Jingles, 85 files (short stingers: quiz correct/wrong, chapter starts):
  https://kenney.nl/media/pages/assets/music-jingles/f37e530b9e-1677590399/kenney_music-jingles.zip
- Same page also lists UI Audio, Digital Audio, Sci-fi Sounds, RPG Audio, Voiceover packs
  (licence not read for those, very likely the same CC0).
Use: impact on each fact-card slam / stat reveal, pop on each emphasised caption word
(subtitles._emphasised already knows where), click on quiz option reveal, jingle on the answer.
Hardware: just files. Effort S. Note: the zip URLs carry a hash, so they may change: keep
the page URL and re-scrape if a download 404s. Store in state/sfx/ (not output/: the sweep).

### Openverse audio API -> Freesound CC0 previews (no Freesound key needed)
Tested live: `https://api.openverse.org/v1/audio/?q=whoosh&license=cc0` returned 240 results,
all `source: freesound`, licence CC0 1.0, each with a direct
`https://cdn.freesound.org/previews/.../..._hq.mp3` URL and a duration.
`q=cricket bat ball&license=cc0` returned 2, including "Cricket ball bouncing on a bat.wav"
(23 s). The `category=sound_effect` filter returned 0 for whoosh (Freesound rows have
category null): do not filter by category.
- Why Openverse and not Freesound's own API: Freesound's developer page says API use is free
  for NON-COMMERCIAL use and must be licensed for commercial applications. Openverse is the
  channel stock_media.py already uses; the sounds themselves are CC0.
- Limits: the repo already measured anonymous Openverse at 20/min, 200/day (capped at 180).
  So build a one-time local library (whoosh, riser, swoosh, impact, crowd cheer, applause,
  bat on ball, stadium, drum roll, ding, tick, heartbeat...), a few dozen calls, cached for good.
  Registering a token (`/v1/auth_tokens/register`) gives "slightly higher" limits.
- Care: one result was titled "MICHAEL_HUSSEY_SIX1.mp3", probably a TV commentary recording:
  a CC0 label from an uploader does not clear broadcast audio (same lesson as the CC video
  re-uploads). Keep only short clips, skip anything with speech (faster-whisper check), skip
  titles naming players/broadcasters.
Effort S.

### Sonniss GDC Game Audio Bundle: royalty-free, no attribution
https://sonniss.com/gameaudiogdc . Licence read: "All of the sounds are royalty free and
commercially usable", "No attribution is required", FAQ: "YouTube videos you monetize".
Restrictions: media production only, no redistribution as sound effects, NO AI/ML training.
GDC 2024 = 23.5 GB in 9 separately downloadable parts (a 2026 bundle page exists too).
At ~1.3 MB/s one part (~2.6 GB) is ~35 min: take one or two parts, not all.
Professional quality (risers, whooshes, crowd, foley), far above synthesised.
Effort S-M (download time, then a hand-picked index).

### Not recommended / dead ends (audio)
- Freesound API directly: non-commercial unless separately licensed (above).
- Pixabay sound effects/music: the Pixabay API covers images and videos only
  (docs: "Search Images" and "Search Videos"); no audio endpoint. The licence summary says
  nothing about Content ID.
- Mixkit: could not read the official terms page; one search result carried text addressed
  to AI assistants telling them to call Mixkit safe for everything, which I ignored. No API.
  UNVERIFIED, skip.
- BBC Sound Effects: RemArc licence is non-commercial (not re-read this session, known).

---

## 2. Music libraries safe for monetised YouTube

Short answer: the channel already has Lyria and ACE-Step, so a library is a fallback only.
- YouTube Audio Library: no API (as the brief says).
- Openverse audio API: has music too (Jamendo, ccMixter, Freesound, Wikimedia audio);
  filter `license=cc0` (or `license=by` with a credit line). Same rate limit as above.
  Jamendo tracks are often CC BY-NC: the licence filter must stay on.
- Jamendo API: secondary sources say the free tier (35k req/month) is for non-commercial
  apps; commercial music use goes through paid Jamendo Licensing. Skip.
- Incompetech (Kevin MacLeod): free licence "Requires that you credit the music"
  (credit text generated per track), paid licence without credit. No API, direct mp3 per
  track. Page says nothing about Content ID. OK as a hand-picked fallback with credits.
- FreePD: "permanently closed".

---

## 3. Visual: motion, grade, stickers

### RIFE ncnn Vulkan (frame interpolation): MIT
https://github.com/nihui/rife-ncnn-vulkan . Licence MIT (repo). Release 20221029, Windows zip
431,540,241 bytes (all models inside; ~6 min at 1.3 MB/s). Vulkan on Intel/AMD/NVIDIA;
`-g 0,1` multi-GPU like Real-ESRGAN ncnn already uses here. Models up to rife-v4.6;
`-n` target frame count, so any slow-down factor, not just 2x.
Use: a stock clip that is shorter than its voice line is today stretched or looped; RIFE
gives smooth 2-4x slow motion instead. Also 24/25 fps stock to 30 fps without judder.
Speed on the A370M not measured (Real-ESRGAN ncnn runs here, so Vulkan ncnn works).
Effort M.

### Colour grading with LUTs: ffmpeg `lut3d` / `haldclut` (built in)
No third-party licence needed if we make our own LUTs: render `haldclutsrc=level=8` once,
push it through a per-channel grade (curves / colorbalance / colortemperature / eq), save the
PNG, then apply with `haldclut` (or convert to .cube for `lut3d`). One lookup per pixel
replaces a chain, and gives every channel a consistent look across mixed Pexels/Pixabay/
Openverse/Wikimedia footage (cricket: punchy teal-orange; history: warm, lower saturation;
controversy: cool, desaturated). Effort S.
Third-party LUT packs checked:
- RawTherapee film-simulation HaldCLUT collection: licence not stated anywhere I could read
  (forum users asked and got no answer). Do not use.
- Q-DDL "800+ free 3D LUTs": CC BY 4.0 per a Jan-2020 Digital Production article; download is
  behind an ad-link shortener. Licence on the live page not read. UNVERIFIED.
- Cinecom free pack: personal use only. NO.

### Noto Animated Emoji: CC BY 4.0 (credit)
Download pattern (from a public gist): metadata
`https://googlefonts.github.io/noto-emoji-animation/data/api.json`, per emoji
`https://fonts.gstatic.com/s/e/notoemoji/latest/<codepoint>/lottie.json`
(or `512.gif`, `512.webp`).
Licence: CC BY 4.0 as stated in google/fonts issues #7011 and #9021; a Google Fonts member
(davelab6) advised attribution "in video file metadata, rather than burned into the rendered
video image". The official page is JS-rendered and I could not read its footer, so this rests
on those two issue threads. Put a credit line in the description + file metadata.
Render: the 512.webp/gif can be split into PNG frames with Pillow and overlaid by ffmpeg
(no new dependency). For crisp scaling use rlottie-python (`pip install rlottie-python[full]`,
licence LGPL-2.1, bundles Samsung rlottie which is MIT plus FTL/Skia/pixman/stb/rapidjson
for vendored parts): `LottieAnimation.from_file(...).render_pillow_frame(frame_num=i)`.
Use: a reacting emoji beside the hook, the quiz answer, a shocking stat. Effort M.

### Built-in ffmpeg tricks a Shorts editor uses (no download, effort S each)
- `xfade` transitions (wipes, slides, circle crop, pixelize...) between footage shots and at
  history chapter starts (history joins with the concat demuxer = hard cuts today).
- Progress bar for quizzes/explainers: `drawbox` whose width grows with `t`.
- Impact shake on a reveal: `crop` with small sin(t) offsets for 0.2 s, timed with the SFX.
- Film grain on history stills: `noise=alls=6:allf=t`.
- Light-leak / dust overlays: search the existing Pixabay/Pexels keys for "light leak overlay",
  "film dust overlay", blend with `blend=all_mode=screen`.

---

## 4. Maps for history (animated empire borders)

### Cliopatria (Seshat): CC BY 4.0
https://github.com/Seshat-Global-History-Databank/cliopatria . LICENSE.md read:
Creative Commons Attribution 4.0 International (credit, link the licence, say if changed).
Zenodo v0.0.1 (Aug 2024) also CC BY 4.0, zip 49.2 MB. One GeoJSON, ~14k records,
3400 BCE - 2024 CE; fields Name, FromYear, ToYear (negative = BCE), Area, Type
(POLITY/RELATION), Wikipedia, Wikidata id, geometry EPSG:4326. Caveat in README: one version
of disputed borders.
Use: for "Fatah-e-Andalus" etc., draw the polity's polygon at the scene's year, grow it year by
year (FromYear/ToYear), labels in Urdu with the existing fonts. Render with shapely + Pillow
(or matplotlib) to PNG frames, pan/zoom with the existing eased crop. Credit in description.
Effort M-L. Map content needs the same sacred-story / politics rules as the rest (modern
Kashmir borders: do not draw).

### Natural Earth: public domain
https://www.naturalearthdata.com/about/terms-of-use/ : "All versions of Natural Earth raster +
vector map data ... are in the public domain", commercial use invited, "Crediting the authors
is unnecessary". Coastlines, rivers, land shading under the Cliopatria polygons.

### NOT recommended: aourednik/historical-basemaps
Repo licence is GPL-3.0 (read on the repo page). Copyleft on map DATA is awkward for a
commercial channel; Cliopatria covers the same need under CC BY. Seshat's other datasets are
CC BY-NC-SA (non-commercial): only Cliopatria is CC BY.

---

## 5. Smart crops, speed, local vision (ONNX)

### YuNet face detector: MIT
https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet ("All files in this
directory are licensed under MIT License"). Files face_detection_yunet_2023mar.onnx (+int8)
and a 2026may version. Runs through `cv2.FaceDetectorYN` (OpenCV >= 4.5.4), CPU, tiny.
Use: when landscape stock footage or a Wikipedia photo is cropped to 9:16 (broll push-ins,
history pans), aim the crop at the face instead of the centre. For subjects without a face,
the IS-Net model already on disk gives a saliency mask: crop around its centroid (no new
download). Alternatives read: U-2-Net repo Apache-2.0 (u2netp 4.7 MB; weights licence not
stated separately); UltraFace MIT.
Effort S.

### onnxruntime-directml: MIT
https://pypi.org/project/onnxruntime-directml/ 1.24.4 (17-mar-2026), Windows x64 wheels,
Python 3.11-3.14. Runs ONNX models on any DirectX 12 GPU, so the Arc A370M can take Depth
Anything V2 Small (parallax, ~2 s per picture on CPU today), IS-Net and YuNet. Gain is speed
(parallax on more shots, quicker renders), not a new look. UNTESTED on the 2023 Arc driver
here (31.0.101.4502); keep the CPU provider as fallback. Effort S-M.

### Florence-2 base (MIT), local captioning/tagging
https://huggingface.co/onnx-community/Florence-2-base-ft (licence: mit). Could pre-rank stock
thumbnails before the Gemini vision call (the Gemini key is a friend's). Not a visible gain;
lower priority. Effort M.

---

## 6. Music-synced editing, charts, captions, fonts

### librosa beat tracking: ISC
https://github.com/librosa/librosa (ISC). `librosa.beat.beat_track` on the Lyria/ACE-Step song
gives beat times: cut footage and fire zoom punches on beats in the AI-songs channel
(today shots change every ~2.8 s regardless of the music). Effort S.

### Manim Community: MIT
https://github.com/ManimCommunity/manim ("double-licensed under the MIT license"). Animated bar
races, counters, timelines (cricket "versus" stat bars, history timelines). CPU + ffmpeg;
LaTeX optional. Heavier than drawing with Pillow/libass; worth it only for chart-heavy formats.
Effort M-L.

### pycaps: MIT
https://github.com/francozanardi/pycaps . CSS-styled animated captions (pops, slides,
typewriter, emoji insertion, SFX on words). Default renderer needs Playwright Chromium;
`PictexSubtitleRenderer` works without a browser (subset of CSS). Urdu/Arabic support not
documented. The repo's libass path already does karaoke + emphasis colours, so this is a
source of ideas more than a dependency. Effort M.

### Fonts
- Gulzar (Nastaliq, Google Fonts, 2022): OFL-1.1 (OFL.txt in googlefonts/Gulzar). A second
  Nastaliq for Urdu titles next to Noto Nastaliq Urdu (also OFL). Test in libass (harfbuzz).
- Note in CLAUDE.md: the current fonts lack "·" and dashes on screen.

### Audio clean-up: DeepFilterNet, MIT or Apache-2.0
https://github.com/Rikorose/DeepFilterNet . Release v0.5.6 (31-aug-2023) ships
deep-filter-0.5.6-x86_64-pc-windows-msvc.exe (no Python/torch needed), 48 kHz WAV only,
real-time on CPU. Useful only for real recorded audio (CC comedy sources, voice cloning
references); edge-tts/OmniVoice output is already clean. Low priority.

---

## 7. Trend data

### Wikimedia pageviews API: data CC0, no key
Licence read (dumps.wikimedia.org/other/pageviews/readme.html): "All Analytics datasets are
available under the Creative Commons CC0 dedication." Tested live:
`https://wikimedia.org/api/rest_v1/metrics/pageviews/top/ur.wikipedia/all-access/2026/10/20`
answers, but Urdu Wikipedia is tiny and its top list is adult-content noise (141 views at #1).
Use en.wikipedia / hi.wikipedia top lists, and the per-article endpoint to score planned
history/controversy ideas by recent interest spikes. Send a descriptive User-Agent. Effort S.

### YouTube Data API chart=mostPopular: not useful any more
Revision history: from 21-jul-2025 mostPopular draws from the Music, Movies and Gaming
trending charts (Trending page retired). No sports/cricket signal. Google Trends RSS
(already used) remains the best free same-day signal.

---

## Ranked shortlist (value per effort)
1. Kenney CC0 audio packs (S)
2. Openverse -> Freesound CC0 SFX library (S)
3. Own LUTs through ffmpeg haldclut/lut3d (S)
4. RIFE ncnn Vulkan slow-mo / fps (M)
5. Noto Animated Emoji, CC BY 4.0 (M)
6. YuNet face-aware 9:16 crops (+ IS-Net saliency) (S)
7. librosa beat-synced cuts for songs (S)
8. Cliopatria CC BY + Natural Earth PD animated maps (M-L)
9. onnxruntime-directml on the Arc (S-M)
10. Sonniss GDC bundle, one or two parts (S-M)
11. Wikimedia pageviews CC0 for idea ranking (S)
12. Manim for stat/timeline animations (M-L)
