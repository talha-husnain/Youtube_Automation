"""Moods and their playlists for the AI-song channel (owner, 5-nov-2026: "we can create playlists... sad song,
romantic song, workout song, gym song, this sort of mode genres").

Every song is made FOR a mood: the planner picks the mood (``pick``: the owner's on/off and "how often", kept
balanced so every playlist keeps growing), the mood picks the song's style and theme, and its brief goes into the
song writer's prompt. The upload carries ``mood``; engage.add_to_playlists files each song into its mood's
playlist (and keeps "New AI songs" as the all-songs list). Songs made before moods existed are filed by ``infer``
from their style and theme. The owner can add moods of their own (a name, the sound, what the songs are about).

Settings live on the channel card as ``ch["moods"]`` = {"off": [keys], "often": {key: 1|2|4}, "custom": [...]}.
"""
import json
import os
import random
import re
import shutil
import time

OFTEN = {"less": 1, "normal": 2, "more": 4}
# Romance and heartbreak are what the channel's viewers click (owner, 19-oct-2026: 75% love themes before moods;
# 10-nov-2026: "make more romantic songs"): sad and romantic "more often", the other song moods "less", so two
# songs in three are love songs and every playlist still grows.
DEFAULT_OFTEN = {"sad": 4, "romantic": 4, "workout": 1, "gym": 1, "chill": 1, "party": 1}

# Songs in English and in Urdu (owner, 10-nov-2026: "one playlist will be English one and one will be for Urdu one,
# and inside them... sad songs, romantic song, workout song"). YouTube has no playlist inside a playlist, so each
# language has its all-songs playlist plus one per mood ("Urdu Sad Songs 💔..."), and engage.py groups them under
# the language as a shelf on the channel page. Songs made before 10-nov-2026 are all English.
LANGS = {
    "english": {"name": "English", "playlist": "English Songs 🎧 New AI Songs Every Day",
                "about": "Every English song of the channel, newest first: original AI songs (lyrics by AI, music and "
                         "vocals by Google Lyria).",
                "shelf": "English Songs 🎧"},
    "urdu": {"name": "Urdu", "playlist": "Urdu Songs 🎧 Naye AI Gaane",
             "about": "Har naya Urdu gaana: original AI songs in Urdu (lyrics by AI, music and vocals by Google "
                      "Lyria). Sad, romantic, workout aur party gaane.",
             "shelf": "Urdu Songs 🎧"},
}
URDU_SHARE = 0.5                  # songs in Urdu; the channel card can change it (0 = English only, 1 = Urdu only)
# The playlists' titles before the language split; engage.py renames them on YouTube (their songs, views and links
# stay) since every song in them is English.
OLD_ALL_SONGS = "New AI songs"

