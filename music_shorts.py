"""AI songs in English as Shorts (CONTENT_GENRE=music), up to a minute.

Gemini writes an original song (title, lyrics, musical direction, a cover
scene); Google's Lyria sings it (lyria-3.5 on the Gemini API: about $0.08 a
song, ~1 min to make, vocals and our lyrics included, SynthID-watermarked,
14-oct-2026); Gemini paints one 9:16 cover; Whisper on this laptop hears
when each line is sung (small model, CPU: every line of a test song landed
within a second, 54 s with the model load), and the Short is a lyric video:
the cover drifting slowly, the line being sung large with its words filling
gold, the next one dimmed, a gold wave line moving with the music.

Lyria refuses requests for an artist's voice or existing lyrics, and the
prompt never names an artist. The upload carries YouTube's altered or
synthetic content label (the voice is realistic and made by AI) and the
description says the song is AI-made.

Env: MUSIC_STYLE, MUSIC_THEME, MUSIC_VOCAL (female/male), MUSIC_AVOID (JSON list of titles already
made), MUSIC_MODEL (Lyria model), MUSIC_WHISPER (Whisper model size).
"""
import base64
import difflib
import json
import os
import re
import subprocess
from typing import List

from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

CX = kit.OUT_W // 2
LYRIA_MODEL = os.environ.get("MUSIC_MODEL") or "lyria-3.5"
MAX_SONG = 58.0      # Shorts music of a minute at most (owner's ask), end card after
# What a song Short uses: the chorus first, ~half a minute, so it loops back into the hook.
# Starting on the verse with a 1.2 s fade-in, viewers left after a median 2 s (4.5% watched,
# 13 Shorts, learning stats 22-oct-2026).
SHORT_SONG = 32.0
FADE = 0.15
SING_TRIES = 3
# Mood footage under the lyrics: a stranger singing or playing would look like
# a music video of someone else's song. A woman as the song's character is
# what the owner asked for (19-oct-2026: the songs had only scenery, no one
# to feel the song through); stock models signed releases for this use.
# Classy, never suggestive: YouTube age-restricts sexually suggestive Shorts,
# and an age-restricted Short is left out of the Shorts feed.
FOOTAGE_RULE = ("Mood footage that fits the song's feeling. In a love or heartbreak song a beautiful young woman "
                "is the song's character: at least every other line's search shows her, with the line's feeling "
                "(\"sad woman window rain\", \"woman walking alone night city\", \"woman red dress sunset\", "
                "\"couple holding hands beach\"); the lines between may show the objects and places the lyrics "
                "name. When choosing clips, a woman whose clip fits the line's feeling beats an object or an "
                "empty place, and a line whose search asked for a woman never gets a man. She is an unnamed "
                "stock model, not a person the song is about, so a close shot of her is fine. Stylish and classy, never revealing, lingerie or suggestive. Other songs: city lights, "
                "rain, roads, sea, sky, nature. Never a person singing, rapping or playing an instrument, never "
                "text. ")
STYLES = ["upbeat pop", "lo-fi chill", "acoustic love song", "EDM dance pop", "R&B slow jam", "pop punk",
          "country pop", "indie folk", "afrobeats", "synthwave", "motivational anthem", "sad piano ballad",
          "heartbreak pop ballad", "romantic slow pop"]
THEMES = ["falling in love", "heartbreak", "summer nights", "late night drive", "best friends",
          "chasing dreams", "missing home", "first crush", "self-love", "rainy days", "gym motivation",
          "city lights", "long distance", "new beginnings", "dancing all night"]
# Romance and heartbreak are what the owner's viewers click (owner, 19-oct-2026):
# LOVE_SHARE of the songs take one of these, the rest any theme.
LOVE_THEMES = ["heartbreak", "falling in love", "first crush", "long distance", "she left without a goodbye",
               "missing her at 3 am", "one-sided love", "love at first sight", "moving on after a breakup",
               "a love I can't let go of", "first date butterflies", "the one that got away",
               "he never deserved her", "still waiting for your text"]
LOVE_SHARE = 0.75
FEMALE_SHARE = 0.65      # songs sung by a woman, to match the woman on screen


