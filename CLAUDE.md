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
  `state/channels/<id>/` (was output/channels), used through `youtube_account.use(account)` (a
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
  They also eat one backslash of `\\` (an ASS `\\kf` regex in a test became `\kf`, 22-oct-2026):
  anything with a backslash goes in through Write/Edit, never `cat >> file <<'EOF'`.
  Hit twice more the same night: `"\\n\\n"` in a heredoc'd patch became a real newline (a syntax
  error), and `\\b` became `\b`, which a normal Python string turns into an INVISIBLE backspace
  (U+0008) in the patched file: the regex silently matched nothing. No heredoc patch scripts at all.
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
  rewritten to match the screen. Since 29-oct-2026 exactly 3 stats (`VS_ROWS`,
  a longer table is cut and its verdict rewritten) and row lines name the
  winner with one number at most: Dhoni vs Kohli read both decimals of 4 rows,
  99 words in 45 s. Frame 0 shows the players, VS, "0 - 0" and the rows with
  "?" values that fill in as each row is spoken (it was an empty gradient).
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
- **Unattended running** (15-oct-2026, `tests/test_hardening.py`):
  - A channel job the server no longer knows, with nothing on disk
    (`_job_clips` says "missing"), fails after `LOST_AFTER` (10 min) as
    transient without a pause; it used to hold the one-job loop until the
    3 h timeout.
  - Descriptions are cut at 5,000 BYTES (`_clean_description`; an emoji is
    4), tags count +2 when they hold a space (YouTube quotes them).
  - Under `MIN_FREE_GB` (5) free no new video starts; Today says so.
  - `keep_awake.py`: SetThreadExecutionState(ES_SYSTEM_REQUIRED) while a
    job runs or an upload is in `keep_awake.task()`, only on the charger,
    called from the event loop's thread (`app._stay_awake_loop`: Windows
    ties the request to the calling thread). `powercfg /requests` needs
    admin, so it was only confirmed by the call's return value.
  - Uploads resume after a dropped connection (`_send_resuming`: PUT
    `Content-Range: bytes */size` -> 308 + Range, then the rest), waits
    `RESUME_WAITS` (~8 min in all) before failing.
  - `safe_json.py`: the channels file and each upload log keep an hourly
    `.bak` and a damaged file reads from it (a damaged file used to read as
    empty and the next write made that permanent). Tokens get no copy.
    On Windows a PermissionError is a BUSY file (another thread's
    os.replace), retried ~1 s on read and on replace and never read as
    damage: the hour-old backup would list uploaded videos as waiting again.
  - Review hold on the phone: the Telegram note carries a "Skip this video"
    button (`telegram_notify.poll` -> `my_channels.telegram_press`), polled
    at the top of the tick, before any upload. getUpdates' allowed_updates
    is remembered by Telegram, so connect() and poll() name the same list.
  - A failed thumbnail or a skipped/failed caption track is copied to
    `state/channels/<id>/retry/` and tried again with each learn pass
    (`retry_extras`, 4 tries, 7 days); thumbnails wait while YouTube says
    the channel is not verified (`long_uploads` "eligible"/"disallowed").
  - Reminders, the evening summary and the Sunday week report
    (`reminders.week_text`) also go to Telegram when it is connected
    (`phone`, Today tab).
