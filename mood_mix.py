"""Long mood mixes for the AI-song channel (owner, 5-nov-2026: "weekly mood mixes... one chapter per song").

Research that day (docs/research-2026-11-05): mood Shorts bring reach but phonk Shorts pay ~$0.50 RPM; long study
(~$3-6) and sleep (~$4-8) mixes earn the watch hours the YPP terms of 1-feb-2027 count (8,000 hours a year to
join; Shorts pay only past 10M Shorts views a quarter). "english songs with lyrics" is the #2 YouTube suggestion
in Pakistan: a song mix shows each song's timed lyrics.

- A SONG mood's mix (sad, romantic, gym...): the channel's own uploaded songs of that mood not mixed before
  (music_moods.archive_song kept each whole song, its timed lyrics and its picture), one chapter each, in a 16:9
  lyric video: the song's picture large on its blurred copy, the title, the line being sung, a wave line.
- A MIX-ONLY mood (study, sleep, instrumental): its tracks are made here by Lyria (instrumental, varied by the
  mood's sounds) up to the card's minutes or its budget, under one AI painting of the mood.

Never a slowed, sped-up or reverb copy of a song (YouTube's reused-content policy names them): every song in a
mix is its own original, once. Uploads carry the altered/synthetic label (app._job_clips: genre "music").

Env: MUSIC_MIX (mood key), MUSIC_MIX_MOOD (the mood as JSON), MUSIC_MIX_SONGS (archive dirs, JSON),
MUSIC_MIX_MINUTES, MUSIC_MIX_BUDGET (USD), MUSIC_MIX_VOL (the mix's number for that mood).
"""
import base64
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

import framed_layout as fl
import short_kit as kit

W, H, FPS = 1920, 1080, 24
GAP = 0.6                     # silence between two songs
FADE_IN, FADE_OUT = 0.4, 1.2
TRACK_USD = 0.08              # one Lyria 3.5 song (music_shorts: ~$0.08)
TRACK_TRIES = 3               # Lyria refusals in a row before the instrumental mix stops adding tracks
MIX_MIN_SECONDS = 8 * 60      # a mix shorter than this is not made (it would be a playlist of Shorts)
MIN_TRACK_SECONDS = 15        # a broken or cut song file is left out of a mix

STYLES = [
    kit.style("MxKicker", "Montserrat ExtraBold", 30, fl.GOLD, shadow=2, spacing=3),
    kit.style("MxTitle", "Anton", 84, "#FFFFFF", outline=0, shadow=5),
    kit.style("MxLine", "Montserrat ExtraBold", 58, "#FFFFFF", outline=4, shadow=3),
    kit.style("MxNext", "Montserrat ExtraBold", 40, "#FFFFFF", outline=3, shadow=2),
    kit.style("MxSmall", "Montserrat ExtraBold", 28, "#FFFFFF", shadow=2),
]


class Titles(BaseModel):
    titles: List[str]


TITLES_PROMPT = """Give {n} short, evocative English titles (2 to 4 words each, no numbers, no artist or song names,
all different) for instrumental tracks in a "{name}" mix: {about}. Like "Rain on the Window", "Midnight Pages",
"Slow Morning Light". Return JSON {{"titles": [...]}}."""


def _esc(text):
    return re.sub(r"[{}\\]", "", str(text or "")).replace("\n", " ")


def _ass(events):
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding", *STYLES, "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return "\n".join(head + list(events)) + "\n"


