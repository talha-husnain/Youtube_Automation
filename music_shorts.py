"""AI songs in English and Urdu as Shorts (CONTENT_GENRE=music): the WHOLE song, about a minute.

Gemini writes an original song (title, lyrics, musical direction, a cover
scene); Google's Lyria sings it (lyria-3.5 on the Gemini API: about $0.08 a
song, ~1 min to make, vocals and our lyrics included, SynthID-watermarked,
14-oct-2026; the same model through fal.ai, $0.10, when the Gemini API has no
credit, 10-nov-2026); Gemini paints one 9:16 cover; Whisper on this laptop hears
when each line is sung (small model, CPU: every line of a test song landed
within a second, 54 s with the model load), and the Short is a lyric video:
the cover drifting slowly, the line being sung large with its words filling
gold, the next one dimmed, a gold wave line moving with the music.

Lyria refuses requests for an artist's voice or existing lyrics, and the
prompt never names an artist. The upload carries YouTube's altered or
synthetic content label (the voice is realistic and made by AI) and the
description says the song is AI-made.

The song opens on its chorus and the Short is the whole song, to its own end
(owner, 10-nov-2026: songs of 20-40 s were cut "in the middle of the sentence"):
chorus, verse, pre-chorus, chorus. An Urdu song is written in Roman Urdu (what
the screen shows) and in Devanagari (what the singer reads and Whisper hears).

Env: MUSIC_STYLE, MUSIC_THEME, MUSIC_VOCAL (female/male), MUSIC_LANG (english/urdu), MUSIC_AVOID (JSON list of
titles already made), MUSIC_MODEL (Lyria model), MUSIC_WHISPER (Whisper model size), MUSIC_FAL (0: never sing
through fal.ai), MUSIC_FAL_MODEL (the fal endpoint).
"""
import base64
import difflib
import json
import os
import re
import subprocess
import unicodedata
from typing import List

from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

CX = kit.OUT_W // 2
LYRIA_MODEL = os.environ.get("MUSIC_MODEL") or "lyria-3.5"
FAL_MODEL = os.environ.get("MUSIC_FAL_MODEL") or "google/lyria-3.5"     # $0.10 a song on fal.ai (10-nov-2026)
# The Short is the whole song (owner, 10-nov-2026: "the song duration is very short... in the middle of the
# sentence it got cut"): it opens on the chorus, so the hook still comes first. Starting on the verse with a
# 1.2 s fade-in, viewers left after a median 2 s (22-oct-2026); then the Short started at the chorus, which is
# the END of a verse-first song, so it ran 19-30 s (server log, 22-oct to 9-nov). Shorts may run 3 minutes.
MAX_SONG = 90.0
SHORT_SONG = 32.0    # a dance Short: the chorus only, as long as the dance (ai_influencer)
FADE = 0.15
END_FADE = 2.5       # a song longer than MAX_SONG ends after a sung phrase, fading over a breath
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
                "stock model, not a person the song is about, so a close shot of her is fine. She is bold and "
                "striking, the kind of shot that stops a scroll: confident, a direct look into the camera, red "
                "lips, a red or black dress, statement earrings, wind in her hair, fashion-editorial light "
                "(\"woman red dress confident\", \"woman red lipstick close up\", \"fashion model walking city "
                "night\"). Stylish and classy, never revealing, lingerie or suggestive. Other songs: city lights, "
                "rain, roads, sea, sky, nature. Never a person singing, rapping or playing an instrument, never "
                "text. ")
# An Urdu song's woman looks like its listeners' world (Pakistani and Indian stock models).
URDU_FOOTAGE = ("This is an URDU song: she is a South Asian woman, in a saree, lehenga, anarkali or shalwar "
                "kameez with a dupatta, or a chic modern outfit (\"indian woman saree\", \"woman red saree\", "
                "\"bride lehenga\", \"henna hands\", \"indian woman rain\", \"woman dupatta wind\"); the places are "
                "rooftops, old city streets, rain on a window, chai, the moon, a wedding's lights. ")
STYLES = ["upbeat pop", "lo-fi chill", "acoustic love song", "EDM dance pop", "R&B slow jam", "pop punk",
          "country pop", "indie folk", "afrobeats", "synthwave", "motivational anthem", "sad piano ballad",
          "heartbreak pop ballad", "romantic slow pop", "gym phonk", "aggressive trap anthem",
          # Urdu songs' sounds (music_moods.URDU).
          "Pakistani sad ballad", "Pakistani romantic pop", "Sufi pop love song", "desi hip hop anthem",
          "desi gym rap", "Urdu lo-fi", "dhol dance pop", "desi dance pop"]
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
# Songs sung by a woman, to match the woman on screen (owner, 10-nov-2026: "we are using female character more
# often, so you can use that even more"; was 0.65).
FEMALE_SHARE = 0.85


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
    final_line: str = ""      # the last chorus's last line, changed: the song's ending, leading back to its start
    sung: List[str] = []      # an Urdu song: its lines in Devanagari (chorus, verse, pre-chorus, final), for the singer