- **English subtitles for Urdu long videos** (`history_videos.translate_srt`,
  `HISTORY_EN_CAPTIONS=0` off): captions.srt joined back into SENTENCES,
  translated 40 per call with their numbers, each timed from its first word
  to its last (a piece's time shared by word length) and split into even
  pieces of up to 84 characters. Translated piece by piece on the real Rome
  script the English drifted a line late and once carried the model's own
  note ("the line cuts off here"); asked for 60 lines at once the model
  dropped 1-3, so missing numbers are asked again. Uploaded as a second
  track (`captions_extra`, row key `captions_en`). The note filter (`_META`)
  matches only note-shaped text: narration says "translated" and "cut off
  the water" too.
- **Stale news is skipped** (`my_channels.stale`): a waiting "match" video
  older than 48 h, or a "today" Short past its own date, is marked skipped
  instead of uploaded (samples made days before a channel is connected,
  the upload limit, a review hold). Quizzes, facts, history and songs keep.
- **First day with all six channels connected** (18-oct-2026, `tests/test_placement.py`):
  - The cricket card was first connected to the music channel by mistake; its
    waiting Short went up there within a minute and the next one was made with
    `@bytebeatsmusic-t5p` on its end card. Now a fresh connection makes and
    uploads nothing for `CONNECT_HOLD` (15 min, Today says so), each job keeps
    the `yt_channel` it was made for (`upload_waiting` refuses it on another
    channel and puts its topic back in the ideas), upload rows keep
    `yt_channel`, and `check_placement` (after a connect and each learn pass,
    read-only) finds a card's uploads public or scheduled on another of our
    channels; Today links them in Studio. It never changes or deletes them.
  - `app._job_reason` read only `RuntimeError:`-style lines, so
    `httpx.ConnectError` / `ServerError: 503` failures read "the job failed"
    and `TRANSIENT` never paused for an outage. Any `...Error:` line counts now.
  - A DNS outage left a quiz with 2 of 10 voice lines and no SEO copy, and it
    went up (QA heard the music bed). `short_kit.voice_all` retries the failed
    lines once and fails the job; `seo_or_fail` likewise; `upload_waiting`
    never posts an empty description. Messages say "network" for TRANSIENT.
  - Titles are one line (`youtube_account._clean_title`): YouTube kept
    "... \n#shorts" as written.
  - Every copy of the app on the laptop has the same INSTANCE_ID, so the
    resume scan of a second copy (test_mcp_stdio's subprocess) re-ran the
    server's RUNNING job in its folder. Self-host now leaves any manifest with
    a fresh heartbeat alone and drops `--generate` manifests instead of
    resuming them (their genre/topic env is not in the manifest: a controversy
    job came back as cricket with no topic). test_mcp_stdio itself fails on
    this Windows Python (asyncio stdin pipe, WinError 6) before and after.
  - **The 24 h job sweep deleted output/channels** (04:0x): it treated every
    folder in output/ except thumbnails as a job, and channels/ itself only
    changes when a channel is added. Five tokens, upload logs and engage.json
    files went; the owner had to reconnect. Both sweeps now touch only uuid4
    job folders (`app._is_job_dir`). Upload logs were rebuilt from the job
    records in .my_channels.json (`rebuilt` on each row). engage reuses a
    playlist of the same title and skips videos already in it, and never
    posts a second first comment (`_ours_on`), so a lost engage.json is safe.
  - Channel files now live in `state/channels/` (gitignored), outside the
    scratch output/ folder; `my_channels.move_old_folder` moves an old
    output/channels at startup. **test_a_second_copy_of_the_app enters the
    real lifespan with AUTOPILOT_LOCAL=1**, and the move carried the real
    folder into the test's redirected CHANNELS_DIR (recovered from the pytest
    temp dir): startup code must do nothing to real files when a path is
    redirected (`_REAL_CHANNELS_DIR` check).
  - Each card remembers its YouTube channel in .my_channels.json
    (`yt_channel`, `yt_title`, set on connect, cleared by disconnect):
    `wrong_pick` refuses another channel on reconnect. "connect all channels"
    (`/api/youtube/connect-all`) walks every unconnected card: a page names
    the channel to pick, Google, then the callback (`chain` in the sign-in
    state) goes on to the next.
  - A connection Google cancels (`invalid_grant` on refresh, never a
    network error or 5xx) is marked `dead` in its token: status() reads it
    as not connected (Today, reminders, connect all), and
    `reminders.connection_lost` tells the owner once (toast + Telegram).
  - Tareekh History is not phone-verified (owner has no spare number): long
    videos stay at 14 min and custom thumbnails fail; YouTube picks a frame.
- **Glamour** (owner, 19-oct-2026: "the videos have no ladies factor"; `tests/test_glamour.py`).
  Classy, never suggestive: YouTube age-restricts sexually suggestive Shorts and leaves them out
  of the Shorts feed, and real women are never edited, AI-made or sexualised.
  - Songs: `music_shorts.pick_theme` takes a love/heartbreak theme 75% of the time,
    `FEMALE_SHARE` (65%) are sung by a woman (`MUSIC_VOCAL`), two romance styles, and the
    footage rule welcomes an unnamed stock model as the song's character.
  - Quiz format `stars` ("PEHCHANO"): four famous women of one group (`STARS`: Pakistani,
    Bollywood, Hollywood; only Wikipedia titles whose lead photo has a free licence, 70 of 93
    tried), `player_photo` kind `star` (the article must say actress/model/singer and the photo
    must be filed under exactly that title: the photo is the answer). Facts go through a Google
    Search check (`_checked_facts`); credits are numbered, not named, so the description does
    not give the answers away.
  - Controversy: half the ideas about famous women. RULES now also refuse leaked private
    photos/videos and rumours about anyone's body, looks, surgery, love life or pregnancy: the
    first planner run with the women hint offered "cosmetic surgery rumors".
  - History: one idea in three a famous woman of history (never a woman of the Prophet's family).
  - Punchline Bazaar unchanged: CC searches for female comedians found only reaction re-uploads.
- **Trending explainers on the long channel** (`trend_explainer.py`, card setting `mode`
  "explainer", `HISTORY_MODE`, `tests/test_explainer.py`; owner, 21-oct-2026: six 8-10 min
  history videos had 0 views each). A scan that day of the month's most viewed Urdu/Hindi long
  videos: current-affairs explainers 1-3M (Abhi and Niyu, Ankit Inspires India), history far
  behind, Pakistan economy ~40k. history_videos keeps the whole pipeline; the mode swaps the
  planner (RIVALS' latest uploads + this week's top explainers + grounded news, specific English
  topics, half of them on a story a rival is riding), research prompts (claims labelled
  CONFIRMED/REPORTED/ALLEGED/OPINION), rules (no Pakistani/Indian party politics, no criticism of
  Pakistan's army or courts), footage rule, description and engage texts (`engage_kind`).
  - Keywords: YouTube's own suggestions (`suggestqueries`, client=firefox, no key) for 3 phrases
    a model writes; seeds guessed from capitalised words were junk ("solved past paper").
  - Rivals are studied, never copied: the top 3 videos' captions go to one call that describes
    their angles in English; the script writer never sees their words, and `copied_runs` (8 words
    in a row) forces a rewrite, then refuses the video. Searching with the whole Hinglish topic
    found no videos; the short phrases did.
  - Ideas carry `at` and go stale after `IDEA_HOURS` (36); owner ideas stay. Switching the mode
    clears the planned ideas; "Aaj ki tareekh" is off in explainer mode.
  - World Affairs by Unacademy, StudyIQ IAS, Adda247 Skills and Nitish Rajput answer "This
    channel is not available" from Pakistan, so they are not in RIVALS.
- **Quran channel** (`quran_videos.py`, channel kind `quran`, `tests/test_quran.py`; owner,
  22-oct-2026). Nothing in the Quran comes from a model: a real qari's per-ayah recordings, the
  Uthmani text and published translations, all from the Quran Foundation API (api.quran.com v4,
  no key; its developer terms allow social videos with credit). Tanzil's translation files say
  non-commercial only; alquran.cloud's audio terms too. AI recitation was refused: Dar al-Ifta
  (fatwa 8874, Jan 2026) accepts it only after a full review by the Mushaf authority. The AI
  voice reads only the translation after each ayah; no music.
  - Urdu default Junagarhi (died 1941, public domain); Jalandhari offered, its copyright status
    not confirmed. English Pickthall (1930). Junagarhi's text writes "والا" with U+FEFB, which
    Noto Nastaliq lacks: a fallback font drew a big "لا" in every line (`_plain_forms`).
  - Per-ayah files of x:1 have no Bismillah (Whisper on 2:1 heard "Alif Lam Mim"); 1:1 is played
    first where `bismillah_pre` says so (not Al-Fatiha, not At-Tawbah, not a later part).
  - `plan_next`: whole ayat, ~225 s, never past 300 s, ends on a ruku after the target; short
    whole surahs share a video, parts never do. Popular surahs first (`POPULAR`), then 1-114.
    A failed passage is made again first (`_quran_payload`, 3 tries); "Up next" takes
    "Surah Yaseen", "36", "2:255", "2:1-20", "Ayat ul Kursi" (`parse_request`).
  - Fonts `fonts/AmiriQuran-Regular.ttf`, `fonts/NotoNastaliqUrdu.ttf` (OFL, from google/fonts);
    ffmpeg's libass has harfbuzz, so Arabic joins. U+06DD + digits does NOT enclose the number in
    libass (digits sit beside it): the ornament and the number are two events at one point.
  - A starry-night clip under the darkening read as 12 s of black and video_qa refused the
    video: no night terms, black@0.32, and `too_dark` redoes a shot with video_qa's detector.
  - The card has `story` off: no teasers, no "Aaj ki tareekh", no minutes/lang; auto replies and
    cross promotion are off, and `promo_targets`/`promote` never mix it with other channels.
- **AI singer** (`ai_influencer.py`, songs channel, `tests/test_influencer.py`; owner,
  22-oct-2026). One fictional woman (`python ai_influencer.py looks` / `pick <file> <name>`,
  state/influencer/), a new Gemini still per song, a free vertical dance clip (Pixabay has only
  ~14 usable; a Pexels key adds many), fal.ai Wan 2.2 Animate "move" ($0.04/s at 480p, billed per
  16 frames, so clips go up at 16 fps). Use fal's returned status/response URLs (the full model
  path answers 405) and check `error` on COMPLETED. Off until `FAL_KEY` is in .env (read fresh)
  and a character is picked; `DAILY_MAX` 2 a day; a failure keeps the song's stock footage.
  The 31-thumbnail pick call chose line-art girls twice even with "never a cartoon" in its rule;
  each pick now gets its own yes/no `filmed()` call (10 of 10 right on known clips, 22-oct-2026).
- **Quality pass** (22-oct-2026, `tests/test_quality.py`; owner: ~1,200 views a week on six channels).
  Our numbers: median watch 2 s (songs), 7 s (quiz), 10 s (cricket), 19 s (controversy); 8 uploads
  a day per new channel, 51 refused at the daily limit. Every channel in these niches with a median
  over 40k posts 0.2-2.1 a day, breakouts are same-day stories, Shorts 20-40 s.
  - Shorts channels default to 2 a day at busy PKT hours (`KINDS` times); the live cards were set too.
  - `trends.searches` reads Google Trends' daily RSS (`trending/rss?geo=PK|IN`, free, headlines
    included, 1 h cache); `searches_hint` goes into the cricket, controversy and explainer planners
    with "a same-day story for this channel comes first". pytrends is dead (archived Apr 2025).
  - Cricket and controversy scripts aim at 30-35 s (fewer, shorter lines); a match Short opened
    "Namaste dosto ... swagat hai": the intro line is now the hook, never a greeting.
  - Quiz titles open on the challenge, "| Quiz #N" goes last (30 of 37 opened "Quiz #N:"). Format
    `islamic` (Urdu GK Shorts median 0.8-3k views, "quran urdu quiz" 16.5k): `ISLAMIC_RULE`
    replaces the prompt's "nothing about religion" (undisputed facts only, no fiqh, sects or
    ranking companions, honorifics), no people in its footage.
  - Songs start on the chorus, ~32 s (`SHORT_SONG`), 0.15 s fade (the 1.2 s fade made the first
    second -26 dB); titles may lead with the AI reveal ("This AI song hits too hard"), which is true.
  - YouTube (help pages, 2025-26): views count every start and replay; only 3 hashtags show; Shorts
    custom thumbnails are YPP + desktop only; the Oct 2026 originality update gives aggregating /
    re-upload channels "less distribution" (the comedy channel's model).
  - `.env` `GEMINI_IMAGE_MODEL` is `gemini-nano-banana-2.1` (the named successor of
    gemini-3.1-flash-image, half the price; tested with our generate_content call).
- Research agents that ran ~250 yt-dlp calls in parallel got this laptop's IP the "Sign in to
  confirm you're not a bot" answer (22-oct-2026), which the pipeline's own yt-dlp shares: never fan
  out yt-dlp from an agent; use web search, or a few calls in a row.
- The Write tool turns `\uXXXX` written in a file into the literal character (invisible U+FEFF,
  RTL letters in regex classes): write `chr()` or fix the escapes after (a patch matching
  `"\\ufeff"` then fails to find it).
- The Write tool refuses a file it has not read, and a patch script run right after that
  failed Write runs the OLD file: give every patch script a new name.
- **Open-source tools live in D:\youtube\oss** (22-oct-2026), outside the repo, each in its own
  folder/venv, each clone checked with `sh ~/.git-guard/worm-guard.sh worktree` first. This laptop
  has an Intel Arc A370M (4 GB) + Iris Xe and no NVIDIA: Vulkan (ncnn) and PyTorch XPU work, CUDA-only
  tools (HeyGem, MuseTalk, LatentSync, local video models) do not.
  - `upscale.py`: Real-ESRGAN ncnn-vulkan (`REALESRGAN_EXE`), `realesr-animevideov3` x2 took an 8 s
    360p Omni Flash clip to 720p in ~60 s on both GPUs (`-g 0,1`), sharper than lanczos, close to real
    720p: 360p clips cost a third. One GPU alone took ~100 s.
  - `local_voice.py` + `omnivoice_worker.py`: OmniVoice (k2-fsa, Apache code; its audio tokenizer is
    Boson's Higgs Audio 2 community licence: commercial OK, "Built with Higgs Materials licensed from
    Boson AI USA, Inc." on an about page, expanded licence past 100k annual active users). Reads the
    lines the edge voice fails before the paid Gemini voice (short_kit.voice_lines, Quran translations);
    `VOICE_ENGINE=omni` puts it first, `LOCAL_VOICE=0` (tests) turns it off. Its own venv in
    D:\youtube\oss\OmniVoice (torch + transformers 5), one worker process per batch, HF_HUB_OFFLINE=1.
    One designed voice per gender is made once (state/voices/omni_<gender>.pt) and cloned for every
    line: a designed voice comes out different on each call. Whisper heard Urdu narration and a Quran
    line back word for word; CPU ~5.4x real time (16 steps), a cloned voice ~12x; English loanwords
    ("match", "wickets") come out bent. Its 3.1 GB model took 41 min to download here (~1.3 MB/s).
    PyTorch's Intel Arc build (D:\youtube\oss\OmniVoice\.venv-xpu, torch 2.14.1+xpu) saw no device:
    the Arc driver here is 31.0.101.4502 (2023). Point OMNIVOICE_PYTHON at it after a driver update.
  - GitHub's anonymous API (60 calls/h) runs out fast when research agents use it in parallel.
  - Real-ESRGAN on history STILLS was tried and dropped: realesrgan-x4plus took 164 s for one 800 px
    picture, and animevideov3 makes photos look painted.
  - `parallax.py`: Depth Anything V2 SMALL (Apache; Base/Large are CC-BY-NC) ONNX in
    D:\youtube\oss\models, one depth map per picture (~2 s CPU, cached .depth.npy), two cv2.remap per
    frame (~45 ms at 1080p), piped to ffmpeg with the shot's .ass. ~27 s per 7 s shot (a plain pan ~2.5 s).
    history_videos.segment uses it for every panned picture; any failure keeps the plain pan. PARALLAX=0.
  - `player_photo.cutout_card`: IS-Net (rembg's isnet-general-use.onnx, Apache) via onnxruntime, cricket
    only (owner: no AI edits of real women, so not the stars quiz or controversy photos); kept only when
    the mask covers 8-75% and reaches the bottom edge, else the framed card. rembg's DEFAULT model is
    BRIA RMBG (non-commercial): never use it. CUTOUT=0.
- **Quality pass 2** (22-oct-2026, `tests/test_quality2.py`): an audit agent claimed most Shorts ship
  without music; wrong: channel jobs send bg_music True (my_channels payloads). Real gaps fixed:
  - Music ducks under the voice (`short_kit._final_mix`: voices -> asplit -> sidechaincompress the bed,
    bed at -24 LUFS instead of -30, alimiter on the sum; history_videos.mix too). MUSIC_DUCK=0: old mix.
  - Footage shots push in (1.00->1.08) or pull out (1/0.86->1.08) with a cosine ease via
    `scale=w='...t...':eval=frame` then a fixed crop; photos pan eased; unsharp on upscaled stock; shot
    crf 17. BROLL_MOTION=0. History: 7 s shots (was 11), eased pans, moving footage, crf 20. HISTORY_MOTION=0.
  - Generated Shorts' captions colour numbers and names (`subtitles._emphasised`, CAPTION_EMPHASIS set
    by short_kit.finish only, so comedy captions stay). Lead silence 0.15 s (was 0.5); end card capped
    at 1.5 s (`short_kit.outro_seconds`, SHORT_OUTRO_SECONDS) so Shorts loop; comedy keeps its 3 s.
  - Narrated channels' empty About texts got a description + the OmniVoice credit (`about_credit`,
    once, after a learn pass; backups in state/channels/<id>/about_backup_2026-10-22.txt).
- **Facebook / Instagram** (`meta_publish.py`, Channels tab panel, `tests/test_meta_publish.py`):
  Facebook Login for Business (resumable local upload needs it; Instagram Login needs a public URL),
  Page tokens that do not expire also drive Instagram; a Short uploaded to YouTube is copied to
  state/meta/outbox and posted at its YouTube time (`my_channels.meta_pass`, every 10 min), FB Reels
  only up to 90 s, is_ai_generated on both, DAILY_MAX 8 per account per platform. Card keys meta_page,
  meta_fb, meta_ig. Nothing queues until META_APP_ID/SECRET are in .env and the owner connects.
- **Writing craft** (`script_craft.py`, `tests/test_craft.py`, 22-oct-2026; research notes: hooks decide
  in 3 s, 2.5-3 words/s, payoff last, one-word comment questions, templated narration = YouTube's
  "inauthentic content"). `short_rules()`/`long_rules()` go after `.format` on every Short and long
  script prompt, with a banned stale-phrase list and a shape per video (`STRUCTURES`, random; a match,
  versus and controversy pass their own fixed order). Cricket stories moved from flash-lite to
  `writer_model()` (3.7-flash). `polish()` = script doctor: scores the hook, writes 5, tightens lines;
  CODE keeps a rewrite only if it keeps every number of the line, adds no number or name absent from
  the research, stays Latin and about the same length (`line_ok`; a first word counts as a name unless
  it is a common opener: "Kohli bhi hairan" slipped through before). Polish runs BEFORE controversy's
  fairness check and history_today's fact check; quizzes polish only hook/outro, versus only hook and
  question (rows say who leads and code checks that). `_scrub` gives lines still holding a banned
  phrase one targeted rewrite. POLISH=0 (conftest). First live run: "Kya aap jante hain Shaheen ne..."
  (old) -> "Sirf 31 runs dekar Rohit, Rahul aur Kohli teeno ko udaya!"; cricket topics now aim 25-30 s.
  Long videos: `polish_opening` rewrites the hook scenes (the first ~30-45 s) before the fact check,
  kept only on a 2+ point self-scored gain and per paragraph by `line_ok`. `_names` is per sentence
  (a capitalised first word counts unless it is an opener; honorifics never count). First live run
  (Constantinople, 6/10 -> 10/10, passed the fact check) turned rulers who "dreamed" of the city into a
  "sacred duty": code guards numbers and names, not claim strength. Both polish prompts now forbid
  making a claim stronger, sacred stories skip the opening polish, and a paragraph with an honorific
  (Hazrat, sallallahu, Allah, imam, nabi...) keeps the writer's wording.
- **Viral remix** (`viral_remix.py`): a viral video is studied, never copied (owner's "get the transcript
  and make our own"). Captions -> one call (`Blueprint`: angle, hook pattern, beats, devices, in its own
  words); stored by topic in state/remix/index.json so generators find it through the idea text
  (`note_for`, `guard` = 8-word copy check vs the source text, also in history's copied_runs). The topic
  goes through our own grounded research; the note says to reorder facts and add one of ours (thin
  protection of "selection and arrangement"). Up next takes a YouTube link (`add_idea`, ~16 s, in a
  thread); cricket/controversy channels study one hit a day (`my_channels._remix_first`, `remix_days`
  counts tries, never ahead of urgent/owner ideas, one rival channel once a week). YouTube search's
  "views" sort is "popularity" since Jan 2026: the week's top cricket Shorts had 1,548 views and were
  song edits, so `candidates` searches a YEAR window, drops edits/songs by title, floor 20k views, and
  reads the Shorts tabs of the 3 channels behind the results for their outliers (>= 3x the channel's
  median): first live run, best candidate 35k -> 141k views, in 10 s.
  VIRAL_REMIX=0 (conftest). Trending page is gone (Jul 2025); Playboard charts exist but were not used.
- **Real swooshes** (`sfx/`, Kenney interface pack, CC0): `kit.WHOOSH` in any Short's sfx list becomes
  a real file, rotating per card (`_voice_sfx_inputs`), at SFX_DB (-8). Picked by a Gemini listening
  pass (26 tried, kept the six 8-9/10). At -11 dB a listening pass of a finished Short called them
  "barely audible", at -5 "too loud"; -8. Both heard the music too close: ducked bed -24 -> -28 LUFS. REAL_SFX=0 = old chirp. Long
  history videos keep their own chirp.
- **Face-aware footage crops** (`faces.py`, YuNet 2023mar ONNX, MIT, D:\youtube\oss\models\yunet): the
  9:16 crop of a footage shot centres on the biggest face (~0.7 s a shot). MediaPipe's face API is
  absent from the installed version, so main.py's face_detection is None on this laptop. FACE_CROP=0.
- **Measuring it** (`reminders.craft_line`): the Sunday week report compares each channel's Shorts
  uploaded after `script_craft.SINCE` (22-oct-2026 22:00) with the month before (median views and %
  watched, 3+ counted Shorts a side, long videos left out). Before/after, not an A/B test.
- **Quiz countdowns one second shorter** (min 3): the median viewer left at 7 s, about when the first
  one starts. Judgement, not measured. **Song hook**: `SongPlan.hook` (3-7 words, POV / send-this /
  AI reveal) shows big for the first 2.6 s (`lyric_events(hook=)`, outlined): the songs channel's
  median viewer left at 2 s with only a song title and grey stock footage on screen.
- **Round 2 the same night** (owner: "do these all"):
  - A blind judge (`script_craft.judge`) decides every polish: the writer's and the polished script go
    in shuffled order, unlabelled. The opening polish's self-score said 9/10 for a rewrite that swapped a
    real question for "Yeh video dikhayegi ke...", now banned ("yeh video", "is video", "this video").
  - A/B tests on the generated channels (`my_channels.EXPERIMENTS`, `ab_stats`, `ab_winner`): the end
    card (all Shorts channels) and the quiz countdown (`quiz_timer_add` -> QUIZ_TIMER_ADD, "long" puts
    back the second cut tonight). A side wins only with 10+ counted a side, a 1.2x median lead, a
    permutation p <= 0.1 on log views (`perm_p`, no scipy) and not watched 5+ points less; Shorts before
    `AB_SINCE` (3 s card, old scripts) are left out. The first end card run: p 0.55-0.95, nothing. The
    week report has a line per test (`ab_line`).
  - Grades per channel on footage only (`broll.GRADES`, before DIM; CHANNEL_GRADE=0), history footage too.
  - Beat cuts for songs (`beats.py`, numpy spectral flux + autocorrelation tempo + Ellis DP; a fixed grid
    drifted a beat a minute; 18 ms median error on test clicks); `plan_shots(beats=)` moves each cut to
    the nearest beat within 0.35 s, never the last. BEAT_CUTS=0.
  - RIFE slow motion (`slowmo.py`, rife-ncnn-vulkan rife-v4.6 in D:\youtube\oss\rife, `-n` frame count):
    a clip shorter than its shot (1.15-4x) is stretched instead of looped; 2 s -> 4 s in 11-14 s at a
    1280 long side. SLOWMO=0.
  - Noto animated stickers (`stickers.py`, CC BY 4.0, D:\youtube\oss\noto-emoji-animation): one Gemini
    pick per Short in `cricket_shorts._finish` (cricket, controversy, history_today), code spaces them and
    blocks death/tragedy/religion/allegation lines; `render(stickers=)`; credit in the description.
    `-f webp_anim -ignore_loop 0` (stream_loop does not loop them). STICKERS=0.
  - Animated empire maps (`history_maps.py`, Cliopatria v0.2.1 CC BY 4.0 + Natural Earth 50m, caches
    in D:\youtube\oss\maps, `python history_maps.py build <zip> <land>` rebuilds them in 29 s): the long
    script's scene `map` ("Mughal Empire | 1526 | 1707") becomes that scene's first shot through
    segment_video (captions, motion, grade). `add_maps`: at most 2, history mode only, never a polity
    whose data runs past 1925 (Kashmir and modern borders; the Ottomans end 1923, the Raj 1947 is out).
    Names in brackets are composites ("(Delhi Sultanate)"). 7 s at 1080p in 7-22 s. HISTORY_MAPS=0.
  - Translated titles (`localize.py`, `youtube_account.upload(localizations=)`): Hindi (Devanagari) and
    Urdu-script title + hook sent with videos.insert (part adds "localizations", no extra quota),
    snippet.defaultLanguage "en" so the Roman Urdu title stays the default; translated descriptions put
    the original in full below the translated hook (credits stay). cricket/quiz/controversy/history
    only. Passed as a kwarg only when present (test fakes of upload have fixed signatures). LOCALIZE=0.
  - Search phrases (`cricket_shorts._search_hint`, YouTube autocomplete, no key): the topic's first 2
    and 4 words go to suggestqueries; the SEO writer (cricket, controversy, on-this-day via `_finish`),
    the history script and quizzes (`quiz_shorts.SEARCH_SEEDS` per format) hear them. TRENDS=0 off.
  - Tried and dropped: YouTube Analytics retention curves (elapsedVideoTimeRatio) came back EMPTY for
    every Short at 11-110 views; worth adding once Shorts pass a few hundred views.
  - The mix measured, not judged by ear: a real voice + Lyria bed through `mix_audio` with and without
    the bed, subtracted: music 20 dB under the voice while it speaks, -31 dBFS in the gaps. Gemini's
    "slightly too loud" at every level was a habit, not a measurement.
  - Old Windows test failures: 6 read source files without encoding (cp1252), restoring_static split a
    backslash path on "/" (fixed in the code), the fcntl ASR slot tests skip on Windows; the billing
    tests need requirements-billing.txt (installed in .venv from cp314 wheels: sqlalchemy 2.1.6 and
    asyncpg 0.32, the pins have no Python 3.14 builds; production pins unchanged).
- **First second** (23-oct-2026): engagedViews/views showed 7-17% of viewers staying past the first seconds
  on cricket and quiz. Frame 0 was an empty gradient (everything faded in) and "kisne banayi?" hooks showed
  the player's photo and name at 0.3 s. Now title, tag and picture are on frame 0 (`fade_in` 0), a hidden
  player shows as `player_photo.mystery` (blurred card, gold "?", "KAUN?") until a line names him
  (`cricket_shorts.says`/`reveal_at`), quizzes open on question 1 (QUIZ_COLD_OPEN=0 = old title card).
  `youtube_account.video_analytics` reads engagedViews (`a_views`/`engaged`, never "views": what_works
  merges rows); learn stores `stayed`; `hook_lessons` (10+ starts, 6+ Shorts, 10-point gap) goes to the
  writer and polish prompts as HOOK_LESSONS. Patch scripts: heredocs ate backslashes twice more tonight;
  build backslashes with chr(92) in a Write-tool script.
- **Title tournament** (`script_craft.pick_title`, POLISH=0 off): every generated Short (via
  `short_kit.seo_or_fail`, so never the comedy channel) and every non-sacred history/explainer video gets 5
  other title angles; `title_ok` drops any with a number or name not in the script/research, "#", "|",
  shouting words or a length outside 25-70; the blind judge must prefer a survivor (2 rounds at most). The
  tail ("#shorts #cricket", "| Quiz #12") is kept as is. Live: "Wasim Akram ka 1992 final wala spell" ->
  "Wasim Akram ne 1992 final mein England ke 3 wicket kaise liye?".
- **Wikipedia most-read** (`trends.wiki_top`, pageviews API, CC0, no key): yesterday's top English (120)
  and Hindi (30) articles go to the cricket, controversy and explainer planners (`wiki_hint`).
- **Quality pass 3** (29-oct-2026, `tests/test_quality3.py`):
  - A history job hung 4.5 h on one dead Gemini connection (10 CPU-seconds used): the genai
    client had no timeout. `short_kit.http_options()` (GEMINI_TIMEOUT, 600 s) goes on every
    generated-job client (kit.gemini, seo_copy, ai_take, caption_script); a timeout is a
    ReadTimeout that ask_json retries. my_channels' "took too long" now calls
    `app._cancel_job`, which kills the process TREE (`taskkill /T`): the venv python.exe is a
    launcher and `kill()` left main.py running in the job slot.
  - `cricket_shorts._txt` cuts between words ("7 SEPT 201", "COMMENT MEIN BAT" before);
    closing questions take 120 characters (they wrap); fact stats 16, sized by `stat_size`.
  - A Pixabay PNG cut-out cached as .jpg kept garbage colour under its transparent part
    (green/magenta streaks round a statue): `stock_media._flatten` lays any see-through photo
    on a dark ground at download (and on cache hits), `short_kit.opaque` for history pictures.
  - Stickers work on ffmpeg 8 (no webp_anim): `stickers.as_apng` converts each Noto WebP once
    to an .apng beside it (Pillow), read with `-f apng -ignore_loop 0`. STICKERS=0 is gone.
  - Quiz: the countdown has a bar draining gold to red along the card's foot (animated
    `\clip`; picture quizzes have no room for it); hook lines 3-7 words (the cold open had
    question 1 on screen while a 12-word hook delayed it, countdown at ~12 s).
  - autostart.bat sets PYTHONUNBUFFERED=1: server.log arrived in 8 KB lumps, minutes late.
- **Hypit, studied not copied** (29-oct-2026): hypit-ai/hypit cloned to D:\youtube\oss\hypit (shallow, no
  hooks; ~/.git-guard is not on this laptop). Its licence is Apache 2.0 with conditions: free for our own
  channels, but no hosted/multi-tenant service and derivatives under the same licence, which conflicts
  with this MIT repo and its cloud mode, so NO code of it is in here, only ideas from its playbooks
  (skills/hypit/references). Its engine (SVML, Node 22, 64 headless Chromium) does not fit this CPU laptop.
  - Captions grouped by meaning (`subtitles._glued`, `_TRAILING`/`_LEADING`): Urdu postpositions and
    particles stay with the word before ("Sharma ne", "35 balls par"), names and number + unit stay whole,
    a sentence end starts a new caption; up to 1.35x the width rather than split a phrase, else the phrase
    moves to the next caption whole. max_chars < 6 (one-word styles) is left as it was.
  - Cricket "top 5" countdown (`CRICKET_MODE=ranking`, idea kind `ranking`, "Top 5 ..." typed in Up next):
    a board of 5 "?" rows on frame 0, #5 revealed first, #1 last with a gold frame and a bell; rank and
    photo sit LEFT of each row's bar because render draws pictures under the text layer; "#1" in a title
    becomes "No. 1" (the title cleaner strips it as a hashtag). 45-55 spoken words, ~23 s.
    First live run (Most ODI sixes by Pakistanis, 452 s, 8 sources, all 5 photos): the hook polish and the
    title tournament both put #1 first ("Afridi ke 351 ODI chhakke..."), as they reward the most surprising
    number: `_spoils` (a word of #1's name or its number) puts the writer's hook / the countdown title back.
    No stickers on the boards (`_finish(stickers=False)` for ranking and versus): a 👇 covered row 5.
  - Viral studies carry a `timeline` (time-coded changes on screen and in sound, and what each does for
    the viewer), passed to the niche playbook and the inspiration note.
- **Quality pass 4** (29-oct-2026, `tests/test_creative_qa.py`, `tests/test_research.py`, `test_quality3.py`):
  - **Visual check before upload** (`creative_qa.py`, CREATIVE_QA=0 off, `=report` records only): after
    video_qa, one Gemini vision call sees the first frame + 12 numbered frames (Shorts sampled before
    the 1.5 s end card, whose sliding words read as "cut off"); a video is held back only when a second
    independent look calls the same defect "broken" (cut_text, overlap, boxes, garbage, empty_open;
    "unreadable" never blocks). Verdicts go to state/creative_qa.jsonl; the job keeps `look`
    ("first frame 7/10, polish 8/10"); the Sunday report has a "Looks" line per channel. Calibrated on
    real Shorts: blocked the streaky controversy cut-out and the empty versus frame 0, passed the songs
    and the ranking, missed one cut closing question (minor), no false block.
  - **Audience research**: a studied viral video's top 60 comments (Data API commentThreads, 1 unit,
    AUDIENCE_RESEARCH=0 off) go into the same watch call as data; the study keeps `audience` (what
    commenters reacted to) and `asks` (topics they asked for), never the comments. Asks of the last 14
    days reach the planners with our own viewers' requests, marked "(asked under a viral video in this
    niche)".
  - **Policy research** (web, 29-oct-2026, sources in the session): the spam policy now names "automated
    or synthetic mass-production" with the example "the exact same background music and repetitive AI
    generated imagery across many videos, each reading out an AI-generated script" (answer/2801973),
    and a termination bars the owner from all their channels (answer/2802168): one channel's strike
    risk is every channel's. Cricket, controversy and quiz had ONE music bed each under every Short:
    `kit.music_track` now picks the least recently used (music/<kind>/.used.json) and
    `music_beds.grow` adds a varied bed (VARIANTS of tempo/key/lead) about once a day per kind up to
    TARGET 12. YPP's "Generic or Repetitive Content" (answer/1311392, July 2026) makes AI personas
    posing as experts on health/legal/finance/politics non-monetizable: `script_craft.PERSONA` in
    every Short and long prompt. Realistic synthetic death/disaster is not monetizable: history AI
    pictures and AI thumbnails are "clearly a painting, never a photograph; no blood, bodies".
    AI songs already carry containsSyntheticMedia (app._job_clips). The Oct 2026 Shorts update cuts
    reach for channels that "mainly aggregate or re-upload other creators' clips" (the comedy
    channel's model); the Quran channel's recitations are "readings of material you did not create"
    for YPP. Metricool (2026) found 2-4 Shorts a week per channel performs best per Short; channels
    post 2 a day (owner's call).
- **Studio** (`studio.py`, `/api/studio/*`, dashboard tab "Studio" = `StudioTab.jsx`, `tests/test_studio.py`,
  29-oct-2026, owner: "add studio to edit video"): every channel's recent videos still on disk (first-frame
  posters), filters by channel and state (held for review / waiting / uploaded / failed / skipped), a player,
  the visual check's verdict, and edits made server-side with ffmpeg in the project's file conventions, so
  the upload needs no change (`app._canonical_clip_file` serves the newest derived file):
  - title / description / tags into the metadata's `shorts[0]` seo fields; for an uploaded video
    optionally pushed with `youtube_account.update_video` (videos.update, 51 units);
  - captions: the metadata's top-level `transcript` (clip time; `kit.finish` leaves per-clip captions out
    of `shorts`) edited line by line (same word count keeps the timings, else spread by word length) and
    burned by `python studio.py reburn <job dir>` = `main.auto_caption_clip` in a subprocess (importing
    main.py into the server is heavy) onto the newest clean cut; older `subtitled_` copies are removed;
    ~26 s for a 30 s Short;
  - trim: `recut_<ts>_<clip>.mp4` from the newest clean cut, transcript shifted, captions burned again;
  - approve (sets `approved`: `held_for_review` lets it go), skip (`my_channels.skip`), make again (skip +
    `_remake`). Any edit clears `qa`/`look`, so video_qa and creative_qa run again before upload.
  Uploaded videos keep their file (YouTube cannot swap it): only details can change. Job ids are checked
  against the uuid pattern before any path is built.
