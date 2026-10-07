"""Song Shorts (CONTENT_GENRE=songs).

Two ways, decided by whether the user owns the music (SONG_OWNED):

- **A song you do not own (default).** The only route YouTube's own pages
  support: the Short is made here with NO sound, and the user adds the song
  in the YouTube app (Create, upload, Sound). A song added with the Shorts
  creation tools gets a "special Content ID claim" that cannot be disputed
  (support.google.com/youtube/answer/13053317) and the Short shares its
  revenue with the music (answer/12504220); a song baked into the file gets a
  standard claim instead. No lyrics on screen in this mode: no YouTube page
  says the in-app licence covers them, and lyrics are a separate work (Delhi
  HC, May 2026). The picture is ours: a mood gradient, a spinning disc, a
  wave line that moves with the music (computed from the song, then the
  sound is dropped) and a relatable Roman Urdu line written for the mood.
- **Music you own or that is royalty-free (SONG_OWNED=1).** The sound stays,
  the lyrics show line by line, and 2-5 links make one mashup Short.

Where to cut is decided here, not by the model: asked for sections of the
whole song, Gemini returned 67-85 s "sections" for 25-45 and lyric times past
the end of a 276 s track (8-oct-2026). So Gemini hears the whole song once
for the mood, colours and rough hook positions; the cut is the loudest
stretch away from the intro and outro (a chorus is the loudest part of most
songs), nudged toward those hooks and snapped to a loudness rise; then
Gemini hears only that stretch for its title, line and lyric times, which on
30-40 s of audio land where the words are.

Env: SONG_OWNED, SONG_URLS (mashup, owned only), CLIP_TARGET_MAX (shorts per
song, default 2), CLIP_MIN/MAX_SECONDS (section length, default 25-45).
"""
import os
import shutil
import subprocess
from typing import List

import numpy as np
from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

DEFAULT_SHORTS = 2
DEFAULT_MIN, DEFAULT_MAX = 25, 45
MASHUP_SECONDS = 58
SNAP_WINDOW = 1.5
FADE = 1.0
# Where a cut may start, as a share of the song: never the intro or the outro.
EARLIEST, LATEST = 0.08, 0.95
HOOK_BONUS = 0.15


class LyricLine(BaseModel):
    start: float
    end: float
    text: str


class SongRead(BaseModel):
    song_title: str
    mood: str
    colors: List[str]
    hooks: List[float]


class PartRead(BaseModel):
    title: str
    vibe: str
    lyrics: List[LyricLine]


class Section(BaseModel):
    start: float
    end: float
    title: str = ""
    vibe: str = ""
    lyrics: List[LyricLine] = []


SONG_PROMPT = """This is the audio of the YouTube video titled "{yt_title}" ({seconds:.0f} seconds).
Return:
- song_title: the song's name taken from that title (no singer, no label, no series or
  season), as people search it.
- mood: one word.
- colors: 3 hex colours (#RRGGBB) that fit the mood.
- hooks: up to 4 times in seconds where the chorus or the main hook starts."""