# key -> mood. ``styles`` are music_shorts.STYLES entries (learning picks the best of them by views);
# ``themes`` what the songs are about; ``brief`` goes into the song writer's prompt.
MOODS = {
    "sad": {"name": "Sad songs", "emoji": "💔", "playlist": "English Sad Songs 💔 Heartbreak AI Songs",
            "old_playlist": "Sad Songs 💔 Heartbreak AI Songs", "urdu_playlist": "Urdu Sad Songs 💔 Dard Bhare AI Gaane",
            "picture": "a lonely window at night with rain streaks on the glass, blurred city lights, one candle, melancholic deep blue tones",
            "styles": ["sad piano ballad", "heartbreak pop ballad", "acoustic love song", "lo-fi chill"],
            "themes": ["heartbreak", "she left without a goodbye", "missing her at 3 am", "one-sided love",
                       "moving on after a breakup", "a love I can't let go of", "the one that got away",
                       "still waiting for your text", "crying in the rain", "we were almost something"],
            "brief": "A SAD song: slow, aching and honest, the kind people play alone at night; a soft opening, "
                     "a chorus that breaks the heart.",
            "tags": ["sad songs", "sad song", "heartbreak song", "broken heart", "sad music"]},
    "romantic": {"name": "Romantic songs", "emoji": "❤️", "playlist": "English Romantic Love Songs ❤️ AI Songs",
                 "old_playlist": "Romantic Love Songs ❤️ AI Songs",
                 "urdu_playlist": "Urdu Romantic Songs ❤️ Pyar Bhare AI Gaane",
                 "picture": "a warm sunset over a quiet beach, two small silhouettes holding hands far away, soft golden light",
                 "styles": ["romantic slow pop", "acoustic love song", "R&B slow jam", "indie folk"],
                 "themes": ["falling in love", "first crush", "love at first sight", "first date butterflies",
                            "long distance", "slow dancing in the kitchen", "you are my home",
                            "the way you look at me", "forever with you"],
                 "brief": "A ROMANTIC love song: warm, tender and sweet, one to send to the person you love; a "
                          "chorus that feels like a hug.",
                 "tags": ["romantic songs", "love song", "love songs 2026", "romantic music", "couple song"]},
    "workout": {"name": "Workout songs", "emoji": "💪", "playlist": "English Workout Motivation Songs 💪 AI Music",
                "old_playlist": "Workout Motivation Songs 💪 AI Music",
                "urdu_playlist": "Urdu Workout Songs 💪 Josh Bhare AI Gaane",
                "picture": "an empty running track at sunrise, long shadows, dramatic sky, energetic and bright",
                "styles": ["motivational anthem", "EDM dance pop", "upbeat pop", "pop punk"],
                "themes": ["no days off", "chasing dreams", "stronger every day", "one more rep",
                           "running at sunrise", "never give up", "new beginnings", "self-love"],
                "brief": "A WORKOUT song: high energy, 125-150 BPM, a driving beat and a chant-along chorus about "
                         "pushing harder; great for running, cardio and training.",
                "tags": ["workout music", "workout songs", "motivation song", "running music", "fitness music"]},
    "gym": {"name": "Gym songs", "emoji": "🔥", "playlist": "English Gym Phonk & Beast Mode Songs 🔥 AI Music",
            "old_playlist": "Gym Phonk & Beast Mode Songs 🔥 AI Music", "urdu_playlist": "Urdu Gym Songs 🔥 Beast Mode AI Gaane",
            "picture": "a dark industrial gym with dramatic red and blue light, heavy barbells, haze, intense",
            "styles": ["gym phonk", "aggressive trap anthem", "motivational anthem"],
            "themes": ["beast mode", "gym motivation", "heavy lifting", "built different", "no pain no gain",
                       "silent grind", "they doubted me", "lion mindset"],
            "brief": "A GYM song: aggressive and heavy, phonk or trap energy (distorted 808 bass, cowbell, hard "
                     "drums), the beat hitting in the first seconds; a 1-3 word chant hook repeated through the "
                     "chorus, lines of 2-4 words, commands (lift, rise, go); made for lifting heavy.",
            "tags": ["gym music", "gym phonk", "phonk", "gym motivation", "beast mode", "workout phonk"]},
    "chill": {"name": "Lo-fi chill", "emoji": "🌙", "playlist": "English Lo-fi Chill Songs 🌙 Late Night AI Songs",
              "old_playlist": "Lo-fi Chill Songs 🌙 Late Night AI Songs", "urdu_playlist": "Urdu Lo-fi Songs 🌙 Raat Ke AI Gaane",
              "picture": "a quiet city street at night after rain, neon reflections, cozy lo-fi mood",
              "styles": ["lo-fi chill", "synthwave", "indie folk", "R&B slow jam"],
              "themes": ["late night drive", "rainy days", "city lights", "midnight thoughts", "study night",
                         "missing home", "summer nights"],
              "brief": "A CHILL lo-fi song: relaxed, dreamy and soft, 70-90 BPM, warm keys and a gentle beat; for "
                       "late nights, studying and driving.",
              "tags": ["lofi", "lofi songs", "chill music", "late night songs", "study music"]},
    "party": {"name": "Party songs", "emoji": "🪩", "playlist": "English Party & Dance Songs 🪩 AI Music",
              "old_playlist": "Party & Dance Songs 🪩 AI Music", "urdu_playlist": "Urdu Party Songs 🪩 Dance & Shaadi AI Gaane",
              "picture": "a colourful dance floor with lights and confetti, festive, seen from above, no faces",
              "styles": ["EDM dance pop", "afrobeats", "upbeat pop", "country pop"],
              "themes": ["dancing all night", "summer nights", "best friends", "weekend vibes", "main character energy",
                         "road trip"],
              "brief": "A PARTY song: bright, bouncy and fun, 115-128 BPM, a call-and-response or counted chant in "
                       "the first seconds and a dance move word in the hook everyone shouts back; for dancing with "
                       "friends.",
              "tags": ["party songs", "dance music", "party music", "dance songs 2026", "happy songs"]},
}
# Instrumental moods are MIX ONLY (research 5-nov-2026: study/lofi music earns $3-6 RPM and sleep $4-8 in long
# mixes, against ~$0.50 for phonk Shorts; an instrumental song makes a poor lyric Short): their tracks are made by
# the weekly mix job itself (mood_mix.py), never as Shorts.
MOODS.update({
    "study": {"name": "Study & focus", "emoji": "📚", "playlist": "Study & Focus Music 📚 Lo-fi AI Beats",
              "styles": [], "instrumental": True, "mix_only": True,
              "sound": ["lo-fi hip hop study beat, dusty drums, mellow Rhodes piano, vinyl crackle, 75 BPM",
                        "calm lo-fi jazz beat, soft upright bass, brushed drums, warm guitar chords, 80 BPM",
                        "chillhop focus beat, soft kick, airy pads, gentle plucked melody, 85 BPM",
                        "ambient lo-fi, slow piano chords, soft rain texture, light tape hiss, 70 BPM"],
              "picture": "a cozy study desk by a rainy window at night, a warm desk lamp, books, a cup of tea, "
                         "city lights blurred outside, soft lo-fi anime-like painting",
              "themes": ["study", "focus"], "brief": "", "tags": ["study music", "lofi", "focus music",
                                                                    "lofi hip hop", "music to study"]},
    "sleep": {"name": "Sleep music", "emoji": "😴", "playlist": "Sleep Music 😴 Calm AI Piano & Ambient",
              "styles": [], "instrumental": True, "mix_only": True,
              "sound": ["slow ambient sleep piano, soft reverb, gentle sustained pads, 60 BPM, very calm",
                        "dreamy ambient soundscape, warm synth pads, distant soft chimes, no drums",
                        "soft solo piano lullaby, slow and tender, light room reverb, 55 BPM",
                        "calm cello and piano, slow and peaceful, airy strings, no percussion"],
              "picture": "a quiet bedroom at night with moonlight through the curtains, stars outside, soft blue "
                         "light, peaceful and dreamy painting",
              "themes": ["sleep", "calm"], "brief": "", "tags": ["sleep music", "relaxing music", "calm piano",
                                                                   "deep sleep music", "ambient music"]},
})
# Urdu songs of each mood: Pakistani moments to write about, the sounds that suit them, what people search for.
URDU = {
    "sad": {"themes": ["she married someone else", "judaai at the railway station", "waiting for his call every night",
                       "her mehndi was for someone else", "his last voice note", "yaadein in the monsoon rain",
                       "a promise he broke", "one-sided love (ek tarfa pyar)", "the letter I never sent",
                       "she blocked me everywhere"],
            "styles": ["Pakistani sad ballad", "sad piano ballad", "acoustic love song"],
            "tags": ["urdu sad song", "sad song urdu", "pakistani sad song", "dard bhare gaane", "hindi sad song"]},
    "romantic": {"themes": ["love at first sight (pehli nazar)", "chai and you on a rainy evening",
                            "mehndi ki raat", "her dupatta in the wind", "a long drive on a winter night",
                            "the first time she smiled at me", "bas tum (only you)", "meeting in the rain",
                            "our nikah dream", "her eyes (tumhari aankhein)"],
                 "styles": ["Pakistani romantic pop", "Sufi pop love song", "romantic slow pop", "acoustic love song"],
                 "tags": ["urdu love song", "romantic urdu song", "pakistani romantic song", "pyar bhare gaane",
                          "hindi love song"]},
    "workout": {"themes": ["believe in yourself (khud pe yaqeen)", "never give up (haar nahi maanni)",
                           "the morning run", "hard work pays (mehnat)", "proving them wrong", "zid (determination)"],
                "styles": ["desi hip hop anthem", "motivational anthem"],
                "tags": ["urdu motivational song", "motivation song urdu", "pakistani motivational song",
                         "workout song"]},
    "gym": {"themes": ["lion heart (sher ka dil)", "beast mode", "silent grind (khamosh mehnat)", "they doubted me",
                       "iron and sweat"],
            "styles": ["desi gym rap", "gym phonk"],
            "tags": ["desi gym song", "gym song urdu", "gym motivation", "urdu rap"]},
    "chill": {"themes": ["raat ki chai", "Lahore winter nights", "a late night drive on the motorway",
                         "the moon from the rooftop (chhat pe chaand)", "a monsoon evening"],
              "styles": ["Urdu lo-fi", "lo-fi chill"],
              "tags": ["urdu lofi", "lofi urdu song", "slowed reverb urdu", "hindi lofi"]},
    "party": {"themes": ["shaadi ki dholki", "mehndi dance night", "best friends (yaari)", "baraat entry",
                         "weekend with friends"],
              "styles": ["dhol dance pop", "desi dance pop"],
              "tags": ["shaadi song", "mehndi song", "dhol song", "pakistani party song", "urdu dance song"]},
}
for _k, _u in URDU.items():
    MOODS[_k].update(urdu_themes=_u["themes"], urdu_styles=_u["styles"], urdu_tags=_u["tags"])