- **AI editor** (`ai_editor.py`, `/api/studio/ai/*`, `/api/studio/upload`, Studio's "Tell the AI what to change"
  box, `tests/test_ai_editor.py`; owner, 29-oct-2026: "not a generic editor... I give it a prompt and it does it").
  Researched first (open-source editors, commercial ones, papers; ideas only, no code copied): video-use (MIT)
  edit list + no cut inside a word + 30 ms fades + captions last + a frame checker; ai-video-editor (MIT)
  revisions that never overwrite the input; Director: the model quotes words, code finds their times.
  - One Gemini call (writer model; `AI_EDIT_MODEL`) turns the words into ops from a CLOSED list (`OPS`: cut,
    keep, tighten, speed, zoom, text, caption_fix/style/captions/translate, music, volume, look, broll, title,
    description, tags, remake, reframe). It sees an edit sheet (status, title, credits, edits so far, the
    spoken words with times as the video is NOW) and, for Shorts (<= 180 s), watches a 360 px 10 fps proxy
    (`proxy`, ~0.3 MB): the full 10-18 MB file sent inline had its connection reset on the first live run.
  - Code resolves (`resolve`): quotes -> word times (`find_quote`, one word off allowed), cuts snapped into
    word gaps (`_snap`), values clamped, ops impossible for this video refused with a reason (already on
    YouTube: details only; music baked into an old Short: cannot be removed). Ops are stored in BASE time
    and every revision re-renders from the original clean cut (`Timeline` maps base <-> output through cuts
    and speed): no quality loss over many edits. Captions are re-burned last from the base transcript with
    fixes / translation (cached per language) and the owner's style; sound levelled (`kit.level`).
  - A before/after frame sheet + the request go to one vision call (`check`); a "not done" earns one re-plan
    (`MAX_PASSES` 2). Results say what was assumed, refused and found. Live run on a real cricket Short
    (upload): cut 1 s, yellow captions, zoom on "record" in 2 passes, 257 s; the check rightly reported the
    captions over the video's own burned-in cards.
  - One encode per pass: the captions are an .ass file (`caption_ass`) drawn last inside `render`'s graph.
    The separate burn (preset medium) was about half of every pass and a second generation on the picture;
    the same 27 s edit now renders with its captions in 29 s. Each stage line in edits/edit.log is timed.
  - Revisions live in `<job>/edits/` (state.json, r<n>/final.mp4); the current one is published as
    `subtitled_<ts>_ai<n>_<clip>.mp4` (newest derived file = what plays and uploads); undo/redo republishes
    (`restore`), the metadata (transcript, seo fields) restored with it. A manual Studio edit starts a new
    chain (`ensure_base`). Runs as `python ai_editor.py apply <job>` (server: `_ai_edits`, `_ai_edit_done`
    re-checks QA, pushes details for a live video, remakes with notes). While it runs the job has
    `editing_until` and `upload_waiting` skips it, urgent or not.
  - New Shorts keep their voices without the bed (`short_kit.stem_path`, `KEEP_STEMS=0` off) so "change the
    music" swaps the bed (mood beds made by Lyria into `music/mood_<words>/`, reused); "remake" sends the
    topic back with the owner's notes (`_remake(notes)` -> idea `notes` -> payload `owner_notes` ->
    `OWNER_NOTES` -> `script_craft.owner_notes()` in every Short/long prompt).
  - Uploads: the owner's own video becomes a Studio job (`create_upload`, genre `studio_upload`, kept 7 days
    via `.source.json` `keep_until`, listed from `state/studio_uploads.json`), transcribed by
    `transcribe_backends` in a subprocess. **`app._queue_clips` skips `studio_upload`**: without it the main
    channel's auto-poster would have published the owner's upload.
