# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenShorts is an AI-powered vertical video generator that transforms long YouTube videos or local uploads into viral-ready short clips (9:16 format) for TikTok, Instagram Reels, and YouTube Shorts. Uses Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`, overridable with `GEMINI_MODEL`) for viral moment detection and title generation.

## Development Commands

### Local Development (Docker)
```bash
docker compose up --build   # Build and run full stack
```
- Backend: http://localhost:8000 (FastAPI/Uvicorn)
- Frontend: http://localhost:5175 (Vite proxies API calls to backend)

### Frontend Only (Dashboard)
```bash
cd dashboard
npm install
npm run dev       # Dev server with HMR (port 5173)
npm run build     # Production build
npm run lint      # ESLint (strict, --max-warnings 0)
```

### Backend Only
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Architecture

### Core Processing Pipeline
1. **Ingest** - YouTube download (yt-dlp) or local upload
2. **Transcription** - faster-whisper with word-level timestamps
3. **Scene Detection** - PySceneDetect for segment boundaries
4. **AI Analysis** - Gemini identifies 3-15 viral moments (15-60 sec each)
5. **FFmpeg Extraction** - Precise clip cutting
6. **AI Cropping** - Vertical reframing with subject tracking
7. **Effects/Subtitles** - Optional AI-generated FFmpeg filters
8. **Hook Overlay** - Text overlays with styled fonts
9. **Voice Dubbing** - Optional ElevenLabs AI translation (30+ languages)
10. **S3 Backup** - Silent background upload
11. **Social Distribution** - Upload-Post API (async upload)

### Key Files
| File | Purpose |
|------|---------|
| `main.py` | Core video processing: transcription, scene detection, clip extraction, vertical reframing |
| `app.py` | FastAPI server with async job queue and REST endpoints |
| `editor.py` | Gemini AI integration for dynamic video effects (FFmpeg filter generation) |
| `hooks.py` | Hook text overlay generation with font rendering |
| `s3_uploader.py` | AWS S3 upload with caching |
| `subtitles.py` | SRT generation, FFmpeg subtitle burning, and dubbed video transcription |
| `translate.py` | ElevenLabs dubbing API for AI voice translation |
| `dashboard/src/App.jsx` | Main React component with state management |
| `dashboard/src/components/TranslateModal.jsx` | Voice dubbing UI with language selection |
| `dashboard/vite-plugin-seo.js` | Build-time SEO surface: injects crawler-visible homepage content, emits static pages, sitemap.xml and llms.txt |
| `dashboard/seo/data.js` | Single source of truth for pricing, pipeline and competitor facts used by every generated page |

### SEO / AI-crawler surface

The dashboard is a client-rendered SPA with hash routing, so the HTML served for
`/` used to contain an empty `<div id="root">`. Googlebot renders JavaScript and
saw the real page; GPTBot, ClaudeBot and PerplexityBot do not and measured the
homepage as zero characters of text. `vite-plugin-seo.js` fixes that at build time:

- Injects the content of `seo/landing-fallback.js` into `#root`. React's
  `createRoot().render()` replaces it on mount, so users get the app and
  non-executing clients get the copy. **Keep it in sync with `Landing.jsx`.**
- Emits the standalone pages (the `/alternatives` cluster, the clip-generator,
  open-source, use-case and automation pages, and `/mcp`; the full list is
  `buildPages()` in `seo/pages.js`) as flat `.html` files.
  nginx resolves the clean URL through `try_files $uri $uri.html`; serving them as
  directories instead makes nginx 301 to a trailing slash and every canonical
  would then point at a redirect.
- Generates `sitemap.xml` and `llms.txt` from the same page list, so they cannot
  drift. Do not add a static `public/sitemap.xml` back.

When editing pricing anywhere, edit `seo/data.js` too. Nothing on the site should
say "OpenShorts is free" without naming the Cloud price in the same breath: both
are true of different editions and quoting only the first one is what makes AI
answers describe the paid product as free.

### Free tools (/tools) and SEO attribution

- `free_tools.py` (router always mounted): `GET /api/tools/youtube-transcript`
  reads the captions a video **already has** on YouTube via yt-dlp (never the
  GPU, never media). Routes: the `STATIC_PROXY_URLS` only (anonymous, then the
  cookies), direct when there are none; **never** the per-GB `PROXY_URL`. A
  static that answers with zero formats and zero captions is a degraded route,
  not a "no captions" verdict (seen on one of the three statics, 23-sep-2026).
  `POST /api/tools/youtube-metadata` = one Gemini text call (tags / titles /
  description) with the managed key. Per-IP windows + global daily cap per tool,
  24 h cache (also for "no captions"/"unavailable").
- Pages: `seo/tools.js` (hub + 3 tools) and `seo/autopilot-pages.js`
  (`/auto-clip`, `/youtube-automation`). A tool page carries `tool: {entry, html}`:
  the form is in the static HTML, the behaviour is a Vite entry in
  `dashboard/tools/*.js` (`vite.config.js` rollupOptions.input) that
  `vite-plugin-seo.js` looks up by name in the bundle. The 9:16 converter runs
  in the browser with mediabunny/WebCodecs (no upload).
- Attribution: `seo/render.js` writes the same first-touch `os_attrib` key the
  app writes, from the static page the visit started on. Before, every signup
  was credited to "/" (7,481/7,481 rows, 30 days to 23-sep-2026). Signup,
  CheckoutStarted and Subscribed carry `landing_path`/`referrer_host`/utm as
  OpenPanel props (`lib/analytics.js`).
- Apex→www: 301 comes from the front app's **stored Coolify custom labels**
  (`redirectregex.permanent=true`, patched 23-sep-2026). The nginx 301 block
  below never sees the apex while that Traefik middleware exists.

### CPU-only machines: captions, sections, framed (5-oct-2026)

Measured on an i7-1360P laptop with no NVIDIA GPU, where a 1 h 49 min job
never finished:
- **YouTube captions replace Whisper** (`youtube_captions.py`): the video's own
  track (json3 has per-word offsets) arrives in ~4 s. Whisper `small` beam-5
  ran slower than real time there. `YT_CAPTIONS=0` turns it off. It must not
  import `free_tools` (that pulls in `cloud/`, see test_audit_hardening).
- **Only the picked clips are downloaded** (`section_fetch.py`): with captions
  the clips are known first, so ffmpeg cuts each one straight from the stream
  URLs (40 s in ~28 s) instead of downloading 1.3 GB (~15 min at 1.5 MB/s).
  The job then has no full source (`source_video` is null). `DOWNLOAD_SECTIONS=0`
  restores the full download; any section failure falls back to it.
- **`yt-dlp-ejs` is required**: without the JS-challenge solver every download
  got HTTP 403 after the first few MB and left a `.part` file.
- **Whisper fallback on CPU** runs batched, 4 threads, `no_repeat_ngram_size=3`
  (35 s per 5 min of audio). Plain batched looped on one word; 8 threads were
  slower (efficiency cores). `WHISPER_BATCHED=0` restores sequential.
- **`output_format=framed`** (`framed_layout.py`, dashboard default): source
  cropped (4:3, 12% zoom, trim taken mostly from the bottom so burned-in
  subtitles go) on a solid colour 1080x1920 canvas, title in the top band,
  captions in the band below. One ffmpeg pass, no face tracking. Per-job look
  is saved in `frame.json` so editor re-renders keep colour, title and caption
  position.
- **Caption + title language** (`caption_script.py`, `CAPTION_SCRIPT`,
  dashboard "subtitles"): `roman` (default) transliterates each caption word
  1:1 into Roman Urdu / Hinglish so word timing survives; when the word count
  does not come back equal (1 clip in 10 on a real job) it converts line by
  line instead. `english` translates per line. Latin-script sources skip it.
