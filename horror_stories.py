"""Horror stories: the long-video channel's third mode (owner, 5-nov-2026: "Urdu/Hindi horror stories, long
videos of 15-30 minutes with teaser Shorts, painted pictures and a narrator").

Research that day (docs/research-2026-11-05): Scary Pumpkin (3.7M subscribers, ~29-minute videos) and Skull Tales
(~18 min) lead the niche; "horror story hindi urdu" is a top YouTube suggestion in Pakistan; long videos are what
the YPP terms of 1-feb-2027 reward (8,000 watch hours, or 10M Shorts views a quarter to keep Shorts pay).

history_videos.run makes the film (HISTORY_MODE=horror): this module gives it the ideas, the story (an ORIGINAL
fiction, so no web research or fact check: a story check instead), the footage rule, the painted look, the voice,
the grade, the music beds and the words of the description. The pipeline's voicing, shots, captions (Urdu and
English), chapters, thumbnail, teaser and moment Shorts are the history channel's.

Risk notes (research): YouTube's "repetitive content" rule (the same plot every time) -> the planner rotates plot
types (PLOTS) and never repeats a premise; ad-friendly horror is dread and suspense, never gore -> the pictures
suggest (a shadow, a door ajar) and never show blood, bodies or injuries; nothing is told as a true event about
real, named people or places (defamation, and Pakistan's PECA law on "fake news").
"""
import os
import re
import time

import short_kit as kit

MODE = "horror"
# Plot types the planner rotates through (one premise each, never the same plot twice in a row).
PLOTS = ["an old haveli and what lives in its locked room", "a highway at night and the passenger who should not "
         "be there", "a village well no one draws water from", "a hostel room and the roommate who never sleeps",
         "a hospital night shift on the empty ward", "a wedding house and the guest no one invited",
         "a mirror that shows the room a moment late", "an abandoned school and its last class",
         "the graveyard caretaker's one rule", "a cursed object bought cheap at a market",
         "a forest path that leads back to the same tree", "an old hill-station hotel and room 13",
         "a phone call from someone who died", "the last train and the empty carriage", "a lift that stops at a "
         "floor that is not there", "a new flat that was too cheap", "a fishing boat and the voice on the water",
         "a jinn story told by a grandmother, and the night it came true", "a photograph that changes",
         "a doll that keeps coming back", "a night bus through the mountains", "a house where the clocks all stop "
         "at 3:00"]

RULES = ("presenting the story as a true event that happened to real, named people or at a real, named building; "
         "naming a real person, family or living public figure as a victim, villain or possessed; gore: blood, "
         "wounds, torture, bodies, dismemberment or death described in graphic detail; any sexual content; a child "
         "hurt or killed; suicide or self-harm shown as a way out; mocking any religion, its rituals or holy "
         "people; quoting Quran verses or duas as spells, or teaching black magic, ta'weez or rituals as if they "
         "work; a religious figure, saint or shrine as the source of evil; hatred of any sect, caste, nation or "
         "people")

FOOTAGE_RULE = ("This is a horror story told by a narrator. Footage must feel dark and eerie and fit the line: night, "
                "fog, rain, candlelight, moonlight, flickering lamps, empty corridors, old doors and windows, "
                "staircases, abandoned houses and rooms, village lanes at night, forests, roads in the dark, old "
                "trains and stations, wells, mirrors, shadows, a person seen only from behind or as a silhouette. "
                "Never blood, wounds, injuries, bodies, coffins being opened, skulls, gore or monsters with gore; "
                "never a child in danger; never mosques, temples, churches, graves with names or any religious "
                "symbol as a scary thing; never text, logos or bright happy scenes. ")

AI_STYLE = ("Dark atmospheric digital painting for a horror story: cinematic, moody and eerie, deep shadows, cold "
            "moonlight or one warm flickering lamp, mist, muted desaturated colours with deep blues and greens, "
            "South Asian settings when the story is set there (old havelis, village lanes, courtyards, old trains, "
            "hill roads), wide 16:9 shot. Dread through suggestion: a shadow in a doorway, a figure far away or "
            "seen from behind, glowing eyes in the dark, a door left ajar. Clearly a painting, never a photograph. "
            "No blood, wounds, gore, bodies or skeletons; no religious symbols; no text, letters, captions, logos "
            "or watermarks.")