def clock(seconds):
    s = int(round(seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def song_events(track, k, n, mix_name, d):
    """One chapter's text: the mix's name and the track number top left, the title for its first seconds,
    and (a song) the line being sung large with the next one dimmed under it."""
    ev = [kit.dialogue(2, 0.2, d, "MxKicker", rf"{{\an7\pos(70,60)\fad(400,400)}}{_esc(mix_name).upper()}"),
          kit.dialogue(2, 0.2, d, "MxSmall", rf"{{\an9\pos({W - 70},60)\fad(400,400)}}{k + 1} / {n}"),
          kit.dialogue(3, 0.3, min(d, 6.0), "MxTitle", rf"{{\an5\pos({W // 2},{H // 2 - 40})\fad(500,600)}}"
                                                       rf"{_esc(track['title'])}")]
    lines = [(t, a, b) for t, a, b in track.get("lines") or [] if b > a]
    for i, (text, a, b) in enumerate(lines):
        if a < 6.0 or a >= d:
            continue                      # the title owns the first seconds
        end = min(d, max(b, lines[i + 1][1] if i + 1 < len(lines) else b))
        ev.append(kit.dialogue(4, a, end, "MxLine", rf"{{\an5\pos({W // 2},{H - 250})\fad(150,150)}}{_esc(text)}"))
        if i + 1 < len(lines):
            ev.append(kit.dialogue(4, a, end, "MxNext", rf"{{\an5\pos({W // 2},{H - 175})\alpha&H70&\fad(150,150)}}"
                                                        rf"{_esc(lines[i + 1][0])}"))
    return ev


def _encode(fast=False):
    from ffmpeg_utils import INTERMEDIATE, QUALITY, video_encode_args
    return video_encode_args(INTERMEDIATE if fast else QUALITY)


def backdrop(picture, out, colors=("#1B1030", "#05040A")):
    """The chapter's still, made once (the first renders blurred every frame: 7 min for a 3-min mix): the picture
    large on its own blurred, darker copy, or the mood's two colours, under a vignette. 1920x1080 PNG."""
    from PIL import Image, ImageDraw, ImageFilter
    if picture and os.path.isfile(picture):
        with Image.open(picture) as src:
            im = src.convert("RGB")
        s = max(W / im.width, H / im.height)
        bg = im.resize((round(im.width * s) + 1, round(im.height * s) + 1), Image.LANCZOS)
        x, y = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(28))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
        fh = round(H * 0.82)
        fg = im.resize((max(1, round(im.width * fh / im.height)), fh), Image.LANCZOS)
        if fg.width > W - 80:
            fw = W - 80
            fg = im.resize((fw, max(1, round(im.height * fw / im.width))), Image.LANCZOS)
        bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2 - 30))
    else:
        def rgb(c, d):
            c = c if isinstance(c, str) and len(c) == 7 and c.startswith("#") else d
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        a, b = rgb(colors[0] if colors else "", "#1B1030"), rgb(colors[-1] if colors else "", "#05040A")
        bg = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(bg)
        for yy in range(H):
            k = yy / H
            draw.line([(0, yy), (W, yy)], fill=tuple(round(a[i] * (1 - k) + b[i] * k) for i in range(3)))
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).ellipse((-W // 4, -H // 4, W + W // 4, H + H // 4), fill=255)
    shade = shade.filter(ImageFilter.GaussianBlur(160))
    bg = Image.composite(bg, Image.new("RGB", (W, H), (0, 0, 0)), shade)
    bg.save(out, "PNG")
    return out


def segment(job_dir, picture, audio, seconds, events, out, colors=("#1B1030", "#05040A")):
    """One chapter: its still (``backdrop``), a wave line moving with the track's sound, the text. Video only.
    Absolute paths: ffmpeg runs in ``job_dir``, and the server's job folders are relative ("output/<id>"), so
    the first live mix (5-nov-2026) failed with "Could not create a libass track" on a path from the wrong place."""
    from ffmpeg_utils import escape_filter_value
    job_dir, audio, out = os.path.abspath(job_dir), os.path.abspath(audio), os.path.abspath(out)
    picture = os.path.abspath(picture) if picture else picture
    ass = out[:-4] + ".ass"
    with open(ass, "w", encoding="utf-8") as f:
        f.write(_ass(events))
    still = backdrop(picture, out[:-4] + ".png", colors)
    src = ["-loop", "1", "-framerate", str(FPS), "-i", still]
    graph = (f"[1:a]aformat=channel_layouts=mono,showwaves=s={W}x140:mode=cline:rate={FPS}:"
             f"colors=white@0.55,format=yuva420p[wv];[0:v][wv]overlay=0:{H - 150},format=yuv420p,"
             f"ass=filename='{escape_filter_value(ass)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'[v]")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *src, "-i", audio, "-filter_complex", graph,
                        "-map", "[v]", "-t", f"{seconds:.3f}", "-r", str(FPS), *_encode(fast=True),
                        "-video_track_timescale", "24000", "-an", out],
                       capture_output=True, text=True, errors="replace", timeout=3600, cwd=job_dir)
    if r.returncode != 0:
        raise RuntimeError(f"mix chapter failed: {r.stderr.strip()[-300:]}")
    os.remove(ass)
    return out