PLAN_PROMPT = """Write an ORIGINAL catchy {language} song for a YouTube Shorts music channel.
Style: {style}. Theme: {theme}. Lead vocal: {vocal}.{mood}
The Short is the WHOLE song, about 60 seconds, and it OPENS ON THE CHORUS (viewers decide in
the first two seconds, so the hook comes first); then the story; then the chorus closes it:
  chorus (4 lines) -> verse (4 lines) -> pre-chorus (2 lines) -> the chorus again, with its
  last line changed to the final line.
What the most replayed part of 42 hit songs is (research, 10-nov-2026): the chorus or hook, about
18 seconds, one 4-line chorus. So:
- The chorus is the song's hot part, the part people replay, hum and send to someone. The title
  (1-3 words) comes from the hook and sits in chorus lines 1 and 4. The chorus talks TO someone:
  "you" ({you}) in most of its lines, as the one the feeling is for, always inside the sentence
  (never a "you" added at a line's end to fill it). Simple words, singable after one
  listen; one phrase repeats or echoes inside the chorus so it sticks.
- The verse is ONE specific, concrete moment (an object, a place, a time of day) that fits the
  song's mood, so the chorus hits harder the second time. The KIND of moment meant (find your own,
  never these ones): {moment_examples} A love song stays warm
  (no breakup, no one else); a sad song stays with the hurt (one memory and what it means now, at
  most one line of blame); one feeling for the whole song. At most one abstract feeling word per
  four lines.
- The pre-chorus lifts into the chorus: rising feeling, two complete phrases.
- The final line is the chorus's last line with one small twist: the song's ending, and it leads
  back into the first chorus line when the Short loops.
- One line is the caption line people quote: 4-8 words, standalone, present tense, a small twist.
- Every line is a complete phrase on its own (a viewer may hear only that line): no sentence
  runs on into the next line.
{lang_rules}
Fresh images, no stacked cliches ({cliches}). Nothing explicit or suggestive; no alcohol; no
politics, army, Kashmir or sectarian topics; in a love, party or sad song no religious words (God's
names, prophets, holy places, namaz, sajda, ibadat). No brand or artist names. Every word is your
own: never copy, quote or rework the lines, hook or title of an existing song, not even a few
famous words.
Never reuse these titles, already made: {avoid}
Return:
- title: max 30 characters.
- youtube_title: max 80 characters: the hook line (the same words as the on-screen hook below),
  then the song title and the search words people type, joined with " | ". The hook fits THIS
  song's mood and theme (a workout song never gets a love hook). {title_hooks} A brand-new song
  title alone has no search demand. At most one emoji, no false claims; the AI note goes in the
  description, not at the front of the title.
- genre: 1-3 words.
- lyria_style: the musical direction for an AI music model in one sentence: genre, mood, tempo in
  BPM, main instruments, the lead vocal above and how it sings. Never name an artist or a song.
- chorus: exactly 4 lines, {chorus_words} words each, the title in lines 1 and 4.
- verse: exactly 4 lines, {verse_words} words each.
- pre_chorus: exactly 2 lines, 4-7 words each.
- final_line: one line, the chorus's last line with one small twist (it replaces that line in the
  last chorus, and it leads back to the first line).
- sung: {sung_rule}
- image_prompt: a cover art scene for a vertical 9:16 picture that fits the song: for a love or
  heartbreak song a beautiful, elegant young {woman} as the song's character (a fictional person:
  her look, outfit, expression, the place, light and mood), bold and striking (a confident look, a
  statement outfit, red lips); otherwise a place, light and mood. Stylish and classy,
  never revealing or suggestive; no text, no letters, no logos, no real or famous person.
- colors: 2 hex colours (#RRGGBB) that match the cover's mood.
- description: 2 short sentences for YouTube about the song's feeling, {desc_lang}.
- tags: 10-15 search tags ({tag_hint}).
- hashtags: 4 hashtags without the # sign.
- hook: 3-7 words shown BIG on screen for the first 2.5 seconds, before any lyric, so a scroller
  stays (most leave in the first 2 seconds, and many watch with the sound off): the moment as a
  POV, or who to send it to. {hook_examples} Not the title again, no emoji, no hashtags."""