def pick_theme(rnd=None):
    import random
    rnd = rnd or random
    return rnd.choice(LOVE_THEMES if rnd.random() < LOVE_SHARE else THEMES)


class SongPlan(BaseModel):
    title: str
    youtube_title: str
    genre: str
    lyria_style: str
    verse: List[str]
    pre_chorus: List[str]
    chorus: List[str]
    image_prompt: str
    colors: List[str]
    description: str
    tags: List[str]
    hashtags: List[str]
    hook: str = ""


PLAN_PROMPT = """Write an ORIGINAL catchy English song for a YouTube Shorts music channel.
Style: {style}. Theme: {theme}. Lead vocal: {vocal}.
Love and heartbreak songs hit hardest when they feel real: one specific moment
(a text left on read, her perfume on his jacket, the last goodbye at the door),
told from the heart, with a chorus people want to send to someone.
It must work in under 60 seconds: one verse, a short pre-chorus, a big chorus that is
easy to sing along to and gets stuck in the head. Fresh images, no cliches stacked up,
nothing explicit, no brand or artist names, never copy or echo an existing song.
Never reuse these titles, already made: {avoid}
Return:
- title: max 30 characters.
- youtube_title: max 70 characters: a hook that makes people tap, then the song title.
  Hooks that work: the AI reveal (it IS an AI song, so it is true: "This AI song hits too
  hard 💔", "An AI wrote this about your ex"), or the moment the song is about ("When she
  leaves you on read"). A brand-new song title alone has no search demand. At most one
  emoji, no false claims.
- genre: 1-3 words.
- lyria_style: the musical direction for an AI music model in one sentence: genre,
  mood, tempo in BPM, main instruments, the lead vocal above and how it sings.
  Never name an artist or a song.
- verse: exactly 4 lines, 5-9 words each.
- pre_chorus: exactly 2 lines.
- chorus: exactly 4 lines, the title in one of them.
- image_prompt: a cover art scene for a vertical 9:16 picture that fits the song: for
  a love or heartbreak song a beautiful, elegant young woman as the song's character
  (a fictional person: her look, outfit, expression, the place, light and mood);
  otherwise a place, light and mood. Stylish and classy, never revealing or suggestive;
  no text, no letters, no logos, no real or famous person.
- colors: 2 hex colours (#RRGGBB) that match the cover's mood.
- description: 2 short sentences for YouTube about the song's feeling, in English.
- tags: 10-15 search tags (genre, mood, "new song 2026", "ai music"...).
- hashtags: 4 hashtags without the # sign.
- hook: 3-7 words shown BIG on screen for the first 2.5 seconds, before any lyric, so a
  scroller stays (most leave in the first 2 seconds, and many watch with the sound off):
  the moment as a POV ("POV: she left her earring behind"), a feeling people send to
  someone ("Send this to the one who left"), or the true AI reveal ("An AI wrote this
  heartbreak"). Not the title again, no emoji, no hashtags."""


def _avoid():
    try:
        return [str(x)[:60] for x in json.loads(os.environ.get("MUSIC_AVOID") or "[]")][-60:]
    except ValueError:
        return []


def plan(client, style, theme, vocal="a female lead singer"):
    from quiz_shorts import quiz_model
    p = kit.ask_json(client, SongPlan, PLAN_PROMPT.format(style=style, theme=theme, vocal=vocal,
                                                          avoid=", ".join(_avoid()) or "(none yet)"),
                     model=quiz_model())
    if len(p.verse) < 2 or len(p.chorus) < 2:
        raise RuntimeError("The song came back without lyrics; try again.")
    return p


def lyria_prompt(p):
    parts = [f"{p.lyria_style}. A complete short song of about 50 seconds: vocals start within the "
             "first 2 seconds (no long intro), then verse, pre-chorus and chorus, ending cleanly.", "",
             "[Verse]", *p.verse]
    if p.pre_chorus:
        parts += ["", "[Pre-Chorus]", *p.pre_chorus]
    parts += ["", "[Chorus]", *p.chorus]
    return "\n".join(parts)


def sing(client, p, out_path):
    """Lyria makes the song; returns the mp3 path."""
    it = client.interactions.create(model=LYRIA_MODEL, input=lyria_prompt(p))
    audio = it.output_audio
    if not audio or not audio.data:
        raise RuntimeError("Lyria returned no song (it refuses some requests); trying another next time.")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(audio.data))
    return out_path