VOICE = os.environ.get("HORROR_VOICE") or "Algenib"        # Gemini TTS: a low, gravelly voice
VOICE_STYLE = {"urdu": "like a horror storyteller telling a ghost story late at night: low, slow and suspenseful, "
                       "natural Urdu accent, soft pauses before the scary moments, almost a whisper when it gets "
                       "close, never shouting",
               "english": "like a horror storyteller late at night: low, slow, suspenseful, soft pauses before the "
                          "scary moments, almost a whisper when it gets close"}
WORDS = {"urdu": {"intro": "Shuruaat", "full": "POORI KAHANI", "chapter": "HISSA",
                  "next": "Agli kahani agli raat", "follow": "Har hafte nayi darawni kahaniyan: subscribe karein 🔔"},
         "english": {"intro": "Intro", "full": "THE FULL STORY", "chapter": "PART",
                     "next": "The next story comes soon", "follow": "Subscribe for the next horror story 🔔"}}
FICTION = {"urdu": ("Yeh kahani farzi (fiction) hai: is ke kirdaar, naam, jagahein aur waqiaat kalpanik hain, kisi "
                    "asal shakhs ya jagah se mel sirf ittefaq hai. Pictures AI se banayi gayi paintings aur free stock "
                    "footage hain."),
           "english": ("This story is fiction: its characters, names, places and events are made up, and any "
                       "likeness to real people or places is a coincidence. The pictures are AI-made paintings and "
                       "free stock footage.")}
# Music beds under the chapters: music_beds.PROMPTS["horror"] (Lyria clips, a pool that grows like every kind's).
# A low hit on each chapter card instead of the documentary's whoosh (aevalsrc, 1.2 s).
STING = "0.55*sin(2*PI*(52-22*t)*t)*exp(-2.6*t)+0.08*(random(0)-0.5)*exp(-5*t)"
GRADE = ("eq=contrast=1.12:brightness=-0.05:saturation=0.55,"
         "colorbalance=rs=-0.05:gs=0.01:bs=0.07:rm=-0.03:bm=0.04,vignette=angle=PI/4.5")
# The same cold look, lifted, for a shot the dark grade turned to black (history_videos._shot_tries): the first
# live story (5-nov-2026) was refused at upload for "6 s of black picture".
GRADE_LIFT = ("eq=contrast=1.04:brightness=0.04:saturation=0.6:gamma=1.3,"
              "colorbalance=rs=-0.05:gs=0.01:bs=0.07:rm=-0.03:bm=0.04,vignette=angle=PI/7")
AI_IMAGES = int(os.environ.get("HORROR_AI_IMAGES") or 14)   # painted scenes per video (~$0.04 each); footage fills the rest
# Measured, not guessed: one test line read at 86 words a minute, but the first whole story (8 paragraphs, 249
# words) at 160, the documentary narrator's pace (history_videos.WORDS_PER_MINUTE 150). Planned at 90 a "14-minute"
# story came out at about 7. FILL leaves room for the cards; a slower voice is caught by history_videos.fit_voices
# (a video meant for an unverified channel never passes 14:45: YouTube refuses over 15:00).
WPM, FILL = 150, 0.95
TREND_QUERIES = {"urdu": ["horror story urdu", "horror story hindi", "bhoot ki kahani", "jinn ki kahani urdu",
                          "darawni kahani"],
                 "english": ["horror story", "scary stories", "haunted house story"]}

IDEAS_PROMPT = """Today is {today}. Plan the next {count} long YouTube videos ({minutes}-minute horror stories
narrated in {lang}) for a horror story channel for Pakistani and Indian viewers: ORIGINAL fiction, told by a
narrator over dark paintings and footage, the way the most watched Hindi/Urdu horror channels tell them.
Each idea is one story premise with a hook and a mystery, set in South Asia (a city, village, highway, hostel,
hospital, haveli...), with ordinary characters a viewer believes in.
Vary the kind of story; plot types to draw from (never two of the same kind in this list, and not the kinds of
the stories already made): {plots}.
{owner}{trending}{learn}Never: {rules}.
Never repeat or closely echo any of these, already made:
{avoid}
One per line, each starting with "topic: ", at most 90 characters, in English, no translation in brackets. You may
plan ONE story too big for a single video as a series of 2 or 3 parts on one line instead:
"series: <series name> | <part 1> | <part 2> | <part 3>". At most one series line. Nothing else."""