- **Quality pass 5** (29-oct-2026, research + measurement):
  - **Gemini TTS migration**: `gemini-2.5-flash-preview-tts` and `3.1-flash-tts-preview` shut down 17-nov-2026
    (deprecations page). `ai_take.speak` now tries `gemini-3.8-flash-tts` / `-lite` first through the
    Interactions API with the delivery in a `speech_metadata` style note (3.8 reads `text` verbatim: the old
    call wrote the instruction into the text, which is why 3.8 read it aloud on 8-oct). Whisper + Gemini heard
    a Roman Urdu take, a cricket line, an Urdu-script Quran line and English word for word.
  - **Loudness**: whole Shorts measured -15 to -16 LUFS (voice lines are levelled, the pauses and bed are not)
    and a Lyria song -10 LUFS with its true peak at 0.0 dBFS. `short_kit.level` = one ebur128 pass, one static
    gain to -14 LUFS never past -2 dBTP, picture copied; after every render with a lead (voices or a song),
    and on long history films. Cricket -15.4 -> -14.0, song -9.5 -> -14.1.
  - **Colour**: renders took full-range BT.601 from JPEG photos/footage ("yuvj420p, bt470bg") or no tags.
    `short_kit.TO_BT709` (+ `setparams`: ffmpeg 8 takes primaries/transfer from the frames, not from output
    options) and `BT709_TAGS`: limited-range BT.709, tags survive the caption burn.
  - **Captions sit under YouTube's own overlay** on phones (glyphs at y 1480-1660 of 1920, the title/handle
    band; right end into the button column x > 888): moved with the card geometry, see **Look pass** below.
