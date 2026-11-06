# Free upgrades for Shortkaar: boot, speed, quality, voices, scripting (4-nov-2026)

Four web-research passes (video quality, audio/voice, scripting/LLMs, automation/distribution), web
search and page reads only: no yt-dlp, no GitHub API. Every number under "Done" was measured on this
laptop today. Claims from the research are marked **(unverified)** where the source was a third party
or the agent could not open the page. Free tiers change: dates are when they were read.

---

## Done today (in the code, tested)

| Change | Measured | Switch |
|---|---|---|
| **Intel Quick Sync encoding** (`ffmpeg_utils`, `FFMPEG_ENCODER=qsv`/`auto`): look-ahead ICQ 20 on the Iris Xe | x264 medium CRF 18 vs QSV: cricket 25.6 s -> 7.1 s (VMAF 98.92 -> 99.01), comedy 58.3 s -> 12.7 s (98.24 -> 98.21); ~1.7x the bits | `FFMPEG_ENCODER=x264` = old |
| **Gradient banding fixed** (`short_kit.bg_source`, fixed grain strength 2) | CAMBI 0.9-17.6 -> 0.00, and 0.00 after a 2.5 Mbps re-encode | `GRADIENT_GRAIN=0` |
| **Parallax worked only on first sight of a picture**: the float16 depth cache reached `cv2.remap` (no float16 kernel) | a live 111-shot history video lost parallax on every reused picture | fixed in `parallax._depth_cached` |
| **OmniVoice model was gone** (C: Hugging Face cache recreated 28-oct): every line went to the PAID Gemini voice | cache now in `oss/hf`, re-downloaded | `OMNIVOICE_HF_HOME` |
| **Stale venv launchers**: 171 `.exe` in 4 venvs still started `D:\youtube\...` (= the F: disk), so `pip install` went into the old copy | 0 left; `ops/fix_venv_paths.py` repairs any moved venv | run it after a move |
| **Watchdog**: crash alert (toast + Telegram), "down 15 min" alert, port 8000 held by another program (Docker publishes 8000 with `restart: unless-stopped`), log rotation (50 MB), a missing log no longer breaks the start | `tests/test_boot.py` runs every path on spare ports | `restart_notice.py` |
| **Stay awake on the charger** (`KEEP_AWAKE=charger` in .env): the laptop is Modern Standby only (no S3, wake timers off), so a doze froze every loop | screen still sleeps; battery and lid still sleep | `KEEP_AWAKE=1` = old |
| **Outside heartbeat** (`heartbeat.py`, off until `HEALTHCHECK_URL` is set): pings while both Autopilot loops tick, `/fail` with the reason when one is stuck 45 min | | unset = off |

Checked and NOT built (verified first, not worth it):
- Wikipedia most-read **per country**: Pakistan is "not loaded" in the pageviews API; India's list is mostly adult sites.
- YouTube `chart=mostPopular&regionCode=PK` (1 unit): works, but it is music videos, film trailers and gaming,
  no cricket; the planners' Google Trends / Wikipedia / niche searches already say more. Maybe for the songs channel.
- A float gradient with error-diffusion dither: x264 smooths the dither away (CAMBI barely moved).
- Moving grain (`allf=t`): 345 Mbps and still banded after a re-encode.

---

## Owner actions (no code; biggest first)

1. **Google Cloud -> Google Auth Platform -> Audience -> "Publish app"**, then reconnect every channel. In
   "Testing" refresh tokens die after 7 days (developers.google.com/identity/protocols/oauth2). Unverified apps
   in Production show a warning screen and are capped at 100 users: fine for one owner. Old tokens keep
   their 7-day life, so the reconnect is needed.
2. **A free healthchecks.io check** (Hobbyist: 20 checks, Telegram integration; healthchecks.io/pricing,
   read 4-nov-2026): period 5 min, grace 20 min, add the Telegram integration, put the ping URL in
   `.env` as `HEALTHCHECK_URL=https://hc-ping.com/<uuid>`, restart. Only an outside service can say "the laptop
   is off / asleep / offline".