def cover(client, p, out_path):
    """One 9:16 cover picture, or None."""
    from google.genai import types
    model = os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image"
    prompt = (f"{p.image_prompt}. Vertical 9:16 album cover art, cinematic, rich colour, soft depth of "
              "field, beautiful light. A fictional woman may be the song's character: elegant, fully clothed, "
              "never suggestive. No text, no letters, no logos, no watermark, no famous or real person.")
    try:
        r = client.models.generate_content(
            model=model, contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                               image_config=types.ImageConfig(aspect_ratio="9:16", image_size="1K")))
        for part in r.parts or []:
            if part.inline_data is not None and part.inline_data.data:
                with open(out_path, "wb") as f:
                    f.write(part.inline_data.data)
                return out_path
    except Exception as e:  # noqa: BLE001 — the gradient stands in
        print(f"   ℹ️ No cover picture ({type(e).__name__}: {str(e)[:120]}).")
    return None


def hear(song_path, lyrics=()):
    """Whisper's sung lines: [(text, start, end, [(word, start, end)])].

    Over music Whisper calls whole 30 s windows "no speech" and drops them (a
    test song lost its verse, 14-oct-2026), and it mishears sung words. Our
    own lyrics as the prompt and no silence threshold got every line of that
    song, in 10 s."""
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ.get("MUSIC_WHISPER") or "small", device="cpu", compute_type="int8",
                         cpu_threads=4)
    segs, _info = model.transcribe(song_path, language="en", word_timestamps=True, vad_filter=False,
                                   initial_prompt=" ".join(lyrics)[:800] or None, no_speech_threshold=None,
                                   log_prob_threshold=None, condition_on_previous_text=False)
    out = []
    for s in segs:
        text = s.text.strip()
        if not text or re.fullmatch(r"[\[(]?\s*(music|instrumental|applause)\s*[\])]?\.?", text, re.I):
            continue
        out.append((text, float(s.start), float(s.end),
                    [(w.word.strip(), float(w.start), float(w.end)) for w in (s.words or [])]))
    return out


def _norm(text):
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).split()


NEXT_BONUS = 0.25    # the lyric due next wins a close call ("Pain in our sin..." = "Painting our silhouettes")
MATCH_MIN = 0.5


def _score(heard, line):
    """Likeness by words and by letters, whichever is higher (misheard words
    still share most letters)."""
    hw, lw = _norm(heard), _norm(line)
    by_words = difflib.SequenceMatcher(None, hw, lw).ratio()
    by_letters = difflib.SequenceMatcher(None, " ".join(hw), " ".join(lw)).ratio()
    return max(by_words, by_letters)


def _best(text, lyrics, nxt):
    s, k = max((_score(text, ly) + (NEXT_BONUS if k == nxt else 0.0), k) for k, ly in enumerate(lyrics))
    return (k, s) if s >= MATCH_MIN else (None, s)


def _split(text, a, b, words, lyrics, nxt):
    """A heard segment that is two lyric lines sung together, cut in two at
    the word where the first line ends (Whisper's word times)."""
    if len(words) < 4 or len(lyrics) < 2:
        return [(text, a, b)]
    _k, one = _best(text, lyrics, nxt)
    pairs = [(_score(text, lyrics[k] + " " + lyrics[k + 1]) + (NEXT_BONUS if k == nxt else 0.0), k)
             for k in range(len(lyrics) - 1)]
    two, k = max(pairs)
    if two < max(one, MATCH_MIN) + 0.1:
        return [(text, a, b)]
    n1, n2 = len(_norm(lyrics[k])), len(_norm(lyrics[k + 1]))
    cut = max(1, min(len(words) - 1, round(len(words) * n1 / max(1, n1 + n2))))
    first, second = words[:cut], words[cut:]
    return [(" ".join(w for w, _s, _e in first), first[0][1], first[-1][2]),
            (" ".join(w for w, _s, _e in second), second[0][1], second[-1][2])]