PART_PROMPT = """This {secs:.0f}-second clip is part of the song "{song}" ({mood} mood).
Return:
- title: max 45 characters, Roman Urdu in Latin letters, a feeling or situation the
  song fits ("Jab woh online ho par reply na kare"), never the lyrics, no emoji.
- vibe: one relatable line in Roman Urdu, max 70 characters, original words that fit
  the mood (the kind people put on a status), never the lyrics.
- lyrics: every sung line in THIS clip, with start and end in seconds counted from the
  start of this clip (0 to {secs:.0f}), written in Roman Urdu / Latin letters. Empty for
  an instrumental clip.
Latin letters only, never Devanagari or Arabic script."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is an aesthetic song Short: our own "
               "animated visual for the song \"{title}\" ({mood} mood){how}. Ignore the comedy "
               "phrases and hashtags above and use music searches instead: the song name, the "
               "mood, 'song status', 'whatsapp status', 'aesthetic', 'lofi' only if it fits. "
               "The song name is welcome; never name the singer, composer or music label "
               "(creator is \"\"). The description tells the story of the feeling, not the "
               "song's facts.")

STYLES = [
    kit.style("SgTitle", "Montserrat ExtraBold", 70, outline=0, shadow=3),
    kit.style("SgSmall", "Montserrat ExtraBold", 34),
    kit.style("SgPill", "Montserrat ExtraBold", 34, "#14142B", spacing=2),
    kit.style("SgVibe", "Montserrat ExtraBold", 62, outline=5, shadow=3),
    kit.style("SgLyric", "Montserrat ExtraBold", 64, fl.GOLD, outline=5, shadow=3, secondary="#FFFFFF"),
]
CX = kit.OUT_W // 2
DISC_Y = 860


def owned():
    return os.environ.get("SONG_OWNED", "0").strip().lower() in ("1", "true", "yes")


def _env_int(name, default):
    try:
        return int(float(os.environ.get(name) or default))
    except ValueError:
        return default


def _mmss(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def loudness(path, rate=20):
    """RMS per 1/rate s of the whole track (16 kHz mono)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True, timeout=300).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    hop = 16000 // rate
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-9), rate


def snap(rms, rate, t):
    """The strongest loudness rise within SNAP_WINDOW of t (a beat or phrase start)."""
    a = max(1, int((t - SNAP_WINDOW) * rate))
    b = min(len(rms) - 1, int((t + SNAP_WINDOW) * rate))
    if b <= a:
        return t
    rise = np.diff(rms[a - 1:b + 1])
    if rise.max() <= 0.05 * (rms.max() or 1.0):
        return t  # nothing that sounds like a start nearby: keep the cut
    return round((a + int(np.argmax(rise))) / rate, 2)