LANG = {
    "english": {
        "language": "English", "whisper": "en",
        "lang_rules": "English: everyday texting words, nothing archaic; chorus lines 2 and 4 rhyme.",
        "you": "you",
        "cliches": "never: heart of gold, tears like rain, broken wings, shattered heart, fire inside, burning "
                   "bright, endless night, forever and always, dancing in the dark",
        "chorus_words": "4-7", "verse_words": "6-10",
        "moment_examples": "Love: a small everyday thing only the two of them share. Hurt: the last trace the "
                           "other one left behind. Drive: the hardest minute of the day.",
        "title_hooks": "Formulas that top song Shorts use: \"POV: [the moment] | [Title] | Sad Song\", \"[hook "
                       "line] 🥀 | [Title] | Heart Touching Song\", \"For Her | [Title] | Romantic Song\", \"[TITLE] "
                       "🔥 | Gym Phonk | Workout Motivation\".",
        "sung_rule": "an empty list.",
        "woman": "woman",
        "desc_lang": "in English",
        "tag_hint": "genre, mood, \"new song 2026\", \"ai music\"...",
        "hook_examples": "(\"POV: she left her earring behind\", \"Send this to the one who left\", \"For the one "
                         "who stayed\")",
        "singer": "",
    },
    "urdu": {
        "language": "URDU", "whisper": "hi",
        "lang_rules": (
            "Language: URDU, about 90% the everyday Urdu of modern Pakistani pop and drama OSTs (how people talk\n"
            "and text), at most ONE poetic or Persian word per stanza (dil, ishq, mohabbat, intezaar, judai, yaad,\n"
            "dua, barsaat are everyday enough), never Sanskrit-only Hindi words, and at most one English phrase\n"
            "in the whole song. The chorus (mukhda) opens the song and comes back; its lines end on the same words\n"
            "(radif) with a rhyme just before them (qafiya), and the radif is part of the sentence (\"...yaad aaye\",\n"
            "\"...mere ho tum\"), never a word stuck on after a comma. One way of saying you for the whole song:\n"
            "\"tum\" (with tumhara, tumhari, tumhein) for tender love, \"tu\" (with tera, teri, tujhe) for raw hurt,\n"
            "never both, and the one you sing to keeps one gender in every line (a woman singing to a man: tum aaye,\n"
            "tum gaye). The title is one evocative word, a word said twice\n"
            "(like \"Pal Pal\"), or a 2-3 word question to the one you love. Write the lyrics in ROMAN URDU, spelled\n"
            "the way Pakistanis text: Mohabbat, Ishq, Dil, Zindagi, Pyaar, Judai, Yaad, Dua, Barsaat, hai, mein,\n"
            "nahi, kyun, tera. The grammar is exactly what a native speaker says: verbs agree with tum / tu and\n"
            "with gender (tum aate ho, tu aata hai, woh muskurayi), and postpositions bend the noun (gaari ke\n"
            "darwaze mein); read every line once more for that before answering."),
        "you": "tum or tu",
        "cliches": "no line made of nothing but dil, dard and aansu",
        "chorus_words": "3-6", "verse_words": "5-8",
        "moment_examples": "Love: a small everyday Pakistani moment only the two of them share. Hurt: the "
                           "last trace the other one left behind, or a family day that went to someone else. "
                           "Drive: the hardest minute of the day, a mother's prayer at the door.",
        "title_hooks": "In Roman Urdu, with the search words people type. Formulas that top Urdu song Shorts use: "
                       "\"[hook line] 💔 | [Title] | Urdu Sad Song\", \"[Title] | Pakistani Romantic Song | Urdu "
                       "Song Status\", \"POV: [the moment] | [Title] | Urdu Love Song\", \"[Title] 🌙 | Chill Urdu "
                       "Song for Chai at Night\".",
        "sung_rule": ("the same 11 lines written in DEVANAGARI letters (with nukta: ज़ ख़ ग़ फ़ क़), in this order:\n"
                      "  the 4 chorus lines, the 4 verse lines, the 2 pre-chorus lines, the final line. Exactly the\n"
                      "  same words as the Roman Urdu lines, only the letters change: it is what the singer reads.\n"
                      "  Exactly 11 items."),
        "woman": "South Asian woman (a Pakistani look, in a saree, lehenga or shalwar kameez, or a chic modern outfit)",
        "desc_lang": "in Roman Urdu with a few English words",
        "tag_hint": "\"urdu song\", THIS song's mood in Urdu and Hindi words (a love song: \"urdu love song\", "
                    "\"hindi love song\"; a sad one: \"urdu sad song\"), \"pakistani song\", \"new urdu song "
                    "2026\", \"ai song\"...",
        "hook_examples": "In Roman Urdu: (\"POV: uski mehndi kisi aur ki thi\", \"Usay bhejo jo chor gaya\", "
                         "\"Us ke liye jo chai pe aata hai\")",
        "singer": "Sung in Urdu (Hindustani) with soft, natural Pakistani pronunciation; modern Pakistani pop "
                  "production.",
    },
}


def lang_info(lang):
    return LANG.get(lang) or LANG["english"]


def _avoid():
    try:
        return [str(x)[:60] for x in json.loads(os.environ.get("MUSIC_AVOID") or "[]")][-60:]
    except ValueError:
        return []


def _sung_count(p):
    return len(p.chorus) + len(p.verse) + len(p.pre_chorus) + (1 if (p.final_line or "").strip() else 0)


def _sung_ok(p):
    return len(p.sung or []) == _sung_count(p)


def plan(client, style, theme, vocal="a female lead singer", brief="", lang="english"):
    from quiz_shorts import quiz_model
    import script_craft
    info = lang_info(lang)
    # The playlist mood the song is made for (music_moods.py): it shapes tempo, lyrics and title.
    mood = (f"\nMood (the playlist this song is made for; the music, lyrics and title must fit it): {brief}"
            if brief else "")
    prompt = PLAN_PROMPT.format(style=style, theme=theme, vocal=vocal, mood=mood,
                                avoid=", ".join(_avoid()) or "(none yet)",
                                **{k: info[k] for k in ("language", "lang_rules", "moment_examples", "title_hooks",
                                                        "sung_rule", "woman", "desc_lang", "tag_hint",
                                                        "hook_examples", "you", "cliches", "chorus_words",
                                                        "verse_words")})
    # + what the niche's most viewed song Shorts do now (niche_research); the song stays our own.
    prompt += script_craft.playbook()
    import ai_fallback
    for attempt in range(2):
        # The lyrics are what this channel sells: when Gemini cannot write, the full OpenAI model does, not the
        # mini one (10-nov-2026: the mini's Urdu forced its rhymes into lines that meant nothing), ~$0.03 more a song.
        with ai_fallback.best_writer():
            p = kit.ask_json(client, SongPlan, prompt, model=quiz_model())
        if len(p.verse) < 2 or len(p.chorus) < 2:
            raise RuntimeError("The song came back without lyrics; try again.")
        if lang != "urdu":
            return p
        if _sung_ok(p):
            return polish_urdu(client, p)
        # The singer's Devanagari lines must match the Roman Urdu ones line for line.
        prompt += (f"\n\nYour last answer had {len(p.sung or [])} Devanagari lines in sung; it needs exactly "
                   f"{_sung_count(p)}, one per lyric line, in the order given.")
    raise RuntimeError("The Urdu song's Devanagari lines did not match its lyrics; trying another song next time.")