- **Branding** (framed only): `FRAME_HANDLE` shows the channel handle at the
  top, the title pops in over the first 0.4 s (no separate intro card, which
  costs the first second on Shorts), and `FRAME_OUTRO` (default on) holds the
  last frame `FRAME_OUTRO_SECONDS` (1-3, default 3), blurred and tinted, under
  an animated end card (`end_card_events`: FOLLOW slam, FOR MORE slide, gold
  handle button pulsing with ripples and a bouncing arrow) and a synthesised
  swoosh + ding (`end_card_audio`, aevalsrc: no sound file to license). Same
  single ffmpeg pass, now a `-filter_complex`. Dashboard defaults are the user's brand
  (`BRAND` in MediaInput.jsx: Punchline Bazaar, #2B0F3D).
- **SEO copy** (`seo_copy.py`, `SEO_COPY=0` off): one Gemini call per job after
  `caption_script` writes per clip `seo_title`, `seo_description` (the model
  returns hook + a 3-paragraph body; `build_description` adds the follow
  CTA with `FRAME_HANDLE` and 5 hashtags, so the layout never depends on the
  model's line breaks). **The original creator is never named** (owner's
  rule, no credit line): the model reports the name in `creator` only so
  `name_pattern` (plus "BY <name>" from the source title) can check every
  field. Clips under `MIN_DESCRIPTION_WORDS` (150), naming the creator, or
  with Devanagari/Arabic letters or bookish words ("apratyashit ant") in
  Roman mode get one more call; a name that survives it is scrubbed. Only the clip's words go in: fed the
  detail pass's title, the model kept its bookish wording. Plus
  `hashtags`, `seo_tags`, the TikTok/IG captions, and a short on-screen title,
  hook and summary in the caption language. ResultCard shows all of it with
  copy buttons; "copy everything" adds no extra hashtags because YouTube
  ignores every hashtag in a description that carries more than 15.
- **Compilation** (`compilation.py`, branch feature/compilation): 2-5 links
  (`urls` on /api/process, dashboard "add another link") become ONE framed
  short of their best moments. app.py starts main.py with the first link and
  `COMPILE_URLS`; main.py hands over before anything else, so a normal job
  never enters it. Picks per video in parallel, each video's best moment
  first, then by score, up to `COMPILE_SECONDS` (Shorts max 3 min, end card
  included); moments joined with 0.4 s crossfades on 1920x1080/30 fps. The
  join encodes plain AAC: `audio_encode_args` adds `-af`, which ffmpeg
  refuses next to `-filter_complex`. A link without YouTube captions falls
  back to a full download + Whisper (slower, worse Hindi subtitles). Real run
  6-oct-2026: 2 videos, 5 moments, 170 s, 8 min.
- **Shortkaar rebrand** (branch feature/shortkaar): the dashboard is the
  user's own product "Shortkaar". Themes are token sets in `tokens.css`
  (Aurora default, Ocean, Sunset, Mint; `?theme=` or the picker), and
  `tailwind.config.js` colours point at those variables, so never hard-code a
  colour. Hidden, code kept: AI Shorts, AI Agent, UGC Gallery, Autopilot,
  post / schedule week, landing, cookie banner, `seo()` build plugin. Local
  History + Gallery read `GET /api/library` (self-host only). Keep `LICENSE`
  (MIT notice) in the repo.
- **Clips start on speech** (`main.trim_to_speech`): sound tags like
  `[Music]`/`[संगीत]` are not speech; a clip starts on its first spoken word
  so a source channel's intro / end screen never gets in (6-oct-2026).
- **Clip length range** (dashboard "clip length", `clip_min/max_seconds`):
  with a max set, `main.clip_length_cap` lets clips reach it (177 s ceiling,
  Shorts' 3 min minus the end card); without one the 119 s cap stays.
- **AI take** (`ai_take.py`, `AI_TAKE=0` off, dashboard checkbox, branch
  feature/content-types): after SEO copy, one Gemini call writes a 10-16
  word Roman Urdu reaction + comment question per clip, a Gemini voice reads
  it (`gemini-2.5-flash-preview-tts`, then `3.1-flash-tts-preview`; the 3.8
  TTS models read the instruction aloud or garbled it, checked by Whisper on
  8-oct-2026), and `framed_layout` holds the last frame for it between the
  clip and the end card, words lit in gold by length (the voice has no word
  times). Stored in `frame.json` `takes` so editor re-renders keep it. A clip
  that would pass 179.5 s with it gets none. Voiced files get the AI tag.
- **Titles and descriptions are always Roman Urdu** (`SEO_SCRIPT`, default
  roman), whatever the subtitle language.
- **Video type** (`genre` on /api/process -> `CONTENT_GENRE`): `comedy` is
  the clip pipeline, untouched. `songs` / `movies` hand over in main.py like
  compilations; `cricket` has no link (`cricket_match`, main.py `--generate`).
  Shared pieces in `short_kit.py` (gradient canvas + ASS + voices + metadata).
  - `song_shorts.py`: silent by default (song added in the YouTube app gets
    the special claim, answer/13053317), `SONG_OWNED=1` keeps sound + lyrics
    and allows a mashup (`SONG_URLS`). Never trust Gemini's timestamps over a
    whole song (67-85 s "sections", lyrics past the end): the cut is the
    loudest stretch away from intro/outro, then Gemini hears only that clip.
  - `movie_dub.py`: new Roman Urdu dialogue per line (one frame per line tells
    it who speaks), a Gemini voice per character, original audio muted,
    letterbox cropped (`black_bars`). Lines come from word times split at
    pauses: Whisper segments run up to 50 s.
  - `cricket_shorts.py`: facts via Google Search grounding (tell it today's
    date; it once answered NOT FOUND for a 2025 match "because it is 2026"),
    animated scenes, no footage, no player images or logos.
  - Fonts here lack "·" and dashes on screen (rendered as boxes).
  - Songs is hidden in the dashboard (owner, 8-oct-2026); the server flow stays.
- **Channel tools** (self-host only, branch feature/channel-autopilot, 8-oct-2026):
  - **Never repeat a moment** (`used_moments.py`, `SKIP_USED=0` off):
    `output/.used_moments.json` by YouTube id, not in job dirs (24 h
    retention, and they never stored the link). `get_viral_clips(used=)`
    drops windows half made of old Shorts and clips 30% made of one; nothing
    left raises `AllUsedError` before any AI call or download. The function
    body has its own local `used` (window ids), so the parameter is aliased
    `old_shorts`: shadowing it failed every clip-floor retry. Compilation and
    movie dub record too; cricket ideas as `topic:<text>`.
  - **Find videos** (`channel_tools.py`): Creative Commons search through
    yt-dlp with YouTube's own `sp` filter (no key, 2-3 s); licence from
    yt-dlp's `license` field (~10 s, cached a day). The label is only the
    uploader's claim: many CC results are re-uploads of stage dramas.
  - **Autopilot** (`autopilot_local.py`, `/api/local-autopilot`): daily at
    `run_at`, caught up the same day if the laptop was off; jobs go through
    /api/process in-process with `X-Shortkaar-Autopilot` so they do not
    replace `.last_settings.json` (the look of the last hand-made job per
    type, which Autopilot copies). Tests must never write these output/
    files: conftest redirects them (a run saved an empty look over the real one).
  - **YouTube account** (`youtube_account.py`): the user's own Google Cloud
    OAuth client (Web app, redirect `http://127.0.0.1:8000/api/youtube/callback`,
    `YT_CLIENT_ID`/`YT_CLIENT_SECRET` in .env), token in
    `output/.youtube_token.json`. videos.insert from an unaudited project is
    locked private (videos/insert docs); analytics needs no audit.
  - **What works** (`what_works.py`, `/api/report*`): comparisons counted in
    code, Gemini only words them; its title rules reach `seo_copy` while the
    report's `use` is true. Public view counts from the /shorts tab when the
    channel is not connected.
  - **Ready to post** (`post_queue.py`, `/api/queue*`): finished Shorts made
    since the plan started (`_since`, so old test jobs never show) get the
    next posting times; pinned comment on demand; posted ones get views by
    title from the /shorts tab and a "part 2" link to their source
    (`.source.json` in the job dir, written by /api/process). A job with a
    Short still waiting skips the retention sweep for up to 7 days.
  - **Comments** (`comment_replies.py`, `/api/comments`): yt-dlp
    `getcomments` needs the full extraction (`process=False` returns none),
    ~15 s per Short. Replies are drafted in one Gemini call; sending needs
    the `youtube.force-ssl` scope.
  - `autostart.bat` starts only the server, minimised, with
    `PYTHONIOENCODING=utf-8` (its log is a file: emoji prints would fail on
    the Windows code page).
- Thumbnail Studio takes the video's YouTube captions when it has them (no
  Whisper), like the clip pipeline.
- **Long video** (`long_video.py`, `/api/long-video*`, Long video tab,
  Autopilot `weekly_long`): 3-15 comedy Shorts of the last 7 days in one
  1920x1080 video counting down to #1 (best plays last). Each Short loses
  its end card (`outro_seconds` from its frame.json) and keeps its take;
  segments share encode settings and join with the concat demuxer, so
  chapter times are measured, not guessed. ffmpeg runs inside the job dir
  and drawtext reads `textfile=` by bare name (no drive colon to escape);
  text files are written with `newline="
"` or Windows' 
 shows as an
  empty line. Built in ~20 s per Short; 2 thumbnails in ~45 s through
  `thumbnail.generate_thumbnail` with a frame of the #1 Short.
- Also local-only: `/api/finder/batch` (one job per ticked video, comedy
  look), `/api/queue/pack` (waiting Shorts + copy as one zip: build it to a
  file and send a FileResponse; a StreamingResponse over BytesIO iterates
  it line by line, 66 MB took 113 s), `/api/queue/{id}/retitle`,
  `/api/system-check` (system_check.py; yt-dlp says 2026.08.19 where PyPI
  says 2026.8.19, compare as int tuples; keep the genai Client in a name or
  it is closed before the call). The audit form answers are in
  `docs/youtube-api-audit.md`.
- Round 3 (8-oct-2026), all local-only:
  - **Your own moments** (`moments` on /api/process, comedy + one link):
    `used_moments.parse_ranges` reads "12:30-13:20, 750-800" (5-119 s each,
    up to 5; the clock pattern must not match inside a longer number or
    "750-800" reads as "50-80"), env `MANUAL_CLIPS`, and
    `main.manual_clips` replaces the AI pick at the top of
    `get_viral_clips`, so every path (captions, audio, full download) obeys
    it. Titles and copy still come from seo_copy.
  - **Similar channels** (`rivals.py`, `/api/rivals*`): other channels'
    /shorts tabs ranked by views; Gemini words the patterns and 5 ideas,
    each with a search that opens Find videos (`os_finder_q`).
  - **Telegram** (`telegram_notify.py`, `/api/telegram/*`, `/api/phone/send`):
    the owner's bot, `TELEGRAM_BOT_TOKEN` in .env, chat id from getUpdates.
    Errors never echo the token (it is in the URL). Keep new POST routes
    out of `/api/queue/<word>`: `POST /api/queue/{iid}` is declared first.
  - **Match watch** (Autopilot `match_watch`, `match_team`): a grounded
    "did <team> finish a match in the last 24 h?" every 3 h; a new one
    becomes a cricket Short at once (topic recorded, never twice).
  - **Take voice** (`take_voice` -> `AI_TAKE_VOICE`, only short_kit's voice
    names): samples at `/thumbnails/voice_samples/<voice>.wav` (never swept).
  - Autopilot/batch jobs stopped by the quality gate say "quality too low
    (224p), skipped" (`_autopilot_submit`), not a KeyError.
- **Credit for Creative Commons sources** (`credits.py`, `CREDIT_CC=0` off,
  12-oct-2026): CC BY allows reuse only with credit (YouTube answer/2797468),
  which the "never name the creator" rule broke. The owner agreed to credit
  in the copy, never on screen: after seo_copy (main, compilation, movie
  dub) a "Credit (original video, licensed under CC BY)" block goes before
  the hashtag line of the description and the Instagram text, a short line
  into the TikTok caption; the long video credits every CC source of its
  Shorts (`sources` from each job's `.source.json`). Standard-licence
  sources get nothing.
- **Research + post all** (12-oct-2026): Autopilot `research` (default on)
  runs each `research_queries` search with the CC filter, medium + long,
  sorted by views (~7 s for 5), drops used / short / under `min_views`, then
  one Gemini call (`autopilot_local.vet`) keeps only the creator's own
  talking comedy: by views alone the top picks were an Indian web-series
  re-upload, a drama episode and a reaction video; vetted, 11 of 40 stayed
  (Jan Rambo, Aakash Deep, Shahveer Jafry...). A failed check uses none.
  Max 2 a day per channel. `POST /api/youtube/post-all` uploads every ready
  Short in slot order, each into the next free posting time (`_spawn` is
  the test seam: patching `threading.Thread` breaks the executor).
  videos.insert has its own 100-a-day quota now (quota calculator,
  12-oct-2026), so 7+ a day fits. Posting times go up to 10. The real cap
  is the channel's own daily upload limit (`uploadLimitExceeded`, no
  published number): the 2-subscriber channel took 10 on 14-oct-2026 and
  refused the 11th, so post-all stops at the first refusal and auto upload
  retries refused rows later. publishAt was kept on all 10 uploads from the
  unaudited project (status private + publishAt; whether they really go
  public at the time was not yet seen).
- **Full autopilot** (14-oct-2026): `auto_upload` now runs the post-all
  routine over all of Ready to post every `AUTO_POST_EVERY` (10 min) and
  pauses `UPLOAD_PAUSE_SECONDS` (3 h) after the daily limit. `autostart.bat`
  starts server + dashboard; a `Shortkaar.lnk` to it is in the user's
  Startup folder.
- **Copyright claims**: two Shorts from a CC-labelled "PATI PATNI AUR PADOSAN
  - Episode 14" were blocked worldwide by Content ID. The API shows it as
  `contentDetails.regionRestriction.blocked` (249 countries; clean uploads
  have none). `youtube_account.claim_check` every 30 min marks the row,
  `app._check_claims` bans the source (`blocked_sources`: video + channel,
  never used again) and skips its waiting siblings. Job dirs go after 24 h,
  so the source link is stored in the upload row (`_source_of` falls back to
  Autopilot's run log). Research drops titles that read as series / drama /
  film (`looks_like_a_series`; a podcast's "EP 29" stays) and the vet prompt
  drops TV broadcast footage (it kept a Lux Style Awards clip before).
- Captions never burn sound tags (`subtitles._SOUND_TAG`, filtered before
  continuation merging): a Short showed "[MUSIC]" as its caption.
- **Scheduled uploads do go public** from the unaudited project (11:00 and
  13:00 Shorts went public on time, 14-oct-2026), so the audit is not
  needed; `learning.refresh` counts uploads still private an hour past their
  time (`locked`) and only then does the dashboard mention the audit.
- **Learning loop** (`learning.py`, `/api/learning*`, My channel card), every
  6 h from the Autopilot loop: YouTube numbers for 30 days of uploads, a
  Short counts after 48 h public; source channels scored by median views
  (research sorts by views x `source_factor`, a poor channel rests 14 days);
  one A/B test at a time on Autopilot comedy jobs (`next_arm`: end card, AI
  take, 35 s clips; 8 counted per side, the challenger wins only at 1.3x
  and +5 median views, else the current look stays); the what-works title
  rules rebuild every 5 newly counted Shorts. Upload rows carry `exp`/`arm`
  and `seconds`.
- **`AUTOPILOT_LOCAL=0`** keeps the Autopilot loop off in any second copy of
  the app: test_mcp_stdio runs mcp_stdio.py as a real subprocess that enters
  the lifespan, and its loop ran a claim check and a learning pass on the
  real output/ files with the owner's token. mcp_stdio and conftest set it.
- **Several channels** (`my_channels.py`, `/api/my-channels*`, dashboard tab
  "Channels", 14-oct-2026): Punchline Bazaar stays "main" with its own files
  and Autopilot, untouched. Each other channel has a kind (cricket facts,
  quiz, AI songs), its own Google token + uploads log in
  `output/channels/<id>/`, used through `youtube_account.use(account)` (a
  contextvar; `run_in_executor` threads do not inherit it, so set it inside
  the function that runs there). One OAuth client and callback serve every
  channel: the sign-in state carries the account, `prompt=select_account
  consent` shows the channel picker, and `_refuse_same_channel` refuses a
  YouTube channel already connected elsewhere WITHOUT revoking (revoking
  could cut the other connection). Jobs carry `channel` in .source.json:
  `_queue_clips` skips them, so they never post to the main channel.
  `my_channels.loop_forever` (own task in the lifespan) makes one generated
  job at a time (channel furthest behind), only for connected channels,
  uploads into each channel's times, pauses 3 h at the upload limit, and
  every 6 h reads views: best/worst titles go into the next ideas, quiz
  formats and song styles are picked by median views (30% explore).
- **Testing-mode tokens die after 7 days**: the owner's token carried
  `refresh_token_expires_in: 604799` (14-oct-2026), Google's sign for an
  OAuth consent screen in "Testing". `youtube_account.refresh_expiry` dates
  it; the Channels tab tells the owner to press "Publish app" and reconnect.
- **Cricket channel**: player photos only from Wikipedia's lead image on
  Commons with a free licence (`player_photo.py`; Google Images is agency
  photos = copyright strikes), credited in the description. commons.wikimedia.org
  reset the connection from this laptop, en.wikipedia.org's API serves the
  file data; Wikimedia 429s bursts, so lookups are cached 30 days and retried.
  Fact cards swipe in with a flash; `channel_ideas` plans a day (grounded).
- **Quiz** (`quiz_shorts.py`, genre `quiz`): QUIZ_MODEL (3.7-flash) writes
  spares, a second call checks every answer (Google Search for GK) and drops
  what it does not confirm. Tell the model how many questions the Short
  uses: asked for 5 (2 spares), it wrote "5/5" into a 3-question title.
- **AI songs** (`music_shorts.py`, genre `music`): Lyria 3.5 via
  `client.interactions.create` ($0.08/song, ~1 min; `lyria-3-clip-preview`
  is a fixed 30 s, $0.04, used for the music beds in `music_beds.py`).
  Whisper over a song drops whole 30 s windows as "no speech" and mishears:
  pass our lyrics as `initial_prompt`, `no_speech_threshold=None`, then
  `align` (split double lines by word times, bonus for the lyric due next,
  never show an unmatched line). Uploads carry containsSyntheticMedia.
- `short_kit.render(images=, bg_image=)`: RGBA pictures with a zoom via
  `scale=eval=frame` (overlay copes with the size change) and a cover
  background panned by a moving crop (cheaper than zoompan).
- Bash heredocs in this shell turn `\n` inside a Python string into a real
  newline even with a quoted delimiter: write patch scripts with the Write tool.
- **Engagement** (`engage.py`, 15-oct-2026), per channel switches run from
  `my_channels.engage_pass` every 15 min: first comment once a Short is
  public (its own `comment_question`, else a template; the API cannot pin),
  auto replies (Gemini, 15 a day, quiz replies check the viewer's answer
  against `answers` in the upload row), playlists per kind/format, and a
  "More from us" line in descriptions (`my_channels.promote`). All off on
  the main channel until the owner switches them on (they post on a live
  channel); on for new channels. API writes cost 50 units of the project's
  10,000/day shared by every channel: `youtube_account.spend/quota_used`
  (per Pacific day), engagement stops at `engage.QUOTA_BUDGET` (6,000).
- **Today tab + reminders** (`/api/today`, `app._today`, `reminders.py`,
  `notify.py`): self-host opens on Today (the dashboard checks /api/today,
  which 404s in cloud mode). Windows toasts through PowerShell 5.1's WinRT
  classes (no package) at 11:00 and 19:00 when something needs the owner
  (a Google token expiring within 5 days, one already stopped, a channel
  not connected), and the day's numbers at 21:30. `snooze_until` holds the
  reminders: the owner asked for Friday or Saturday (set to 16-oct 10:59).
- **Player vs player** (cricket `CRICKET_MODE=versus`): the code decides
  each row's winner from the numbers (`fix_better`), because the model got
  it wrong twice on a real run: a bowler's strike rate and average are
  lower-is-better (`context()` = bowling/batting/mixed, mixed keeps the
  model's call for a bare "AVERAGE"), "4/15" beats "4/22", matches played
  wins nothing; when the code changes the result the voiced verdict is
  rewritten to match the screen.
- **Fast results** (`my_channels.match_watch`, cricket channel, every 2 h):
  a finished Pakistan or India match jumps the idea queue (`urgent`), is
  made even past the day's count and is scheduled 20 min after it is done.
  Duplicates are found by the two teams within 20 h, not by the text: the
  same match comes back with its date written differently.
- **Flag quiz** (`flags.py`, quiz format `flags`): the "Flag of <country>"
  article's lead image, public domain, cached in output/flags/; wrong options
  from the same region. `QUIZ_NUMBER` makes "QUIZ #12" a daily series.
- **Songs end without an end card** (`frame_outro` false in the payload):
  a Short that ends on the music loops, and replays count as views.
- **Controversies, explained** (`controversy_shorts.py`, genre/channel kind
  `controversy`, 15-oct-2026): no news footage (Content ID) and no rumour
  told as fact. Three gates: grounded research with every claim labelled
  REPORTED/ALLEGED/ADMITTED/RULED and at least 3 sources; a script that says
  "ilzaam" for allegations and gives the person's side; a second call that
  checks the script against the facts for defamation risk (one rewrite with
  its notes, then no video). `RULES` (religion, politics, army, minors,
  unruled sexual allegations, health...) are refused at every step. Grounding
  source links are vertexaisearch redirects that expire: `_real_url` follows
  each to the article for the description's "Sources:" block. Photos through
  `player_photo` kind "person" (the article description must say what they
  are). Cricket helpers are shared (`_voice_timeline(voice, style)`,
  `_bed(kind)`, `_finish(genre, after_seo)`, `fact_events(count=False)` so a
  year is not counted up from 0). Tests run with `.venv/Scripts/python` (the system
  Python has no httpx) and `--continue-on-collection-errors`.
- **History and stories** (`history_videos.py`, genre/channel kind `history`,
  15-oct-2026): the one LONG channel, 2-30 min 16:9 documentaries, 1-3 a day
  (`KINDS[...]["long"]`, `max_per_day` 3, job timeout 3 h; per channel
  `minutes` and `lang` urdu/english, `notes` = the owner's topic wishes).
  Research (2 grounded calls, 3+ sources), script of chapters/scenes, fact
  check with one rewrite. Pictures: free-licence images of each scene's
  Wikipedia article (`prop=images` + `imageinfo`, request width 1920, a
  standard Wikimedia thumbnail size), matched to scenes by one text call;
  AI pictures (1K, ~$0.067) only for the rest, max `HISTORY_AI_IMAGES` (10).
  A "sacred" story (prophets, Ahl al-Bayt, companions, imams) shows no
  people and has no music; a picture naming a revered figure is dropped on
  every video unless it is a place ("shrine of Imam Hussain" stays). Render:
  one ffmpeg per shot (the still is decoded once and repeated with the
  `loop` filter, `-loop 1` would decode it every frame; the pan is a crop on
  a 2x canvas scaled down, half-pixel steps) joined by the concat demuxer,
  then one audio pass copies the video: ~4x faster than real time with 3
  workers. Libass finds Noto Serif only as "Noto Serif Bold" (plain "Noto
  Serif" fell back to a sans). Uploads stream in 8 MB pieces with an explicit
  Content-Length (httpx would go chunked otherwise); `youtube_account.add_thumbnail`
  sets the thumbnail (50 units). YouTube refuses videos over 15 minutes and
  custom thumbnails until the channel is phone-verified (youtube.com/verify).
  Found on the first real Karbala runs: the script said a bare "Husayn" and
  "Prophet Muhammad" (`HONOUR` now asks for Hazrat / sallallahu alaihi
  wasallam / (SAW)), quoted the viral, unsourced Dickens and Gandhi lines on
  Husayn (research and check now refuse quotes without a documented
  original), and the voice read "Yazid I" as "Yazid one" (no Roman numerals
  in spoken lines). Names cannot catch Ottoman/Persian manuscript paintings
  ("Maktel-i Al-i Resul"), so a sacred story sends its chosen free pictures
  to one vision call (`artwork_with_people`) and drops artwork with people.
  The fact check rejected a whole Rome script for naming Ravenna: it must
  only flag claims that contradict the research or look invented. The
  picture match asked for pictures that "clearly fit": 5 of 27 Rome scenes
  out of 151 free pictures; "best fit, a real picture beats none" matched 19
  on the same script. Description sources go through `rank_sources`: in
  Google's order the Rome video listed wikihow and medium first.
- **Free footage, free voices, exact captions** (15-oct-2026, ideas from
  MoneyPrinterTurbo, MIT, cloned at D:\youtube\MoneyPrinterTurbo for
  reference only; the owner wants one system and everything free):
  - `stock_media.py`: Pexels + Pixabay (free keys in .env) and Openverse
    (no key, `license=cc0,pdm` only, anonymous limit 20/min and 200/day, so
    capped at 180). One vision call picks a clip per scene with a `fit`
    score; under `MIN_FIT` (6) is dropped: with only Openverse, a cricket
    Short got old leather book covers for "records". Clips used lately rest
    14 days. Tests turn it off (`OPENVERSE=0`, `STOCK_FOOTAGE=0`).
  - `broll.py`: footage cut to the voice lines (a shot every ~2.8 s, every
    other one a closer crop) behind cricket, controversy, quiz and song
    Shorts; `short_kit.render(bg_video=)` adds a dark fade top and bottom.
    Under half the lines with good footage: the Short keeps its own look.
    `prefetch` searches while the lines are voiced (~1 min saved).
  - `free_voice.py` (edge-tts, Microsoft's unofficial read-aloud service):
    read as Roman Urdu it was garbled (half the words skipped); converted to
    Urdu script first (one cheap Gemini call per video) Whisper heard it back
    almost word for word. Default voice engine; Gemini reads any line it
    fails. `VOICE_ENGINE=gemini` / Today tab "Video style" switches back.
  - Caption timing (`short_kit.line_word_times`): the free voice's own word
    times, else Whisper's (Urdu script has as many words as the Roman line
    once izafat "-e-" pairs count as two), aligned clause by clause, else the
    voice's measured pauses (sentence ends take the longest pauses; a plain
    length spread put one 3 s early). Tests use `EXACT_CAPTIONS=pauses`.
  - A render whose captions are burned later encodes veryfast CRF 16
    (`fast=True`): medium CRF 18 took 57 s of a 61 s Short.
  - **Over footage, `short_kit.render` is three passes** (bg_video, no
    music): `mix_audio` (all sound, audio only), the picture with `-an`,
    then a join copying the picture. In one graph ffmpeg 9.0.1 stalled for
    good (CPU flat, no error) with a footage background: at frame 352 when
    a photo card's input ended early (fixed separately: pictures there run
    to the end, hidden by enable=), at 47.6 s with the music bed, and even
    with a finished track mapped as is. Bisected by input with a replay of
    the stuck job; the gradient path never stalled and is unchanged.
  - Other sessions and projects share this laptop's CPU (another Claude
    session, a Next.js dev server at 100% load on 15-oct-2026): slow
    renders are not always ours.
  - The laptop sleeps and its network drops (DNS failing for minutes): a
    10-minute video died at its picture-matching call with its voices made.
    `short_kit.ask_json` now retries network and 5xx blips (3 tries), the
    history matching falls back to each scene's own article, and the free
    voice rests 10 minutes on an unreachable host (30 on a 403/429).
  - `trends.py`: this week's most viewed short videos per niche (yt-dlp
    search, 12 h cache) go into the cricket and controversy planners.
- **Teaser Shorts for long videos** (`history_videos.run_teaser`,
  `my_channels.teaser_due`): once a history long video is uploaded, the
  next job is its 9:16 teaser (the opening narration's own voice files and
  pictures, one new closing line, "Poori video: youtu.be/<id>" in the
  description), uploaded 15 min after the long video's slot (genre
  `history_teaser`, Shorts URL). Teasers are extra: not counted in the day's
  videos, not in the planner's best/worst; the long job dir is kept until
  its teaser exists (`keeps`). The long video's metadata carries `voices`
  and `scene_pictures` for it.
  - **Moment Shorts** (`HISTORY_TEASER_PART` 1-2, `moments_for`): after the
    teaser, two more Shorts per long video, each one chapter's run of scenes
    with a new spoken set-up line. One Gemini call picks the moments, kept in
    the long job dir as `moments.json`. A long job counts `parts` started
    (`_parts`: old jobs say only `teaser`); `shorts_per_long` drops to the
    teaser alone at 3 long videos a day (Shorts count toward the upload
    limit). Part N goes up N days after the long video. Each long scene is
    one picture for 15-25 s, so these Shorts cut per sentence and search
    free footage per sentence, the scene's picture filling the misses; the
    long video's picture credits (`photo_credit`, `footage`) go into the
    Short's description, trimmed, pointing to the full list.
  - **Caption track** (`write_srt` -> `captions.srt`, `youtube_account.add_captions`):
    each long video uploads its own SRT after the video (captions.insert,
    400 units, skipped past 9,000 used that day). YouTube's own auto
    captions handle Urdu badly.
- **Quality check before unattended uploads** (`video_qa.py`, `VIDEO_QA=0`
  off): `my_channels.upload_waiting` runs one 5 fps / 320 px ffmpeg pass
  per job (2-3 s a Short, ~19 s for 3 min of long video) and fails the job
  instead of uploading on: no sound track or mean volume under -45 dB,
  3 s+ of black, a 15 s+ frozen picture, a Short not vertical or past 3 min.
  No false alarms on 14 real Shorts and a long video (15-oct-2026). The main
  channel's comedy uploads do not go through it. Tests set `VIDEO_QA=0`.
- **Quiz formats** `truefalse` ("SACH YA JHOOT", options forced to
  [Sach, Jhoot] with the answer moved along when the model flips or
  translates them) and `oddone`; both fact-checked with Google Search.
- **Posting-time tip** (`my_channels.time_tip`, Today tab "use HH:00"):
  `learn` keeps median views per local posting hour (`stats.hours`, Shorts
  only). With 4+ counted Shorts at two hours and the best 1.5x and 10 views
  ahead, it suggests moving the weakest time next to the best.
- **Viewers steer the ideas** (`engage.Reply.request`, `engage.requests`):
  the reply call also returns any topic a commenter asks for; the last 14
  days' requests go to the cricket, controversy and history planners as a
  hint (`requests=` when the planner takes it), whose rules still win. Today
  shows them per channel.
- **Up next** (`UpNext.jsx`, `POST /api/my-channels/{cid}/ideas`): the
  planned ideas per channel; `{"add"}` puts the owner's topic first
  (cricket's kind guessed: "A vs B, final" match, "A vs B" versus),
  `{"drop"}` removes one and adds it to `used`, so it is not planned again.
- **History series** (`series_ideas`, `HISTORY_SERIES/PART/PARTS/BEFORE`):
  the planner may write one "series: name | part 1 | part 2 ..." line (2-4
  parts; on the first real call it planned "Fatah-e-Andalus" in 3). Each part's
  script is told its place (recap of the last part, the next part teased),
  its title gets "| Part N", its description links the earlier parts
  (`series_links`), and the previous part's description gets "Agla hissa"
  through `youtube_account.add_to_description` (videos.update sends the whole
  snippet back, 51 units). Each series gets its own playlist. Dropping one
  part from Up next drops the rest of that series.
- **Retention in learning** (`my_channels.learn`, `format_score`): each
  counted Short gets `retention` (YouTube Analytics averageViewPercentage);
  `stats.formats[f].watched` and `stats.watched` are medians, and quiz
  formats / song styles are picked by median views x (0.5 + watched/100).
  Analytics refusing leaves views-only learning as before.
- `VOICE_ENGINE` is `edge` (free) or `gemini`; `free` is accepted as `edge`.
  Test runs with `free` went to the paid Gemini voice before (15-oct-2026),
  and without the free voice's word timings captions fall back to Whisper
  alignment: 7 silent minutes on this CPU for a 3-minute video.
- **Aaj ki tareekh** (`history_today.py`, `HISTORY_TODAY=1`, history channel
  switch `daily_short`, on by default): one "on this day" Short a day on top
  of the long videos (format `today`, in `EXTRA_FORMATS` with `teaser`, so
  it is not one of the day's videos, gets no teasers, is QA'd as a Short and
  uploads from noon on its own date). Grounded research of an event on
  today's day and month, 3+ sources, the history RULES and HONOUR, one fact
  check with a rewrite; sacred stories get no people and no music. Events
  go on `used` as `today:<event>` and come back as `history_avoid`. First
  real one (15-oct): Abdus Salam's Nobel, announced 15 Oct 1979.
- **History videos stay at 14 min until verified** (`long_minutes`,
  `youtube_account.long_uploads` = channels.list status.longUploadsStatus,
  asked every 6 h): "eligible"/"disallowed" caps the length; unknown keeps it.
- **Outage failures pause, not count** (`my_channels.TRANSIENT`): a job that
  failed on Gemini's quota, a rate limit or the network marks itself
  `transient` and pauses the channel 30 min (`paused_until`, shown on Today);
  up to 6 a day do not use one of the day's tries (TRIES_PER_SHORT = 2 per
  wanted video, which an hour-long outage used to burn).
- **Review hold** (`review_hours` per channel, 0-24, Channels tab): a
  finished video (`done_at`) waits that long before uploading so the owner
  can watch and skip it; Telegram, when connected, says when one is ready.
  Urgent match results never wait. Default 0 = upload at once, as before.
- **Watchdog** (`autostart.bat watch`): autostart leaves one minimised copy
  of itself that reruns the port checks every 5 minutes (a stopped server
  came back in 4 minutes on 15-oct-2026). It is found by its command line
  through Get-CimInstance: `tasklist /v` took 2 minutes on this laptop.
- Review fixes (15-oct-2026): teaser and moment Shorts move 40 min at a time
  off any scheduled upload (`_clear_of`); a long folder is kept only within
  TEASER_WINDOW; a quality check that cannot run (`video_qa.Unchecked`)
  retries on 3 passes before failing the job; owner ideas go after urgent
  match results and a real result replaces an owner's typed match;
  blocked videos are never linked; `_no_roman` only touches Roman Urdu.
- **Wikipedia as a fourth free library** (`stock_media._wikipedia_photos`,
  `WIKIPEDIA_PHOTOS=0` off, 300 searches a day): article search -> lead
  pictures -> free licences only, ~2 s. Articles about a person are skipped
  (description words like cricketer/born/king) and the pick prompt forbids a
  recognisable person the line does not name: "Babar Azam's century" got a
  photo of Cameron Green first. upload.wikimedia.org answers 429 to the
  browser-like agent and 200 to player_photo.UA (`_agent`); picker
  thumbnails are 500 px (`_commons_thumb`; 400 px is refused). CC BY/BY-SA
  files get their own credit line (file, author, licence, link).
- A stock library that times out twice rests 15 min (`stock_media._missed`):
  Openverse timed out on every search for hours on 15-oct-2026 and held
  each Short 70-100 s. Its search timeout is 12 s (it answers in 1-2 s).
- **The local dashboard runs on port 5180** (`autostart.bat`, `--strictPort`):
  another of the owner's projects (D:\bd\tool) runs Vite on 5173, and the
  old "is 5173 listening?" check then skipped starting Shortkaar's dashboard
  at all. The CDP harness BASE is http://127.0.0.1:5180.
- Patch scripts: always the Write tool, and write files back as LF (the
  repo stores LF; some working files are CRLF on disk, and a half-CRLF file
  got CLAUDE.md committed as CRLF once). The scratch `patchlib.patch`
  pattern: read bytes, replace CRLF with LF, patch, write bytes. A bash heredoc turned `\n` inside a
  Python string into a real newline three times on 8-oct-2026.
- Before starting uvicorn, check :8000: a server from an earlier session may
  still answer with old app.py code (job subprocesses load new code anyway).
- UI checks on this laptop: headless Edge `--screenshot` with
  `--virtual-time-budget` hangs on pages with `<video>` (History, Gallery)
  and without it captures before React loads. Drive Edge over CDP instead
  (`--remote-debugging-port` + the `websockets` package). Only ever kill
  Edge processes whose command line has your own `--user-data-dir`.
- Flaky on this laptop: tests posting a YouTube URL to /api/process can 400
  in a full run, because `assert_public_url` does a live DNS lookup.
- **Section fetch retries with fresh links**: YouTube sometimes 403s every
  request on one set of stream URLs; each retry round re-resolves
  (`RESOLVE_ROUNDS`, 3) before the full-download fallback.
- **Dashboard is links-only and uses the server key**: the upload tab is gone
  (the API still accepts uploads), and `/api/config.serverGeminiKey` tells the
  dashboard that `.env` has `GEMINI_API_KEY`, so it never asks for one.
- **Clips stay under 2 minutes**: `main.cap_clip_lengths` (`MAX_CLIP_SECONDS`,
  119) trims every pick, before the section fetch too; the API caps
  `clip_max_seconds` at 119.
- Windows tests: `TestHostAsrSlot` (fcntl) and two cp1252 file reads fail on
  Windows before and after these changes.

### Cómo se elige el layout

`POST /api/process` acepta `layouts`: una lista (JSON) o cadena separada por
comas con `auto`, `split`, `screencast`, `speaker_cut`, `punch_in` y `none`.
Cada nombre enciende su variable de entorno para **ese** trabajo
(`app.py:layout_env`); `none` apaga el picker aunque prod corra con
`AUTO_LAYOUT=1` (recorte simple y nada más). Sin `layouts` manda el env del
despliegue, que desde el 25-ago-2026 es `AUTO_LAYOUT=1`. El dashboard lo expone
en opciones avanzadas ("vertical layout": auto / split / screencast / none,
`MediaInput.jsx`, recordado en `localStorage.os_layout`).

`auto` activa `layout_picker.py`: **una** llamada a Gemini por vídeo de origen
(no por clip) que elige entre `none` / `screencast` / `split`. Medido sobre el
corpus de 48 contra etiquetas revisadas a mano: 94% / 92% / 96% en tres pasadas,
con 0-1 falsos positivos sobre los 28 clips que no deben tocarse, y solo 2 clips
que cambian de respuesta entre pasadas.

**Manda 12 fotogramas a 1024px, no el vídeo.** Gemini factura vídeo a ~300
tokens por segundo: una hora de fuente son ~1,08M de tokens (no cabe en una
ventana de 1M) y una subida de 1-2 GB para recibir una palabra. Doce fotogramas
cuestan ~3k tokens **dure lo que dure la fuente**, que es lo que hace viable
esto con los podcasts de una hora que entran de verdad. La resolución importa y
el número de fotogramas no: a 640px detecta 15 de 20 (una hoja de cálculo es
ilegible), a 1024px sube a 17, y pasar a 24 fotogramas lo empeora. A 1024px la
diferencia con mandar el vídeo entero cae dentro de la varianza que ya tiene el
propio modo vídeo, a 2,2 s por clip en vez de ~15 s.

Lo que hace que funcione, y que conviene no deshacer: se le pide una **decisión
entre opciones cerradas**, no una medida. Los cuatro intentos anteriores (Canny,
MSER, cobertura temporal, anchura) le pedían un número y ninguno separó una hoja
de cálculo de un marcador de esquina. La varianza que este repo atribuía a
Gemini era de las medidas continuas, no del modelo.

`layout_picker.apply()` sólo **añade**: una elección explícita del usuario nunca
se desactiva porque el modelo diga `none`.

### Hook grounding for on-screen clips (`hook_grounding.py`)

The hook and title come from the detail pass, which only reads the
transcript, so on a clip whose meaning is on the screen (a settings dialog,
a spreadsheet) they summarise the video's topic instead of naming what is
shown. After the render, if the `<clip>.layout.json` sidecar says at least
25% of the clip is `screencast` / `wide` / `inset` (plus `general` when the
layout picker called the video a screencast: a face-less scene there is a
slide or a dialog, not a group shot), three frames from those
stretches at 1024px plus the clip's own words go to Gemini
(`GroundedHook`) and `viral_hook_text` / `video_title_for_youtube_short`
are rewritten in place before `auto_hook_clip` burns them; the originals
stay under `hook_grounding.before`. Gemini-only (frames): with just a local
LLM it logs one line and keeps the transcript hook. `HOOK_GROUNDING=0`
disables it. The detail prompt itself now carries the rule "about this
moment, not the video", which is the cheap half of the same fix.

### The quota wall offers the first N minutes (`app.partial_offer`)

The wall (`TopUpModal`, context `wall`) opens on a 402 from `/api/process`.
Measured on 16-sep-2026, 93 of 99 walls were shown to accounts with their
20 free minutes **untouched** that had pasted a 21-90 min video: the user was
asked for $12 before seeing one clip, and 41 of the 68 subscriptions Stripe
created in 30 days expired unpaid, none of them a card decline. So the 402
now carries `partial_minutes` (the floored balance, when it is at least
`PARTIAL_MIN_MINUTES` and shorter than the source), the wall shows "clip the
first N min" next to the plans, and the dashboard resubmits the same job with
`max_minutes=N`. `reserve_process_minutes` then reserves N (never more than
the balance, whatever the client asks) and sets `MAX_SOURCE_MINUTES` for
`main.py`, whose `cap_source_duration` cuts the downloaded/uploaded file **in
place** before anything reads it, so transcription, the layout picker, the
editor and `/api/source` all see a short video. The cut travels in the
resume manifest: a resumed job downloads the source again and would
otherwise process 45 minutes on a 20-minute reservation. `/api/status` and
the process response carry `partial`, and the results view says which part
of the video the clips came from, with the upsell for the rest.

### The free plan's watermark is a copy, and paying removes it (`watermarked.py`)

Every file the pipeline and the clip editor write is clean. On the free plan
the file that is *served* is `wm_<final>`, a copy of the final file with the
mark burned in (`main.mark_delivery`, the last step after captions; the
editor endpoints get it from `app._deliver`, decided from the caller's plan
right now, not from the job's flag, which a restart loses). Both twins live
on disk and in R2 (`cloud.videos._twins_to_archive`). Before 30-sep-2026 the
mark was burned into the canonical reframe, so every derivative inherited it
and the upgrade modal's "upgrade to remove the watermark" was false for the
clips already made: the first cancellation for "clip quality" was a user who
paid 15 minutes after their first job and kept the mark on every download.

- **Upgrade**: `cloud/billing._upsert_subscription` fires
  `videos.unmark_user_library` on the free→live transition
  (`became_live`). Per clip it checks the clean twin exists in R2, moves the
  history row and the project state to it, deletes the marked object and
  calls back into `app._unmark_local_job` so an open dashboard polls the
  clean URL. No render, no source video. The dashboard chases the job
  result after the plan flips (`App.jsx`, the `wm_` regex) and refreshes
  the durable map.
- **Walk-backs**: `wm_` is the outermost layer; `_strip_burned_captions` /
  `_strip_burned_hook` drop it first, `_canonical_clip_file` globs
  `wm_*{clean}`.
- **`/videos` guard** (`app._media_guard`): a job rendered for the free plan
  carries a `.marked` dotfile (`watermarked.MARKER_FILE`, written by
  main.py, restored with the project, removed on unmark; `_deliver` marks
  only jobs that carry it, so a job from before this scheme, whose canonical
  has the mark burned in, never gets a second one);
  while it exists the clean deliverables of that job are refused, so the
  twin cannot be fetched by stripping the prefix off a URL. The editor's
  `temp_*` scratch files and the caption sidecars stay servable.
- **Notice**: `WatermarkModal` shows once per job when the clips land on a
  free account (`source=results`, 2.5 s after the grid) and, if skipped,
  before the first download; tracked as `WatermarkNoticeSeen` /
  `WatermarkNoticeUpgrade` with `source`. Its Upgrade opens the upsell
  `TopUpModal`.

### Free sources past the balance never meet the wall (`app.free_overflow`)

Since 28-sep-2026 the wall above only shows to paid plans and to free
accounts with less than `PARTIAL_MIN_MINUTES` left. For a free account whose
source is longer than its balance, `reserve_process_minutes` decides on its
own (the client sends no `max_minutes`):

- **First video, up to `FIRST_VIDEO_MAX_MINUTES` (60):** clipped whole. Only
  the floored balance is reserved (it lands at zero) and the download's safety
  cap (`SOURCE_CAP_MINUTES`) is the probed length, not the reservation. Once
  per account: `metering.has_processed_before` (any reserved/committed
  `process` row; a released one keeps the grant for the retry), and once per
  client IP every `FIRST_VIDEO_IP_WINDOW_DAYS` (30): `first_video_grants`
  holds an HMAC of the IP (never the IP), is not tied to the user row so an
  account deletion does not reset it, and only counts grants whose job
  reservation is live. A blocked network gets the first-N-minutes cut. The response
  carries `first_video: true`; the dashboard says so and tracks
  `FirstVideoGrant`.
- **Anything else:** `max_minutes` becomes the balance, so the job clips the
  first N minutes exactly as if the user had taken the wall's offer. Tracked
  client-side as `AutoPartial`.

### Lifecycle emails (`cloud/lifecycle.py`)

Welcome (minutes after sign-up), first-clip nudge (24-72 h, nothing
processed), win-back (2-7 days after the first committed video, no plan; with
`WINBACK_PROMO_CODE` when set) and checkout recovery (`checkout.session.expired`
with the `after_expiration.recovery` URL that `create_checkout` now enables).
Each at most once per account: a `lifecycle_emails` row is claimed before the
send (unique `user_id, kind`). The loop sends at most `BATCH` per 10-minute
tick. All four are commercial: `emails.send_commercial_email` skips
`marketing_opt_out` accounts and adds the unsubscribe footer and
`List-Unsubscribe` headers (the out-of-minutes upsell goes through it too).
The Stripe webhook endpoint must have `checkout.session.expired` enabled.
Promotion codes and coupon ids live in the env / Stripe, never in this repo.

### Cancel flow (`cloud/cancellation.py`, `CancelPlanModal.jsx`)

Account → "Cancel subscription" opens three steps: reason (closed list,
`CANCEL_REASONS`, plus an optional detail box), a 1-5 rating with an optional
review (and an "OK to quote publicly" box), then confirm.
`POST /api/billing/cancel` sets `cancel_at_period_end` in Stripe with
`cancellation_details` (our reason mapped to Stripe's feedback enum), and only
after Stripe accepts writes a `cancellation_feedback` row (user-owned, erased
with the account) and flips the local row, so the webhook sees no transition
and the generic churn alert does not fire twice. The alert names the reason and
rating, never the written text (Telegram, see `alerts.user_ref`): read reviews
in the table.

The last step leads with a retention offer (`RETENTION_COUPON_ID` env, the
coupon the portal used to offer): `GET /api/billing/retention-offer` says
whether this subscription gets it (live monthly plan, no discount on it, never
offered before: `retention_offer` in the Stripe subscription metadata; any
Stripe error means no offer), `POST /api/billing/retention-offer/accept` applies
it and stores the feedback row with `outcome="retained"` (cancels store
`"canceled"`). Cancelling is OFF in the Stripe portal config since 2026-09-28,
so this flow is the only way to cancel; `POST /api/billing/resume` undoes a
scheduled cancel ("Keep my subscription" on the account page), since the
portal's renew went with its cancel feature. The webhook alert for a portal
cancel stays for cancels made from the Stripe Dashboard.

### Sign-up survey (`cloud/onboarding.py`, `OnboardingSurvey.jsx`)

`signup_attribution` says which page a user came from, not why. Accounts
younger than 7 days get one skippable screen before the clip tutorial (never
over a running job): what they want to make (multi-select: clips, AI avatar /
UGC videos, autopilot, thumbnails...), how they heard of us, and who they are.
Closed lists mirrored in the JSX (a test checks), stored in
`onboarding_surveys` (user-owned; a skip is a row too, so it is asked once),
and tracked as `SignupSurveyAnswered` with one `goal_<x>` prop per goal so
OpenPanel can break conversion down by what people came for.

### How many clips a job returns (`clip_selection.py`)

The count is not a setting, it is derived, and every stage of the derivation
used to leak. `get_viral_clips` builds ~90s scoring windows over the
transcript, scores them in batches, shortlists the best `shortlist_target`
(`min(10, duration//90 + 2)`, floor 3) and asks the detail pass for
`clip_count_targets(len(shortlist))` clips — a floor that matters because
users who got 1-3 clips came back a second day 0.4% of the time against
16.1% for 4-9.

Two things broke that chain, both found on a 9:10 source on 22-sep-2026 that
delivered 3 clips in prod:

- **The scoring pass selected instead of ranking.** Its prompt said "choose up
  to 3 windows from this batch", so the shortlist ceiling was
  `3 * n_batches`, not the target: 9 windows batched 8 + 1 gave 3 + 1 = 4
  against a target of 8, and `clip_count_targets` then asked for 4-8 clips
  instead of 6-12. Every source under ~30 min was starved this way — this is
  the mechanism behind "95% of jobs deliver 3 clips or fewer". It also threw
  away the ranking it was computing, since a batch of five great moments
  could still only contribute three. The prompt now scores **every** window
  and the shortlist is the global top N. Batches are near-equal
  (`score_batches`) for the same reason the cap is gone: a trailing batch of
  one window returned that window whatever its score, so the tail of the
  video entered the shortlist by arithmetic.
- **The clip floor was only a sentence in the prompt.** Nothing in code
  checked it, so a detail pass that returned half was shipped as-is. When it
  comes back under `min_clips`, the shortlist windows that produced nothing
  get one more call for the difference. An empty answer is accepted: that is
  material that genuinely holds no more, and padding is worse than a short
  list.

Measured on that source, same transcript, three runs: shortlist 4 → 8 and
4 clips → 6, at the same cost (~$0.005, 3 calls). `target_clips` on
`/api/process` (dashboard: advanced options) still pins both ends via
`CLIP_TARGET_MIN`/`MAX` when the user wants an exact number.

### Silent footage: the vision fallback (`main.get_visual_clips`)

The moment picker reads the transcript, so a video with nothing said in it
would score nothing. `main.py` switches paths by itself instead, and the
switch is the part worth knowing because it is not only "no audio track":
`transcribe_video` raising `NoAudioError`, **and** `speech_is_sparse()`
coming back true, both set `transcript = None` and route to
`get_visual_clips`. Sparse means under `MIN_SPEECH_WORDS` (8) in total or
under `MIN_SPEECH_WORDS_PER_MIN` (5). Music-only footage and a session
recorded with the mic muted transcribe to a handful of stray words, which
is worse than silence: without that second test the picker scores those
words and cuts around them.

The vision pass uploads the video, Gemini watches it and returns the same
`{"shorts"}` shape (`gemini_worker.VisualResponse`) in the same 15-60s
band, so every stage after it is byte-identical: layouts, inset detection,
hooks. `CLIP_TARGET_MIN`/`MAX` apply directly here rather than being
derived from scoring windows, because there are none. The transcript is
stored as `{"language": "none", "segments": []}`, so the clips come out
with no subtitles, which is correct and not a bug.

**This is the one stage that sends Gemini the video instead of frames, and
that is deliberate** — 12 frames can say what kind of video this is (which
is all the layout picker needs), they cannot say which 40 seconds to cut.
The cost is the ceiling: Gemini bills video at ~300 tokens/second, so an
hour is ~1.08M tokens, past a 1M window, and **nothing guards the length**.
A silent multi-hour source fails at the model rather than politely. If that
needs fixing, the answer is a guard or segmenting the source, not porting
the frame trick over from the layout picker. Gemini-only either way: a
text-only `LLM_BASE_URL` server cannot see footage, and with no
`GEMINI_API_KEY` the function logs one line and returns None, which fails
the job outright.

The public `/gta-5-clips` page states these thresholds and this ceiling to
users; if the behaviour changes, change `dashboard/seo/pages.js` too.

### Local LLM for the moment picker (`llm_backend.py`)

`LLM_BASE_URL` (+ `LLM_MODEL`, `LLM_API_KEY`) routes the two transcript
passes of `get_viral_clips` to any OpenAI-compatible `/chat/completions`
instead of Gemini; the response is validated with the same pydantic schemas
Gemini enforces server-side, so `main.py` sees one shape. `main.score_batch_size`
drops to 3 windows per call there (local contexts are 4-8k; a truncated
prompt scores garbage silently). Self-host `/api/process` then accepts a
request without `X-Gemini-Key` and `/api/config.localLlm` tells the dashboard
not to demand one. Frame-based stages (`layout_picker`, `screencast_layout`,
`get_visual_clips`) stay on Gemini and degrade as they always did without a
key. Never wired in cloud mode: `BILLING_ENABLED` ignores it.

### Thumbnail Studio (`thumbnail.py`, `/api/thumbnail/*`)

Titles come from the transcript plus 10 frames at 1024px, never the whole
video (same reasoning as the layout picker: an hour of video is ~1M tokens for
a text task). Two calls: a 25-title brainstorm across fixed styles, then a
critic that scores, dedupes by angle and returns 10, each paired with a 1-4
word `thumbnail_text` that complements the title rather than repeating it.
Rules baked in: payoff inside 50 characters (phones cut there), keyword in the
first 3 words, same language as the transcript. Text model is
`GEMINI_MODEL_THUMBNAIL` (default `gemini-3.7-flash`), deliberately not
`GEMINI_MODEL`: flash-lite is fine for a closed-choice layout pick and visibly
worse at creative titles. Image model is `GEMINI_IMAGE_MODEL` (default
`gemini-3.1-flash-image`).

Thumbnails are `count` **different concepts**, not one prompt repeated: a text
call designs each (hook text, side for the text, palette, scene prompt), then
one image call per concept in parallel. By default (`burn_text=true`) the
image model is told to leave that side as negative space and PIL sets the text
in Anton with a black stroke, so accents and spelling are never wrong; the
`AI painted` toggle lets the model render the text itself. Every output is
cover-cropped to 1280x720 and saved under YouTube's 2 MB limit.
`GET /api/thumbnail/frames/{session}` scores sampled frames by face area and
sharpness (MediaPipe + Laplacian), keeps them spread across the runtime, and
the dashboard offers them as the person reference so the thumbnail shows the
creator instead of a stranger; an uploaded face photo still wins.

### Video Reframing Modes

**A source already shot vertical is passed through untouched.**
`reframe_v2.source_already_fits()` gates it: every layout below reorganises the
frame to buy back width the crop threw away, and on a 9:16 upload there is none
to buy. GENERAL was the visible failure — its 0.42 height ratio, which buys
presence on a landscape source by overflowing the sides, scaled a 1080x1920
source down to a 453px sliver floating over a blurred copy of itself, and the
scene classifier routes every face-less shot (a slide, a screen recording) there.
So the picker is skipped (one Gemini call saved per upload), the classifier is
skipped, and every scene renders TRACK, whose crop is the whole frame.
`general_filtergraph` additionally floors the foreground at the height where the
source fills the output width, so the editor's explicit GENERAL override on a
portrait clip cannot reproduce the shrink either.

- **TRACK Mode** (single subject): MediaPipe face detection + YOLOv8 fallback with "Heavy Tripod" stabilization
- **GENERAL Mode** (groups/landscapes): Blurred background layout preserving full width
- **SPLIT Mode** (two-shot conversation, `split_layout.py`): both speakers stacked
  in half-frames. Off by default (`SPLIT_LAYOUT=1`); v2 engine only, so a
  fallback to the v1 loop silently renders GENERAL instead. It upgrades scenes
  the classifier already sent to GENERAL, never TRACK ones, and needs both faces
  visible **in the same frame** for at least half the sampled frames — that is
  what separates a real two-shot from a plano/contraplano, where stacking would
  show the same person twice. `SPLIT_TIGHTNESS` (default 0.8) trades a little
  upscale for keeping the other speaker out of each half. Captions on a SPLIT
  stretch sit on the seam between the halves (`{\an5}` per word event in
  `subtitles.generate_ass`), the one place they cover nobody; the render
  records which stretches are stacked in a `<clip>.layout.json` sidecar
  (`layout_ranges.py`) and every metadata writer copies it into the clip's
  `layout_ranges`, so `/api/subtitle` finds it after a restyle too. The fast
  rerender (cut without reframe) carries the canonical clip's ranges through
  the new cut (`layout_ranges.remap`, in `recut.perform_recut`). Only the
  ASS path can do this; SRT burns keep one alignment for the whole file.
- **SCREENCAST / WIDE Modes** (`screencast_layout.py`, `SCREENCAST_LAYOUT=1`):
  for scenes whose meaning lives outside the centre. Gemini reports each range's
  **width_fraction**, and that is the gate — coverage was tried before and did
  not separate a spreadsheet from a corner ticker, while width does (a bug spans
  ~15% and survives any crop, a spreadsheet spans ~100% and cannot). Content
  narrower than 0.5 moves nothing. Between 0.5 and 0.85 there is room beside the
  content, so SCREENCAST stacks it over the presenter. Above 0.85 the presenter
  is composited **on top of** the content and stacking would show it twice, so
  those scenes get WIDE: the GENERAL layout with side-cropping disabled.
- **INSET Mode** (`camera_inset.py`): pantalla a ancho completo arriba, el
  recuadro de la webcam ampliado abajo. Para el caso de una sola fuente con la
  cámara compuesta en una esquina (OBS, VOD de stream). Se encadena detrás de
  la decisión `screencast`, **no** se le pregunta a Gemini: ofrecido como cuarta
  opción respondió `screencast` en los 5 clips que tienen recuadro, en dos
  pasadas, y la exactitud global cayó de 92% a 83-85%. El detector geométrico
  encuentra esos 5 sin falsos positivos. Los tres filtros que hacen falta, cada
  uno pagado con una iteración: sujeto **pequeño**, **descentrado en
  horizontal** (una cara de talking head está centrada aunque esté alta), y
  **quieto entre muestras** (3-11px frente a 316px de una persona real).
- **ALTERNATE Mode** (`active_speaker.py`, `SPEAKER_SIGNAL=1` + `SPEAKER_CUT=1`):
  hard cuts to whoever is talking, rendered through the TRACK path as a
  trajectory with jumps. `SPEAKER_SIGNAL=1` alone just gates SPLIT on both people
  actually speaking. Mouth activity **must** be normalised per speaker before
  comparing (`normalise_activity`): raw frame-difference magnitude scales with
  local contrast and lighting, and on a real two-shot it handed one speaker
  90-100% of the scene.
- **Punch-in** (`punch_in.py`, `PUNCH_IN=1`): not a layout. A ~12% push on the
  clip's beats, riding the TRACK path by widening its per-frame crop command
  from x-only to w/h/x/y. Beats currently come from the audio envelope;
  `emphasis_times` is a plain list of seconds so the transcript's hook words can
  replace it without touching the module.

### Key Classes
- `SmoothedCameraman` - Stabilized camera movement with safe zone logic (prevents jitter)
- `SpeakerTracker` - Prevents rapid speaker switching, handles temporary occlusions

### API Endpoints
| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/process` | Submit video for processing |
| GET | `/api/status/{job_id}` | Poll job status and logs |
| POST | `/api/edit` | Apply AI video effects |
| POST | `/api/subtitle` | Generate and apply subtitles (auto-transcribes dubbed videos) |
| POST | `/api/hook` | Add text hook overlays |
| POST | `/api/translate` | AI voice dubbing via ElevenLabs |
| GET | `/api/translate/languages` | List supported dubbing languages |
| POST | `/api/social/post` | Post to social media (async upload) |
| POST | `/mcp` | MCP server (JSON-RPC): the pipeline as agent tools |
| POST/GET/DELETE | `/api/keys` | User API keys (cloud mode, session JWT only) |
| DELETE | `/api/account` | Erase the account and everything in it (GDPR art. 17) |
| GET/PUT | `/api/autopilot` | Autopilot settings, connected accounts, recent runs (cloud only) |
| GET | `/api/autopilot/videos` | Latest uploads of the connected YouTube channel + what Autopilot did |
| POST | `/api/autopilot/run` | Clip one channel video now (`{video_id}`) |

### Agent access (MCP, API keys, webhooks)

- **API keys** (`cloud/api_keys.py`): `osk_...` tokens, sha256-stored, created in
  the dashboard account page. `cloud/auth.get_current_user_optional` accepts
  them (`Bearer osk_...` or `X-API-Key`) and resolves the owner, so metering,
  entitlement, plan priority and job ownership apply to agents with zero
  endpoint changes. Key management itself refuses API-key auth: a leaked key
  cannot mint replacements.
- **MCP server** (`mcp_server.py`, mounted always): stateless Streamable-HTTP
  JSON-RPC at `/mcp` — no SDK dependency, ~3 methods + 8 tools. Each tool calls
  back into this same app in-process (`httpx.ASGITransport`) forwarding the
  caller's auth headers, so it can never drift from the REST behavior. Cloud
  mode 401s without a resolvable user; self-host stays BYOK-open.
- **stdio transport** (`mcp_stdio.py`): the same `handle_message` / `call_tool`
  as a subprocess, for hosts that only launch MCP servers as a command (Glama's
  Dockerfile deployments wrap one; a local client can skip the web server).
  Two invariants: `sys.stdout` is swapped for stderr **before `app` is
  imported**, because the pipeline prints everywhere and one stray line
  corrupts the JSON-RPC stream; and the app's lifespan is entered
  (`router.lifespan_context`), which `ASGITransport` does not do on its own.
- **OAuth for MCP clients** (`cloud/mcp_oauth.py`, cloud mode only): claude.ai
  and ChatGPT connect by URL, so the server publishes RFC 9728/8414 metadata
  under `/.well-known/`, accepts dynamic client registration (`POST
  /oauth/register`, public clients, PKCE S256 mandatory) and bounces
  `GET /oauth/authorize` to the dashboard consent screen (`#/oauth/authorize`),
  because the session JWT lives in localStorage on the frontend host and a
  bare API GET cannot see it. `POST /api/oauth/authorize` (session auth) mints
  the code; `POST /oauth/token` redeems it by **minting an ordinary `osk_`
  key** named after the client and returning it as the access token. No new
  auth path, no refresh tokens: the key shows up in Account → API keys and
  revoking it disconnects the app. The `/mcp` 401 carries
  `WWW-Authenticate: Bearer resource_metadata=...` so clients find the flow.
  `oauth_codes` is in `USER_OWNED_TABLES`; `oauth_clients` deliberately not.
- **Webhooks**: `POST /api/process` takes `webhook_url` + optional
  `webhook_secret` (HMAC-SHA256, `X-OpenShorts-Signature`). Validated with
  `security_utils.assert_public_url` at submit AND at delivery (DNS rebinding).
  Fired once per job from `run_job_wrapper` after the R2 archive so the payload
  can carry durable download links; survives redeploys via the resume manifest.
  `PUBLIC_API_URL` env sets the absolute-URL base when behind a proxy.

### Autopilot (`cloud/autopilot.py`, dashboard tab "Autopilot")

Cloud-only retention feature: every new video on the user's connected YouTube
channel becomes clips on its own, and optionally the best ones are scheduled
on their socials, one a day. Paid plans only (it spends minutes unattended).

- **Channel listing** comes from Upload-Post, not scraping:
  `GET /api/uploadposts/media?platform=youtube&user=os_<id>` reads the
  channel's uploads playlist with the user's own OAuth token, so it includes
  videos uploaded straight to YouTube. There is no push from Upload-Post, so a
  loop polls (tick 5 min, each user at most once per 55 min).
- **Jobs go through the normal pipeline**: an in-process `POST /api/process`
  (`httpx.ASGITransport`, like the MCP server) authenticated with a freshly
  issued session JWT for the user. Metering, the probe, the per-plan job
  limit, the quality gate and the download proxies apply unchanged. The
  per-job content attestation is recorded once as `rights_ack_at`.
- **Guard rails**: only videos published after `enabled_at` (switching on never
  clips the back catalogue) and at most 3 days old; 1 automatic job per user
  per 24 h; `max_minutes` per video (default 30, sent as the partial-clip
  `max_minutes`); YouTube Shorts are skipped (`HEAD /shorts/<id>` answers 200
  for a Short and 303 to `/watch` for a regular video; the SOCS consent cookie is required, from the EU servers every request is otherwise a 302 to consent.youtube.com).
- **Dedupe across the deploy handover**: two containers poll at once during a
  rolling deploy, so a video is claimed by INSERTing its `autopilot_runs` row
  (unique `user_id, video_id`) before anything is submitted. A draining
  instance stops polling. A 429 (job limit) or 5xx drops the claim to retry.
- **Completion**: `run_job_wrapper` calls `on_job_finished` after the R2
  archive. A guarded UPDATE (`status='processing'` → final) makes it once-only;
  it sends the Autopilot email (replacing the generic clips-ready one) and,
  with autopublish on, uploads the top `clips_to_publish` clips by
  `predicted_score` to Upload-Post in a background task, scheduled one a day at
  `publish_hour` in the user's IANA `timezone`. Runs stuck in processing for
  6 h are marked `timeout`.
- `AUTOPILOT_DISABLED=1` turns the poller off without touching the API.
- Both tables are in `account.USER_OWNED_TABLES`.

### Account erasure (GDPR art. 17)

`DELETE /api/account` (`cloud/account.py`, dashboard: Account → Delete account)
is immediate and irreversible: there is no recovery window because after the
delete there is nothing left to authenticate a recovery request against. It
refuses API-key auth (a leaked `osk_` must not destroy its own account) and
requires the caller to retype the account email.

The order of the steps is the design, and each one is a failure mode:
**Stripe cancel first**, aborting the whole thing if it fails, so we never erase
a user we are still billing; **R2 before the database**, because those rows are
the only index of which objects are theirs and dropping them first turns a
failed purge into permanent orphans; the DB delete is **one transaction** over
an explicit table list (`USER_OWNED_TABLES`) rather than the declared ON DELETE
CASCADEs, since `create_all` never ALTERs an existing table and a constraint
added after a table shipped exists in the models but not in production.
`tests/test_account_erasure.py` fails if a new table references `users.id`
without joining that list.

`app.py` registers a callback for the local working files, which record
ownership three different ways: the `.owner` file clip jobs write (so jobs
recovered from disk after a restart count too), `saas_jobs`, and
`thumbnail_sessions`. That last one is the only thing that ever deletes
generated thumbnails: the hourly sweep skips their directory and they are
served publicly at `/thumbnails/`.

What deliberately survives: the Stripe customer and its invoices (6-year
retention, Spanish commercial law) and one `account_deletions` row holding a
sha256 of the email as proof the erasure happened, itself purged after 5 years.
The "why are you leaving" answer is a closed list (`DELETION_REASONS`), never
free text — anything the user could type would land in a row designed to
outlive them. Deleting users also made one webhook path reachable that never
was before: `_apply_topup` reads the user id from Stripe metadata, so it now
confirms the row still exists before inserting, or the FK violation makes
Stripe retry the same doomed event for three days.

### Concurrency Model
Async job queue with semaphore-based concurrency control. Configure via `MAX_CONCURRENT_JOBS` env var (default: 5). Jobs auto-cleanup after 1 hour.

The real limit on the GPU box is VRAM, not CPU: each `main.py` job holds
Parakeet (onnxruntime CUDA), TransNetV2 (torch, ~2 GB at peak) and an
NVENC session, and when the card is full a cut fails as "Generic error in
an external library" / exit 187 with 0 bytes, TransNetV2 as CUDA OOM, and
the reframe writer as a broken pipe. The retry in `ffmpeg_utils.cut_clip`
waits for a **busy** GPU; it cannot help with a **full** one. The API
process itself was the biggest tenant (7.7 GB idle on 17-sep-2026): the
thumbnail studio and `/api/subtitle` on a dubbed clip transcribe
in-process and the ASR singletons then lived in uvicorn for good, so both
now call `transcribe_backends.release_models()` when they are done. Size
`MAX_CONCURRENT_JOBS` against the free VRAM first, then check the CPU.

The CPU is the other ceiling (a 20-thread host sat at load ~100 at peak on
22 and 25-sep-2026). Two costs were pure waste and are gone, with the
delivered clips byte-identical (decoded-frame MD5s + audio, 15 clips of 3
real videos, bench of 25-sep-2026):
- **onnxruntime threads spinning** during Parakeet: ~160 CPU-s per 9 min of
  audio while the GPU did the work. `parakeet_session_options()` turns
  spinning off for the ASR session only; the VAD must keep `load_vad`'s
  defaults (see the docstring for why).
- **A seek per sampled frame** in `analyze_scenes_strategy` and
  `split_layout`: each seek re-decoded the GOP. `frame_sampler.read_at`
  reads forward once and returns the same frames.
Net: a job's CPU roughly halves (Python side -65-80%).

Then speed at equal quality (25-sep-2026; SSIM 0.990-0.9998 vs before,
checked by eye, audio identical):
- **Cut on the card** (`ffmpeg_utils.cut_clip`, NVDEC -> NVENC with
  `-hwaccel_output_format cuda`) for 8-bit 4:2:0 sources; byte-identical to
  the CPU cut. Other sources and a failed GPU cut decode on the CPU.
- **Silero VAD on one CPU thread** (`vad_load_kwargs`): on CUDA it ran one
  32 ms chunk per launch and was most of the transcription's wall time.
- **Blur at quarter size** (`ffmpeg_utils.blurred_backdrop`).
- **Watermark as a served copy** (`main.mark_delivery`, see the section
  on the free plan's watermark): one NVENC pass per free clip, after
  captions. It used to ride the reframe encode, which made it permanent.
- **hooked_ + subtitled_ from one ffmpeg** (`hooks.add_hook_to_video(also=)`):
  the editor still needs both files (re-caption walks back to hooked_,
  hook replace to the canonical), so nothing is skipped, only one decode.
- **CLIP_WORKERS=6** by default.
Tried and dropped: NVDEC for the analysis decodes and `scale_cuda` (slower in
wall, and scale_cuda does not match swscale); yt-dlp chunking/concurrent
fragments (YouTube serves DASH over https, no gain beyond network noise).
Measured with a side-by-side bench: Gemini decisions recorded once and
replayed, old and new code run at the same time, clips compared by
decoded-frame MD5 / SSIM.

Three guards keep the card from filling (22-sep-2026: 30-60% of jobs failing
per hour at peak with `MAX_CONCURRENT_JOBS=8`):
- **Job processes release the ASR model after transcribing**
  (`main.transcribe_video` → `release_models()`). Before, a job kept Parakeet's
  onnxruntime CUDA arena (~4-6 GB) for its whole render; TransNetV2 also
  `empty_cache()`s after each pass.
- **Parakeet runs lean** (`transcribe_backends.parakeet_providers`,
  `PARAKEET_VAD_BATCH`=4): 4 VAD segments per encoder batch instead of 8, CUDA
  arena `kSameAsRequested`, no max cuDNN workspace. Peak per transcription
  6.1 → 4.6 GB with the same words (benchmark 22-sep-2026: 10 real videos,
  4,850 words, 1 word changed outside a clip that goes to whisper anyway).
  Batch 2 dropped a sentence and int8 was 11x slower with 11.7% of words
  different: both rejected.
- **Host-wide transcription slots** (`transcribe_backends.host_asr_slot`,
  `ASR_HOST_SLOTS`, default 2): flock files `output/.asr-gpu-N.lock`, shared by
  every job process and by both containers of a deploy.
- **Queue admission** (`app._wait_for_shared_gpu`): a job starts only when
  running-here + running-on-the-draining-instance < `MAX_CONCURRENT_JOBS` and
  `nvidia-smi` reports at least `GPU_MIN_FREE_MB` (4500) free; an idle card
  always starts, and the wait is bounded by the drain timeout.

Failures the user should never see (`app.run_job_wrapper`):
- **Auto-retry**: a failed job whose error text is transient (CUDA/OOM,
  NVENC "Generic error in an external library", cublas, Gemini 5xx, "No clips
  could be rendered") is re-queued once after `AUTO_RETRY_DELAY_SECONDS` (30),
  keeping its reservation and transcript checkpoint (`AUTO_RETRY_LIMIT`=1).
  Content failures (no audio, private video, no clips found, policy block)
  are final as before. Inside a job, `main.py` retries each failed clip once,
  alone, after a pause, and renders clips best-score first.
- **Shutdown is not failure**: when the drain timeout cancels a running job,
  the child is killed and the manifest + reservation are kept, so the next
  instance resumes it. A manifest next to a metadata file means "stopped
  mid-render" and is resumed, not recovered as completed.
- `/api/status` returns `queue: {position, ahead, eta_seconds}` while queued;
  the dashboard shows it with a "paid plans skip the line" upsell (paid plans
  do dispatch first: `PLAN_PRIORITY`).

### Paid proxy accounting (`cloud/proxy_ledger.py`)

Downloads go direct → static ISP proxies (flat rate) → DataImpulse (per GB),
and the duration probe (`cloud/metering.probe_url_minutes`) follows the same
order, with one extra free step before any per-GB attempt: the fallback
clients through a static (`fallback-static`). **The client list is explicit
and shared** (`yt_clients.py`: `default,mweb` + the bgutil PO token
provider): with account cookies yt-dlp's own defaults are `tv_downgraded` +
`web`, and on a share of videos both come back UNPLAYABLE / SABR-only, which
yt-dlp reports as "Video unavailable". That was mistaken for an IP ban for a
week (it happened on every static IP too) and fed ~26 downloads a week to
the per-GB proxy, which then fetched 360p through the same dead list.
Measured in the prod container on 6-sep-2026, same static, same video:
cookies + defaults → unavailable; cookies + `default,mweb` → 1080p; no
cookies → 1080p. `mweb` needs the PO token, and the token needs the
webpage: never put `player_skip: webpage` back. A fallback attempt runs
anonymously when an HD attempt already failed with the cookies on that
route, and every attempt asks for the 1080p format spec (the old
`best[ext=mp4]` fallback spec was itself the 360p progressive file).
Two rules keep the per-GB proxy at zero on a normal day: the probe
reaches it **only** when a static route failed for a reason another IP can
fix (`static_failure_warrants_paid`: bot-check, 403/429, proxy/network
errors), never for a private/removed/members-only video, an uploader's
country block (the residential pool failed identically in 5 of 6 paid
probes, 3-5 sep) or a live stream
with no duration (those failed the same on every IP and used to cost ~1.7 MB
× 2 extractors each), and **never for a non-YouTube URL** (the download
plan already excluded those; Twitch, Kick, Rumble and product pages were
reaching it through the probe). The probe also carries `YOUTUBE_COOKIES`,
like the download does: an anonymous probe from the static IPs gets "Sign in
to confirm you're not a bot" in bursts (4-sep-2026: ~10 probes in one hour,
1.8 MB each on the per-GB proxy) because a datacenter IP's anonymous rate
limit is low and we make ~400 YouTube hits a day from three of them, while
the authenticated download sails through the same IPs. But the **first**
attempt on a route carries them and the second drops them, on the probe as
on the download: with the cookies attached YouTube answers UNPLAYABLE for
every client (`web_embedded`, `tv_downgraded`, `web` **and** `mweb`) on a
share of videos, which yt-dlp reports as "Video unavailable" (9-sep-2026,
same video on all three statics; anonymous on the same IP → 1080p 137+140).
Without that anonymous second attempt the probe read a cookie problem as an
IP problem and escalated to the per-GB proxy, which carries the same cookies
and fails identically, while the download recovered for free on the same
static. `main.py` prints `PROXY_ROUTE=<json>` after
every download (winner, paid bytes across all attempts including failed
paid ones, each free attempt's error); `app.py` persists it as a
`proxy_usage` row at job end and pages Telegram when the paid proxy carried
bytes, folding a burst into one message per 5 min. The in-memory monthly
counter and the container log (rotates within the hour) cannot answer "what
cost $14 on the 28th"; the table can. Both the probe and the download pass `noplaylist`: a
`watch?v=X&list=...` or mix link is the one video the user was watching,
and without it yt-dlp walks the whole list, dies on its first private /
age-gated / bot-checked entry (a video nobody pasted), the probe reads
that as an IP problem and pays the proxy to walk the same list again, and
the user gets a 400 for a valid link (26 of the 37 paid probes between
7 and 17-sep-2026). And the probe keeps **every** attempt's error per
static route, not the last one: the anonymous retry ends in a bot-check
by design, and a "confirm your age" from the cookie attempt is the
verdict, so it must not be overwritten into an escalation. A URL that is
not one video is refused by path before any request
(`yt_clients.youtube_non_video_reason`): `noplaylist` does nothing for
those and yt-dlp walks them entry by entry (one search URL held the
probe thread for 37 min in the prod container). That check is an
**allowlist** of the paths that carry a video id, not a list of the bad
ones: while it named the pages it knew, a hashtag page and the legacy
`/<vanity>` channel URL went straight through, and one of them walked to
page 23 on the static pool and then paid the per-GB proxy to walk it
again (20-sep-2026).
Since 30-sep-2026 YouTube answers the bot-check to anonymous requests
from every one of our non-residential IPs (the 3 statics and the server's
own IP alike), **per video**: the same video fails on all of them and a few
popular ones pass on all of them, whatever the client (web, mweb, ios,
android_vr, tv, web_embedded, with or without a player PO token). Only an
authenticated session or a residential IP gets through. So when the probe
saw every static bot-checked and the paid proxy answer, the job carries
`DOWNLOAD_SKIP_STATICS=1` (`metering.pop_statics_bot_checked`, also in the
resume manifest) and `plan_download_attempts` goes straight to the paid
attempts instead of repeating four anonymous hits for the same verdict.
The proxy watcher also checks the ytcfg `LOGGED_IN` marker when
`YOUTUBE_COOKIES` is set and pages on the first probe that says the session
is gone. `PAID_PROXY_DAILY_MB` (default
500) is the hard ceiling: past it the paid proxy is dropped from the probe
and from every new job's env until UTC midnight. The watcher probes the
static pool against a real YouTube watch page (playable markers), not
google.com — the 28th happened because YouTube refused the static IPs while
google kept answering 204. On the dev Mac, do not keep
`PROXY_URL` in `.env`: every local `main.py` run then bills DataImpulse.

### Deploys and running jobs (handover + drain)

Every push to `main` redeploys the API container. Coolify starts the NEW
container before stopping the old one (rolling update) and both share
`output/`, so `app.py` coordinates them instead of relying on a fast swap:

- Each instance writes its id to `output/.instance` at startup. An instance
  that sees another id there is the old one and **drains**: it finishes the
  jobs it is running, starts none, and leaves queued manifests on disk.
- A running job heartbeats its `.resume.json` every 10 s. The resume scan
  (startup + every 30 s) re-enqueues only manifests nobody heartbeated for
  60 s, so no job runs twice and none is lost. Max 2 resume attempts.
- SIGTERM (`docker stop`) drains too, up to `DRAIN_TIMEOUT_SECONDS` (840),
  then hands the signal to uvicorn. The app's Coolify stop grace period is
  900 s (`application_settings.stop_grace_period`); keep the timeout below it.
  After the drain hands the signal to uvicorn, `--timeout-graceful-shutdown 15`
  (Dockerfile) caps the wait for in-flight connections: uvicorn's default is
  unbounded, and one open range download kept a drained container alive for
  the full grace period while Traefik still routed half the traffic to its
  closed port.
- `/health/ready` + the Dockerfile `HEALTHCHECK` are what keep Traefik off a
  dying container: its docker provider only routes to `healthy` containers,
  so an instance answers 503 from the moment it gets SIGTERM (out of rotation
  within ~10 s, socket still open) and a booting one gets no traffic until it
  answers. Only SIGTERM flips it, not the marker drain: at that point the new
  container is still booting and nobody else would be routable. The Coolify
  app has its health check enabled on that path so it waits for the new
  container to be `healthy` before stopping the old one. With that option on,
  Coolify replaces the Dockerfile HEALTHCHECK with its own curl/wget command
  AND its own interval/retries (5 s × 3), so the image must ship `curl` or
  every deploy rolls back as unhealthy, and a stopping container takes 15 s
  to turn `unhealthy`. That is why the drain keeps serving for
  `PROXY_DRAIN_SECONDS` (20) after the jobs are done before it hands the
  signal to uvicorn: closing the socket earlier is 502s until Traefik
  notices (measured ~60 s per deploy with retries=12 and no grace). And
  `HARD_EXIT_SECONDS` (30) after that the process is ended outright: uvicorn
  finishing does not end the interpreter while an executor thread hangs in
  a network probe, and that kept a drained container alive for the full 900 s.
  `/health` stays a plain liveness probe for the external watcher.
- `/api/status` answers from disk for a job this instance never held, so a
  poll landing on either container during the handover is fine.
- `main.py` leaves `.transcript_checkpoint.json` in the job dir so a job that
  does get re-run skips the paid transcription (download and Gemini repeat).

Before pushing, still batch small commits (tests, docs) with the next real
change: every deploy is a ~5 min build plus a handover.

## CI: a green pipeline closes the task, not the push
- After every `git push`, wait for the commit's workflow and confirm it is green: `ci-wait` (Victor's Mac) or `gh run watch $(gh run list -c $(git rev-parse HEAD) -L1 --json databaseId -q ".[0].databaseId") --exit-status`.
- If it is red: fix, push, check again. Never report the task as done with a red CI.
- Before pushing, run locally what the CI runs (lint + tests of this repo).