def _track_audio(src, out, seconds):
    """The track faded in and out, with GAP of silence after it, as 48 kHz stereo WAV."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-af",
                        f"afade=t=in:d={FADE_IN},afade=t=out:st={max(0.0, seconds - FADE_OUT):.3f}:d={FADE_OUT},"
                        f"apad=pad_dur={GAP},aresample=48000,aformat=channel_layouts=stereo",
                        "-t", f"{seconds + GAP:.3f}", out], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"mix audio failed: {r.stderr.strip()[-200:]}")
    return out


def make_tracks(client, mood, minutes, budget, job_dir, log=print):
    """Instrumental tracks for a mix-only mood, by Lyria, until ``minutes`` or ``budget`` (USD): [track]."""
    import music_shorts as ms
    want = minutes * 60
    most = max(0, int(budget / TRACK_USD))
    sounds = mood.get("sound") or [mood["name"]]
    sounds = sounds if isinstance(sounds, list) else [sounds]
    try:
        names = kit.ask_json(client, Titles, TITLES_PROMPT.format(n=max(8, most), name=mood["name"],
                                                                  about="; ".join(sounds))).titles
    except Exception:  # noqa: BLE001 — numbered titles then
        names = []
    tracks, total, refused = [], 0.0, 0
    k = 0
    while total < want and len(tracks) < most and refused < TRACK_TRIES:
        sound = sounds[k % len(sounds)]
        prompt = (f"Instrumental only, no vocals, no singing, no spoken words. {sound}. A complete track of about "
                  "2 to 3 minutes with a gentle start and a soft, clean ending; calm, steady, no sudden loud parts.")
        out = os.path.join(job_dir, f".mix_t{k + 1:02d}.mp3")
        k += 1
        try:
            it = client.interactions.create(model=ms.LYRIA_MODEL, input=prompt)
            audio = it.output_audio
            if not audio or not audio.data:
                raise RuntimeError("no audio")
            with open(out, "wb") as f:
                f.write(base64.b64decode(audio.data))
        except Exception as e:  # noqa: BLE001 — a refused or failed track: try the next sound
            refused += 1
            log(f"   ℹ️ Track {k} not made ({type(e).__name__}: {str(e)[:80]}).")
            continue
        refused = 0
        secs = ms.media_seconds(out)
        if secs < MIN_TRACK_SECONDS:
            continue
        title = (names[len(tracks)] if len(tracks) < len(names) else f"{mood['name']} {len(tracks) + 1}")[:40]
        tracks.append({"title": title, "audio": out, "seconds": secs, "lines": []})
        total += secs + GAP
        log(f"   🎼 Track {len(tracks)}: \"{title}\" ({secs:.0f} s), {clock(total)} so far.")
    return tracks


def painting(client, mood, out):
    """The instrumental mix's one picture (16:9, AI), or None."""
    from google.genai import types
    import thumbnail
    prompt = (f"{mood.get('picture') or mood['name']}. Wide 16:9, soft cinematic light, calm and beautiful, rich "
              "but gentle colours, a painting; no text, letters, logos or watermarks, no real or famous person.")
    try:
        r = client.models.generate_content(
            model=thumbnail.IMAGE_MODEL, contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                               image_config=types.ImageConfig(aspect_ratio="16:9", image_size="2K")))
        for part in r.parts or []:
            if part.inline_data is not None and part.inline_data.data:
                with open(out, "wb") as f:
                    f.write(part.inline_data.data)
                return out
    except Exception as e:  # noqa: BLE001 — the gradient stands in
        print(f"   ℹ️ No painting for the mix ({type(e).__name__}).")
    return None