# Styles a mood needs that the older style list did not have (music_shorts.STYLES takes them in).
NEW_STYLES = ["gym phonk", "aggressive trap anthem"] + sorted({s for u in URDU.values() for s in u["styles"]})

# ------------------------------------------------------------------ mood mixes (mood_mix.py makes them)
MIX_MIN_SONGS = 8                 # a song mood's mix: at least this many uploaded songs not mixed before (~8 min)
MIX_MAX_SONGS = 30
MIX_PER_WEEK = 1                  # default; the card can say 0 (off) to 3
MIX_MINUTES = 30                  # an instrumental mix's length (the card: 20-60)
MIX_BUDGET = 1.5                  # US dollars of Lyria tracks per instrumental mix (~$0.08 a track)
MIX_RETRY = 24 * 3600             # after a failed mix, the next try waits a day
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "songs")
ARCHIVE_DAYS = 120

CUSTOM_MAX = 8
_KEY = re.compile(r"[^a-z0-9]+")


def _clean(text, n):
    return " ".join(str(text or "").split())[:n]


def _list(text, n=12):
    items = text if isinstance(text, list) else re.split(r"[,\n;]", str(text or ""))
    return [x for x in dict.fromkeys(_clean(i, 60) for i in items) if x][:n]


def settings_of(raw):
    """The card's mood settings, cleaned: {"off": [...], "often": {...}, "custom": [...]}."""
    raw = raw if isinstance(raw, dict) else {}
    custom = []
    for c in raw.get("custom") or []:
        if not isinstance(c, dict):
            continue
        name = _clean(c.get("name"), 40)
        key = "c_" + (_KEY.sub("_", name.lower()).strip("_")[:24] or "mood")
        if not name or key in {x["key"] for x in custom}:
            continue
        custom.append({"key": key, "name": name, "emoji": _clean(c.get("emoji"), 4) or "🎵",
                       "sound": _clean(c.get("sound"), 160), "themes": _list(c.get("themes")),
                       "playlist": _clean(c.get("playlist"), 100) or f"{name} | AI Songs"})
    keys = set(MOODS) | {c["key"] for c in custom}
    often = {}
    for k, v in (raw.get("often") or {}).items():
        if k in keys:
            v = OFTEN.get(v, v)
            try:
                often[k] = max(1, min(4, int(v)))
            except (TypeError, ValueError):
                pass
    off = [k for k in dict.fromkeys(raw.get("off") or []) if k in keys]
    out = {"off": off, "often": often, "custom": custom[:CUSTOM_MAX]}
    for key, lo, hi, default, cast in (("mixes", 0, 3, MIX_PER_WEEK, int), ("mix_minutes", 20, 60, MIX_MINUTES, int),
                                       ("mix_budget", 0.0, 5.0, MIX_BUDGET, float)):
        if key in raw:
            try:
                out[key] = max(lo, min(hi, cast(raw[key])))
            except (TypeError, ValueError):
                pass
    return out