- **Safety from studying two automation repos** (29-oct-2026; darkzOGx/youtube-automation-agent and
  raunakpatil/youtube-agentic-ai-studio, both MIT, ideas only):
  - Edited descriptions keep every credit block (`studio.keep_credits` / `credit_blocks`, `CREDIT_START`):
    CC BY credits, Commons pictures, maps, stickers, stock footage, sources, Quran.com. Used by the manual save
    and the AI editor; the body is cut, never the credits, at 5,000 bytes.
  - No duplicate uploads: an upload whose end we never heard is `unknown` (session URL + size kept), and the
    next `youtube_account.upload` of that file asks the session first (`_unfinished`): done -> that video id,
    partial -> resumed, expired -> a fresh upload; still offline -> stays unknown, nothing new sent.
  - Auto replies: comments are data, replies use only facts from the title or the comment, and a comment
    saying a fact is wrong gets no reply (`Reply.correction`, `engage.corrections`, shown on Today).
  - Same-age views: `learn` keeps `views_48h` (first pass at 48-72 h); format picks, A/B tests, the hour tip
    and best/worst lists compare it; Today's median stays lifetime views.
- The desktop sidebar scrolls (`App.jsx` nav `min-h-0 overflow-y-auto`): inside the overflow-hidden shell
  the last tabs were cut off on a laptop screen (owner, 29-oct-2026); checked by a CDP mouse wheel at 600 px.