URDU_EDIT_PROMPT = """You are a Pakistani lyricist and a careful Urdu editor. Below is a new Urdu song as JSON.
Fix ONLY real mistakes a native listener would wince at: verb agreement with tum / tu and with gender
(tum ne kaha, tum aaye, tu gaya), postpositions (gaari ke darwaze mein), a "tum" mixed with tera/teri
(use tumhara/tumhari) or a "tu" mixed with tumhara, a word stuck on after a comma just to rhyme, and
lines that do not mean anything. Keep everything else exactly: the meaning, the title, the rhymes and
the repeated line endings, the number of lines and roughly the same number of syllables per line, and
every other field. Then rewrite "sung" so its Devanagari lines match your Roman Urdu lines word for
word, in the same order (chorus, verse, pre-chorus, final line). Return the whole song as JSON.

{song}"""


def polish_urdu(client, p):
    """A second read of an Urdu song by an Urdu editor: the writer's agreement and grammar slips ("tum keh ke
    bola", "gaari ka darwaza mein", 10-nov-2026 samples) fixed, nothing else changed. The song as it was when the
    edit fails or breaks its shape."""
    from quiz_shorts import quiz_model
    import ai_fallback
    try:
        with ai_fallback.best_writer():
            q = kit.ask_json(client, SongPlan, URDU_EDIT_PROMPT.format(
                song=json.dumps(p.model_dump(), ensure_ascii=False, indent=1)), model=quiz_model())
    except Exception as e:  # noqa: BLE001 — the writer's song is sung then
        print(f"   ℹ️ Urdu edit skipped ({type(e).__name__}: {str(e)[:80]}).")
        return p
    same_shape = (len(q.chorus) == len(p.chorus) and len(q.verse) == len(p.verse)
                  and len(q.pre_chorus) == len(p.pre_chorus) and bool(q.final_line) == bool(p.final_line))
    return q if same_shape and _sung_ok(q) else p


def sections(p):
    """[(tag, shown lines, sung lines)] in the order the song is sung: chorus, verse, pre-chorus, and the chorus
    again with its last line turned into the final line (research 10-nov-2026: a last chorus with one changed
    line). The sung lines are what the singer reads (an Urdu song's Devanagari), the shown ones the screen's."""
    chorus, verse, pre = list(p.chorus), list(p.verse), list(p.pre_chorus or [])
    final = (getattr(p, "final_line", "") or "").strip()
    sung = list(getattr(p, "sung", None) or [])
    n = len(chorus) + len(verse) + len(pre)
    if len(sung) == n + (1 if final else 0):
        sc, sv, sp = sung[:len(chorus)], sung[len(chorus):len(chorus) + len(verse)], sung[len(chorus) + len(verse):n]
        sf = sung[n] if final else ""
    else:
        sc, sv, sp, sf = chorus, verse, pre, final
    out = [("Chorus", chorus, sc), ("Verse", verse, sv)]
    if pre:
        out.append(("Pre-Chorus", pre, sp))
    last, last_sung = list(chorus), list(sc)
    if final and last:
        last[-1], last_sung[-1] = final, sf
    return out + [("Final Chorus", last, last_sung)]


def lyria_prompt(p, lang="english"):
    singer = lang_info(lang)["singer"]
    parts = [f"{p.lyria_style}. {singer + ' ' if singer else ''}A complete song of about 60 seconds that "
             "OPENS ON THE CHORUS: the vocals start in the first second (no intro), then the verse, the "
             "pre-chorus and the final chorus, which lifts (fuller, higher, with harmonies), ending cleanly on its "
             "last line with a short musical tail (no fade-out, no extra verse)."]
    for tag, _shown, sung in sections(p):
        parts += ["", f"[{tag}]", *sung]
    return "\n".join(parts)


def _lyria(client, p, out_path, lang="english"):
    it = client.interactions.create(model=LYRIA_MODEL, input=lyria_prompt(p, lang))
    audio = it.output_audio
    if not audio or not audio.data:
        raise RuntimeError("Lyria returned no song (it refuses some requests); trying another next time.")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(audio.data))
    return out_path


def fal_enabled():
    if os.environ.get("MUSIC_FAL", "1") == "0":
        return False
    import ai_influencer
    return bool(ai_influencer.key())


def fal_sing(p, out_path, lang="english"):
    """The same Lyria 3.5 through fal.ai ($0.10 a song, 10-nov-2026), paid from the fal balance: the Gemini API
    had no credit from 6-nov-2026 and ACE-Step's songs on this laptop sounded off (owner, 10-nov-2026: "there's
    no sync between the voice and the music") and took 14-40 minutes."""
    import talkies                      # its fal queue helpers
    body = talkies.fal_job(FAL_MODEL, {"prompt": lyria_prompt(p, lang)[:5000]})
    url = ((body or {}).get("audio") or {}).get("url") if isinstance(body, dict) else None
    if not url:
        raise RuntimeError(f"fal's Lyria returned no song: {str(body)[:160]}")
    talkies._download(url, out_path)
    return out_path


def free_sing(p, out_path, lang="english"):
    """The same song by ACE-Step on this PC (free_song.py)."""
    import free_song
    singer = lang_info(lang)["singer"]
    style = (f"{p.lyria_style} {singer + ' ' if singer else ''}Vocals start right away with the chorus, no long "
             "intro; then the verse, the pre-chorus and the big catchy chorus again, ending cleanly.")
    lyrics = free_song.lyrics_text([(tag, sung) for tag, _shown, sung in sections(p)])
    # ACE-Step plays an intro whatever the prompt says (22 s in the first test, 8-nov-2026); the Short starts at
    # the first sung line, so the song is made longer to leave ~50-60 s after the intro.
    return free_song.make(style, lyrics, out_path, seconds=free_song._int_env("ACESTEP_SECONDS", 80))