def song_tracks(dirs):
    import music_moods
    root = os.path.realpath(music_moods.ARCHIVE_DIR)
    out = []
    for d in dirs:
        if not os.path.realpath(d).startswith(root + os.sep):
            continue                      # only the song archive's own folders

        try:
            with open(os.path.join(d, "info.json"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        audio = os.path.join(d, "song.mp3")
        if not os.path.isfile(audio):
            continue
        import music_shorts as ms
        pic = os.path.join(d, "picture.jpg")
        out.append({"title": info.get("title") or "Untitled", "audio": audio, "seconds": ms.media_seconds(audio),
                    "lines": info.get("lines") or [], "picture": pic if os.path.isfile(pic) else None,
                    "colors": info.get("colors") or [], "dir": d})
    return [t for t in out if t["seconds"] >= MIN_TRACK_SECONDS]


def mix_title(mood, vol, n, total, instrumental):
    name = mood["name"]
    minutes = max(1, round(total / 60))
    if instrumental:
        return f"{name} Mix {mood.get('emoji', '')} Vol. {vol} | {minutes} Minutes of Calm AI Music".replace("  ", " ")[:100]
    return f"{name} Mix {mood.get('emoji', '')} Vol. {vol} | {n} AI Songs with Lyrics ({minutes} min)".replace("  ", " ")[:100]


def describe(mood, tracks, starts, instrumental, handle):
    tags = " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", t.title().replace(" ", "")) for t in (mood.get("tags") or [])[:4])
    lines = [(f"{mood['name']} {mood.get('emoji', '')}: {len(tracks)} original AI "
              f"{'tracks' if instrumental else 'songs'} in one mix, back to back."
              + ("" if instrumental else " Lyrics on screen.")).replace("  ", " "),
             "", "Tracklist:"] + [f"{clock(a)} {t['title']}" for t, a in zip(tracks, starts)]
    lines += ["", "Every song is original and AI-generated: "
              + ("music made with Google Lyria." if instrumental
                 else "lyrics written with AI, music and vocals made with Google Lyria."),
              "", f"New mixes every week{(': ' + handle) if handle else ''} 🔔", "", f"{tags} #aimusic".strip()]
    return "\n".join(lines)


def thumb(picture, mood, vol, out, colors=("#1B1030", "#05040A")):
    """1280x720: the mix's first picture with the mix name big on the left."""
    try:
        from PIL import Image
        import thumbnail as th
        if picture and os.path.isfile(picture):
            im = Image.open(picture).convert("RGB")
        else:
            im = Image.new("RGB", (th.THUMB_W, th.THUMB_H), tuple(int(colors[0][i:i + 2], 16) for i in (1, 3, 5)))
        s = max(th.THUMB_W / im.width, th.THUMB_H / im.height)
        im = im.resize((max(th.THUMB_W, round(im.width * s)), max(th.THUMB_H, round(im.height * s))))
        x, y = (im.width - th.THUMB_W) // 2, (im.height - th.THUMB_H) // 2
        im = im.crop((x, y, x + th.THUMB_W, y + th.THUMB_H))
        text = f"{mood['name'].upper()} MIX VOL {vol}"
        th.burn_thumbnail_text(im.convert("RGBA"), text, "left", "yellow").convert("RGB").save(out, "JPEG", quality=90)
        return out
    except Exception as e:  # noqa: BLE001 — YouTube picks a frame
        print(f"   ℹ️ No mix thumbnail ({type(e).__name__}).")
        return None