def mix_setting(settings, key):
    return (settings or {}).get(key, {"mixes": MIX_PER_WEEK, "mix_minutes": MIX_MINUTES,
                                      "mix_budget": MIX_BUDGET}[key])


def all_moods(settings):
    """Every mood (built-in and the owner's), key -> mood."""
    out = {k: dict(v, key=k) for k, v in MOODS.items()}
    for c in (settings or {}).get("custom") or []:
        out[c["key"]] = {"key": c["key"], "name": c["name"], "emoji": c["emoji"], "playlist": c["playlist"],
                         "picture": f"{c['name']} mood: a beautiful atmospheric scene that feels like "
                                    f"{', '.join(c['themes'][:3]) or c['name']}",
                         "styles": [], "sound": c["sound"], "themes": c["themes"] or [c["name"]],
                         "brief": f"A {c['name'].upper()} song" + (f": {c['sound']}" if c["sound"] else "") + ".",
                         "tags": [c["name"].lower(), f"{c['name'].lower()} songs"], "custom": True}
    return out


def active(settings):
    moods = all_moods(settings)
    off = set((settings or {}).get("off") or [])
    return {k: v for k, v in moods.items() if k not in off}


def song_moods(settings):
    """The moods a Short can be made for (on, and not mix-only)."""
    return {k: v for k, v in active(settings).items() if not v.get("mix_only")}