SUNG_BY = {"engine": "Google Lyria"}     # what sang the last song, for the description


def _refused(e):
    t = str(e).lower()
    return any(w in t for w in ("policy", "blocked", "safety", "content_policy", "inappropriate"))


def sing(client, p, out_path, lang="english"):
    """Lyria makes the song: on the Gemini API while it has credit, else the same model through fal.ai; when
    neither can (no credit anywhere, an outage), ACE-Step makes it free on this PC (owner, 7-nov-2026). A
    content-filter refusal goes back to the caller, which writes another song. Returns the mp3 path."""
    import ai_fallback
    import free_song
    errors = []
    if not ai_fallback.status().get("gemini_down"):
        try:
            _lyria(client, p, out_path, lang)
            SUNG_BY["engine"] = "Google Lyria"
            return out_path
        except Exception as e:  # noqa: BLE001
            if _refused(e):
                raise
            errors.append(str(e))
            print(f"   ⚠️ Lyria on the Gemini API could not sing ({str(e)[:90]}).")
    if fal_enabled():
        try:
            if not errors:
                print("   ℹ️ Gemini is out of credit for now, so Lyria sings it through fal.ai ($0.10).")
            fal_sing(p, out_path, lang)
            SUNG_BY["engine"] = "Google Lyria (through fal.ai)"
            return out_path
        except Exception as e:  # noqa: BLE001
            if _refused(e):
                raise RuntimeError(f"Lyria's content filter (fal) blocked it: {str(e)[:160]}") from e
            errors.append(f"fal: {e}")
            print(f"   ⚠️ Lyria on fal.ai could not sing ({str(e)[:90]}).")
    if not free_song.enabled() or (not errors and not free_song.installed()):
        raise RuntimeError(" | ".join(errors) or "No song maker is available (Gemini and fal have no credit, "
                                                  "ACE-Step is off).")
    print("   ℹ️ The free song maker (ACE-Step) sings it.")
    try:
        free_sing(p, out_path, lang)
        SUNG_BY["engine"] = "ACE-Step (open source)"
        return out_path
    except Exception as e2:  # noqa: BLE001
        raise RuntimeError(" | ".join(errors + [f"free song maker: {e2}"])) from e2


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