def align(lyrics, heard):
    """Each heard line paired with the lyric it is, so the screen shows our
    spelling at Whisper's times. Lyrics run in order (a repeated chorus
    starts over), so the one due next gets a bonus; a heard line that is
    like none of them (an ad-lib, a mishearing) is not shown at all: wrong
    words on screen are worse than a gap."""
    lines, nxt = [], 0
    for text, a, b, words in heard:
        for piece, pa, pb in _split(text, a, b, words, lyrics, nxt):
            k, _s = _best(piece, lyrics, nxt)
            if k is None:
                continue
            lines.append((lyrics[k], pa, pb))
            nxt = (k + 1) % len(lyrics)
    return lines


def window(lines, song_seconds, longest=MAX_SONG, chorus=None):
    """(start, end) of the part used: from just before the first sung line
    (or the first ``chorus`` line: a dance Short is the hook only), ending
    after the last line that finishes by ``longest``."""
    first = next((a for t, a, _b in lines if chorus and t == chorus), None)
    if first is not None and song_seconds - first > 6:
        start = max(0.0, first - 0.8)
    else:
        start = max(0.0, lines[0][1] - 1.0) if lines and lines[0][1] > 3.0 else 0.0
    if song_seconds - start <= longest:
        return start, song_seconds
    ends = [b for _t, _a, b in lines if b - start <= longest - 1.5]
    end = (max(ends) + 1.5) if ends else start + longest
    return start, min(song_seconds, end, start + longest)