def pick(settings, recent, rnd=random):
    """The next song's mood: the one furthest below its share ("how often") of the last songs, ties at random,
    so every playlist keeps growing. ``recent``: the moods of the channel's latest songs, newest last.
    None when every mood is off (the channel then makes songs as before). Mix-only moods are never a Short."""
    moods = song_moods(settings)
    if not moods:
        return None
    often = (settings or {}).get("often") or {}
    weight = {k: often.get(k, DEFAULT_OFTEN.get(k, OFTEN["normal"])) for k in moods}
    total = sum(weight.values())
    window = [m for m in (recent or [])[-30:] if m in moods]
    n = len(window) + 1
    made = {k: window.count(k) for k in moods}
    gap = {k: weight[k] / total * n - made[k] for k in moods}
    best = max(gap.values())
    return rnd.choice(sorted(k for k, g in gap.items() if g >= best - 1e-9))


def song_choice(mood, styles_ok, pick_style, rnd=random, lang="english"):
    """(style, theme, brief) for a song of ``mood``. ``pick_style(options)`` chooses among the mood's styles
    (my_channels.pick_format: views decide once each was tried); a custom mood has its own sound instead.
    An Urdu song takes the mood's Urdu styles and themes when it has them."""
    urdu = lang == "urdu"
    options = [s for s in ((mood.get("urdu_styles") if urdu else None) or mood.get("styles") or []) if s in styles_ok]
    if options:
        style = pick_style(options)
    else:
        style = (mood.get("sound") or mood["name"])[:60]
    theme = rnd.choice((mood.get("urdu_themes") if urdu else None) or mood.get("themes") or [mood["name"]])[:60]
    return style, theme, mood.get("brief") or ""