def hear(song_path, lyrics=(), language="en"):
    """Whisper's sung lines: [(text, start, end, [(word, start, end)])].

    Over music Whisper calls whole 30 s windows "no speech" and drops them (a
    test song lost its verse, 14-oct-2026), and it mishears sung words. Our
    own lyrics as the prompt and no silence threshold got every line of that
    song, in 10 s. An Urdu song is heard as Hindi (the same spoken language;
    Whisper writes it in Devanagari, like the lyrics the singer read)."""
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ.get("MUSIC_WHISPER") or "small", device="cpu", compute_type="int8",
                         cpu_threads=4)
    segs, _info = model.transcribe(song_path, language=language, word_timestamps=True, vad_filter=False,
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
    """The words, lower case, punctuation gone; letters of any script kept (an Urdu song is matched in
    Devanagari, whose vowel signs are marks). The nukta goes: Whisper writes ज़ as ज as often as not."""
    t = unicodedata.normalize("NFD", (text or "").lower()).replace("़", "")
    return "".join(c for c in t if c.isspace() or unicodedata.category(c)[0] in "LMN").split()


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


def align(lyrics, heard, shown=None):
    """Each heard line paired with the lyric it is, so the screen shows our
    spelling at Whisper's times. Lyrics run in order (a repeated chorus
    starts over), so the one due next gets a bonus; a heard line that is
    like none of them (an ad-lib, a mishearing) is not shown at all: wrong
    words on screen are worse than a gap. ``shown``: the lines the screen
    shows, one per lyric (an Urdu song is heard in Devanagari, shown in Roman
    Urdu)."""
    shown = shown if shown and len(shown) == len(lyrics) else lyrics
    lines, nxt = [], 0
    for text, a, b, words in heard:
        for piece, pa, pb in _split(text, a, b, words, lyrics, nxt):
            k, _s = _best(piece, lyrics, nxt)
            if k is None:
                continue
            lines.append((shown[k], pa, pb))
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


CHAR_SECONDS = 0.075  # one sung letter, until the song's own pace is measured
MATCH_SHARE = 0.25    # a line is timed by its own letters when at least this share of them was heard


def time_lines(lyrics, heard, shown=None):
    """Every lyric line timed: [(shown text, start, end)], in the order sung.

    Whisper's words are matched to the WHOLE lyric sheet letter by letter, in order (a misheard word still shares
    most of its letters, and the second chorus matches the second time it is sung). align() matched each heard
    chunk to one or two lines, and Whisper hears a sung chorus as one 12 s chunk: an Urdu sample on 10-nov-2026
    had 8 of 14 lines on screen and 18 s of verse with no words. A line with too little of it heard is placed
    between its timed neighbours by its length; lines after the last thing heard (the song ended) are left out."""
    shown = shown if shown and len(shown) == len(lyrics) else lyrics
    L, owner = [], []                      # lyric letters (spaces between words) and the line of each
    for i, line in enumerate(lyrics):
        for w in _norm(line):
            L.extend(w)
            owner.extend([i] * len(w))
            L.append(" ")
            owner.append(i)
    H, at = [], []                         # heard letters and when each was sung
    for text, a, b, words in heard or []:
        for w, s, e in [x for x in (words or []) if _norm(x[0])] or [(text, a, b)]:
            letters = "".join(_norm(w))
            for k, c in enumerate(letters):
                H.append(c)
                at.append(s + (e - s) * (k + 0.5) / max(1, len(letters)))
            H.append(" ")
            at.append(e)
    if not L or not H:
        return []
    got = {}
    for i, j, n in difflib.SequenceMatcher(None, L, H, autojunk=False).get_matching_blocks():
        if n >= 3:                         # one or two letters in common is chance
            for k in range(n):
                if L[i + k] != " ":
                    got[i + k] = at[j + k]
    letters = [[p for p in range(len(L)) if owner[p] == i and L[p] != " "] for i in range(len(lyrics))]
    # The song's pace: seconds per letter over the lines heard best.
    paces = []
    for ps in letters:
        hit = [p for p in ps if p in got]
        if len(hit) >= 6 and got[hit[-1]] > got[hit[0]]:
            paces.append((got[hit[-1]] - got[hit[0]]) / max(1, ps.index(hit[-1]) - ps.index(hit[0])))
    pace = sorted(paces)[len(paces) // 2] if paces else CHAR_SECONDS
    pace = min(0.2, max(0.03, pace))
    span = [None] * len(lyrics)
    last_end = -1.0
    for i, ps in enumerate(letters):
        hit = [p for p in ps if p in got]
        if not ps or len(hit) < max(3, MATCH_SHARE * len(ps)):
            continue
        a = got[hit[0]] - ps.index(hit[0]) * pace
        b = got[hit[-1]] + (len(ps) - 1 - ps.index(hit[-1])) * pace + 0.2
        # A stretch far longer than the line, or running back in time, is a chance match: placed instead.
        if b - a > max(6.0, 3.5 * len(ps) * pace) or a < last_end - 1.0:
            continue
        span[i] = [max(0.0, a), b]
        last_end = b
    heard_end = max(at)
    known = [i for i, s in enumerate(span) if s]
    if not known:
        return []
    k = 0
    while k < len(lyrics):
        if span[k]:
            k += 1
            continue
        run = k
        while k < len(lyrics) and not span[k]:
            k += 1
        need = [len(letters[x]) * pace + 0.3 for x in range(run, k)]
        lo = span[run - 1][1] if run > 0 else None
        hi = span[k][0] if k < len(lyrics) else None
        if lo is None:
            lo = max(0.0, hi - sum(need))
        if hi is None:
            if heard_end <= lo + 0.5:
                break                      # nothing sung after the last timed line
            hi = min(heard_end + 0.3, lo + sum(need) * 1.5)
        t = lo
        for x, d in zip(range(run, k), need):
            share = (hi - lo) * d / max(0.01, sum(need))
            span[x] = [t, t + share]
            t += share
    out = []
    for i, s in enumerate(span):
        if not s:
            continue
        a, b = s
        nxt = next((span[x][0] for x in range(i + 1, len(span)) if span[x]), None)
        if nxt is not None:
            b = min(b, nxt - 0.05)
        if out:
            a = max(a, out[-1][2] + 0.05)
        if b - a >= 0.3:
            out.append((shown[i], round(a, 3), round(b, 3)))
    return out


BREATH = 0.8         # a pause this long after a phrase is where a song too long may end
TAIL = 3.5           # seconds of music kept after the last sung line when the song idles on far longer


def _phrases(lines, heard):
    """Every stretch of singing, timed lyric lines and whatever else Whisper heard, merged: [(start, end)]."""
    spans = sorted([(a, b) for _t, a, b, *_w in heard or []] + [(a, b) for _t, a, b in lines or []])
    out = []
    for a, b in spans:
        if out and a <= out[-1][1] + 0.25:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def song_span(lines, heard, song_seconds, longest=MAX_SONG):
    """(start, end, fade out) of the part used: the WHOLE song, from just before its first sung word to its own
    end. A song longer than ``longest`` ends after a sung phrase with a breath after it, and fades out before the
    next one starts: never inside a line (owner, 10-nov-2026: "in the middle of the sentence it got cut").
    ``heard`` counts too: a line Whisper heard but could not match is still singing."""
    phrases = _phrases(lines, heard)
    first = phrases[0][0] if phrases else 0.0
    start = max(0.0, first - 0.6) if first > 1.5 else 0.0
    # A long instrumental ending is cut a few seconds after the last thing sung (Lyria played 16 s of outro
    # after the last line of a 65 s song, 10-nov-2026): the Short loops back to its chorus instead of idling.
    # Sung = a timed lyric line, or a heard chunk of 3+ words (Whisper invents a lone "You" in the silence).
    sung_end = max([b for _t, _a, b in lines or []] +
                   [b for t, _a, b, *_w in heard or [] if len(_norm(t)) >= 3] or [0.0])
    stop, stop_fade = song_seconds, FADE
    if sung_end and song_seconds - sung_end > TAIL + 1.5:
        stop, stop_fade = sung_end + TAIL, TAIL - 0.3
    if stop - start <= longest:
        return start, stop, stop_fade
    song_seconds = stop
    limit = start + longest - END_FADE
    ends = []
    for k, (_a, b) in enumerate(phrases):
        if b > limit:
            break
        nxt = phrases[k + 1][0] if k + 1 < len(phrases) else song_seconds
        ends.append((nxt - b >= BREATH, b, nxt))
    if not ends:
        return start, start + longest, END_FADE
    _breath, b, nxt = max(ends, key=lambda e: (e[0], e[1]))
    # The fade starts as the phrase ends and the music is gone before the next phrase starts.
    end = min(song_seconds, start + longest, b + 0.2 + END_FADE, max(b + 0.25, nxt - 0.05))
    return start, end, max(0.2, end - b - 0.05)


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


# Lyric lines wrap inside x 192-888 (the event's own margins; \pos keeps them centred): at the style's
# 60/60 a long line reached x 1050, under YouTube's like/comment column (frames of 29-oct-2026).
NARROW = ",192,192,0,,"
LYRIC_Y, NEXT_Y = 1150, 1315      # were 1180 and 1310; a 3-line lyric now ends ~1240
FOLLOW_Y = 1400                   # the closing follow line sat at 1640, under YouTube's channel row


def _narrow(event):
    return event.replace(",0,0,0,,", NARROW, 1)


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
        ev.append(_narrow(kit.dialogue(5, a - 0.12, hold, "MuLine",
                                       rf"{{\an5\pos({CX},{LYRIC_Y})\fad(120,150)\fscx92\fscy92\t(0,160,\fscx100\fscy100)}}"
                                       rf"{karaoke}")))
        if nxt and nxt[1] - b < 3.0:
            ev.append(_narrow(kit.dialogue(4, a - 0.12, hold, "MuNext",
                                           rf"{{\an5\pos({CX},{NEXT_Y})\alpha&H70&\fad(120,150)}}{_t(nxt[0], 60)}")))
    return ev


def _with_mood_tags(tags, mood, lang="english"):
    """The song's own tags, then what people search for its mood ("sad songs", "gym phonk"; an Urdu song "urdu
    sad song"), 15 at most."""
    import music_moods
    m = music_moods.MOODS.get(mood) or {}
    extra = (m.get("urdu_tags") if lang == "urdu" else None) or m.get("tags") or []
    own = [t for t in tags if t]
    return list(dict.fromkeys(own[:15 - min(len(extra), 4)] + extra[:4] + own))[:15]


def broll_frame(video, out, at=1.0):
    """A still of the song's footage for its mix chapter, or None."""
    import subprocess
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1",
                        "-q:v", "2", out], capture_output=True, text=True, timeout=120)
    return out if r.returncode == 0 and os.path.isfile(out) else None