SCRIPT_PROMPT = """You write the full script of a {minutes}-minute horror story for the YouTube channel {handle}.
Story premise: {topic}
Audience: Pakistani and Indian viewers who love a good scare. Every spoken line, the title, chapter titles, labels
and the question are in {lang_rule}.
This is ORIGINAL FICTION: invent the characters (everyday names), the places (a town, a lane, a house: never a
real, named building or a real person) and every event. Never copy or retell a film, book, game or famous online
story. Never claim it really happened ("sachi kahani", "a true story"); the narrator may say "kehte hain..." or
"yeh kahani mujhe ek dost ne sunai thi" as storytelling.
{fixes}
How great horror narration works: open cold on the scariest moment, then go back to an ordinary beginning; build
dread slowly with small wrong details (a sound, a smell, a door that was closed); give the hero a reason to stay;
each chapter ends on a cliffhanger; the truth is revealed late; the ending has a twist the viewer did not see
coming, and one last chill. Suspense through what is NOT shown; no gore.
Write about {words} spoken words in total: this sets the video's length, so do not stop short.
Return:
- allowed: false only if the premise needs {rules}. reason: why, or "".
- sacred: false.
- title: the YouTube title, max 70 characters, in the way horror titles work ("Purani Haveli Ka Band Kamra |
  Horror Story in Urdu"), the main search words early ("horror story", "darawni kahani"), no emoji, no claim that
  it is true.
- thumb_text: 2 to 4 words for the thumbnail, chilling and short ("WOH WAPAS AAYI", "KAMRA NO. 13").
- thumb_picture: English, one eerie picture for the thumbnail (place, light, a silhouette; no text, no gore).
- summary: 2 sentences for the top of the description that tease the story without the ending.
- hook: 2 or 3 scenes, the first 30-45 seconds: the scariest moment, cut off before the answer, then "par yeh sab
  shuru kaise hua?"; no "hello friends", no channel intro.
- chapters: {chapters} chapters in story order (title max 40 characters), each with about {scenes} scenes.
- each scene: line = what the narrator says, one paragraph of 35-70 words, vivid, simple, spoken, full of small
  sounds and details; picture = English, what the screen shows during it for stock footage or a painting: a
  concrete dark place, object or light ("long corridor of an old haveli at night, one lamp flickering", "a woman in
  a shawl seen from behind on a foggy village lane"), never gore, never a face up close; wiki = ""; label = an
  on-screen label of at most 32 characters: a time or place ("RAAT 3:00 BAJE", "MURREE, DECEMBER"), or "";
  map = "".
- outro: one paragraph: a last chill, then ask viewers whether something like this ever happened to them, and to
  subscribe for the next story.
- question: max 90 characters, asks viewers' opinion or their own experience in the comments.
- tags: 8 to 12 YouTube search tags ("horror story in urdu", "darawni kahani", "bhoot ki kahani", "hindi horror
  story", the setting...)."""

CHECK_PROMPT = """You check a horror story script for a YouTube channel before it is narrated and published.
SCRIPT (title, then the narration in order):
{script}

List only real problems:
- it breaks a rule: {rules};
- it is a retelling of a known film, book, game or famous online story (name it);
- the plot contradicts itself, the twist is missing or explained away, or a chapter does nothing;
- a picture description asks for gore, a body, a child in danger or a religious symbol as evil.
Small wording choices are fine. Return ok=true when there is no real problem; otherwise ok=false and the problems,
each short and specific."""


def lang_rule(lang):
    import history_videos as hv
    return hv.LANG_RULE.get(lang, hv.LANG_RULE["urdu"])