def pick_windows(rms, rate, duration, n, length, hooks=()):
    """Start times of the n loudest non-overlapping stretches of ``length`` s,
    away from the intro and outro, nudged toward the model's hook times."""
    per_s = np.array([rms[i * rate:(i + 1) * rate].mean() for i in range(int(len(rms) // rate))])
    if not len(per_s):
        return [0.0]
    per_s = per_s / (per_s.max() or 1.0)
    length = int(round(length))
    lo = int(duration * EARLIEST)
    hi = int(min(duration * LATEST, duration) - length)
    if hi <= lo:
        return [round(max(0.0, (duration - length) / 2), 2)]
    # The bonus fades over 6 s, so among equally loud starts the one on a hook wins.
    scores = {s: float(per_s[s:s + length].mean())
              + max([HOOK_BONUS * (1 - abs(s - h) / 6) for h in hooks if abs(s - h) <= 6] or [0.0])
              for s in range(lo, hi + 1)}
    chosen = []
    for s in sorted(scores, key=scores.get, reverse=True):
        if all(abs(s - c) >= length + 3 for c in chosen):
            chosen.append(s)
        if len(chosen) == n:
            break
    return sorted(snap(rms, rate, float(s)) for s in chosen)


def _mp3(path, start=None, secs=None):
    out = f"{path}.{int(start or 0)}.gemini.mp3"
    cut = (["-ss", f"{start:.3f}", "-t", f"{secs:.3f}"] if start is not None else [])
    subprocess.run(["ffmpeg", "-y", "-v", "error", *cut, "-i", path, "-ac", "1", "-ar", "16000",
                    "-b:a", "48k", out], check=True, timeout=300)
    return out


def _hear(client, schema, mp3, prompt):
    from google.genai import types
    try:
        with open(mp3, "rb") as f:
            audio = types.Part.from_bytes(data=f.read(), mime_type="audio/mp3")
        return kit.ask_json(client, schema, [audio, prompt])
    finally:
        os.remove(mp3)


def read_song(client, path, seconds, yt_title):
    return _hear(client, SongRead, _mp3(path),
                 SONG_PROMPT.format(yt_title=yt_title.replace('"', "'"), seconds=seconds))


def read_part(client, path, start, secs, song, mood):
    part = _hear(client, PartRead, _mp3(path, start, secs),
                 PART_PROMPT.format(secs=secs, song=song.replace('"', "'"), mood=mood))
    part.lyrics = [ln for ln in part.lyrics
                   if 0 <= ln.start < secs and ln.end > ln.start and ln.text.strip()]
    for ln in part.lyrics:
        ln.end = min(ln.end, secs)
    return part


def disc_events(t0, t1):
    """A vinyl that spins for the whole section. A dot circles the label so
    the turn shows; a drawing with negative coordinates (a two-sided shine)
    landed off the disc, since libass places a drawing by its bounding box."""
    turns = (t1 - t0) / 4.0
    spin = rf"\t(0,{int((t1 - t0) * 1000)},\frz{-360 * turns:.0f})"
    ev = []
    for r, col, alpha in ((300, "&H101010&", "10"), (270, "&H1E1E1E&", "20"), (220, "&H101010&", "10"),
                          (170, "&H1E1E1E&", "20")):
        ev.append(kit.dialogue(2, t0, t1, "Shape",
                               rf"{{\an5\pos({CX},{DISC_Y})\1c{col}\1a&H{alpha}&\bord0\shad0\p1}}"
                               rf"{fl._circle(r)}{{\p0}}"))
    ev.append(kit.dialogue(3, t0, t1, "Shape",
                           rf"{{\an5\pos({CX},{DISC_Y})\1c{fl._ass_colour(fl.GOLD)}\bord0\shad0\p1}}"
                           rf"{fl._circle(80)}{{\p0}}"))
    for radius, size, alpha in ((240, 14, "60"), (195, 10, "90")):
        ev.append(kit.dialogue(4, t0, t1, "Shape",
                               rf"{{\an5\pos({CX},{DISC_Y - radius})\org({CX},{DISC_Y})\1c&HFFFFFF&"
                               rf"\1a&H{alpha}&\bord0\shad0{spin}\p1}}{fl._circle(size)}{{\p0}}"))
    ev.append(kit.dialogue(4, t0, t1, "Shape",
                           rf"{{\an5\pos({CX},{DISC_Y})\1c&H14142B&\bord0\shad0\p1}}{fl._circle(12)}{{\p0}}"))
    return ev


def lyric_events(lines, t_end):
    """Each sung line (clip time) lights up word by word over its own time."""
    ev = []
    for ln in lines:
        a, b = ln.start, min(ln.end, t_end)
        words = fl.clean_title(ln.text).split()
        if b <= a + 0.3 or not words:
            continue
        weights = [len(w) + 2 for w in words]
        body = " ".join(rf"{{\kf{max(1, round((b - a) * 100 * wt / sum(weights)))}}}{w}"
                        for w, wt in zip(words, weights))
        ev.append(kit.dialogue(5, a, b, "SgLyric", rf"{{\an5\pos({CX},1300)\fad(120,120)}}{body}"))
    return ev


def section_events(sec, song_title, seconds, show_lyrics):
    cfg = fl.settings()
    ev = disc_events(0, seconds)
    if cfg["handle"]:
        ev.append(kit.dialogue(1, 0, seconds, "SgSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{cfg['handle']}"))
    if sec.title:
        ev.append(kit.dialogue(1, 0, seconds, "SgTitle",
                               rf"{{\an5\pos({CX},380)\fad(150,0)\fscx70\fscy70\t(0,260,\fscx106\fscy106)"
                               rf"\t(260,400,\fscx100\fscy100)}}{fl.clean_title(sec.title)}"))
    name = fl.clean_title(song_title)[:30]
    if name:
        w = max(300, 24 * len(name) + 120)
        ev.append(kit.dialogue(3, 0.2, seconds, "Shape",
                               rf"{{\an7\pos({CX - w // 2},{DISC_Y - 400})\1c&HFFFFFF&\bord0\shad0"
                               rf"\fad(200,0)\p1}}{fl._round_rect(w, 70, 35)}{{\p0}}"))
        ev.append(kit.dialogue(4, 0.2, seconds, "SgPill",
                               rf"{{\an5\pos({CX},{DISC_Y - 365})\fad(200,0)}}{name.upper()}"))
    lyrics = lyric_events(sec.lyrics, seconds) if show_lyrics else []
    if lyrics:
        ev += lyrics
    elif sec.vibe:
        # No lyrics shown (a song added in the app, or an instrumental part).
        ev.append(kit.dialogue(5, 0.6, seconds, "SgVibe",
                               rf"{{\an5\pos({CX},1300)\fad(300,0)}}{fl.clean_title(sec.vibe)}"))
    return ev


def _short(out_path, audio, sec, song_title, colors, keep_sound):
    """Render one section as a short. Returns its length."""
    cfg = fl.settings()
    body = sec.end - sec.start
    card_ev, card_sfx = kit.end_card(body, cfg["outro_seconds"])
    if not keep_sound:
        card_sfx = []  # truly silent: the song added in the app is all you hear
    total = body + (cfg["outro_seconds"] if card_ev else 0.0)
    events = section_events(sec, song_title, body, keep_sound) + card_ev
    kit.render(out_path, total, colors, events, STYLES, sfx=card_sfx,
               music=(audio, sec.start, 1.0), visualizer=True, silent=not keep_sound,
               fades=(FADE, body) if keep_sound else None, music_seconds=body)
    return total


def _colors(read):
    bg = fl.settings()["bg"]
    return [bg] + [kit.blend(c, bg, 0.45) for c in (read.colors or [])[:2]]


def _get_audio(url, vdir, pipeline):
    import section_fetch
    try:
        return section_fetch.fetch_audio(url, vdir)
    except Exception as e:  # noqa: BLE001 — the full download is the proven path
        print(f"   ℹ️ Audio-only download failed ({type(e).__name__}); downloading the video instead.")
        path, title = pipeline.download_youtube_video(url, vdir)
        seconds = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            timeout=60).decode().strip() or 0)
        return title, seconds, path


def run(urls, output_dir, pipeline):
    import seo_copy
    keep = owned()
    urls = [u for u in urls if u][:5]
    if len(urls) > 1 and not keep:
        raise RuntimeError("A mashup of several songs needs music you own or royalty-free music: "
                           "tick 'I own this music'. With songs you add in the YouTube app, use one link.")
    lo = _env_int("CLIP_MIN_SECONDS", DEFAULT_MIN)
    hi = max(lo + 5, _env_int("CLIP_MAX_SECONDS", DEFAULT_MAX))
    n = min(3, max(1, _env_int("CLIP_TARGET_MAX", DEFAULT_SHORTS)))
    mashup = len(urls) > 1
    length = (min(hi, MASHUP_SECONDS / len(urls) + FADE) if mashup else (lo + hi) / 2)
    client = kit.gemini()
    print(f"🎵 Song short{'s' if n > 1 and not mashup else ''}: "
          + ("keeping the sound (you own it)" if keep else "silent video, add the song in the YouTube app"))

    songs = []
    for k, url in enumerate(urls):
        vdir = os.path.join(output_dir, f".song_{k + 1}")
        os.makedirs(vdir, exist_ok=True)
        yt_title, seconds, audio = _get_audio(url, vdir, pipeline)
        read = read_song(client, audio, seconds, yt_title)
        rms, rate = loudness(audio)
        starts = pick_windows(rms, rate, seconds, 1 if mashup else n, length, read.hooks)
        sections = []
        for start in starts:
            end = min(seconds, start + length)
            part = read_part(client, audio, start, end - start, read.song_title, read.mood)
            sections.append(Section(start=start, end=end, title=part.title, vibe=part.vibe,
                                    lyrics=part.lyrics))
        print(f"   🎯 {read.song_title} ({read.mood}): "
              + ", ".join(f"{_mmss(s.start)}-{_mmss(s.end)}" for s in sections))
        songs.append((audio, read, sections))

    stem = kit.neutral_stem("Song")
    clips = []
    if mashup:
        clips.append(_mashup(output_dir, stem, songs))
    else:
        audio, read, sections = songs[0]
        for i, sec in enumerate(sections):
            final = os.path.join(output_dir, f"{stem}_clip_{i + 1}.mp4")
            print(f"🎬 Rendering short {i + 1} ({sec.end - sec.start:.0f}s)...")
            total = _short(final, audio, sec, read.song_title, _colors(read), keep)
            clip = {"start": sec.start, "end": sec.end, "seconds": round(total, 3), "file": final,
                    "video_title_for_youtube_short": fl.clean_title(sec.title),
                    "viral_hook_text": sec.vibe,
                    "why": f"{read.mood} mood, {_mmss(sec.start)}-{_mmss(sec.end)} of the song",
                    "predicted_score": 90 - i, "genre": "songs", "captions": None}
            if not keep:
                clip["in_app_song"] = {"title": read.song_title, "start": _mmss(sec.start),
                                       "seconds": round(sec.end - sec.start)}
            clips.append(clip)
    # Lyrics in song time, for the SEO pass to read what each short is about.
    lyrics = {"language": "ur", "segments": [
        {"start": s.start + ln.start, "end": s.start + ln.end, "text": ln.text,
         "words": [{"word": " " + w, "start": s.start + ln.start, "end": s.start + ln.end}
                   for w in ln.text.split()]}
        for _, _, secs in songs for s in secs for ln in s.lyrics]}
    first = songs[0][1]
    how = (", with the song's own sound and lyrics" if keep
           else ", the song itself is added in the YouTube app")
    seo_copy.apply(clips, lyrics, source_title=first.song_title,
                   context=SEO_CONTEXT.format(title=first.song_title, mood=first.mood, how=how))
    kit.finish(output_dir, stem, clips, None, pipeline, extra={"genre": "songs"})
    for k in range(len(urls)):
        shutil.rmtree(os.path.join(output_dir, f".song_{k + 1}"), ignore_errors=True)


def _mashup(output_dir, stem, songs):
    """2-5 owned songs, one section each, joined with crossfades into one short."""
    parts = [(audio, sections[0], read) for audio, read, sections in songs]
    joined = os.path.join(output_dir, f".{stem}_mashup.m4a")
    inputs, graph = [], []
    for k, (audio, sec, _) in enumerate(parts):
        inputs += ["-ss", f"{sec.start:.3f}", "-t", f"{sec.end - sec.start:.3f}", "-i", audio]
        graph.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo[p{k}]")
    last = "[p0]"
    for k in range(1, len(parts)):
        graph.append(f"{last}[p{k}]acrossfade=d={FADE}[m{k}]")
        last = f"[m{k}]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph),
                    "-map", last, "-c:a", "aac", "-b:a", "192k", joined], check=True, timeout=600)
    # Each part's text on the joined timeline.
    cfg = fl.settings()
    events, t = [], 0.0
    for audio, sec, read in parts:
        length = sec.end - sec.start
        events += [_shift(e, t) for e in section_events(sec, read.song_title, length, True)]
        t += length - FADE
    body = t + FADE
    card_ev, card_sfx = kit.end_card(body, cfg["outro_seconds"])
    total = body + (cfg["outro_seconds"] if card_ev else 0.0)
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    print(f"🎬 Rendering the mashup ({body:.0f}s, {len(parts)} songs)...")
    kit.render(final, total, _colors(parts[0][2]), events + card_ev, STYLES, sfx=card_sfx,
               music=(joined, 0.0, 1.0), visualizer=True, fades=(FADE, body), music_seconds=body)
    os.remove(joined)
    first = parts[0][1]
    return {"start": 0.0, "end": round(body, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": fl.clean_title(first.title), "viral_hook_text": first.vibe,
            "why": f"Mashup of {len(parts)} songs", "predicted_score": 90, "genre": "songs",
            "captions": None, "mashup_parts": [r.song_title for _, _, r in parts]}


def _shift(event, by):
    """Move a Dialogue line ``by`` seconds later."""
    head = event.split(",", 3)
    a, b = (_secs(x) + by for x in head[1:3])
    return f"{head[0]},{fl._ts(a)},{fl._ts(b)},{head[3]}"


def _secs(ts):
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