# ------------------------------------------------------------------ languages
def lang_of(row):
    """A song's language: the one it was made in; every song before 10-nov-2026 is English."""
    lang = (row or {}).get("lang")
    return lang if lang in LANGS else "english"


def urdu_share(ch):
    """The channel card's share of Urdu songs (0 to 1)."""
    try:
        return max(0.0, min(1.0, float((ch or {}).get("urdu_share", URDU_SHARE))))
    except (TypeError, ValueError):
        return URDU_SHARE


LANG_WINDOW = 6


def pick_lang(share, recent, rnd=random):
    """The next song's language: the one furthest below its share of the last LANG_WINDOW songs (ties at random),
    so at half and half the two alternate instead of running in streaks. ``recent``: the latest songs' languages,
    newest last (None = an English song made before languages)."""
    if share <= 0:
        return "english"
    if share >= 1:
        return "urdu"
    window = [x if x in LANGS else "english" for x in (recent or [])][-LANG_WINDOW:]
    n = len(window) + 1
    urdu = share * n - window.count("urdu")
    english = (1 - share) * n - window.count("english")
    if abs(urdu - english) < 1e-9:
        # A tie: the other language from the last song (none yet: either).
        return ({"urdu": "english", "english": "urdu"}[window[-1]] if window
                else rnd.choice(["english", "urdu"]))
    return "urdu" if urdu > english else "english"


def lang_playlist(lang):
    return LANGS.get(lang, LANGS["english"])["playlist"]


def lang_about(lang):
    return LANGS.get(lang, LANGS["english"])["about"]


def renames(settings=None):
    """{old title: new title} of the playlists made before the language split (all their songs are English)."""
    out = {OLD_ALL_SONGS: LANGS["english"]["playlist"]}
    for m in all_moods(settings).values():
        if m.get("old_playlist"):
            out[m["old_playlist"]] = m["playlist"]
    return out


def shelf_lists(settings, lists):
    """{lang: (shelf title, [playlist ids])}: each language's all-songs playlist, then its mood playlists in
    the moods' order, those that exist on the channel (``lists``: title -> id)."""
    out = {}
    for lang, info in LANGS.items():
        titles = [info["playlist"]] + [playlist_title(settings, k, lang) for k in song_moods(settings)]
        ids = [lists[t] for t in dict.fromkeys(titles) if t and lists.get(t)]
        if ids:
            out[lang] = (info["shelf"], ids)
    return out


# Words of a song's style or theme -> its mood, for the songs made before moods (and for any upload without one).
_INFER = [("gym", ("gym", "phonk", "beast", "lifting", "trap")),
          ("workout", ("motivat", "workout", "running", "dreams", "never give up", "stronger", "no days off",
                       "new beginnings", "self-love", "one more rep")),
          ("sad", ("heartbreak", "sad", "left", "missing", "one-sided", "moving on", "got away", "let go",
                   "waiting for your text", "never deserved", "breakup", "crying")),
          ("romantic", ("love", "crush", "romantic", "first date", "long distance", "forever", "r&b slow")),
          ("chill", ("lo-fi", "lofi", "chill", "late night", "rainy", "city lights", "synthwave", "midnight",
                     "missing home", "study")),
          ("party", ("dance", "edm", "afrobeats", "party", "summer", "best friends", "weekend", "road trip"))]


def infer(style, theme):
    """The mood a song most likely belongs to from its style and theme words, or None."""
    text = f"{theme or ''} | {style or ''}".lower()
    for key, words in _INFER:
        if any(w in text for w in words):
            return key
    return None


def mood_of(row):
    """A song upload's mood: the one it was made for, else inferred."""
    return row.get("mood") or infer(row.get("format"), row.get("topic"))