def channel_ideas(client, count=2, avoid=(), best=(), worst=(), notes="", lang="urdu", minutes=20, requests=()):
    """The next story ideas, like history_videos.channel_ideas ([{"kind": "topic", "text"}], a series as parts)."""
    import cricket_shorts as cs
    import engage
    import history_videos as hv
    learn = engage.request_hint(requests)
    if best:
        learn += "These did BEST on the channel, make more of their kind:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    owner = f"The channel owner wants stories like: {notes}\n" if (notes or "").strip() else ""
    hot = trending(lang)
    hint = ("Horror videos like these got the most views on YouTube this month (learn what pulls viewers in, never "
            "copy a title or a plot):\n" + "\n".join(hot) + "\n") if hot else ""
    text, _ = cs.grounded(client, IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=max(count * 3, 6), minutes=minutes,
        lang=hv.LANG_NAME.get(lang, lang), plots="; ".join(PLOTS), owner=owner, trending=hint, learn=learn,
        rules=RULES, avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    ideas = [i for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen]
    return (hv.series_ideas(text, seen) + ideas)[:count * 3 + 2]


def trending(lang, limit=8):
    """Titles of the most viewed horror videos this month (trend_explainer's YouTube search), or []."""
    try:
        import trend_explainer as te
        rows = []
        for q in TREND_QUERIES.get(lang, TREND_QUERIES["urdu"])[:3]:
            rows += te._search(q, date="month", limit=6)
        rows.sort(key=lambda r: -(r.get("views") or 0))
        return [f"{r['title']} ({r.get('views') or 0:,} views)" for r in rows[:limit] if r.get("title")]
    except Exception:  # noqa: BLE001 — the planner works without them
        return []


def shape(minutes):
    """(words, chapters, scenes per chapter) of a story ``minutes`` long when read at the horror pace."""
    import history_videos as hv
    words = round(minutes * WPM * FILL)
    _w, chapters, _s = hv.shape(minutes)
    scenes = max(2, min(8, round((words - 60) / chapters / 50)))
    return words, chapters, scenes


def write(client, topic, handle, minutes=20, lang="urdu", series_note=""):
    """(Script, story brief, []) that passed the story check, or raises. The brief (title + summary + chapter
    titles) stands in for the research facts where the pipeline wants text about the video."""
    import history_videos as hv
    import script_craft as craft
    from quiz_shorts import quiz_model
    words, chapters, scenes = shape(minutes)
    fixes, notes, got = "", [], 0
    for attempt in range(2):
        script = kit.ask_json(client, hv.Script, SCRIPT_PROMPT.format(
            minutes=minutes, handle=handle, topic=topic + (f"\n{series_note}" if series_note else ""),
            lang_rule=lang_rule(lang), fixes=fixes, words=words, chapters=chapters, scenes=scenes, rules=RULES)
            + "\n\n" + craft.long_rules(), model=quiz_model())
        if not script.allowed:
            raise RuntimeError(f"Not made: {script.reason or 'the story is not for this channel'}.")
        if len(script.chapters) < 2 or not script.hook:
            raise RuntimeError("The story came back without chapters; try again later.")
        script.sacred = False
        for s in hv.scenes_of(script):           # fiction: never a Wikipedia picture or an empire map
            s.wiki, s.map = "", ""
        craft.polish_opening(client, script, brief(script), what="horror story",
                             language=hv.LANG_NAME.get(lang, "Roman Urdu") + (" in Latin letters" if lang == "urdu" else ""))
        notes = []
        got = hv.word_count(script)
        if got < words * 0.75:
            notes.append(f"The story is too short: {got} words. Write about {words} words, with more scenes.")
        check = kit.ask_json(client, hv.Check, CHECK_PROMPT.format(script=hv._narration_text(script), rules=RULES),
                             model=quiz_model())
        if not check.ok:
            notes += check.problems
        if not notes or (check.ok and got >= hv.MIN_MINUTES * WPM * 0.8 and attempt == 1):
            return script, brief(script), []
        if attempt == 0:
            print(f"   ⚠️ Rewriting once: {len(notes)} note(s) ({'; '.join(n[:60] for n in notes[:3])}).")
            fixes = "Fix these problems found in the last version:\n- " + "\n- ".join(notes)
    if check.ok:
        raise RuntimeError(f"The story came back too short twice ({got} words); try again later.")
    raise RuntimeError("The story did not pass its check twice (" + "; ".join(notes[:2])[:200] + "); skipped.")


SEARCH_WORDS = {"urdu": "Horror Story in Urdu", "english": "Horror Story"}


def search_title(title, lang="urdu"):
    """The title with the niche's search words: the title tournament picks the clickiest line ("Khali ward mein
    3:15 baje bajti hai emergency bell", first live run) and dropped "Horror Story", which is what viewers type."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if "horror" in title.lower() or "darawni" in title.lower() or "bhoot" in title.lower():
        return title[:100]
    tail = f" | {SEARCH_WORDS.get(lang, SEARCH_WORDS['urdu'])}"
    return title[:100 - len(tail)].rstrip(" |") + tail


def brief(script):
    return "\n".join([script.title, script.summary] + [c.title for c in script.chapters])


def describe_extra(lang):
    """Lines for the description: the fiction note."""
    return FICTION.get(lang, FICTION["urdu"])


def thumb_colour():
    return os.environ.get("HORROR_THUMB_COLOUR") or "red"


def clean_label(text):
    """Labels stay short and plain on a dark picture."""
    return re.sub(r"\s+", " ", text or "").strip()[:32]