- **Look pass** (29-oct-2026, `tests/test_look.py`; owner: the videos "are not that good"):
  - **Captions out of YouTube's overlay.** Real Shorts had caption glyphs at y 1500-1650 (1876 when a block
    wrapped), under the title/channel/subscribe row that covers a phone's bottom quarter, and lines to x 1022,
    under the like/comment column (x > 888). Generated Shorts caption with `subtitles.SHORTS_CAPTION_STYLE`
    (`auto_caption_style()`: where CAPTION_EMPHASIS=1, i.e. short_kit.finish and studio's reburn; CAPTION_SAFE=0
    off; comedy untouched): font 38, ONE line inside x 48-888 (`box`), centred on 540 when it fits 192-888, else
    moved left just enough (per-event margins). Blocks are cut by measured width, the pop included (`text_px`:
    libass sizes a font by OS/2 usWinAscent+usWinDescent, 1.73 em for Anton, not PIL's hhea metrics), so
    libass never wraps one; a lone too-wide word is drawn smaller on the same baseline. `CAPTION_TOP_PX` 1430
    -> 1206: over every frame of a long track drawn by libass the glyphs (outline in) stay in y 1238-1433,
    x 65-880. Centred 192-888 at font 40 came first: "MAXWELL T20I" needs 777 px, captions went one word a time.
  - Above them everything ends by `cricket_shorts.BOARD_END` 1232: fact card 790 -> 672 tall, versus rows from
    970, ranking rows 613 + 140k with values ending at x 876 (they sat under the like button), the opening photo
    card at 88% centred 800 with its name pill across its bottom edge, a hidden player's name on the card's foot.
    Stickers moved to the top-left corner (y 1290 is the caption band now and cards draw over stickers). Song
    lyrics wrap inside x 192-888 (event margins), the follow line at 1400 (was 1640). Quiz was already clear.
  - **Cricket footage that passes.** 40 of 46 cricket renders kept the gradient (server.log): the libraries hold
    little cricket and the rule allowed cricket only. `stock_media.pool(kind)` (POOL_TERMS, cricket only): 7 broad
    searches once a day through `search()` (its cache, rests, caps), kept 7 days, each clip tagged once by a
    vision call that also reads its library tags / file name (kind / atmosphere / reject); other sports and the
    insect are rejected in code first (POOL_NEVER), flags, text on shirts, named players and paintings by the
    prompt. The picker sees 10 pool clips as "general" for every line; lines still empty get unused pool clips
    (used longest ago first) before the 50% floor drops the footage. CRICKET_FOOTAGE takes neutral atmosphere
    (lights, crowds, grass, trophies), never another sport. Same lines of two real cricket Shorts: old step 1/5
    and 0/7 (both stayed on the gradient), new 5/5 and 7/7 (4 and 5 from the pool). With only a Pixabay key
    the pool is mostly photos: 2 of 33 videos passed (insects, soccer, bats, streets); a Pexels key would add
    portrait video. The pool alone may take landscape 4K cropped to 9:16 (1215x2160, never enlarged), only
    files Pixabay says are <= STOCK_CROP_MB (25): its 4K ran 1.7-148 MB, downloads here 50 KB/s that night.
  - Candidates are full HD first (720p only to fill), only enlarged clips are sharpened (`broll.upscaled`),
    and a line without a clip borrows the least-used clip, not its neighbour's (`broll.borrow`; was a,a,a,b,b).
  - **Footage that shows.** Over footage the fact cards are glass: `cricket_shorts.panel` names the panel
    "frost x y w h r", `_finish` sends `frost_boxes(events)` to broll, which blurs the footage under each card
    inside the shot encode (boxblur through a rounded mask, clearing in as the card lands), and `glass()` makes
    the panel 54% opaque (was 81%). `broll.DIM` -0.10 -> -0.04; the title and small labels get a dark outline
    over footage (`outlined`: the title nearly vanished on a white trophy photo). The gradient look is unchanged.
  - Captions: "Dr.", "vs.", "etc.", initials ("M.S.") and "No." before a number no longer end a caption
    (`subtitles._ends_sentence`; the name after "Dr." gets its colour too), and the active word's pop settles
    back to 100% (`\t(110,200,...)`; it stayed at 108% while the word was said).
- **Title ideas in Studio** (`POST /api/studio/video/{id}/titles`, declared before `{action}`, which would take
  "titles"): `studio.title_options` = the title tournament's contenders that pass `title_ok`
  (`script_craft.title_options`, also used by `pick_title`) + YouTube autocomplete for the topic's first 2 and 4
  words; chips fill the title, search phrases add a tag, nothing saves until "save". A live checklist under the
  fields: title 25-70 characters, no shouting words, description 150+ words, at most 15 hashtags (past that
  YouTube ignores them all), tags within 500 characters.
- **Money channel in motion graphics** (`money_shorts.py`, `motion_scenes.py`, channel kind / genre `money`,
  `tests/test_money.py`; owner, 29-oct-2026: "research the most viral content of a niche, script it, make
  motion graphics and voice it"). Research that day: money told as stories (prices then and now, salaries at
  home and in the Gulf, company blunders, who earns what) leads the narrated viral Shorts with a number in the
  title and first line; finance has the highest ad rates; no faceless Roman-Urdu channel does it. YPP does not
  monetise "content that looks like it's made with a template": every video is its own researched story, the
  templates only draw it, a colour set per topic (`palette_for`) and a writing shape per video.
  - Drawn as ASS vector events through `short_kit.render`, like the cricket boards: libass drew a frame of 10
    growing bars + a counter in 34 ms here, Pillow anti-aliased 656 ms, matplotlib 486 ms; headless-browser
    renderers do worst on this CPU (and Remotion's licence does not fit MIT). Templates: `big_number` (count-up,
    a comparison and code's ratio), `versus` (bars from the foot, code picks the winner), `bars`, `timeline`
    (area + line revealed by an animated `\clip`), `list` (#n..#1, a bell on #1), `grid` (out of 100), `fact`
    (a stamp). Hook number + hook words on frame 0, the biggest number last under turning rays, a source line
    per scene. Everything ends above `cricket_shorts.BOARD_END`. Drawings start at (0, 0) and are placed by
    their box: libass aligns a drawing by its bounding box. A waiting bar at 1% width showed as a sliver: a bar
    appears when it starts to grow. Flags (`flags.fetch`, public domain) are pictures, drawn UNDER every ASS
    layer, so no track or panel sits over a flag's spot. 44 s of all templates rendered in 45 s.
  - The number gate (`validate`): every number on screen and in the voice must be in the grounded research
    (`figures` reads "2.3 arab"/"$2.3B"/"1,20,000"; a scaled number matches only as scaled, so "23 crore" is
    not supported by some 23 percent; "$38B" is an honest rounding of $38.3 billion); ratios, changes and gaps
    between years come from code (`derived`, only from numbers that passed). A scene is dropped when its items
    are not one measure in one currency (`motion_scenes.comparable`: never Rs against AED, never Pakistani
    against Indian rupees; a first preview called Rs 45,000 vs AED 2,500 "18x"). Then one fact-check call (net
    worth told as income, an old price as today's); one rewrite with the notes, then no video.
  - Pure motion graphics: the job sets `STOCK_FOOTAGE=0` in its own process. Beds: `music_beds` kind "money".
    Wired into my_channels (planner, end-card A/B, About text), engage (comments, replies that never give
    advice: `MONEY_EXTRA`), niche_research / trends / viral_remix queries, localize, category 27.
- **An outage no longer loses a planned idea**: a planned idea leaves the queue when its job starts, so a job
  that failed on the network, the quota or a server restart (`transient`), or never started, lost its topic: an
  urgent match result, the owner's own idea, one part of a history series. Jobs keep their `idea` and
  `my_channels._requeue` puts it back after any urgent ideas, at most `REQUEUE_MAX` (2) times. A long video's
  next try also skips what the failed one paid for: `history_videos` keeps the researched, fact-checked and
  titled script in `state/resume/<hash of topic, minutes, language, mode, series, owner notes>.json` for
  `RESUME_HOURS` (48) and starts at the voice; a finished video deletes it, so "make again" writes anew.
- **Cricket birthdays**: the planner may plan "<player>'s birthday" for a
  player born today; `cricket_shorts.birthday_ok` keeps it only when the
  Wikipedia intro's "(born 15 October 1994)" matches (`player_photo.born`).
  First real run: Babar Azam and Umar Gul, both right.
- Read for real on Punchline Bazaar (15-oct-2026): channels.list
  `longUploadsStatus` answered "eligible" (= not phone-verified yet) and
  Analytics gave averageViewPercentage for 17 Shorts (43-55%).
- **Length tip** (`my_channels.length_tip`, Today tab): with 4+ counted long
  videos, under 30% watched suggests 0.7x the minutes (5 at least), over
  50% suggests 3 more (14 at most until verified).
- The Channels tab lists each channel's last uploads (`RecentUploads.jsx`):
  when it goes public, views and % watched, thumbnail/caption steps.
- **The local dashboard runs on port 5180** (`autostart.bat`, `--strictPort`):
  another of the owner's projects (D:\bd\tool) runs Vite on 5173, and the
  old "is 5173 listening?" check then skipped starting Shortkaar's dashboard
  at all. The CDP harness BASE is http://127.0.0.1:5180.
- Patch scripts: always the Write tool, and write files back as LF (the
  repo stores LF; some working files are CRLF on disk, and a half-CRLF file
  got CLAUDE.md committed as CRLF once). The scratch `patchlib.patch`
  pattern: read bytes, replace CRLF with LF, patch, write bytes. A bash heredoc turned `\n` inside a
  Python string into a real newline three times on 8-oct-2026.
- Starting autostart.bat from a Claude shell: cmd here does not run a bare `autostart.bat`
  from the working folder ("not recognized"), so pass its full path, and launch it through a
  separate `powershell.exe -File` script (processes started straight from the tool's shell can
  stop when the command ends).
- **Lives on the internal disk at `D:\Shortkaar`** (4-nov-2026; `Automate\`, `oss\`, `MoneyPrinterTurbo\`).
  F: was an external USB disk that dropped off and was not mounted at login, so Shortkaar never started at
  boot; the old Startup shortcut was gone too. `oss/` tools are found next to the project folder (every
  default is `<project>/../oss/...`, env overrides kept), never by drive letter. The Startup folder's
  `Shortkaar.lnk` runs `D:\Shortkaar\Automate\autostart.bat` minimised. F:\youtube is an old copy, and
  D:\youtube is a junction to it, unused now.
- Before starting uvicorn, check :8000: a server from an earlier session may
  still answer with old app.py code (job subprocesses load new code anyway).
- **Boot + speed + quality pass** (4-nov-2026, `tests/test_boot.py`, `test_qsv_and_grain.py`,
  `test_parallax_cache.py`; research notes in `docs/research-2026-11-04/free-upgrades.md`):
  - The moved venvs' `Scripts\*.exe` (pip, pytest, edge-tts... 171 in 4 venvs) still started
    `D:\youtube\...\python.exe` = the F: copy: `pip install` went into the OLD venv. `ops/fix_venv_paths.py`
    (run with the venv's own python) rebuilds them from entry points; run it after any move.
  - **Never edit autostart.bat while its watchdog runs**: cmd reads a running batch file by byte offset, so
    the waiting `autostart.bat watch` resumes mid-line in the new file. Kill that cmd (found by command line)
    and start autostart.bat again. The watchdog now: sets `SHORTKAAR_RESTART=watchdog` for a restart (the
    server then toasts/Telegrams "it had stopped", `restart_notice.py`, once an hour), says "down" after 3
    misses in a row (~15 min, the case where the server cannot start at all), refuses a port 8000 held by
    another program (`ops/port_check.ps1`; Docker Desktop starts at login and docker-compose.yml publishes
    8000 with restart: unless-stopped) and rotates server.log past 50 MB. `%~z1` of a missing file is empty
    and made the size comparison a syntax error: check `if not exist` first.
  - `KEEP_AWAKE=charger` (owner's .env; code default unchanged): the laptop is Modern Standby only (no S3,
    RTC wake timers off), so between jobs it dozed and every loop froze. `heartbeat.py` pings
    `HEALTHCHECK_URL` (off when unset) while both loops' `last_tick` are fresh.
  - **Intel Quick Sync** (`FFMPEG_ENCODER=qsv`, also tried by `auto` after nvenc): the Iris Xe does h264/hevc
    (no AV1). Look-ahead ICQ 20 matched x264 medium CRF 18 within 0.1 VMAF at 3.6-4.6x the speed (table in
    ffmpeg_utils). A late `-pix_fmt yuv420p` from a caller just warns and uses nv12; BT.709 tags survive.
    short_kit's fast render uses the new INTERMEDIATE tier (= FAST_PASS on x264). The hardcoded libx264 sites
    (history shots, broll, parallax, long_video joins...) are unchanged.
  - Gradient banding: CAMBI (`libvmaf=feature=name=cambi`, same file as both inputs) 0.9-17.6 on short_kit's
    gradient (it varies: `gradients` picks random points; tests pass `seed=`); a FIXED grain
    (`noise=alls=2`, no allf=t) -> 0.00, also after a 2.5 Mbps re-encode. `GRADIENT_GRAIN=0` off.
  - parallax lost its depth effect on every cache hit: the .depth.npy is float16 and cv2.remap has no float16
    kernel (`ifunc != 0`, imgwarp.cpp); only first-seen pictures moved.
  - The OmniVoice model was missing from every disk (the user-profile HF cache was recreated 28-oct) and
    every local-voice line went to Gemini. Its cache is now `oss/hf` (`local_voice.HF_DIR`, used when the
    folder exists and HF_HOME is unset).
- **AI editor, stronger** (4-nov-2026, `tests/test_ai_editor_plus.py`, `tests/test_phone_edit.py`; owner: "make it
  more strong and better"). Tested live on sandbox copies (`studio.OUTPUT_DIR` redirected: a copy in output/
  could be queued and uploaded) with real Gemini calls:
  - New ops: `bleep` (beep or mute words), `blur` (box 0-1000 from the watched proxy, or a named spot; pixelate),
    `sfx` (whoosh = the Kenney files, pop/ding/boom/click/rise/scratch synthesised by aevalsrc), `sticker` (Noto
    via `stickers.overlay_args`, `alive_until=D`), `clean_audio` (highpass + afftdn tn=1 + gentle compressor),
    `fade`, `undo` (typed: last or all; later versions stay to redo), `text` colour/size, and `speed` on ONE
    stretch. `Timeline` is now pieces (a, b, factor): cuts, whole-video speed and a slow-motion stretch are one
    thing; render trims each piece with setpts/atempo (atempo < 0.5 is chained). Footage covers every piece of a
    stretch (it used to `break` after the first). Renders use `video_encode_args(INTERMEDIATE)` (Quick Sync).
  - Found live and fixed: `sine=` is made at amplitude 1/8 (the beep came out 13 dB under the speech); the planner
    sends a sound "at the start" as start=0/end=0 (both sounds dropped as "not found") and a sticker "there too"
    with no moment (it now inherits the previous op's moment); the planner blurred the channel's OWN handle for
    "another channel's logo" (the sheet lists OUR OWN BRANDING from frame.json + the card); an audio-only edit
    after a blur went to the frame check, which said "cannot be seen" and forced a second render (only THIS
    request's `VISIBLE_OPS` are checked); the planner's proxy encodes ultrafast. Quotes match spoken variants
    (`_same`: records/record, 15,000/15000, Roman spellings).
  - **Comedy (main pipeline) jobs are refused**: their metadata `transcript` is the WHOLE source (source seconds,
    Devanagari) while the captions are Roman Urdu per clip, so the editor read the wrong words and burned another
    part of the show; that transcript also serves the job's other clips. They are not in Studio anyway (the main
    channel is not a card); bringing them in needs per-clip, multi-clip support.
  - `ai_editor.suggest` + `POST /api/studio/ai/{id}/suggest` + Studio's "Suggest edits": one call watches the video
    and proposes 3-5 instructions in the owner's language, cached in edits/suggest.json until the file changes.
  - **Editing from the phone**: review notes carry `ref <job id>` and a hint; `telegram_notify.poll(on_text=)`
    hands the owner's text REPLIES to `my_channels.telegram_reply`, which starts the edit through
    `start_ai_edit` (= `app._phone_ai_edit`: the poll runs in an executor thread, so the start is scheduled on
    `_main_loop`); `_ai_edit_done` sends the new video back (`send_video`, under 50 MB) with the ref again, so
    replies chain. "suggest" as the reply sends the suggestions as one-per-row buttons (`ed:<job>:<n>`).
  - A plan once degenerated into 62,000 characters of "000..." in a number (7 minutes, cut at the output
    limit, the whole edit lost): `short_kit.ask_json(max_tokens=, invalid_tries=)` (opt-in; defaults unchanged)
    caps and re-asks, and a failed second pass keeps the first version.
- **Found in server.log, fixed** (4-nov-2026, tests in `test_boot.py`):
  - 33 `open()` of job files in app.py had no encoding: studio._write / ai_editor keep Urdu and emoji as UTF-8,
    so every Studio-edited job read as cp1252 failed ("Could not recover job ...: 'charmap' codec", 15 times;
    the edit/subtitle/hook endpoints too). All UTF-8 now (the pipeline's own ASCII JSON reads the same).
    A regex patch first turned the `'w'` opens into `open(x, 'w', 'r', ...)`: review every line a bulk patch touches.
  - History teaser / moment Shorts passed their long video's pictures as `output\<long>\.hv_pics\...` (app's
    OUTPUT_DIR is relative), but broll runs ffmpeg inside the teaser's folder: "footage shot failed". Absolute
    paths there, and `broll._located` resolves any project-relative path.
  - OmniVoice re-downloaded into `oss/hf` (xet transfer stalled here: `HF_HUB_DISABLE_XET=1`); one Urdu line
    through `local_voice.speak_many` came back word for word through Whisper.
- **The main comedy channel in Studio** (4-nov-2026, `tests/test_comedy_studio.py`; owner: "make it more powerful"):
  - A Studio id is `<job id>` or `<job id>.<n>` (`studio.REF`, `split_ref`, `ref_of`; `.1` = the job id): each clip
    of a comedy job (3 per show) is its own Studio video. Routes, the dashboard and the phone's `ref` carry it as is.
    `studio.videos(main=app._queue_clips())` lists them with post-queue states (ready=waiting, posted=uploaded,
    skipped); skip / approve ("put back") act on `post_queue`; no remake.
  - `studio.shares_transcript` / `clip_transcript`: a comedy job's transcript is the WHOLE show (source seconds); a
    clip reads the words that overlap it, moved to 0 (as its captions were made). The AI editor's base is that
    slice; `_publish` never writes the shared transcript nor the clip's start/end (only `seconds`; `_job_clips`
    prefers it). Edit chains: `edits/` for clip 1, `edits_clip<n>/` (`ae.edits_name`).
  - Manual trim / caption save are refused for shared clips: they rewrite the shared words and `studio._reburn_here`
    deletes EVERY `subtitled_*` of the folder (the other clips' too). The AI box does both.
  - The comedy genre lives in `.source.json`, not the metadata: the editor read "" and would have drawn the Shorts'
    emphasis captions instead of the comedy look (`ctx["genre"]` reads both now).
  - A main clip being AI-edited carries `editing_until` in post_queue; `post_queue.plan` marks it `editing` and
    `_auto_post_ready` / post-all skip it. Live on a sandbox copy of a real show: clip 3 "pehle 1 second kaato aur
    captions peele karo", 75 s with one re-plan from the frame check; clips 1-2 and the transcript byte-identical.
- **Mood playlists on the song channel** (5-nov-2026, `music_moods.py`, `tests/test_music_moods.py`; owner: "sad
  song, romantic song, workout song, gym song"): MOODS sad / romantic / workout (upbeat cardio) / gym (phonk, trap) /
  chill / party, each with its playlist title, styles (all in `music_shorts.STYLES`; "gym phonk" and "aggressive trap
  anthem" added), themes and a brief for the song writer (`music_shorts.plan(brief=)`, env MUSIC_MOOD/MUSIC_BRIEF).
  The card's `ch["moods"]` = {off, often (1/2/4), custom (name, sound, themes; up to 8)}; `pick` takes the mood
  furthest below its share of the last 30 songs (`DEFAULT_OFTEN`: sad and romantic start at "more", so love songs
  stay ~half, the 19-oct LOVE_SHARE finding; `pick_theme` only runs with every mood off); `next_mood` (Channels card "make one now", `/make {"mood"}`;
  queued while a song is being made) wins once and is cleared by `make_one`. Within a mood `pick_format` still
  learns the best style. Jobs and upload rows carry `mood`; `engage._mood_playlists` files EVERY song (old ones by
  `infer` from style + theme: 46 of the 47 songs on the channel) into its mood playlist, `MOOD_PER_PASS` (10) a
  pass, marked in engage.json `mood_playlisted`; "New AI songs" stays the all-songs list. Live plans: gym came
  back as 145 BPM phonk with distorted 808 and cowbell, romantic as 72 BPM slow pop.
- **Round of 5-nov-2026 (owner: "go ahead and do these all in detail"; research in
  `docs/research-2026-11-05/channels-and-features.md`)**:
  - **Horror channel** = the long channel's third mode (`LONG_MODES` "horror", `horror_stories.py`,
    `tests/test_horror.py`): original fiction, no web research; a story check (rules, retold films, plot holes) gets one
    rewrite. Pictures: no Wikipedia; the hook and chapter openers are AI paintings (`HORROR_AI_IMAGES` 14, even where
    footage exists), dark stock footage between, one cold grade on both (`history_videos.mode_grade`); voice Algenib
    with a slow style; a low sting per card; music_beds kind "horror"; red thumbnail text; "fiction" note in every
    description; title keeps "Horror Story in Urdu" (`search_title`: the title tournament dropped it). Uploads are
    Entertainment (`CATEGORY` "horror"/"horror_teaser" 24, `LONG_GENRES`); watch_next/series links accept both
    genres. Pace MEASURED: one test line read at 86 wpm but a whole story at 160, so `WPM` 150 (planned at 90 a
    "14-minute" story came out ~7). Safety net for every long video: `fit_voices` speeds the narration (atempo, at most
    1.15x) when a <=14-min video would pass 14:45 (YouTube refuses >15:00 from unverified channels). Live 3-min run in
    the sandbox: 18.7 min to make, -14.1 LUFS.
  - Latent bug fixed: `segment_video` imported broll only in its motion branch but used `broll.grade()` in both.
  - **Mood mixes** (`mood_mix.py`, `tests/test_mood_mix.py`): every finished song is archived whole with its timed
    lyrics and a still (`music_moods.archive_song`, state/songs/<job>/, 120 days). `next_mix`: at most `mixes` a week
    (default 1; 0 off), a day after a failed try; a song mood is ready with 8 uploaded songs never mixed; study and
    sleep are MIX-ONLY instrumental moods (never Shorts, `song_moods`) whose tracks Lyria makes in the job up to
    `mix_minutes` / `mix_budget` (~$0.08 a track, default $1.50). A mix is an EXTRA_FORMAT job (on top of the day's
    Shorts), `MIX_TIMEOUT` 150 min, uploads as `music_mix` (Music, long), lyric-video chapters with a wave line, the
    mood's painting for songs without a picture. Chapter stills are composed once by PIL (`backdrop`): blurring every
    frame in ffmpeg took 7 min for a 3-min mix. `/api/process` keeps only song folders inside the archive.
    Old song tests turn mixes off: a new music card's first job is otherwise the weekly study mix.
  - **Duplicate songs** (`audio_dedupe.py`, Chromaprint `fpcalc` 1.5.1 in `oss/chromaprint/`): the Short's audio is
    fingerprinted before upload and compared (best shift, popcount table: 39 ms a pair) with the channel's uploaded
    songs; >= 0.80 is skipped. Live: the same song re-encoded and cut 5 s later 0.944, other songs 0.57-0.61.
  - **YouTube's numbers** (`yt_insights.py`, `tests/test_insights.py`), checked live read-only: the retention curve
    (the music channel's top Short: half gone by 0:07.9, a 26% drop at 0:04.7), real search terms ("long distance
    song", "razia sultana"), creatorContentType comes back as "shorts"/"videoOnDemand" (NOT the documented SHORTS),
    the Reporting API is on in the project. learn: curves for 6 videos a pass (`_insights`), the channel's
    `retention_lesson` + search words into `hook_text` (the writers) and the AI editor's sheet and suggestions;
    Studio's "On YouTube" panel (`studio.insights`: drops with the words said, search terms as tag chips); the week
    report ends with the 2027 YPP targets (`reminders.ypp_lines`); thumbnail reach (Reporting API
    channel_reach_basic_a1, daily) feeds the "thumb" A/B test (text left/right, metric ctr, `HISTORY_THUMB`).
  - `MAX_CHANNELS` 6 -> 8 for the horror ("Raat Ki Kahaniyan": a history card in horror mode, 1 a day, 20 min,
    capped at 14 until verified) and money ("Paisa Kahani") cards: the six cards had kept the laptop busy ~4 h of 24.
  - **Podcasts** (`engage.podcasts`, switch "podcasts", long kinds only): a 1400x1400 cover (playlistImages.insert,
    type "hero", upload URL /upload/youtube/v3/playlistImages) then playlists.update podcastStatus "enabled"; never
    the 60-second lists; a failure waits a week.
- **Channel hand-over** (5-nov-2026, `my_channels.hand_over`, POST `/api/my-channels/{cid}/take-over {"from"}`,
  "or use the channel of" on an unconnected card, `tests/test_channel_handover.py`; owner: no Google accounts left
  for new channels, "remove 2 least performing channel"). The new card takes the token; the old card's record,
  uploads log, engagement state and kit MOVE to `state/retired/<old>-<time>/` (remove() would rmtree them). The
  new card keeps its own empty uploads log (numbers, A/B tests, replies and playlists start from its own videos)
  and drops about_credit/last_learn/long_uploads, so its first learn pass replaces the About text with its own
  ABOUT (`add_to_channel_about(replace=, backup=)`, old text in the card folder). Name, handle and picture have no
  API: the card tells the owner what to rename in Studio. Done that day after measuring all six (3 weeks, ~45
  videos each): quiz median 1 view, history/explainer 0 in its last week, cricket's last week median ~1,000; Quran
  kept (3 uploads in 14 days is too few to judge). Sawal Paheli -> Paisa Kahani (money), Tareekh History -> Raat Ki
  Kahaniyan (horror). Old videos stay public until the owner decides.
- **Few Instagram accounts** (5-nov-2026, `meta_publish.IG_RAMP` / `ig_cap` / `_ig_ready`, `my_channels.meta_ig_mode`
  / `meta_score`). Every Instagram account starts slow: 1 Reel a day for 7 days from our first Reel on it, 2 until
  day 14, then IG_DAILY 3 (state/meta/accounts.json). Cards that share one Page/Instagram ("auto" mode) send only
  YouTube winners there: judged 24 h after the YouTube time, views >= max(20, 1.5 x the channel median), the best
  ratio first, given up at 72 h ("skipped" with why). Facebook Pages take every Short (one Facebook profile owns
  any number of Pages, no new email). Also fixed: a finished item's "done" was rewritten every pass (nothing ever
  left the queue), and a Short queued during a pass was lost when the pass saved. Meta was never connected yet
  (no META_APP_ID), so neither had bitten.
- **Teardown** (5-nov-2026, `teardown.py`, `tests/test_teardown.py`; owner shared the REA reverse-engineering repo,
  "see how we can reverse engineer something and make our system better"). REA itself (an MCP for binaries, apps,
  websites; "software you own or are authorized to examine") was NOT installed: our rivals are videos, and taking
  YouTube Studio's private calls apart would break YouTube's terms. Its idea was applied to videos: the research
  pass fetches 2 studied winners a day (yt-dlp with `yt_clients.fallback_extractor_args`; format 18 alone was
  "not available" and default/mweb alone 403'd), measures them and up to 3 of ours still on disk
  (`recent_files`), each in its own process (Whisper "small", the cached model; "base" was a 150 MB download):
  first cut, median shot, cuts/10 s, first word, words/s, words in 3 s, first-frame light, loop. `compare` keeps
  gaps over a floor and 25%, with >= 4 winners and 3 of ours; `measured_text` heads `playbook_text`
  (NICHE_PLAYBOOK now 2700). First numbers: our cricket Short first cut 4.1 s, shot 2.5 s, 2.8 words/s; a 4.3M-view
  cricket winner first cut 6.3 s, shot 3.0 s, talking 93%. "pace" A/B (cricket, controversy, music): the winners'
  shot scaled to our cut (`pace_cut`, 1.5-4 s, only when 15%+ apart) as BROLL_CUT -> `broll.cut_seconds`.
  TEARDOWN=0 in the tests.
- **Second REA pass, same day** (owner: "take all the good things", "make it easier for me", "go ahead"):
  - **Channel doctor** (`channel_doctor.py`, `tests/test_channel_doctor.py`, summary()["doctor"], "What holds it
    back" on each card): REA's investigation ledger on a channel. Fixed checks (connection, posting vs plan, reach
    last week vs the two before, watch share + half_at, formats, posting hour = time_tip, A/B tests, measured niche
    gaps with the winners as evidence links, search, and for long kinds clicks/length/verified); status problem /
    tip / unknown / info / good, problems first; "next" says what the system already does. Its first run found: a
    4-day outage (30 Oct-3 Nov: nothing in server.log; the Startup shortcut pointed elsewhere until 4 Nov; Windows
    crash 30 Oct 03:13), the first study mix failing, Quran stuck, and the search-word leak below.
  - **mood_mix.segment** takes absolute paths: ffmpeg runs in job_dir and the server's job folders are relative,
    so the first live mix failed "Could not create a libass track" (the same class as the Quran mix on 23 Oct;
    the rest of the cwd= calls use bare names). The render test now runs from a relative folder and was shown to
    fail on the old code (mutant loaded as `mood_mix` through sys.modules: conftest puts ROOT first on sys.path).
  - **Quran first frame**: the first background shot no longer fades in and the title card starts at 0 (fade
    (0, 300)): frame 0 was black but for the handle and video_qa refused Yaseen part 2 three times; 36:13-22 was
    queued again first through the card's ideas.
  - **Search words after a hand-over**: `_insights` reads search_terms(days=days since the hand-over), none in the
    first 2 days (the money card heard the quiz channel's "mushkil paheliyan").
  - **Old videos private** (`hide_retired`, update(hide_old=True), the card's button): the retired log's done
    uploads and its engage playlists (`ya.playlist_private`, snippet sent back) set private, HIDE_PER_PASS 15
    every 10 min while the day's quota is under HIDE_CEILING 6000; done ids in the archive's hidden.json. Never a
    row with "elsewhere" or another yt_channel; a 403 is "not this channel's" and not tried again.
  - **An uploads-log row's "id" is OUR 12-character row id; YouTube's is "video_id" (11).** The first live hide
    pass asked YouTube for 30 row ids, found nothing and marked them "gone" (nothing changed on YouTube); the
    tests had used "id" as the video too, so they passed. hide_retired, recent_files and the doctor's evidence
    use video_id now, hidden.json keeps only 11-character keys, update(hide_old=True) re-arms a finished pass,
    and the tests' rows carry both ids (`V()` in test_channel_handover).
  - **Horror shots that the grade turns black** (`history_videos._shot_tries`, `too_dark`, horror_stories.GRADE_LIFT):
    the first live story was refused for "6 s of black picture" (chapter cards are 2.6 s of near-black under the
    grade, plus a night shot after one). In horror mode every shot is measured (video_qa's detector at 1.5 s) and
    made again with GRADE_LIFT, then without the horror grade. 0x282828 is black under GRADE, fine lifted.
  - **Teardown on a busy laptop**: measurements run BELOW_NORMAL_PRIORITY_CLASS; a timeout raises `Busy`, which
    ends the pass without marking the video failed (and old "TimeoutExpired" failures are measured again).
  - **Meta made easy**: keys pasted in the dashboard (`save_keys`: format check, client_credentials app token
    check, `.env` + os.environ, `write_env` refuses the real .env under pytest), META_CONFIG_ID -> `config_id`
    in the dialog (Facebook Login for Business uses a configuration, not scope), `refresh_pages`, `check`
    (Page token + content_publishing_limit, posts nothing), `use_redirect_host` (localhost / 127.0.0.1). One
    Instagram per Page and one Page per Instagram, so a card has `meta_page` (Facebook) and `meta_ig_page` (whose
    Instagram); queue items carry `ig_page`. `auto_link` after connect: Page by name (card name / YouTube title,
    `page_for`), Instagram by IG_GROUPS (cricket alone; controversy, money, history/horror share; music and quran
    Facebook only), owner choices kept. Setup guide for the owner: https://claude.ai/artifact/RDeepUwMHtaGfzbnabLDn4
- **Cartoon channel "Billo aur Gang"** (`toon_shorts.py`, kind/genre `toons`, `tests/test_toons.py`; owner, 5-nov-2026:
  "cartoons, baby talking, animal talking ... with a strong script"). Research: AI pet micro-dramas (stitched AI
  pictures, under a minute, twist or cliffhanger) are the format of 2025-26; YouTube's July 2026 "inauthentic
  content" clarification refuses templated repeats and "animals in exaggerated distress or peril"; animation is not
  "made for kids" by itself (FTC factors). So: one fixed cast (`CAST`: Billo cat, Sheru dog, Mithu parrot, baby
  Guddu who talks like an old uncle, Ammi heard off screen), one house (`PLACES`), a comic engine per episode
  (`SHAPES`, never the last three), grown-up home comedy, never suffering (`RULES`).
  - Writers' room: 2 drafts (two shapes, in parallel) -> code gates (`problems`: lines, words, hook, every speaker
    in their shot, Latin, stale phrases) -> judge -> punch-up (kept only if it still passes) -> safety check (one
    rewrite). `channel_ideas` drops premises too close to old ones (word Jaccard 0.5) and plans one idea in four as
    a TWO-PART story: part 1 ends on a cliffhanger ("PART 2 JALD!"), part 2 opens on part 1's last lines
    (`series_part`, from series.json "ending"); uploads link the parts (`history_videos.series_rows(genres=)`).
  - Talking without a lip-sync model: each shot is one picture with mouths closed; the image model edits ONLY the
    speaker's mouth open (and the eyes shut for blinks); `mask_of` = the changed blob (median diff <= 12, 0.02-6% of
    the picture, centroid on the character's side) laid over the closed picture when the voice is loud (`flaps`,
    held 2 frames). The picture check (`look_check`, one vision call) found open mouths in 4 of 5 first shots: those
    get a close-mouths EDIT (`close_mouths`), only other problems are redrawn. Camera: push-in, lean to the speaker,
    punch on the punchline, depth parallax (`DEPTH_AMP`, parallax.depth_of; TOON_PARALLAX=0). Real-ESRGAN anime x2.
  - Voices: 4 Urdu edge voices pitched apart (free_voice.speak `pitch`, `edge_voice` on the item); a line that fell
    to the local/Gemini voice is asked of the character's edge voice again (`same_voices`: a transient
    NoAudioReceived gave Sheru the narrator's voice on episode 1). Whisper heard episode 1 back almost word for word.
  - State in state/toons/ (cast/ references: keep or replace the PNGs; series.json; episodes/ for the compilation;
    art/ banner + icon from `python toon_shorts.py art`). Tests redirect STATE_DIR (conftest).
  - Weekly compilation (`toon_mix.py`, format "mix", genre "toons_mix" = a long Comedy video): every episode is kept
    cut before its end card; with 7 new ones and 6 days since the last, the next job joins up to 16 with chapters
    and a 3-picture thumbnail. Why: from 1-feb-2027 new YPP applicants need 8,000 watch hours or 20M Shorts views,
    and Shorts views are no watch hours. meta_publish skips vertical videos over 180 s (REEL_MAX_SECONDS).
  - Cost ~$0.4 of Gemini an episode (~6 text calls, ~15-18 pictures), ~10 min on this laptop.
  - Replies in character (`engage.TOONS_EXTRA`): auto replies are written as Billo, Sheru, Mithu or Guddu and signed.
  - A/B test `toonlen` (my_channels EXPERIMENTS, `TOON_LENGTH`, toon_shorts.LENGTHS/`limits()`): 35-45 s vs 25-32 s
    episodes, since our Shorts lose half their viewers by 0:07-0:12 (channel doctor, 5-nov-2026).
  - The writer may return a shape's description for its key ("secret out: ..."); `tidy` maps it back.
  - A shot the image model returns no picture for (3 tries; episode 4's "Guddu reads the bill" first shot) is drawn
    once more without its action (`shot_prompt(simple=True)`, SIMPLE_PICTURE); the error carries the model's text.
  - toon_shorts / toon_mix run in the job process (main.py), so their changes need no server restart; my_channels,
    app, engage and meta_publish do.
- A replace-Edit whose old_string is a `def` line must keep that line in new_string: adding `with_part` above
  `same_voices` deleted the latter's header, its body sat dead after a `return`, and only the live part-2 run hit the
  NameError (the -k test runs skipped its test). Run the whole module's tests after such an edit.
- Reels captions ask for the send (`meta_publish.SHARE_LINES`, toons/quiz/cricket/money): Instagram ranks sends per
  reach and watch time first.
- `upscale._run` falls back to the first GPU on "invalid gpu device" (5-nov-2026 Vulkan saw only the Iris Xe; the Arc
  A370M was gone, so every upscale failed).
- Never write heredoc patch scripts containing backslashes (this harness turns `\\n` into a newline inside the
  Python string: a toon_shorts prompt became an unterminated literal); use the Edit tool.
- `caption_script._roman_clip` takes every word OVERLAPPING the clip (as `_collect_word_blocks` shows them): a long
  word starting > 1 s before the clip stayed Devanagari on Roman captions (2 of 15 caption files on disk).
- `tests/test_editor_properties.py`: seeded random invariants (no Hypothesis) for Timeline out/base roundtrip,
  order, duration, out_ranges, compile_ops keep ranges and the clip slice. At a cut's seam `base()` answers the
  earlier side (same frame on screen): not a bug.
- **Every tab needs its own scrolling frame**: the shell and `<main>` are
  overflow-hidden, so a tab whose root is plain content (Today and Channels
  were) cannot be scrolled at all. They now sit in App.jsx's
  `h-full overflow-y-auto p-4 sm:p-8` wrapper like the rest. A CDP check
  must scroll with `Input.dispatchMouseEvent` mouseWheel and read scrollTop:
  `scrollIntoView` scrolls an overflow-hidden box from code, which hid this
  from every earlier check (the owner could not reach the channel cards).
- Voice samples play on the Today tab (`app.VOICE_SAMPLES`, files in
  output/thumbnails/voice_samples/compare/).
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