def playlist_title(settings, key, lang="english"):
    """The mood's playlist for songs in ``lang`` (an instrumental mix-only mood has one, in no language)."""
    m = all_moods(settings).get(key)
    if not m:
        return None
    if lang == "urdu" and not m.get("mix_only"):
        return m.get("urdu_playlist") or f"Urdu {m['name']} {m.get('emoji', '🎵')} AI Gaane"[:150]
    return m["playlist"]


def playlist_about(settings, key, lang="english"):
    m = all_moods(settings).get(key) or {}
    if lang == "urdu" and not m.get("mix_only"):
        return (f"{m.get('name', 'AI songs')} {m.get('emoji', '')} in Urdu: original AI gaane (lyrics by AI, music "
                f"and vocals by Google Lyria). Har hafte naye gaane.").replace("  ", " ")
    return (f"{m.get('name', 'AI songs')} {m.get('emoji', '')}: original AI songs (lyrics by AI, music and vocals "
            f"by Google Lyria). A new one every week.").replace("  ", " ")


def summary(settings, jobs, playlists=None):
    """Each mood for the channel card: name, on, how often, songs made, its playlist link when there is one."""
    playlists = playlists or {}
    counts, mixes = {}, {}
    for j in jobs or []:
        if j.get("status") in ("done", "uploaded"):
            if j.get("format") == "mix":
                if j.get("mood"):
                    mixes[j["mood"]] = mixes.get(j["mood"], 0) + 1
                continue
            k = j.get("mood") or infer(j.get("format"), j.get("topic"))
            if k:
                counts[k] = counts.get(k, 0) + 1
    often = (settings or {}).get("often") or {}
    off = set((settings or {}).get("off") or [])
    rows = []
    for k, m in all_moods(settings).items():
        pid = playlists.get(m["playlist"])
        urdu_pid = playlists.get(playlist_title(settings, k, "urdu") or "") if not m.get("mix_only") else None
        rows.append({"key": k, "name": m["name"], "emoji": m.get("emoji", "🎵"), "on": k not in off,
                     "urdu_url": f"https://www.youtube.com/playlist?list={urdu_pid}" if urdu_pid else None,
                     "often": {v: n for n, v in OFTEN.items()}.get(often.get(k, DEFAULT_OFTEN.get(k, 2)), "normal"),
                     "songs": counts.get(k, 0), "playlist": m["playlist"], "custom": bool(m.get("custom")),
                     "sound": m.get("sound", "") if m.get("custom") else "",
                     "themes": m.get("themes") if m.get("custom") else [],
                     "mix_only": bool(m.get("mix_only")), "mixes": mixes.get(k, 0),
                     "url": f"https://www.youtube.com/playlist?list={pid}" if pid else None})
    return rows


# ------------------------------------------------------------------ the song archive (for mood mixes)
# A job folder is swept a day after its upload; a mix needs the WHOLE song, its timed lyrics and its picture
# later, so every finished song keeps them here: state/songs/<job id>/ = song.mp3, info.json, picture.jpg.

def archive_song(job_id, song_path, info, picture=None, root=None):
    """Keep one finished song for its mood's mix. ``info``: title, mood, style, theme, lyrics, lines
    [(text, start, end)] over the whole song, colors. Returns the folder, or None (a mix is a bonus)."""
    root = root or ARCHIVE_DIR
    try:
        if not job_id or not os.path.isfile(song_path):
            return None
        d = os.path.join(root, re.sub(r"[^A-Za-z0-9_-]", "", job_id)[:64])
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(song_path, os.path.join(d, "song.mp3"))
        if picture and os.path.isfile(picture):
            from PIL import Image
            with Image.open(picture) as im:
                im.convert("RGB").save(os.path.join(d, "picture.jpg"), "JPEG", quality=90)
        with open(os.path.join(d, "info.json"), "w", encoding="utf-8") as f:
            json.dump({**info, "job_id": job_id, "at": int(time.time()), "picture": os.path.isfile(
                os.path.join(d, "picture.jpg"))}, f, ensure_ascii=False)
        return d
    except Exception as e:  # noqa: BLE001 — the Short is made either way
        print(f"   ℹ️ Song not archived for mixes ({type(e).__name__}: {str(e)[:100]}).")
        return None