def media_seconds(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=nk=1:nw=1", path], capture_output=True, text=True, timeout=60)
    return float(r.stdout.strip() or 0)


LYRIC_STYLES = [
    kit.style("MuSmall", "Montserrat ExtraBold", 34, "#FFFFFF", shadow=2),
    kit.style("MuPill", "Montserrat ExtraBold", 34, "#14142B", spacing=2),
    kit.style("MuTitle", "Anton", 92, "#FFFFFF", outline=0, shadow=5),
    # Karaoke: \\kf fills from the secondary colour (white) to the primary (gold).
    kit.style("MuLine", "Montserrat ExtraBold", 66, fl.GOLD, outline=4, shadow=3, secondary="#FFFFFF"),
    kit.style("MuNext", "Montserrat ExtraBold", 48, "#FFFFFF", outline=3, shadow=2),
]


def _t(text, limit):
    return fl.clean_title(re.sub(r"\s*[·•–—]\s*", " - ", text or ""))[:limit]


def lyric_events(lines, total, title, genre, handle, hook=""):
    ev = []
    if hook.strip():
        # The first 2.6 s: a big hook line before any lyric (the songs channel's median viewer
        # left at 2 s with only a song title on screen, 22-oct-2026).
        end = min(2.6, total)
        ev.append(kit.dialogue(6, 0, end, "MuTitle",
                               rf"{{\an5\pos({CX},760)\fscx85\fscy85\t(0,220,\fscx108\fscy108)"
                               rf"\t(220,320,\fscx100\fscy100)\fad(0,250)\bord5\3c&H000000&}}{_t(hook, 44)}"))
    # A dark wash behind the lyrics so they read on any cover.
    ev.append(kit.dialogue(1, 0, total, "Shape",
                           rf"{{\an7\pos(0,980)\1c&H000000&\1a&H60&\bord0\shad0\blur80\p1}}"
                           rf"{fl._round_rect(kit.OUT_W, 760, 0)}{{\p0}}"))
    ev.append(kit.dialogue(1, 0, total, "Shape",
                           rf"{{\an7\pos(0,0)\1c&H000000&\1a&H90&\bord0\shad0\blur60\p1}}"
                           rf"{fl._round_rect(kit.OUT_W, 420, 0)}{{\p0}}"))
    if handle:
        ev.append(kit.dialogue(2, 0, total, "MuSmall", rf"{{\an5\pos({CX},70)\alpha&H30&}}{handle}"))
    w = max(240, 24 * len(genre) + 100)
    # Genre tag and title on frame 0 (no fade from nothing): the frame the feed shows while people swipe.
    ev.append(kit.dialogue(2, 0, total, "Shape",
                           rf"{{\an7\pos({CX - w // 2},{170 - 36})\1c{fl._ass_colour(fl.GOLD)}\bord0\shad0"
                           rf"\p1}}{fl._round_rect(w, 72, 36)}{{\p0}}"))
    ev.append(kit.dialogue(3, 0, total, "MuPill", rf"{{\an5\pos({CX},170)}}{_t(genre, 22).upper()}"))
    ev.append(kit.dialogue(3, 0, total, "MuTitle",
                           rf"{{\an5\pos({CX},290)\fscx92\fscy92\t(0,300,\fscx100\fscy100)}}"
                           rf"{_t(title, 30)}"))
    for k, (text, a, b) in enumerate(lines):
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        hold = min(nxt[1], b + 1.2) if nxt else min(total, b + 1.5)
        words = text.split()
        sung = max(0.3, b - a)
        weights = [len(x) + 2 for x in words] or [1]
        karaoke = "".join(rf"{{\kf{max(1, round(sung * 100 * wt / sum(weights)))}}}{x} "
                          for x, wt in zip(words, weights)).strip()
        ev.append(kit.dialogue(5, a - 0.12, hold, "MuLine",
                               rf"{{\an5\pos({CX},1180)\fad(120,150)\fscx92\fscy92\t(0,160,\fscx100\fscy100)}}"
                               rf"{karaoke}"))
        if nxt and nxt[1] - b < 3.0:
            ev.append(kit.dialogue(4, a - 0.12, hold, "MuNext",
                                   rf"{{\an5\pos({CX},1310)\alpha&H70&\fad(120,150)}}{_t(nxt[0], 60)}"))
    return ev


def run(output_dir, pipeline):
    import random
    cfg = fl.settings()
    style = (os.environ.get("MUSIC_STYLE") or random.choice(STYLES))[:60]
    theme = (os.environ.get("MUSIC_THEME") or pick_theme())[:60]
    vocal = os.environ.get("MUSIC_VOCAL") or ("female" if random.random() < FEMALE_SHARE else "male")
    if os.environ.get("MUSIC_DANCE") == "1":
        vocal = "female"           # the dancer is the singer
    vocal = "a male lead singer" if vocal.lower().startswith("m") else "a female lead singer"
    client = kit.gemini()
    stem = kit.neutral_stem("Song")
    song = os.path.join(output_dir, f".{stem}_song.mp3")
    for attempt in range(SING_TRIES):
        print(f"🎵 AI song: writing a {style} song about {theme} ({vocal})...")
        p = plan(client, style, theme, vocal)
        print(f"   ✅ \"{p.title}\" ({p.genre})")
        print("🎤 Lyria is singing it...")
        try:
            sing(client, p, song)
            break
        except Exception as e:  # noqa: BLE001
            # Lyria's filter refuses some songs with no reason given ("Request
            # blocked for an unspecified policy reason", an indie folk song on
            # 14-oct-2026): a fresh song usually passes.
            if "policy" not in str(e).lower() and "blocked" not in str(e).lower():
                raise
            print(f"   ⚠️ Lyria refused \"{p.title}\" (its content filter); writing another one.")
            os.environ["MUSIC_AVOID"] = json.dumps(_avoid() + [p.title])
    else:
        raise RuntimeError(f"Lyria refused {SING_TRIES} songs in a row; the next Short tries another style.")
    seconds = media_seconds(song)
    print(f"   ✅ {seconds:.0f}s of song.")
    print("👂 Timing the lyrics...")
    lyrics = [*p.verse, *p.pre_chorus, *p.chorus]
    lines = align(lyrics, hear(song, lyrics))
    if len(lines) < 3:
        raise RuntimeError("The sung lyrics could not be timed; trying another song next time.")
    dance_bg, dance_clips, dancer = None, [], None
    if os.environ.get("MUSIC_DANCE") == "1":
        # The channel's AI singer dances to the chorus (ai_influencer.py); she
        # costs money per second, so the Short is as long as her dance.
        import ai_influencer
        if ai_influencer.available():
            dancer = ai_influencer.character()
            dance_bg, dance_clips, usd = ai_influencer.dance_background(
                client, {"title": p.title, "genre": p.genre, "theme": theme, "scene": p.image_prompt},
                ai_influencer.SECONDS, output_dir)
            if usd:
                ai_influencer.record(usd)
    start, end = window(lines, seconds, media_seconds(dance_bg) if dance_bg else SHORT_SONG,
                        p.chorus[0] if p.chorus else None)
    lines = [(t, a - start, min(b, end) - start) for t, a, b in lines if a < end - 0.5 and a >= start]
    body = end - start
    print(f"   ✅ {len(lines)} lines timed; using {start:.1f}-{end:.1f}s.")

    outro_s = cfg["outro_seconds"]
    card_ev, card_sfx = kit.end_card(body, outro_s)
    total = body + (outro_s if card_ev else 0.0)
    colors = [c for c in p.colors if re.fullmatch(r"#[0-9A-Fa-f]{6}", c or "")][:2] or [cfg["bg"]]
    events = lyric_events(lines, body, p.title, p.genre, cfg["handle"], hook=p.hook) + card_ev
    if not card_ev:
        # Loop-friendly ending (no end card): a small follow line over the
        # last seconds of the music instead.
        events.append(kit.dialogue(6, max(0.0, body - 4.0), body, "MuPill",
                                   rf"{{\an5\pos({CX},1640)\1c&HFFFFFF&\fad(300,300)}}"
                                   rf"NEW SONG EVERY DAY{(' | ' + cfg['handle']) if cfg['handle'] else ''}"))
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    # Free mood footage under the lyrics, one clip per line (broll.py); the
    # AI cover (a paid image call) only when no footage is found.
    import beats as beat_track
    import broll
    # Footage cuts land on the song's beats (beats.py, numpy only).
    on_beat = beat_track.track(song, start, body)
    if on_beat:
        print(f"   🥁 {len(on_beat)} beats (~{beat_track.bpm(on_beat) or 0:.0f} BPM): footage cuts on the beat.")
    bg, footage = (dance_bg, dance_clips) if dance_bg else broll.background_for(
        f"{p.title}: a {p.genre} song about {theme}", [{"start": a, "text": t} for t, a, _b in lines], total,
        output_dir, client, FOOTAGE_RULE, beats=on_beat)
    art = None if bg else cover(client, p, os.path.join(output_dir, f".{stem}_cover.png"))
    print(f"🎬 Rendering the song short ({total:.0f}s{', with footage' if bg else ', with cover' if art else ''})...")
    kit.render(final, total, [kit.blend(colors[0], "#000000", 0.6), kit.blend(colors[-1], "#000000", 0.5)],
               events, LYRIC_STYLES, sfx=card_sfx, music=(song, start, 1.0), visualizer=True,
               fades=(FADE, body), music_seconds=body, bg_image=art, bg_video=bg)
    hashtags = " ".join("#" + re.sub(r"[^A-Za-z0-9_]", "", h) for h in (p.hashtags or [])[:4] if h.strip())
    description = (f"{p.description.strip()}\n\nLyrics:\n" + "\n".join(p.chorus) +
                   "\n\nAn original AI-generated song: lyrics written with AI, music and vocals made "
                   "with Google Lyria." + (f"\nThe singer, {dancer['name']}, is an AI character, not a real "
                                            "person; her dance is AI-animated from stock dance clips."
                                            if dance_bg else "")
                   + (f"\n{__import__('stock_media').credit_line(footage)}" if footage else "")
                   + (f"\n\n{hashtags} #shorts" if hashtags else "\n\n#shorts"))
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": p.title, "viral_hook_text": p.chorus[0],
            "why": f"AI song: {style}, {theme}", "predicted_score": 80, "genre": "music",
            "seo_title": p.youtube_title[:100], "seo_description": description,
            "seo_tags": [t for t in p.tags if t][:15], "hashtags": (p.hashtags or [])[:4],
            "video_description_for_tiktok": f"{p.title} {hashtags}".strip(),
            "video_description_for_instagram": description,
            "ai_voice": "AI music and vocals (Google Lyria)", "ai_made": bool(dance_bg),
            "comment_question": "Which line hit you the hardest? 🎧",
            "song": {"title": p.title, "style": style, "theme": theme, "genre": p.genre, "vocal": vocal,
                     "lyrics": lyrics, "cover": bool(art),
                     **({"dancer": dancer["name"]} if dance_bg else {})},
            "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in footage]}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "music"})