3. **Sign-in after Windows Update restarts**: Settings -> Accounts -> Sign-in options -> "Use my sign-in info to
   automatically finish setting up after an update" (ARSO; needs Device Encryption/BitLocker on). Without it a
   night-time update reboot leaves Shortkaar stopped until someone logs in.
4. **Intel Arc A370M driver**: Windows lists only the Iris Xe. A current Arc driver would give OmniVoice
   PyTorch XPU (`.venv-xpu`, then `OMNIVOICE_PYTHON`), a second GPU for Real-ESRGAN/RIFE, and AV1 encode.
5. **Lid closed on the charger**: if the laptop runs shut, Control Panel -> Power Options -> "Choose what closing
   the lid does" -> Plugged in: Do nothing (charger mode cannot stop a lid sleep).
6. **Phone-verify every channel** (youtube.com/verify): 15+ min videos and custom thumbnails.

---

## Next code steps, ranked (value per effort)

### 1. Speech cleanup for the comedy channel (S)
ffmpeg's built-in `arnndn` with GregorR's RNNoise models (github.com/GregorR/rnnoise-models: "none of this
work is creative and thus none of it is subject to copyright"); `bd.rnnn` (beguiling-drafter) is trained on
voice incl. laughter vs recording noise; `afftdn` for steady hiss. Tiny, far faster than real time. **Gate
it** on a measured noise floor (astats in the quiet parts) so clean sources are untouched, and A/B it: it
can thin audience laughter. DeepFilterNet 3 (MIT/Apache, Rust `deep-filter` binary, RTF ~0.19 on an i5) for
bad clips; check a Windows binary exists.

### 2. Upscaler for live-action stock (M)
`realesr-animevideov3` makes photos look painted (22-oct note). `realesr-general-x4v3` (+ wdn variant,
BSD-3, Real-ESRGAN repo) is the live-action model, with `-dn` denoise strength; it needs an ncnn conversion
(pnnx). `2xNomosUni_span_multijpg_ldl` (CC-BY-4.0, openmodeldb.info, 8.5 MB) is a fast 2x robust to JPEG
artefacts; SPAN under realesrgan-ncnn-vulkan is **unverified**. CC-BY needs a credit line.

### 3. No-reference render gate (S-M)
All in the installed ffmpeg: `blockdetect`, `blurdetect`, `freezedetect`, `blackdetect`, CAMBI through
`libvmaf=feature=name=cambi` (used today). Thresholds from past good uploads per channel, failures to
creative_qa. `vmaf_v0.6.1neg` if the encoder is ever recalibrated.

### 4. Official Microsoft voice: Azure Speech F0 (S-M, needs a free Azure account with a card)
Same Urdu voices as edge-tts (ur-PK-AsadNeural / UzmaNeural) through an official endpoint: no 403/429
rests, and full SSML (`<break>`, `<prosody>`, `<sub alias>` for English loanwords). 0.5M neural characters
a month free (Azure pricing page, via search: **unverified**) = roughly 400-500 Shorts. New first engine,
edge-tts as fallback.

### 5. Verified cricket numbers: Cricsheet (M)
Ball-by-ball data under ODC-BY 1.0 (commercial OK with attribution; cricsheet.org blocked the fetch, licence
from a search snippet: **unverified**). Nightly zip -> SQLite; versus / top-5 stats computed by code instead
of grounded search. Phrase as "in matches Cricsheet covers".

### 6. Free LLM fallback for the non-grounded passes (S each, needs free keys)
Read 4-nov-2026. Cloudflare Workers AI free: 10,000 neurons/day (~100 calls of 4K in / 2K out) with Gemma 4
26B-A4B (Apache 2.0; 70.2% on UrduMMLU vs 90.3% Gemini 3.5 Flash, arXiv 2606.07167). Groq free: 1,000
requests/day, 8K tokens/min (console.groq.com/docs/rate-limits). Both OpenAI-compatible. Gains little while
the first step of every job is Gemini's grounded research; worth it for polish/titles/SEO that fail midway.
Don't switch the blind judge's model mid-A/B test.

### 7. Facebook Reels scheduled in advance (M)
The Reels finish step takes `video_state=SCHEDULED` + `scheduled_publish_time` (10 min-29 days ahead; 30 API
Reels/Page/24 h; developers.facebook.com Reels Publishing guide). Upload once and Facebook posts at the
slot, laptop awake or not. Instagram has no API scheduling (**unverified**).

### 8. Free film looks: LUTs (S)
Spectral Film LUT (MIT, github.com/JanLohse/spectral_film_lut) builds film-emulation LUTs, so no third-party
licence on the output; `lut3d=file=x.cube:interp=tetrahedral`, blended back 40-70%. A log-input LUT looks
wrong on Rec.709 footage.

### 9. Layered "living stills" for history (M-L)
IS-Net foreground (already installed) over an inpainted plate (OpenCV Telea for the thin strips small moves
uncover), depth-of-field from the depth map, masked `displace` for sky/water. DepthFlow is AGPL (subprocess
only, and a problem for cloud mode); LivePortrait's InsightFace models are non-commercial.

### 10. Policy guard: per-channel sameness (S-M)
YouTube's "inauthentic content" (renamed 15-jul-2025, support.google.com/youtube/answer/1311392) names
"templated storylines ... with minimal or no narrative"; reused content covers clips "edited together with
little or no narrative", even with permission. The comedy channel's model is the exposure. A gate comparing
each new script/beat sheet with the channel's last 30, and a narration-to-clip seconds check on clip videos.

---

## Skip (fails licence, hardware or value)

- **TTS**: MMS-TTS (CC-BY-NC), F5-TTS base (CC-BY-NC), XTTS-v2 (Coqui non-commercial), Fish Speech /
  OpenAudio and Spark-TTS (CC-BY-NC-SA), Piper Hindi (NC-SA data, GPL code), Chatterbox / CosyVoice / Kokoro /
  Kyutai / Kitten (no Urdu), Indic Parler-TTS (Urdu unproven, ~7x slower than real time on CPU),
  Indic-Speak (hosted use needs written permission: conflicts with cloud mode).
- **Music**: MusicGen (CC-BY-NC). ACE-Step 1.5 (MIT, cloned with its venv, not wired in) runs on CPU at
  1-5 min a track (**unverified**): only as an overnight bank of beds, never per job.
- **Separation**: Demucs weights ("the license of the weights is not clear"), UVR MDX ONNX (no licence).
  Kim MelBand-RoFormer via audio-separator (MIT package, weights tagged MIT but no LICENSE file) is the only
  candidate, Python 3.12 venv, ~1-3 min per clip on CPU (**unverified**).
- **Video**: 3D Ken Burns (CC BY-NC-SA), Depth Anything V2 Base/Large (CC-BY-NC), local image-to-video
  (LTX / Wan / SVD: CUDA or far more VRAM), Upscayl (AGPL), Remotion (company licence), AV1 uploads
  (the Iris Xe cannot encode it; no evidence it helps).
- **LLM tiers gone or not free (2026)**: GitHub Models (retired 30-jul-2026), Hugging Face free credits,
  Cerebras ($5 card credit), Cohere trial (non-commercial), Reddit API (commercial terms), IPEX-LLM (archived).
- **Distribution**: TikTok Direct Post (unaudited apps post SELF_ONLY; the guidelines reject "a utility tool
  to help upload contents to the account(s) you or your team manages"), X (pay-per-use since Feb 2026),
  Snapchat Spotlight (partner-only), Moj / Josh / ShareChat (no public upload API). Threads (250 posts/day,
  needs a public video URL) and Bluesky (open API, app password) are possible but small for a PK/IN audience.
- **Windows**: running the server as a service (Session 0: no toasts), WakeToRun timers (Modern Standby,
  wake timers off here), NSSM (no release since 2017).