def archived(root=None, now=None):
    """Every archived song's info (+ "dir"), oldest first; songs past ARCHIVE_DAYS are removed."""
    root = root or ARCHIVE_DIR
    now = now or time.time()
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        d = os.path.join(root, name)
        try:
            with open(os.path.join(d, "info.json"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if now - info.get("at", now) > ARCHIVE_DAYS * 86400:
            shutil.rmtree(d, ignore_errors=True)
            continue
        out.append({**info, "dir": d})
    return sorted(out, key=lambda i: i.get("at", 0))


def mark_mixed(dirs, mix_id):
    for d in dirs:
        p = os.path.join(d, "info.json")
        try:
            with open(p, encoding="utf-8") as f:
                info = json.load(f)
            info["mixed"] = mix_id
            with open(p, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)
        except (OSError, ValueError):
            pass


def mix_songs(mood, uploaded, songs=None):
    """The archived songs of ``mood`` that went up (job id in ``uploaded``) and were in no mix yet, oldest first.
    English songs only: a mix is one language (Urdu mood mixes are not made yet)."""
    songs = archived() if songs is None else songs
    return [s for s in songs if s.get("mood") == mood and s.get("job_id") in uploaded and not s.get("mixed")
            and lang_of(s) == "english"]


def next_mix(settings, jobs, songs=None, now=None, wanted=""):
    """(mood key, [song dirs]) of the mix due now, or None. At most ``mixes`` a week (the card's setting; 0 =
    off), a day after a failed try; a song mood is ready with MIX_MIN_SONGS of its uploaded songs not mixed
    before, a mix-only (instrumental) mood always (its tracks are made by the mix). The mood mixed longest ago
    goes first. ``wanted``: the owner's "make a mix now" (ignores the week's count)."""
    now = now or time.time()
    per_week = mix_setting(settings, "mixes")
    mixes = [j for j in jobs or [] if j.get("format") == "mix"]
    if not wanted:
        if per_week <= 0:
            return None
        recent = [j for j in mixes if j.get("status") in ("running", "done", "uploaded")
                  and now - j.get("at", 0) < 7 * 86400]
        if len(recent) >= per_week or any(j.get("status") == "running" for j in mixes):
            return None
        if any(j.get("status") == "failed" and now - j.get("at", 0) < MIX_RETRY for j in mixes):
            return None
    uploaded = {j.get("job_id") for j in jobs or [] if j.get("status") == "uploaded"}
    songs = archived() if songs is None else songs
    ready = []
    for key, m in active(settings).items():
        if wanted and key != wanted:
            continue
        if m.get("mix_only"):
            if m.get("instrumental") and mix_setting(settings, "mix_budget") > 0:
                ready.append((key, []))
            continue
        picked = mix_songs(key, uploaded, songs)
        if len(picked) >= (1 if wanted else MIX_MIN_SONGS):
            ready.append((key, [s["dir"] for s in picked[:MIX_MAX_SONGS]]))
    if not ready:
        return None
    last = {}
    for j in mixes:
        if j.get("mood"):
            last[j["mood"]] = max(last.get(j["mood"], 0), j.get("at", 0))
    return min(ready, key=lambda r: (last.get(r[0], 0), -len(r[1])))


def mix_summary(settings, jobs, songs=None):
    """{mood key: "6 of 8 songs for its next mix" / "mix only"} for the card."""
    uploaded = {j.get("job_id") for j in jobs or [] if j.get("status") == "uploaded"}
    songs = archived() if songs is None else songs
    out = {}
    for key, m in all_moods(settings).items():
        if m.get("mix_only"):
            out[key] = "mix only: its tracks are made for each mix"
        else:
            n = len(mix_songs(key, uploaded, songs))
            out[key] = (f"{n} new songs: a mix is ready" if n >= MIX_MIN_SONGS
                        else f"{n} of {MIX_MIN_SONGS} songs for its next mix")
    return out