def run(output_dir, pipeline):
    import random
    if os.environ.get("MUSIC_MIX"):
        import mood_mix                 # the weekly long mood mix (music_moods.next_mix)
        return mood_mix.run(output_dir, pipeline)
    cfg = fl.settings()
    style = (os.environ.get("MUSIC_STYLE") or random.choice(STYLES))[:60]
    theme = (os.environ.get("MUSIC_THEME") or pick_theme())[:60]
    vocal = os.environ.get("MUSIC_VOCAL") or ("female" if random.random() < FEMALE_SHARE else "male")
    if os.environ.get("MUSIC_DANCE") == "1":
        vocal = "female"           # the dancer is the singer
    vocal = "a male lead singer" if vocal.lower().startswith("m") else "a female lead singer"
    mood = (os.environ.get("MUSIC_MOOD") or "")[:30]
    brief = (os.environ.get("MUSIC_BRIEF") or "")[:300]
    lang = "urdu" if (os.environ.get("MUSIC_LANG") or "").lower() == "urdu" else "english"
    if mood:
        print(f"🎧 Mood: {mood}, in {lang.title()} (its playlists get this song)")
    client = kit.gemini()
    stem = kit.neutral_stem("Song")
    song = os.path.join(output_dir, f".{stem}_song.mp3")
    for attempt in range(SING_TRIES):
        print(f"🎵 AI song: writing a {lang.title()} {style} song about {theme} ({vocal})...")
        p = plan(client, style, theme, vocal, brief, lang)
        print(f"   ✅ \"{p.title}\" ({p.genre})")
        print("🎤 Lyria is singing it...")
        try:
            sing(client, p, song, lang)
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
    print(f"   ✅ {seconds:.0f}s of song ({SUNG_BY['engine']}).")
    print("👂 Timing the lyrics...")
    order = sections(p)
    lyrics = [line for _tag, shown, _sung in order for line in shown]       # what the screen shows
    sung_lines = [line for _tag, _shown, sung in order for line in sung]   # what was sung (Devanagari in Urdu)
    try:                                # the plan beside the job, to see later why a song came out as it did
        with open(os.path.join(output_dir, f".{stem}_plan.json"), "w", encoding="utf-8") as f:
            json.dump({"lang": lang, "style": style, "theme": theme, "mood": mood, **p.model_dump()}, f,
                      ensure_ascii=False, indent=1)
    except (OSError, TypeError, ValueError):
        pass
    heard = hear(song, sung_lines, lang_info(lang)["whisper"])
    lines = time_lines(sung_lines, heard, lyrics)
    if len(lines) < 3:
        lines = align(sung_lines, heard, lyrics)
    elif lines:
        # The singer may repeat the chorus past the written sheet: those lines, chunk by chunk, as before.
        tail = [h for h in heard if h[1] >= lines[-1][2] - 0.1 and len(_norm(h[0])) >= 3]
        lines += [x for x in align(sung_lines, tail, lyrics) if x[1] >= lines[-1][2]]
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
    if dance_bg:
        # A dance Short is the chorus, as long as the dance.
        start, end = window(lines, seconds, media_seconds(dance_bg), p.chorus[0] if p.chorus else None)
        fade_out = FADE
    else:
        start, end, fade_out = song_span(lines, heard, seconds)
    full_lines = list(lines)            # the whole song's timed lyrics, for its mood mix (music_moods.archive_song)
    lines = [(t, a - start, min(b, end) - start) for t, a, b in lines if a < end - 0.5 and a >= start]
    body = end - start
    print(f"   ✅ {len(lines)} lines timed ({len(lyrics)} written); using {start:.1f}-{end:.1f}s "
          f"({'the whole song' if end >= seconds - 0.01 else f'the song, its end faded over {fade_out:.1f}s'}).")

    outro_s = cfg["outro_seconds"]
    card_ev, card_sfx = kit.end_card(body, outro_s)
    total = body + (outro_s if card_ev else 0.0)
    colors = [c for c in p.colors if re.fullmatch(r"#[0-9A-Fa-f]{6}", c or "")][:2] or [cfg["bg"]]
    events = lyric_events(lines, body, p.title, p.genre, cfg["handle"], hook=p.hook) + card_ev
    if not card_ev:
        # Loop-friendly ending (no end card): a small follow line over the
        # last seconds of the music instead.
        events.append(_narrow(kit.dialogue(6, max(0.0, body - 4.0), body, "MuPill",
                                           rf"{{\an5\pos({CX},{FOLLOW_Y})\1c&HFFFFFF&\fad(300,300)}}"
                                           rf"NEW SONG EVERY DAY{(' | ' + cfg['handle']) if cfg['handle'] else ''}")))
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    # Free mood footage under the lyrics, one clip per line (broll.py); the
    # AI cover (a paid image call) only when no footage is found.
    import beats as beat_track
    import broll
    # Footage cuts land on the song's beats (beats.py, numpy only).
    on_beat = beat_track.track(song, start, body)
    if on_beat:
        print(f"   🥁 {len(on_beat)} beats (~{beat_track.bpm(on_beat) or 0:.0f} BPM): footage cuts on the beat.")
    urdu = lang == "urdu"
    bg, footage = (dance_bg, dance_clips) if dance_bg else broll.background_for(
        f"{p.title}: a {'Urdu ' if urdu else ''}{p.genre} song about {theme}",
        [{"start": a, "text": t} for t, a, _b in lines], total,
        output_dir, client, FOOTAGE_RULE + (URDU_FOOTAGE if urdu else ""), beats=on_beat)
    art = None if bg else cover(client, p, os.path.join(output_dir, f".{stem}_cover.png"))
    print(f"🎬 Rendering the song short ({total:.0f}s{', with footage' if bg else ', with cover' if art else ''})...")
    kit.render(final, total, [kit.blend(colors[0], "#000000", 0.6), kit.blend(colors[-1], "#000000", 0.5)],
               events, LYRIC_STYLES, sfx=card_sfx, music=(song, start, 1.0), visualizer=True,
               fades=(FADE, body, fade_out), music_seconds=body, bg_image=art, bg_video=bg)
    hashtags = " ".join("#" + re.sub(r"[^A-Za-z0-9_]", "", h) for h in (p.hashtags or [])[:4] if h.strip())
    description = (f"{p.description.strip()}\n\nLyrics:\n" + "\n".join(p.chorus) +
                   f"\n\nAn original AI-generated {'Urdu ' if urdu else ''}song: lyrics written with AI, music "
                   f"and vocals made with {SUNG_BY['engine']}."
                   + (f"\nThe singer, {dancer['name']}, is an AI character, not a real "
                      "person; her dance is AI-animated from stock dance clips." if dance_bg else "")
                   + (f"\n{__import__('stock_media').credit_line(footage)}" if footage else "")
                   + (f"\n\n{hashtags} #shorts" if hashtags else "\n\n#shorts"))
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": p.title, "viral_hook_text": p.chorus[0],
            "why": f"AI song: {style}, {theme}", "predicted_score": 80, "genre": "music",
            "seo_title": p.youtube_title[:100], "seo_description": description,
            "seo_tags": _with_mood_tags(p.tags, mood, lang), "hashtags": (p.hashtags or [])[:4],
            "video_description_for_tiktok": f"{p.title} {hashtags}".strip(),
            "video_description_for_instagram": description,
            "ai_voice": f"AI music and vocals ({SUNG_BY['engine']})", "ai_made": bool(dance_bg),
            "comment_question": "Kaunsi line dil ko lagi? 💔👇" if urdu else "Which line hit you the hardest? 🎧",
            "song": {"title": p.title, "style": style, "theme": theme, "genre": p.genre, "vocal": vocal, "mood": mood,
                     "lang": lang, "engine": SUNG_BY["engine"], "lyrics": lyrics, "cover": bool(art),
                     **({"dancer": dancer["name"]} if dance_bg else {})},
            "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in footage]}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "music"})
    if mood:
        import music_moods
        still = art or (broll_frame(bg, os.path.join(output_dir, f".{stem}_still.jpg")) if bg else None)
        music_moods.archive_song(os.path.basename(os.path.normpath(output_dir)), song, {
            "title": p.title, "youtube_title": p.youtube_title, "mood": mood, "lang": lang, "style": style,
            "theme": theme,
            "genre": p.genre, "lyrics": lyrics, "lines": [[t, round(a, 2), round(b, 2)] for t, a, b in full_lines],
            "colors": colors, "seconds": round(seconds, 2), "vocal": vocal}, still)