def run(output_dir, pipeline):
    import music_moods
    mood_key = re.sub(r"[^a-z0-9_]", "", (os.environ.get("MUSIC_MIX") or "").lower())
    try:
        mood = json.loads(os.environ.get("MUSIC_MIX_MOOD") or "{}") or music_moods.all_moods({}).get(mood_key)
        dirs = [str(d) for d in json.loads(os.environ.get("MUSIC_MIX_SONGS") or "[]")]
    except ValueError:
        mood, dirs = music_moods.all_moods({}).get(mood_key), []
    if not mood:
        raise RuntimeError(f"Unknown mood for the mix: {mood_key!r}.")
    minutes = int(float(os.environ.get("MUSIC_MIX_MINUTES") or music_moods.MIX_MINUTES))
    budget = float(os.environ.get("MUSIC_MIX_BUDGET") or music_moods.MIX_BUDGET)
    vol = max(1, int(os.environ.get("MUSIC_MIX_VOL") or 1))
    instrumental = bool(mood.get("instrumental"))
    cfg = fl.settings()
    handle = cfg["handle"] or ""
    client = kit.gemini()
    started = time.time()
    print(f"🎧 {mood['name']} mix, vol. {vol}: {'making its tracks' if instrumental else f'{len(dirs)} songs'}...")
    picture = None
    if instrumental:
        tracks = make_tracks(client, mood, minutes, budget, output_dir)
        picture = painting(client, mood, os.path.join(output_dir, ".mix_painting.png"))
        for t in tracks:
            t["picture"] = picture
    else:
        tracks = song_tracks(dirs)
        if any(not t.get("picture") for t in tracks):
            # A song kept without a picture (no footage, no cover) gets the mood's painting, not a bare gradient.
            picture = painting(client, mood, os.path.join(output_dir, ".mix_painting.png")) if client else None
            for t in tracks:
                t["picture"] = t.get("picture") or picture
    total = sum(t["seconds"] + GAP for t in tracks)
    if total < MIX_MIN_SECONDS:
        raise RuntimeError(f"Only {clock(total)} of music for the {mood['name']} mix; it waits for more.")
    stem = kit.neutral_stem("Mix")
    os.makedirs(os.path.join(output_dir, ".mix_seg"), exist_ok=True)
    starts, t0 = [], 0.0
    for t in tracks:
        starts.append(t0)
        t0 += t["seconds"] + GAP
    print(f"🎬 Rendering {len(tracks)} chapters ({clock(total)})...")
    wavs = []

    def one(k):
        t = tracks[k]
        d = t["seconds"] + GAP
        wav = _track_audio(t["audio"], os.path.join(output_dir, ".mix_seg", f"a{k:03d}.wav"), t["seconds"])
        seg = segment(output_dir, t.get("picture"), wav, d, song_events(t, k, len(tracks), f"{mood['name']} mix", d),
                      os.path.join(output_dir, ".mix_seg", f"v{k:03d}.mp4"), t.get("colors") or ("#1B1030", "#05040A"))
        return wav, seg
    with ThreadPoolExecutor(max_workers=2) as pool:
        done = list(pool.map(one, range(len(tracks))))
    wavs = [w for w, _s in done]
    with open(os.path.join(output_dir, ".mix_v.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"file '{os.path.relpath(s, output_dir).replace(os.sep, '/')}'\n" for _w, s in done))
    with open(os.path.join(output_dir, ".mix_a.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"file '{os.path.relpath(w, output_dir).replace(os.sep, '/')}'\n" for w in wavs))
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", ".mix_v.txt",
                        "-f", "concat", "-safe", "0", "-i", ".mix_a.txt", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                        os.path.basename(final)], cwd=output_dir, capture_output=True, text=True, errors="replace",
                       timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"mix join failed: {r.stderr.strip()[-300:]}")
    kit.level(final)                     # the whole mix to -14 LUFS, as every Short and long video
    first_pic = next((t.get("picture") for t in tracks if t.get("picture")), None)
    thumbnail_path = thumb(first_pic, mood, vol, os.path.join(output_dir, "thumbnail.jpg"),
                           tracks[0].get("colors") or ("#1B1030", "#05040A"))
    title = mix_title(mood, vol, len(tracks), total, instrumental)
    desc = describe(mood, tracks, starts, instrumental, handle)
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": title, "seo_title": title, "seo_description": desc,
            "seo_tags": list(dict.fromkeys((mood.get("tags") or []) + ["ai music", "music mix", "playlist"]))[:15],
            "why": f"{mood['name']} mix vol. {vol}", "predicted_score": 80, "genre": "music",
            "ai_voice": "AI music" + ("" if instrumental else " and vocals") + " (Google Lyria)", "ai_made": True,
            "comment_question": "Which track should be in the next mix? 🎧",
            "thumbnail_file": os.path.basename(thumbnail_path) if thumbnail_path else None,
            "chapters": [{"title": t["title"], "at": round(a, 2)} for t, a in zip(tracks, starts)],
            "mix": {"mood": mood_key, "vol": vol, "tracks": len(tracks), "instrumental": instrumental,
                    "songs": [t.get("dir") for t in tracks if t.get("dir")],
                    "usd": round(TRACK_USD * len(tracks), 2) if instrumental else 0.0}}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "music", "format": "16:9"})
    if not instrumental:
        music_moods.mark_mixed([t["dir"] for t in tracks if t.get("dir")], os.path.basename(os.path.normpath(output_dir)))
    print(f"   ⏱️ Mix made in {(time.time() - started) / 60:.1f} min.")
