"""Long videos for the history channel (CONTENT_GENRE=history).

2-30 minute 16:9 documentaries about empires, countries, famous events,
governments and economies ("Rome ki poori kahani", Karbala, the US debt),
told by a Gemini narrator over slowly moving pictures. The channel plans
its own topics (what similar long videos get views on YouTube this month,
plus Google Search, plus the owner's wishes and the channel's own numbers).

How one video is made:
1. Research: two Google-Search-grounded calls (the dated story; the
   lesser-known facts). Fewer than MIN_SOURCES sources: no video.
2. Script: a hook, chapters of scenes (one voice paragraph each, what the
   picture shows, the Wikipedia article whose pictures fit, an on-screen
   label), an outro and a comment question. A second call checks it against
   the research (dates, numbers, a disputed point told as settled, words
   that judge a religion, sect or nation); one rewrite with its notes, then
   no video.
3. Pictures: free-licence pictures of the scenes' Wikipedia articles first
   (paintings, maps, coins, places; credited in the description), matched to
   scenes by one text call; AI pictures for scenes nothing fits, at most
   AI_IMAGES a video (about $0.067 each at 1K, Gemini API pricing
   15-oct-2026); the rest re-use a picture with a closer crop. Never Google
   Images: agency photos are what copyright strikes are made of.
4. Voice per scene; a new shot every ~SHOT_SECONDS with a slow pan; chapter
   cards; captions. Each shot is its own short encode (the picture is decoded
   once and looped, the pan is a crop on a 2x canvas scaled down, so it moves
   in half pixels) and the concat demuxer joins them, so the video is encoded
   once. The narration, chapter whooshes and a music bed per chapter are mixed
   in a last pass that copies the video.
5. A thumbnail (AI picture with PIL text) and YouTube chapters in the
   description.

Religion: a story about prophets, the Prophet's family, the companions, the
imams or other revered figures is `sacred`: nobody is shown (AI pictures show
places, landscapes and objects; paintings and artwork are dropped), there is
no music bed, and where Sunni and Shia (or other) accounts differ the script
says so without judging. A picture whose name or description names a prophet
or revered figure is dropped on every video unless it is a place or object
("The shrine of Imam Hussain in Karbala" stays, a painting of him does not).

Env: HISTORY_TOPIC, HISTORY_MINUTES (2-30), HISTORY_LANG (urdu | english),
HISTORY_VOICE, BG_MUSIC, HISTORY_AI_IMAGES, HISTORY_IMAGE_SIZE,
HISTORY_CAPTIONS (default on). HISTORY_TEASER_OF (a finished long video's job
dir) + HISTORY_VIDEO_ID make its teaser Short instead (run_teaser).
"""
import glob
import io
import json
import os
import random
import re
import subprocess
import textwrap
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import List

import httpx
from pydantic import BaseModel

import framed_layout as fl
import script_craft as craft
import short_kit as kit
import viral_remix
from ffmpeg_utils import LOUDNORM_FILTER, METADATA_SCRUB, escape_filter_value

W, H, FPS = 1920, 1080, 30
SUPER = 2                      # the pan runs on a 2x canvas, then scales down: half-pixel steps
PAN = 1.15                     # the canvas is 15% larger than the frame: room to pan
CANVAS_W, CANVAS_H = round(W * PAN) * SUPER, round(H * PAN) * SUPER
MIN_MINUTES, MAX_MINUTES, DEFAULT_MINUTES = 2, 30, 10
WORDS_PER_MINUTE = 150
MIN_SOURCES = 3
# A new picture or a closer crop about this often: 7 s since quality pass 2 (was 11; the audit put
# pro documentaries at 4-6 s a shot, and every scene is one picture, so shorter means more crops of it).
SHOT_SECONDS = 7.0 if os.environ.get("HISTORY_MOTION", "1").strip() != "0" else 11.0
GAP = 0.35                     # after each voice paragraph
TITLE_CARD, CHAPTER_CARD, END_CARD = 3.2, 2.6, 6.0
# Free by default (owner, 15-oct-2026: "everything should be free"): Wikipedia
# and stock footage only. AI pictures (~$0.067 each) and the AI thumbnail
# (~$0.10) come back with HISTORY_AI_IMAGES=10 / HISTORY_AI_THUMBNAIL=1.
AI_IMAGES = int(os.environ.get("HISTORY_AI_IMAGES") or 0)
AI_THUMBNAIL = os.environ.get("HISTORY_AI_THUMBNAIL", "0") == "1"
AI_IMAGE_SIZE = os.environ.get("HISTORY_IMAGE_SIZE") or "1K"
WIKI_WIDTH = 1920              # a standard Wikimedia thumbnail width
MAX_ARTICLES = 16
PER_ARTICLE = 14
LANGS = ("urdu", "english")
LANG_NAME = {"urdu": "Roman Urdu", "english": "English"}
LANG_RULE = {
    "urdu": "everyday Roman Urdu (Urdu/Hindi in Latin letters, the way Pakistani YouTubers write it), never "
            "Devanagari or Arabic script; English words where people use them; years and numbers as digits",
    "english": "simple, vivid spoken English that viewers in Pakistan and India follow easily; years and numbers "
               "as digits"}
VOICE_STYLE = {
    "urdu": "like a calm, captivating history documentary narrator, natural Urdu accent, warm, clear, steady pace",
    "english": "like a captivating history documentary narrator, warm, clear and steady"}
MODES = ("history", "explainer", "horror")
MODE_NAME = {"history": "History", "explainer": "Explainer", "horror": "Horror story"}
# Uploads of the long channel: "horror" ones go up as Entertainment (youtube_account.CATEGORY), the rest as history.
LONG_GENRES = ("history", "horror")


def mode_now():
    """The long video's subject (HISTORY_MODE): history documentaries, news explainers (trend_explainer.py) or
    horror stories (horror_stories.py)."""
    m = (os.environ.get("HISTORY_MODE") or "").lower()
    return m if m in MODES else "history"


def voice_for(mode):
    if mode == "horror":
        import horror_stories
        return horror_stories.VOICE
    return "Charon"


def words_for(lang, mode="history"):
    if mode == "horror":
        import horror_stories
        return dict(horror_stories.WORDS.get(lang, horror_stories.WORDS["urdu"]))
    return dict(WORDS.get(lang, WORDS["urdu"]))


WORDS = {"urdu": {"intro": "Shuruaat", "full": "POORI KAHANI", "chapter": "CHAPTER",
                  "next": "Agli kahani jald aa rahi hai", "follow": "Nayi tareekhi kahaniyon ke liye subscribe karein 🔔"},
         "english": {"intro": "Intro", "full": "THE FULL STORY", "chapter": "CHAPTER",
                     "next": "The next story is coming soon", "follow": "Subscribe for the next story 🔔"}}
# Pakistani viewers expect these titles; the first real video (Karbala, 15-oct-2026)
# said "Prophet Muhammad" and a bare "Husayn", which reads as disrespect there.
HONOUR = {
    "urdu": "When the Prophet Muhammad is named, the narration says \"Hazrat Muhammad sallallahu alaihi wasallam\" "
            "and written text (title, labels, summary, question) says \"Hazrat Muhammad (SAW)\"; call the Prophet's "
            "family and companions \"Hazrat\" (Hazrat Imam Husain, Hazrat Ali, Hazrat Zainab, Hazrat Abbas) and other "
            "prophets \"Hazrat ... alaihis salam\". No title that only one sect uses.",
    "english": "When the Prophet Muhammad is named, write \"Prophet Muhammad (peace be upon him)\"; call the Prophet's "
               "family and companions by their respectful titles (Imam Husain, Hazrat Ali). No title that only one "
               "sect uses."}
RULES = ("mocking or judging any religion, sect, prophet or revered religious figure; taking sides in current "
         "party politics or elections; hate against any nation, ethnic group or religion; graphic gore; "
         "private people who are not public figures")
SACRED = ("prophets, the Prophet's family (Ahl al-Bayt), the companions (Sahaba), the imams, or other revered "
          "religious figures")
NO_PEOPLE = f"For anything about {SACRED}: show NO people at all, only places, landscapes, objects, maps and light."
# Stock libraries are mostly today's world: a car or a phone in a scene about 476 AD breaks the story.
FOOTAGE_RULE = ("This is a history documentary: never modern things (cars, phones, screens, modern buildings, "
                "power lines, people in modern clothes) unless the scene is about today. ")
# A long video that dies of an outage is queued again (my_channels._requeue) and used to start from nothing:
# the grounded research, the script, its fact check and the title tournament are paid again (~$0.3-0.5 and
# 5-15 minutes). They are kept here for RESUME_HOURS, by the video's settings, and the next try starts at the voice.
RESUME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "resume")
RESUME_HOURS = 48


class Scene(BaseModel):
    line: str
    picture: str
    wiki: str
    label: str
    map: str = ""


class Chapter(BaseModel):
    title: str
    scenes: List[Scene]


class Script(BaseModel):
    allowed: bool
    reason: str
    sacred: bool
    title: str
    thumb_text: str
    thumb_picture: str
    summary: str
    hook: List[Scene]
    chapters: List[Chapter]
    outro: str
    question: str
    tags: List[str]


class Check(BaseModel):
    ok: bool
    problems: List[str]


class Pick(BaseModel):
    scene: int
    picture: int


class Picks(BaseModel):
    picks: List[Pick]


FACTS_PROMPT = """Today is {today}. Research this topic for a {minutes}-minute history documentary on YouTube: {topic}
Use Google Search and reliable sources (encyclopaedias, universities, museums, major newspapers, historians).
Write a detailed, dated account: the background; the main events in order with dates, places and the key
people; numbers (armies, money, population, years); causes and consequences; how it ended or where it stands
today. Mark anything historians dispute as DISPUTED and say who holds which view. If it touches religion, give
the mainstream historical account and say where Sunni, Shia or other accounts differ.
Be thorough: about {fact_words} words, enough for every chapter of the video.
If fewer than three reliable sources cover it, answer only "NOT FOUND"."""

EXTRA_PROMPT = """Today is {today}. For a history documentary about: {topic}
Use Google Search. List 8 to 12 surprising, lesser-known but well sourced facts, numbers and short quotes (with
who said them) that make viewers say "I never knew that". One per line, each with its source's name.
Only quotes with a documented original (a book, letter, speech or chronicle); skip popular quotes that circulate
online without one (many quotes about historical figures credited to Dickens, Gandhi, Einstein or Napoleon are)."""

SCRIPT_PROMPT = """You write the full script of a {minutes}-minute YouTube documentary for the channel {handle}.
Topic: {topic}
Audience: Pakistani and Indian viewers. Every spoken line, the title, chapter titles, labels and the question are
in {lang_rule}.
Use ONLY the facts below; never invent a date, number, name or quote.
{fixes}
FACTS:
{facts}

MORE FACTS:
{extra}

Write about {words} spoken words in total: this sets the video's length, so do not stop short.
Return:
- allowed: false if the topic can only be told with {rules}. reason: why, or "".
- sacred: true if the story involves {sacred}.
- title: the YouTube title, max 70 characters, curiosity first with the main keyword early (e.g. "Roman Empire
  Kaise Khatam Hua? Rome Ki Poori Kahani"), true, no clickbait lies, no emoji.
- thumb_text: 2 to 4 words for the thumbnail, big and punchy, not the title repeated.
- thumb_picture: English, one dramatic picture for the thumbnail (place, objects, era, light; no text).
- summary: 2 or 3 sentences for the top of the description.
- hook: 2 or 3 scenes, the first 30-45 seconds: open on the most gripping moment or question of the story and
  promise what the viewer will learn; no "hello friends", no channel intro.
- chapters: {chapters} chapters in story order, each with a title (max 40 characters) and about {scenes} scenes.
- each scene: line = what the narrator says, one paragraph of 35-70 words, vivid, simple, spoken, telling a story
  with tension and a reason to keep watching (end some chapters on a small cliffhanger);
  picture = English, what the screen shows during it: a concrete place, building, object, map, coin, document,
  an army or crowd seen from far away, with era-accurate details;
  wiki = the exact English Wikipedia article title whose pictures fit this scene best ("Battle of Karbala",
  "Colosseum", "Great Depression"), or "";
  label = an on-screen label of at most 32 characters: a year, place, name or number ("680 AD", "KARBALA, IRAQ"),
  or "";
  map = only for one or two scenes where seeing an empire's land grow or shrink tells the story (a conquest, its
  peak, its fall): "<empire as maps name it> | <from year> | <to year>", years as plain numbers AD (BC negative),
  e.g. "Mughal Empire | 1526 | 1707"; else "".
- outro: one paragraph that wraps up the story and its lesson and asks viewers to subscribe for the next story.
- question: max 90 characters, asks viewers' opinion in the comments, never which religion or sect is right.
- tags: 8 to 12 YouTube search tags (topic, places, people, "history in urdu"...).
{no_people} {honour}
Never mock or judge any religion, sect, nation or people; dates in AD (and Hijri for Islamic history when
known); where accounts differ, say so fairly. Spoken lines are read aloud by a voice: no Roman numerals
("Yazid awwal" / "Yazid the First", never "Yazid I"), "Hijri" not "AH". Quote someone only when the facts tie the
quote to a documented original; leave out famous quotes that circulate online without one."""

CHECK_PROMPT = """You fact-check a YouTube documentary script before it is published.
FACTS (from research with sources):
{facts}

MORE FACTS:
{extra}

SCRIPT (title, then the narration in order):
{script}

A true, widely known fact the research happens not to mention is fine (the first real check rejected a whole
Rome script for naming Ravenna). List only real problems:
a date, number, name or quote that contradicts the facts or looks invented; a quote from a famous person
with no documented original (viral quotes are often misattributed); a DISPUTED point told as settled;
one-sided or judgmental words about any religion, sect, nation or people; disrespect to any religious figure,
including the Prophet Muhammad or his family named without their customary titles ({honour_short});
taking sides in current party politics{more} Small wording choices are fine.
Return ok=true when there is no real problem; otherwise ok=false and the problems, each short and specific."""

PICK_PROMPT = """Pick pictures for the scenes of a history documentary about: {topic}
SCENES (number: what the screen should show):
{scenes}

FREE PICTURES (number: file name | description):
{pictures}

For each scene choose the free picture that fits it best: the very place, building, object, person or event; else
the same era, ruler, city or region (a bust of the emperor named, ruins of the city, a coin of the time); a map
fits a scene about where something happened. A real picture that fits is better than none: use -1 only when
nothing is close (an AI picture is made instead, and there are few of those). Use each picture at most twice.
Never choose a picture that shows {sacred}{art}.
Return exactly {n} picks, one per scene, by number."""

AI_STYLE = ("Cinematic digital painting for a history documentary: realistic, era-accurate clothing, architecture "
            "and objects, dramatic natural light, rich but muted colours, wide 16:9 shot. No text, letters, "
            "numbers, captions, logos or watermarks anywhere. No modern objects. Clearly a painting, never a "
            "photograph; no blood, wounds, bodies or people dying: show war and disaster through places, "
            "distant armies and objects.")
# The last sentence (29-oct-2026): YouTube does not monetize realistic synthetic visuals that imply a
# death or a disaster (support.google.com/youtube/answer/1311392, clarified July 2026).

IDEAS_PROMPT = """Today is {today}. Plan the next {count} long YouTube videos ({minutes}-minute documentaries, in
{lang}) for a history and stories channel for Pakistani and Indian viewers. Topics like: the rise and fall of
empires (Rome, the Ottomans, the Mughals, the Abbasids), Islamic history told with respect (Karbala, the Caliphs,
Al-Andalus), famous wars and events, how countries work and why they got rich or poor (the US government, the US
economy, the dollar, China, the Gulf states), mysteries and turning points of history.
About one idea in three is the story of a famous woman of history, told as drama and power: queens,
empresses, warriors and rulers (Razia Sultana, Noor Jahan, Cleopatra, Rani of Jhansi, Hurrem Sultan,
Chand Bibi, Elizabeth I, Shajar al-Durr). Never a woman of the Prophet's family or his companions:
those stories are told only with the respect of a sacred story.
{owner}{trending}Use Google Search for what people search and talk about now: anniversaries this month, news
that makes an old story matter again.
Each idea is one clear story with a hook, e.g. "Roman Empire: how the greatest empire fell", "Karbala: what
happened in 680 AD", "How the US government really works", "Why America owes so much money".
Never: {rules}.
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "topic: ", at most 90 characters, no translation in brackets.
When one big story is too much for a single video (an empire's whole history), you may plan it ONCE as a series
of 2 to 4 parts on one line instead: "series: <series name> | <part 1 topic> | <part 2 topic> | <part 3 topic>",
each part its own clear story in time order. At most one series line. Nothing else."""

TREND_QUERIES = {
    "urdu": ["history in urdu", "tareekh documentary urdu", "islamic history urdu", "rise and fall empire urdu",
             "economy explained urdu hindi"],
    "english": ["history documentary", "rise and fall of empire documentary", "economy explained documentary",
                "islamic history documentary", "ancient history story"]}

EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".svg")
JUNK = re.compile(r"logo|icon|symbol|\bpog\b|arrow|commons-|wiki|question_book|padlock|ambox|nuvola|crystal_clear|"
                  r"folder|portal|stub|edit-|signature|disambig|speaker|audio|sound|increase|decrease|steady|"
                  r"red_x|check_mark|yes_check|blank|placeholder|location_dot|ooj|emblem-|lock-", re.I)
SACRED_NAMES = re.compile(r"muhammad|mohammed|mohammad|prophet|husayn|hussain|husain|hosein|hasan ibn|ali ibn abi|"
                          r"\bimams?\b|fatima|fatimah|zainab|zaynab|abbas ibn ali|abu bakr|umar ibn|omar ibn|"
                          r"uthman|ahl al-bayt|sahaba|jesus|\bchrist\b|moses|abraham|\bnoah\b|\bangels?\b|"
                          r"gabriel|jibril|buraq|mi'?raj", re.I)
PLACE = re.compile(r"shrine|mosque|masjid|tomb|mausoleum|\bmap\b|coin|dinar|dirham|inscription|building|gate|"
                   r"minaret|dome|city|aerial|view of|interior|exterior|courtyard|pilgrim|mount\b|desert|river|"
                   r"ruins?\b|manuscript page|quran", re.I)
ART = re.compile(r"painting|artwork|miniature|museum|depict|illustration|fresco|mural|ta'?ziy|tazia|scene de|"
                 r"sc[eè]ne|tile ?work|drawing|engraving|portrait|battle of", re.I)


# ------------------------------------------------------------------ planning

def trending(lang, limit=8):
    """Titles and views of long videos like ours that got views this month."""
    import channel_tools

    def one(q):
        try:
            return channel_tools.search(q, cc=False, date="month", sort="views", limit=limit)
        except Exception:  # noqa: BLE001 — a hint, never needed
            return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        found = [v for got in pool.map(one, TREND_QUERIES.get(lang) or TREND_QUERIES["urdu"]) for v in got]
    seen, rows = set(), []
    for v in found:
        if v["id"] in seen or not v.get("views") or (v.get("seconds") or 0) < 240:
            continue
        seen.add(v["id"])
        rows.append(v)
    rows.sort(key=lambda v: v["views"], reverse=True)
    return [f"{v['title'][:90]} ({v['views']:,} views)" for v in rows[:25]]


def channel_ideas(client, count=2, avoid=(), best=(), worst=(), notes="", lang="urdu", minutes=DEFAULT_MINUTES,
                  requests=(), mode="history"):
    if mode == "explainer":
        import trend_explainer
        return trend_explainer.channel_ideas(client, count, avoid, best, worst, notes, lang, minutes, requests)
    if mode == "horror":
        import horror_stories
        return horror_stories.channel_ideas(client, count, avoid, best, worst, notes, lang, minutes, requests)
    import cricket_shorts as cs
    import engage
    learn = engage.request_hint(requests)
    if best:
        learn += "These did BEST on the channel, make more like them:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    owner = f"The channel owner wants topics like: {notes}\n" if (notes or "").strip() else ""
    hot = trending(lang)
    hint = ("Long videos like these got the most views on YouTube this month (topics to learn from, never copy a "
            "title):\n" + "\n".join(hot) + "\n") if hot else ""
    text, _ = cs.grounded(client, IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=max(count * 3, 6), minutes=minutes, lang=LANG_NAME.get(lang, lang),
        owner=owner, trending=hint, rules=RULES, learn=learn,
        avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    ideas = [i for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen]
    return (series_ideas(text, seen) + ideas)[:count * 3 + 2]


def series_ideas(text, seen=()):
    """The planner's "series: name | part 1 | part 2 ..." line as one idea per
    part, in order (one series per plan; the first one wins)."""
    for line in (text or "").splitlines():
        m = re.match(r"\W*series\s*:\s*(.+)", line.strip(), re.I)
        if not m:
            continue
        bits = [re.sub(r"\s+", " ", b).strip(" *\"'")[:120] for b in m.group(1).split("|")]
        name, parts = bits[0], [b for b in bits[1:] if b][:SERIES_MAX]
        if not name or len(parts) < 2 or any(p.lower() in seen for p in parts):
            continue
        return [{"kind": "topic", "text": p, "series": name, "part": k, "parts": len(parts), "before": parts[:k - 1]}
                for k, p in enumerate(parts, 1)]
    return []


# ------------------------------------------------------------------ writing

def minutes_wanted(raw):
    try:
        return max(MIN_MINUTES, min(MAX_MINUTES, int(float(raw))))
    except (TypeError, ValueError):
        return DEFAULT_MINUTES


def shape(minutes):
    """(words, chapters, scenes per chapter) for a video of ``minutes``."""
    words = minutes * WORDS_PER_MINUTE
    chapters = max(2, min(12, round(minutes * 0.6)))
    scenes = max(2, min(8, round((words - 100) / chapters / 55)))
    return words, chapters, scenes


def research(client, topic, minutes, prompts=None):
    """(facts, extra facts, [(source name, url)]). ``prompts``: (facts, extra)
    prompt templates of another mode (trend_explainer's)."""
    from google.genai import types
    facts_prompt, extra_prompt = prompts or (FACTS_PROMPT, EXTRA_PROMPT)
    today = time.strftime("%d %B %Y")

    def ask(prompt):
        r = client.models.generate_content(
            model=kit.text_model(), contents=prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        gm = r.candidates[0].grounding_metadata if r.candidates else None
        out = []
        for c in getattr(gm, "grounding_chunks", None) or []:
            web = getattr(c, "web", None)
            if web and web.uri:
                out.append(((web.title or "").strip(), web.uri))
        return (r.text or "").strip(), out
    with ThreadPoolExecutor(max_workers=2) as pool:
        main = pool.submit(ask, facts_prompt.format(today=today, minutes=minutes, topic=topic,
                                                    fact_words=max(600, min(3000, minutes * 120))))
        more = pool.submit(ask, extra_prompt.format(today=today, topic=topic))
        (facts, s1), (extra, s2) = main.result(), more.result()
    seen, sources = set(), []
    for name, uri in s1 + s2:
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        sources.append((name, uri))
    return facts, extra, sources


# The description lists 8 sources. In Google's order the first real Rome video
# listed wikihow, medium and studypug while Britannica-class sources sat lower.
GOOD_SOURCE = re.compile(r"britannica|wikipedia|worldhistory|\.edu\b|\.ac\.|museum|bbc|nationalgeographic|"
                         r"history\.com|smithsonian|nytimes|theguardian|reuters|apnews|aljazeera|dawn\.com|jstor|"
                         r"oxford|cambridge|loc\.gov|archives|livius|\.gov\b|nasa|unesco|imf\.org|worldbank", re.I)
WEAK_SOURCE = re.compile(r"wikihow|medium\.com|quora|reddit|studypug|study\.com|youtube|facebook|instagram|tiktok|"
                         r"pinterest|blogspot|wordpress|brainly|coursehero|scribd|slideshare|planner|answers\.", re.I)


def rank_sources(sources):
    """Reputable sources first, social and homework sites last, else Google's order."""
    def key(item):
        k, (name, url) = item
        text = f"{name} {url}"
        return (0 if GOOD_SOURCE.search(text) else 2 if WEAK_SOURCE.search(text) else 1, k)
    return [s for _k, s in sorted(enumerate(sources), key=key)]


MAX_MAPS = 2
MAP_LAST_YEAR = 1925     # empires that ended before modern borders (the Ottomans, 1923, stay; the Raj, 1947, not)


def add_maps(script, pics, log=print):
    """Scenes whose ``map`` names an empire the Cliopatria data knows (history_maps.find) get an
    animated map as their first shot. pics[k] is shared between scenes with the same picture, so a
    scene with a map gets its own copy. Returns how many maps the video uses."""
    import history_maps
    if not history_maps.available():
        return 0
    used = 0
    for k, s in enumerate(scenes_of(script)):
        parts = [p.strip() for p in (getattr(s, "map", "") or "").split("|")]
        if used >= MAX_MAPS or len(parts) != 3 or k not in pics:
            continue
        try:
            y0, y1 = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        name = history_maps.find(parts[0])
        if not name or not -3000 <= y0 < y1 <= 2025:
            continue
        # Never modern borders: Kashmir and other disputed lines are a legal and political minefield in
        # both Pakistan and India, and the data has modern states ("Islamic Republic of Pakistan").
        try:
            if history_maps.span(name)[1] > MAP_LAST_YEAR:
                continue
        except Exception:  # noqa: BLE001
            continue
        pics[k] = {**pics[k], "map": (name, y0, y1)}
        # The map draws its own name and years top left, where the scene's label box sits: the
        # first real run (Mughal Empire, 22-oct-2026) showed "MUGHAL EMPIRE AT PEAK" over "MUGHAL EMPIRE".
        if hasattr(s, "label"):
            s.label = ""
        used += 1
        log(f"   🗺️ Scene {k + 1}: a map of {name}, {y0}-{y1}.")
    return used


def scenes_of(script):
    return list(script.hook) + [s for c in script.chapters for s in c.scenes]


def word_count(script):
    return sum(len(s.line.split()) for s in scenes_of(script)) + len(script.outro.split())


def _narration_text(script):
    out = [f"TITLE: {script.title}"] + [s.line for s in script.hook]
    for c in script.chapters:
        out.append(f"[{c.title}]")
        out += [s.line for s in c.scenes]
    return "\n".join(out + [script.outro, script.question])


# ------------------------------------------------------------------ series
# A topic too big for one video (the Ottomans, the Mughals) is planned as 2-4
# parts; each part knows the series, opens with where the last part ended and
# ends on what the next one tells, so a viewer watches on.

SERIES_MAX = 4


def series_env():
    """{"name", "part", "parts", "before": [earlier part topics]} from the job's env, or None."""
    name = re.sub(r"\s+", " ", os.environ.get("HISTORY_SERIES") or "").strip()[:120]
    try:
        part, parts = int(os.environ.get("HISTORY_PART") or 0), int(os.environ.get("HISTORY_PARTS") or 0)
    except ValueError:
        return None
    if not name or not 1 <= part <= parts <= SERIES_MAX:
        return None
    try:
        before = [str(b)[:120] for b in json.loads(os.environ.get("HISTORY_BEFORE") or "[]")][:SERIES_MAX]
    except ValueError:
        before = []
    return {"name": name, "part": part, "parts": parts, "before": before}


def series_topic(topic, series):
    """What research searches for: the part, named with its series."""
    if not series or series["name"].lower() in topic.lower():
        return topic
    return f"{series['name']}: {topic}"


def series_note(series, lang="urdu"):
    if not series:
        return ""
    k, n = series["part"], series["parts"]
    note = [f"This video is PART {k} of {n} of our series \"{series['name']}\". Tell only this part's story."]
    if series["before"]:
        note.append("Earlier parts told: " + "; ".join(series["before"]) + ". Do not retell them.")
    if k > 1:
        note.append(f"Open the hook with one line that tells a new viewer where part {k - 1} ended.")
    if k < n:
        note.append(f"In the outro, say in one line what part {k + 1} will tell, and ask viewers to watch it next.")
    else:
        note.append("This is the last part: the outro closes the whole series.")
    return " ".join(note)


def part_title(title, part):
    """The title with its part number, which viewers look for in a series."""
    if re.search(r"\b(part|hissa|qist)\s*\d", title, re.I):
        return title
    return f"{title.strip()[:88]} | Part {part}"


def write(client, topic, handle, minutes=DEFAULT_MINUTES, lang="urdu", research_fn=None, series_note="",
          mode="history", study_fn=None, keywords_fn=None):
    """(Script, facts, sources) that passed the fact check, or raises.
    ``series_note``: where this part sits in a series (series_note()).
    ``mode`` "explainer": trend_explainer's research, script and rules, the
    top videos on the topic studied and YouTube's search phrases."""
    from quiz_shorts import quiz_model
    if mode == "horror":
        # Original fiction (horror_stories.py): no web research and no fact check, a story check instead.
        import horror_stories
        return horror_stories.write(client, topic, handle, minutes, lang, series_note)
    explainer = mode == "explainer"
    import trend_explainer as te
    if explainer:
        with ThreadPoolExecutor(max_workers=3) as pool:
            got_research = pool.submit(research_fn or research, client, topic, minutes,
                                       (te.FACTS_PROMPT, te.EXTRA_PROMPT))
            got_study = pool.submit(study_fn or te.study, client, topic)
            got_keywords = pool.submit(keywords_fn or te.keywords, topic, client)
            facts, extra, sources = got_research.result()
            studied, phrases = got_study.result(), got_keywords.result()
        prompt, rules = te.SCRIPT_PROMPT, te.RULES
    else:
        facts, extra, sources = (research_fn or research)(client, topic, minutes)
        studied, phrases, prompt, rules = {}, [], SCRIPT_PROMPT, RULES
    if not facts or "NOT FOUND" in facts[:200].upper() or len(sources) < MIN_SOURCES:
        raise RuntimeError(f"Not enough reliable sources for this topic ({len(sources)}).")
    words, chapters, scenes = shape(minutes)
    # What people type into YouTube about the topic, for the title and tags (explainer mode has its own
    # keyword list in the prompt already).
    import cricket_shorts as cs
    search = "" if explainer else cs._search_hint(topic)
    fixes = ""
    for attempt in range(2):
        script = kit.ask_json(client, Script, prompt.format(
            minutes=minutes, handle=handle, topic=topic + (f"\n{series_note}" if series_note else ""),
            lang_rule=LANG_RULE.get(lang, LANG_RULE["urdu"]),
            fixes=fixes, facts=facts, extra=extra or "(none)", words=words, rules=rules, sacred=SACRED,
            chapters=chapters, scenes=scenes, no_people=NO_PEOPLE,
            study=studied.get("notes") or "(not available)",
            rival_titles="\n".join(studied.get("titles") or []) or "(not available)",
            keywords="\n".join(phrases) or "(not available)",
            honour=HONOUR.get(lang, HONOUR["urdu"])) + viral_remix.note_for(topic) + search + "\n\n"
            + craft.long_rules(),
            model=quiz_model())
        if not script.allowed:
            raise RuntimeError(f"Not made: {script.reason or 'the topic is not for this channel'}.")
        if len(script.chapters) < 2 or not script.hook:
            raise RuntimeError("The script came back without chapters; try again later.")
        # The first 30 seconds decide a long video; polished before the fact check reads it.
        craft.polish_opening(client, script, facts + "\n" + (extra or ""),
                             what="news explainer" if explainer else "history documentary",
                             language=LANG_NAME.get(lang, "Roman Urdu") + (" in Latin letters" if lang == "urdu" else ""))
        notes = []
        got = word_count(script)
        if got < words * 0.75:
            notes.append(f"The script is too short: {got} words. Write about {words} words, with more scenes.")
        sources_seen = (studied.get("texts") or []) + [t for t in [viral_remix.source_text(topic)] if t]
        copied = te.copied_runs(_narration_text(script), sources_seen) if sources_seen else []
        if copied:
            notes.append("These runs of words repeat another creator's video word for word; say them in your "
                         "own words: " + "; ".join(f'"{c}"' for c in copied[:8]))
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(
            facts=facts, extra=extra or "(none)", script=_narration_text(script),
            more=("; " + te.CHECK_MORE) if explainer else ".",
            honour_short="\"Hazrat\", \"sallallahu alaihi wasallam\" / \"(SAW)\"" if lang == "urdu"
            else "\"peace be upon him\""), model=quiz_model())
        if not check.ok:
            notes += check.problems
        if copied and attempt == 1:
            raise RuntimeError("The script still repeated another creator's words after a rewrite; skipped.")
        if not notes or (check.ok and got >= MIN_MINUTES * WORDS_PER_MINUTE * 0.8 and attempt == 1):
            return script, facts, sources
        if attempt == 0:
            print(f"   ⚠️ Rewriting once: {len(notes)} note(s) ({'; '.join(n[:60] for n in notes[:3])}).")
            fixes = "Fix these problems found in the last version:\n- " + "\n- ".join(notes)
    if check.ok:
        raise RuntimeError(f"The script came back too short twice ({got} words); try again later.")
    raise RuntimeError("The script did not pass the fact check twice; skipped to be safe.")


# ------------------------------------------------------------------ pictures

def _sacred_name(text):
    return bool(SACRED_NAMES.search(text)) and not PLACE.search(text)


def wiki_pictures(article, sacred=False):
    """Free-licence pictures on one English Wikipedia article:
    [{"file", "url", "w", "h", "licence", "artist", "desc", "page"}]."""
    import player_photo as pp
    res = pp._api({"action": "query", "titles": article, "prop": "images", "imlimit": 80, "redirects": 1})
    if res is None:
        print(f"   ℹ️ Wikipedia did not answer for '{article}' (busy).")
    pages = ((res or {}).get("query") or {}).get("pages") or {}
    files = [i["title"] for p in pages.values() for i in p.get("images") or []]
    files = [f for f in files if f.lower().endswith(EXTS) and not JUNK.search(f)
             and (not f.lower().endswith(".svg") or "map" in f.lower())]
    out = []
    for k in range(0, min(len(files), 50), 25):
        res = pp._api({"action": "query", "titles": "|".join(files[k:k + 25]), "prop": "imageinfo",
                       "iiprop": "extmetadata|url|size", "iiurlwidth": WIKI_WIDTH})
        for p in (((res or {}).get("query") or {}).get("pages") or {}).values():
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            licence = pp._strip((meta.get("LicenseShortName") or {}).get("value"))
            nonfree = str((meta.get("NonFree") or {}).get("value") or "").lower() == "true"
            w, h = info.get("width") or 0, info.get("height") or 0
            if nonfree or not pp.FREE.match(licence or "") or not info.get("thumburl") or min(w, h) < 400 or w < 640:
                continue
            name = p.get("title", "")[5:]
            desc = pp._strip((meta.get("ImageDescription") or {}).get("value"))[:160]
            text = f"{name} {desc}"
            if _sacred_name(text) or (sacred and ART.search(text)):
                continue
            out.append({"file": name, "url": info["thumburl"], "w": w, "h": h, "licence": licence,
                        "artist": pp._strip((meta.get("Artist") or {}).get("value"))[:80] or "unknown",
                        "desc": desc, "article": article,
                        "page": f"https://commons.wikimedia.org/wiki/File:{name.replace(' ', '_')}"})
            if len(out) >= PER_ARTICLE:
                return out
        time.sleep(0.3)   # Wikimedia answers bursts with 429
    return out


def candidates(articles, sacred=False):
    pool, seen = [], set()
    for a in articles[:MAX_ARTICLES]:
        try:
            got = wiki_pictures(a, sacred)
        except Exception as e:  # noqa: BLE001 — one article less
            print(f"   ℹ️ No pictures from '{a}' ({type(e).__name__}).")
            continue
        for p in got:
            if p["file"] not in seen:
                seen.add(p["file"])
                pool.append(p)
    return pool


def pick(client, topic, scenes, pool, sacred):
    """{scene index: pool index} for the scenes a free picture fits."""
    if not pool:
        return {}
    from quiz_shorts import quiz_model
    listing = "\n".join(f"{k}: {s.picture[:160]}" for k, s in enumerate(scenes))
    pics = "\n".join(f"{k}: {p['file'][:90]} | {p['desc'][:110]}" for k, p in enumerate(pool))
    got = kit.ask_json(client, Picks, PICK_PROMPT.format(
        topic=topic, scenes=listing, pictures=pics, sacred=SACRED, n=len(scenes),
        art=" and no painting or artwork of people at all" if sacred else ""), model=quiz_model())
    used, out = {}, {}
    for p in got.picks:
        if 0 <= p.scene < len(scenes) and 0 <= p.picture < len(pool) and used.get(p.picture, 0) < 2:
            if p.scene not in out:
                out[p.scene] = p.picture
                used[p.picture] = used.get(p.picture, 0) + 1
    return out


class Seen(BaseModel):
    index: int
    artwork_with_people: bool


class Looks(BaseModel):
    pictures: List[Seen]


LOOK_PROMPT = """These are {n} pictures, numbered from 0 in the order given. For each one say whether it is a
painting, drawing, miniature, manuscript illustration, mosaic or other artwork that shows one or more people
(artwork_with_people). Photos, maps, buildings, landscapes, coins and objects are false."""


def artwork_with_people(client, paths):
    """Indexes of ``paths`` that are artwork showing people, by one look at
    small copies. A sacred story drops those: a name filter cannot tell a
    manuscript painting of Karbala ("Maktel-i Al-i Resul") from a map."""
    from google.genai import types
    from PIL import Image
    if not paths:
        return set()
    parts = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((512, 512))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))
    got = kit.ask_json(client, Looks, parts + [LOOK_PROMPT.format(n=len(paths))])
    return {s.index for s in got.pictures if s.artwork_with_people and 0 <= s.index < len(paths)}


def own_article_picks(scenes, pool):
    """{scene: picture} without the model: each scene gets the next unused free
    picture of the Wikipedia article it named (used when the matching call fails)."""
    used, out = set(), {}
    for k, s in enumerate(scenes):
        for i, p in enumerate(pool):
            if i not in used and (s.wiki or "").strip().lower() == (p.get("article") or "").lower():
                out[k] = i
                used.add(i)
                break
    return out


def ai_order(n_hook, chapters):
    """Scene indexes in the order AI pictures are worth most: the hook, each
    chapter's first scene, then the rest in story order."""
    first, rest, k = list(range(n_hook)), [], n_hook
    for size in chapters:
        if size:
            first.append(k)
            rest += list(range(k + 1, k + size))
        k += size
    return first + rest


def download(url, out):
    import player_photo as pp
    wait = 2
    for attempt in range(4):
        try:
            r = httpx.get(url, headers={"User-Agent": pp.UA}, timeout=40, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(out, "wb") as f:
                    f.write(r.content)
                return out
        except httpx.HTTPError:
            pass
        time.sleep(wait)
        wait *= 2
    return None


def ai_picture(client, prompt, out, sacred, style=None):
    """One AI picture (16:9) for a scene; returns the path or raises. ``style``: another look (the horror
    channel's dark paintings) instead of the history painting style."""
    from google.genai import types
    from PIL import Image
    import thumbnail
    rule = (NO_PEOPLE + " ") if sacred else "Never show any prophet or revered religious figure. "
    r = client.models.generate_content(
        model=thumbnail.IMAGE_MODEL, contents=[f"{style or AI_STYLE} {rule}Scene: {prompt}"],
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                           image_config=types.ImageConfig(aspect_ratio="16:9",
                                                                          image_size=AI_IMAGE_SIZE)))
    for part in r.parts or []:
        if part.inline_data is not None and part.inline_data.data:
            Image.open(io.BytesIO(part.inline_data.data)).convert("RGB").save(out, "JPEG", quality=92)
            return out
    raise RuntimeError("no picture came back")


def canvas(src, out, close=False, dark=0.0, blur=0):
    """The picture on the pan canvas. A picture near 16:9 and large enough
    fills it; anything else sits whole on a blurred, darkened copy of itself
    (a portrait or a small map stretched to fill looks broken). ``close`` is
    a tighter crop of the same picture: a second shot for a long scene."""
    from PIL import Image, ImageEnhance, ImageFilter
    im = kit.opaque(Image.open(src))
    cw, ch = CANVAS_W, CANVAS_H
    ratio = im.width / max(1, im.height)
    fills = 1.45 <= ratio <= 2.2 and im.width >= 1100

    def cover(img, w, h, lean=0.4):
        s = max(w / img.width, h / img.height)
        img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
        x, y = (img.width - w) // 2, round((img.height - h) * lean)
        return img.crop((x, y, x + w, y + h))
    if fills or close:
        if close and not fills:
            # the whole picture, larger, on its blurred copy
            base = canvas(src, out + ".tmp.jpg")
            im2 = Image.open(base).convert("RGB")
            os.remove(base)
            frame = cover(im2, round(cw * 0.78), round(ch * 0.78), 0.45).resize((cw, ch), Image.LANCZOS)
        else:
            frame = cover(im, cw, ch)
            if close:
                frame = cover(frame, round(cw * 0.74), round(ch * 0.74), random.choice([0.3, 0.5])).resize(
                    (cw, ch), Image.LANCZOS)
    else:
        frame = cover(im, cw // 4, ch // 4, 0.5).filter(ImageFilter.GaussianBlur(10)).resize((cw, ch), Image.LANCZOS)
        frame = ImageEnhance.Brightness(frame).enhance(0.45)
        s = min(cw * 0.80 / im.width, ch * 0.86 / im.height)
        fg = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        shadow = Image.new("L", (fg.width + 120, fg.height + 120), 0)
        shadow.paste(200, (60, 60, 60 + fg.width, 60 + fg.height))
        shadow = shadow.filter(ImageFilter.GaussianBlur(40))
        x, y = (cw - fg.width) // 2, (ch - fg.height) // 2
        frame.paste((0, 0, 0), (x - 60 + 20, y - 60 + 30), shadow)
        frame.paste(fg, (x, y))
    if blur:
        frame = frame.resize((cw // 4, ch // 4)).filter(ImageFilter.GaussianBlur(blur)).resize((cw, ch))
    if dark:
        frame = ImageEnhance.Brightness(frame).enhance(1 - dark)
    frame.save(out, "JPEG", quality=90)
    return out


# ------------------------------------------------------------------ voice

UNVERIFIED_MINUTES = 14       # my_channels.UNVERIFIED_MINUTES: the length asked of a channel YouTube has not verified
UNVERIFIED_LIMIT = 885        # seconds (14:45): YouTube refuses uploads over 15:00 from such a channel
FIT_MAX = 1.15                # the most the narration is sped up to fit


def fit_voices(said, total, job_dir, log=print):
    """The voiced paragraphs a little faster (atempo, at most FIT_MAX) so the film ends by UNVERIFIED_LIMIT;
    the cards and pauses stay as they are. ``total``: the film's planned length with the voices as they are."""
    voice = sum(s for p, s in said if p)
    room = UNVERIFIED_LIMIT - (total - voice)
    if voice <= 0 or room <= 0:
        return said
    f = voice / room
    if f > FIT_MAX:
        log(f"   ⚠️ The narration is {f:.2f}x too long for 14:45; sped up {FIT_MAX}x, the upload may be refused.")
        f = FIT_MAX
    log(f"   ⏩ Narration {f:.2f}x faster so the video stays under 15 minutes ({clock(total)} planned).")
    out = []
    for p, s in said:
        if not p:
            out.append((p, s))
            continue
        q = os.path.splitext(p)[0] + "_fit.wav"
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", p, "-filter:a", f"atempo={f:.4f}", q],
                           capture_output=True, text=True, timeout=300)
        out.append((q, round(s / f, 3)) if r.returncode == 0 and os.path.isfile(q) else (p, s))
    return out


def voice_all(client, texts, job_dir, lang, voice, mode="history"):
    """[(wav, seconds) | (None, 0)] per text; failed or odd lines get two more tries."""
    import ai_take
    language = LANG_NAME.get(lang, "Roman Urdu")
    if mode == "horror":
        import horror_stories
        style = horror_stories.VOICE_STYLE.get(lang, horror_stories.VOICE_STYLE["urdu"])
    else:
        style = VOICE_STYLE.get(lang, VOICE_STYLE["urdu"])
    said = kit.voice_lines(client, [{"text": t, "voice": voice, "style": style, "language": language}
                                    for t in texts], job_dir, "hv")

    # The horror voice reads slowly on purpose (~0.7 s a word, horror_stories.WPM): its "rambling" mark is higher.
    slow = 0.95 if mode == "horror" else 0.75

    def odd(k):
        path, secs = said[k]
        n = len(texts[k].split())
        # A voice that rambles on or cuts off is redone (seconds per word far off a narrator's).
        return not path or secs > n * slow + 4 or secs < n * 0.15
    for attempt in range(2):
        bad = [k for k in range(len(texts)) if odd(k)]
        if not bad:
            break
        print(f"   🔁 Voicing {len(bad)} paragraph(s) again...")
        time.sleep(15 * (attempt + 1))
        for k in bad:
            path = os.path.join(job_dir, f".hv_{k + 1}.wav")
            secs = ai_take.speak(client, texts[k], path, voice, style, language=language)
            if secs:
                said[k] = (path, secs)
    return said


# ------------------------------------------------------------------ render

def _esc(text):
    return re.sub(r"\s+", " ", str(text or "").replace("\\", "").replace("{", "(").replace("}", ")")).strip()


def _wrap(text, width):
    return r"\N".join(textwrap.wrap(_esc(text), width)) or ""


STYLES = [
    kit.style("HvCap", "Montserrat ExtraBold", 52, "#FFFFFF", outline=3, shadow=1, align=2),
    # Karaoke captions: words fill from white to gold as they are said (\kf; see _karaoke).
    kit.style("HvCapK", "Montserrat ExtraBold", 52, fl.GOLD, outline=3, shadow=1, align=2, secondary="#FFFFFF"),
    kit.style("HvLabel", "Montserrat ExtraBold", 38, "#FFFFFF", outline=0, shadow=2, align=4, spacing=2),
    kit.style("HvKicker", "Montserrat ExtraBold", 34, fl.GOLD, outline=0, shadow=2, spacing=8),
    kit.style("HvTitle", "Noto Serif Bold", 84, "#FFFFFF", outline=0, shadow=4),
    kit.style("HvBig", "Anton", 130, fl.GOLD, outline=4, shadow=4),
    kit.style("HvHandle", "Montserrat ExtraBold", 28, "#FFFFFF", outline=0, shadow=1, align=9),
    kit.style("HvQ", "Montserrat ExtraBold", 54, "#FFFFFF", outline=4, shadow=2),
    kit.style("Shape", "Montserrat ExtraBold", 20, "#FFFFFF"),
]


def _ass(events):
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding", *STYLES, "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return "\n".join(head + list(events)) + "\n"


def _rect(layer, t0, t1, x, y, w, h, colour="#000000", alpha="70", fade=(250, 250)):
    return kit.dialogue(layer, t0, t1, "Shape",
                        rf"{{\an7\pos({x},{y})\1c{fl._ass_colour(colour)}\1a&H{alpha}&\bord0\shad0"
                        rf"\fad({fade[0]},{fade[1]})\p1}}m 0 0 l {w} 0 l {w} {h} l 0 {h}{{\p0}}")


def chunks(text, t0, secs, max_words=7, max_chars=44, wav=None, language="ur"):
    """Caption groups [(text, start, end)], a group ends at punctuation. The
    voice has no word times: with its wav they come from Whisper or the real
    pauses (short_kit.line_word_times), else from length."""
    words = (text or "").split()
    if not words or secs <= 0:
        return []
    times = kit.line_word_times(text, wav, secs, language) if wav else None
    if not times:
        weights = [len(w) + 2 for w in words]
        acc, times = 0.0, []
        for wt in weights:
            times.append((secs * acc / sum(weights), secs * (acc + wt) / sum(weights)))
            acc += wt
    out, cur, first = [], [], 0
    for k, w in enumerate(words):
        if not cur:
            first = k
        cur.append(w)
        last = k == len(words) - 1
        full = len(cur) >= max_words or (not last and len(" ".join(cur + [words[k + 1]])) > max_chars)
        if last or full or (len(cur) >= 3 and w[-1:] in ".,?!;:"):
            out.append((" ".join(cur), t0 + times[first][0], t0 + times[k][1]))
            cur = []
    # Each group stays up until the next one starts: no blink during short pauses.
    return [(t, a, out[i + 1][1] if i + 1 < len(out) and out[i + 1][1] - b < 0.6 else b)
            for i, (t, a, b) in enumerate(out)]


def shot_events(d, label=None, caps=(), handle="", question=None):
    """Text over one shot: the handle, an on-screen label, captions, a question."""
    ev = []
    if handle:
        ev.append(kit.dialogue(5, 0, d, "HvHandle", rf"{{\an9\pos({W - 48},{36})\alpha&H70&}}{_esc(handle)}"))
    if label:
        text = _esc(label).upper()[:32]
        w = 60 + round(len(text) * 25)
        ev.append(_rect(3, 0.3, max(0.6, d - 0.2), 48, 52, w, 72, alpha="60"))
        ev.append(_rect(4, 0.3, max(0.6, d - 0.2), 48, 52, 8, 72, colour=fl.GOLD, alpha="00"))
        ev.append(kit.dialogue(4, 0.3, max(0.6, d - 0.2), "HvLabel",
                               rf"{{\an4\move(60,88,80,88,0,300)\fad(250,250)}}{text}"))
    for text, a, b in caps:
        if b - a > 0.05:
            if _karaoke_on():
                ev.append(kit.dialogue(6, a, b, "HvCapK", rf"{{\an2\pos({W // 2},{H - 46})}}{_karaoke(text, b - a)}"))
            else:
                ev.append(kit.dialogue(6, a, b, "HvCap", rf"{{\an2\pos({W // 2},{H - 46})}}{_esc(text)}"))
    if question:
        a = max(0.0, question[1])
        ev.append(_rect(2, a, d, 0, 0, W, H, alpha="90", fade=(300, 0)))
        ev.append(kit.dialogue(4, a, d, "HvQ", rf"{{\an5\pos({W // 2},{H // 2 - 20})\fad(300,0)}}"
                                               rf"{_wrap(question[0], 36)}"))
    return ev


def _karaoke_on():
    """Quality pass 2: the long videos' captions were static blocks; they now fill word by word.
    HISTORY_KARAOKE=0 brings the static captions back."""
    return os.environ.get("HISTORY_KARAOKE", "1").strip() != "0"


def _karaoke(text, seconds):
    """``text`` with an ASS \\kf sweep per word, each word's share of ``seconds`` by its length: the chunk
    already starts and ends with the voice, and a smooth fill hides the small drift of a length guess
    (the same idea as the AI take's gold words)."""
    words = _esc(text).split()
    if not words:
        return ""
    lead = 0.08 * seconds                       # a breath before the first word
    weights = [len(w) + 2 for w in words]
    total = sum(weights)
    cs = [max(1, round((seconds - lead) * 100 * wt / total)) for wt in weights]
    return f"{{\\k{round(lead * 100)}}}" + " ".join(f"{{\\kf{c}}}{w}" for c, w in zip(cs, words))


def card_events(d, kicker, title):
    return [_rect(1, 0, d, W // 2 - 90, H // 2 - 70, 180, 4, colour=fl.GOLD, alpha="00", fade=(400, 300)),
            kit.dialogue(3, 0, d, "HvKicker", rf"{{\an5\pos({W // 2},{H // 2 - 115})\fad(300,300)}}{_esc(kicker)}"),
            kit.dialogue(3, 0.15, d, "HvTitle", rf"{{\an8\pos({W // 2},{H // 2 - 40})\fad(400,300)"
                                                rf"\t(0,600,\fscx100\fscy100)\fscx92\fscy92}}{_wrap(title, 32)}")]


def end_events(d, handle, lang, mode="history"):
    return [kit.dialogue(3, 0, d, "HvBig", rf"{{\an5\pos({W // 2},{H // 2 - 80})\fad(300,0)"
                                           rf"\t(0,400,\fscx100\fscy100)\fscx80\fscy80}}SUBSCRIBE"),
            kit.dialogue(3, 0.3, d, "HvKicker", rf"{{\an5\pos({W // 2},{H // 2 + 50})\fad(300,0)}}{_esc(handle)}"),
            kit.dialogue(3, 0.6, d, "HvLabel", rf"{{\an5\pos({W // 2},{H // 2 + 130})\fad(300,0)}}"
                                               rf"{_esc(words_for(lang, mode)['next'])}")]


MOTIONS = ["right", "left", "down", "diag", "up", "left"]


def _motion():
    """Quality pass 2 (22-oct-2026): eased pans, moving footage, shorter shots. HISTORY_MOTION=0: the old look."""
    return os.environ.get("HISTORY_MOTION", "1").strip() != "0"


# One encode is all a long video's picture gets (segments are joined and muxed by copy): 20 keeps more
# detail than the old 21 without making a 14-minute upload much bigger on this connection.
CRF = "20"


def mode_grade(lift=0):
    """The horror channel's dark, cold grade on EVERY shot (paintings and footage alike, so they read as one
    film), as a filter prefix; "" otherwise (history pictures stay as the archive has them). ``lift`` 1 is the
    lighter variant, 2 no horror grade: for a shot the dark one turned black (_shot_tries)."""
    if mode_now() != "horror" or os.environ.get("CHANNEL_GRADE", "1") == "0" or lift >= 2:
        return ""
    import horror_stories
    return (horror_stories.GRADE_LIFT if lift else horror_stories.GRADE) + ","


def too_dark(path):
    """True when a shot holds 1.5 s+ that video_qa would call black (its own detector at half its length)."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", path, "-vf",
                        "fps=5,scale=320:-2,blackdetect=d=1.5:pix_th=0.10", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", timeout=300)
    return "black_start" in r.stderr


def _shot_tries(render, job_dir, out):
    """Render a shot; in horror mode, again lighter while it comes out black (the dark grade on a night clip or
    a dark painting): the grade, then GRADE_LIFT, then no horror grade."""
    if not mode_grade():
        return render(0)
    for lift in (0, 1, 2):
        render(lift)
        if not too_dark(os.path.join(job_dir, out)):
            break
        print(f"   ℹ️ A shot came out black under the horror grade; lighter ({lift + 1}).")
    return out


def segment(job_dir, picture, out, frames, motion, events):
    """One shot: ``picture`` (a canvas, relative to job_dir) panned over
    ``frames`` frames under ``events``. Video only; same settings for all."""
    return _shot_tries(lambda lift: _segment(job_dir, picture, out, frames, motion, events, lift), job_dir, out)


def _segment(job_dir, picture, out, frames, motion, events, lift=0):
    ass = out[:-4] + ".ass"
    with open(os.path.join(job_dir, ass), "w", encoding="utf-8") as f:
        f.write(_ass(events))
    d = frames / FPS
    ass_vf = (f"{mode_grade(lift)}ass=filename='{escape_filter_value(ass)}':"
              f"fontsdir='{escape_filter_value(fl.FONTS_DIR)}'")
    if _motion() and motion != "still":
        # Depth parallax (parallax.py) when its model is there; any failure keeps the plain pan below.
        try:
            import parallax
            if parallax.available():
                parallax.render(picture, out, frames, FPS, motion, (W, H), vf_tail=ass_vf, crf=CRF, cwd=job_dir)
                os.remove(os.path.join(job_dir, ass))
                return out
        except Exception as e:  # noqa: BLE001
            print(f"   ℹ️ Parallax skipped for one shot ({type(e).__name__}: {str(e)[:80]}).")
    cw, chh = W * SUPER, H * SUPER
    # Eased (cosine) since quality pass 2: a linear pan starts and stops with a jolt at every cut.
    p = f"(0.5-0.5*cos(PI*t/{d:.4f}))" if _motion() else f"(t/{d:.4f})"
    x, y = {"right": (f"(iw-ow)*{p}", "(ih-oh)/2"), "left": (f"(iw-ow)*(1-{p})", "(ih-oh)/2"),
            "down": ("(iw-ow)/2", f"(ih-oh)*{p}"), "up": ("(iw-ow)/2", f"(ih-oh)*(1-{p})"),
            "diag": (f"(iw-ow)*{p}", f"(ih-oh)*{p}"), "still": ("(iw-ow)/2", "(ih-oh)/2")}[motion]
    vf = (f"loop=loop={frames - 1}:size=1:start=0,setpts=N/{FPS}/TB,crop={cw}:{chh}:x='{x}':y='{y}',"
          f"scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p,{ass_vf}")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", picture, "-vf", vf, "-frames:v", str(frames),
                        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF,
                        "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", "-an", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"shot failed: {r.stderr.strip()[-300:]}")
    os.remove(os.path.join(job_dir, ass))
    return out


def segment_video(job_dir, video, out, frames, offset, close, events):
    """One shot from a stock clip (looped if short), same encode settings as segment()."""
    return _shot_tries(lambda lift: _segment_video(job_dir, video, out, frames, offset, close, events, lift),
                       job_dir, out)


def _segment_video(job_dir, video, out, frames, offset, close, events, lift=0):
    import broll                # both branches use broll.grade() (it was imported in the motion one only)
    ass = out[:-4] + ".ass"
    with open(os.path.join(job_dir, ass), "w", encoding="utf-8") as f:
        f.write(_ass(events))
    if _motion():
        a, b = broll.PULL if close else broll.PUSH
        z = f"({a:.4f}+{b - a:.4f}*{broll._ease(frames / FPS)})"
        move = (f"fps={FPS},setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame:flags=bicubic,crop={W}:{H},{broll.SHARPEN},")
    else:
        zoom = "crop=iw*0.86:ih*0.86," if close else ""
        move = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}scale={W}:{H},fps={FPS},"
    # The channel's grade on footage (broll.GRADES), never on the archival pictures; horror's own on both.
    vf = (f"{move}setsar=1,{mode_grade(lift) or broll.grade()}format=yuv420p,"
          f"ass=filename='{escape_filter_value(ass)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{offset:.2f}", "-stream_loop", "-1", "-i", video,
                        "-vf", vf, "-frames:v", str(frames), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", CRF, "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", "-an", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"footage shot failed: {r.stderr.strip()[-300:]}")
    os.remove(os.path.join(job_dir, ass))
    return out


def _srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, texts, said, voices, lang="urdu"):
    """The narration as an SRT caption track, in the groups and times the
    burned captions use. ``voices`` holds (wav, start) for each voiced text
    in order (plan() skips a text whose voice failed). Path, or None."""
    starts = iter(voices)
    cues = []
    for text, (wav, secs) in zip(texts, said):
        if not wav:
            continue
        _w, start = next(starts)
        cues += chunks(text, start, secs, wav=wav, language="en" if lang == "english" else "ur")
    if not cues:
        return None
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for k, (text, a, b) in enumerate(cues, 1):
            f.write(f"{k}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n\n")
    return path


# English subtitles for an Urdu video: YouTube shows them to viewers whose
# language is English and its search reads caption text, so the video can
# reach people who do not read Roman Urdu.
# Translated by SENTENCE, then timed over the caption pieces it spans: piece
# by piece (a piece stops mid-sentence) the English drifted a line late and
# once carried the model's own note "(the line cuts off here...)", because
# Urdu puts the verb last (gemini-2.5-flash, Rome script, 15-oct-2026).
EN_CAPTIONS_BATCH = 40     # sentences per call
EN_CAPTIONS_MIN = 0.95     # share that must come back; a missing sentence shows no English
EN_CUE_CHARS = 84          # two lines of 42 on screen
TRANSLATE_PROMPT = """Translate these numbered sentences of a Roman Urdu history documentary's narration
into natural, simple English subtitles. Return all {n}, each with its own number; never merge or split
them. Keep names, places and dates as they are; keep honorifics such as "Hazrat", "(SAW)", "(AS)", "(RA)"
where the sentence has them. Only the translation: no notes or comments.

{lines}"""
# A model note, not narration: "Greek books were translated" and "they cut off
# the water" are real lines, "(the line cuts off here...)" is not.
_META = re.compile(r"^\s*(?:note|translation|translator)\b|\([^)]*\b(?:translat\w*|the line|this line|"
                   r"original text)\b[^)]*\)", re.I)


class Cue(BaseModel):
    n: int
    en: str


class Cues(BaseModel):
    lines: List[Cue]


def _srt_seconds(text):
    h, m, rest = text.replace(".", ",").split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def read_srt(path):
    """[(start, end, line)] of an SRT we wrote (write_srt), times in seconds."""
    with open(path, encoding="utf-8") as f:
        blocks = [b for b in f.read().replace("\r\n", "\n").split("\n\n") if b.strip()]
    out = []
    for b in blocks:
        rows = b.strip().split("\n")
        if len(rows) >= 3 and " --> " in rows[1]:
            a, z = rows[1].split(" --> ")
            try:
                out.append((_srt_seconds(a.strip()), _srt_seconds(z.strip()), " ".join(rows[2:]).strip()))
            except ValueError:
                continue
    return out


def srt_sentences(cues):
    """[(sentence, start, end)]: the caption pieces joined back into sentences,
    each timed from its first word to its last. A piece's time is shared by
    its words' lengths, so a sentence that starts mid-piece does not overlap
    the one that ended there."""
    out, words, first = [], [], None
    for a, z, text in cues:
        ws = text.split()
        size = sum(len(w) + 1 for w in ws) or 1
        t = a
        for w in ws:
            end = t + (z - a) * (len(w) + 1) / size
            if not words:
                first = t
            words.append(w)
            t = end
            if re.search(r"[.?!۔؟][\"')”]*$", w):
                out.append((" ".join(words), first, end))
                words = []
    if words:
        out.append((" ".join(words), first, cues[-1][1]))
    return out


def _pieces(text, start, end):
    """One English sentence as cues of at most EN_CUE_CHARS, its time shared
    by length."""
    # Even pieces: filled greedily, a sentence left "Empire." alone for 0.3 s.
    target = len(text) / max(1, -(-len(text) // EN_CUE_CHARS))
    parts, cur = [], ""
    for w in text.split():
        if cur and (len(cur) >= target or len(cur) + 1 + len(w) > EN_CUE_CHARS):
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        parts.append(cur)
    total = sum(len(p) for p in parts) or 1
    out, t = [], start
    for p in parts:
        span = (end - start) * len(p) / total
        out.append((p, t, t + span))
        t += span
    return out


def translate_srt(client, src, dst, ask=None):
    """The SRT at ``src`` in English at ``dst``, sentence by sentence at the
    same times. Path, or None when too little came back."""
    ask = ask or kit.ask_json
    sentences = srt_sentences(read_srt(src))
    if not sentences:
        return None

    def run(items):
        got = ask(client, Cues, TRANSLATE_PROMPT.format(
            n=len(items), lines="\n".join(f"{n}. {sentences[n - 1][0]}" for n in items)))
        return {c.n: c.en.strip() for c in got.lines
                if c.n in items and c.en.strip() and not _META.search(c.en)}

    # Lines carry their numbers: asked for 60 at a time the model dropped 1-3
    # of them in every batch; the dropped ones are asked again on their own.
    done = {}
    for k in range(0, len(sentences), EN_CAPTIONS_BATCH):
        items = list(range(k + 1, min(len(sentences), k + EN_CAPTIONS_BATCH) + 1))
        done.update(run(items))
        missing = [n for n in items if n not in done]
        if missing:
            done.update(run(missing))
    if len(done) < EN_CAPTIONS_MIN * len(sentences):
        return None
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        k = 0
        for n, (_ur, a, z) in enumerate(sentences, 1):
            for text, s, e in _pieces(done.get(n, ""), a, z):
                k += 1
                f.write(f"{k}\n{_srt_time(s)} --> {_srt_time(e)}\n{text}\n\n")
    return dst


def clock(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def narration(path, voices, total, rate=24000):
    """One mono wav of ``total`` seconds with each (wav, at) voice in place."""
    buf = bytearray(int(round(total * rate)) * 2)
    for wav, at in voices:
        with wave.open(wav, "rb") as w:
            if w.getframerate() != rate or w.getsampwidth() != 2 or w.getnchannels() != 1:
                continue
            data = w.readframes(w.getnframes())
        start = int(round(at * rate)) * 2
        end = min(len(buf), start + len(data))
        if end > start:
            buf[start:end] = data[:end - start]
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return path


def plan(script, said, handle, lang, captions=True, mode="history"):
    """The frame-exact timeline: (segments, voices, whooshes, chapter marks,
    bed sections, total seconds). ``said`` is one (wav, seconds) per voiced
    paragraph: hook scenes, chapter scenes, outro, question.

    A segment is {"pic": scene index | "title" | "end", "variant", "frames",
    "motion", "events"}; a scene index refers to scenes_of(script)."""
    segs, voices, whooshes, marks, sections = [], [], [], [], []
    frames, n = 0, 0
    word = words_for(lang, mode)

    def at():
        return frames / FPS

    def add(pic, variant, secs, events_fn, motion=None):
        nonlocal frames
        f = max(1, round(secs * FPS))
        segs.append({"pic": pic, "variant": variant, "frames": f,
                     "motion": motion or MOTIONS[len(segs) % len(MOTIONS)], "events": events_fn(f / FPS)})
        frames += f

    def scene(idx, text, voiced, label="", question=None, pic=None):
        wav, secs = voiced
        start = at()
        dur = (secs or 0) + GAP
        if wav:
            voices.append((wav, start))
        caps = chunks(text, 0.0, secs, wav=wav, language="en" if lang == "english" else "ur") if captions and wav and not question else []
        shots = max(1, round(dur / SHOT_SECONDS))
        edges = [round(dur * k / shots * FPS) for k in range(shots + 1)]
        for k in range(shots):
            a, b = edges[k] / FPS, edges[k + 1] / FPS
            mine = [(t, max(0.0, s - a), min(b, e) - a) for t, s, e in caps if e > a and s < b]
            q = (question, 0.0) if question else None
            add(pic if pic is not None else idx, "close" if k % 2 else "full", b - a,
                lambda d, mine=mine, k=k, q=q: shot_events(d, label if k == 0 else None, mine, handle, q))

    sc = scenes_of(script)
    sections.append(0.0)
    for s in script.hook:
        scene(n, s.line, said[n], s.label)
        n += 1
    marks.append((word["intro"], 0.0))
    sections.append(at())
    whooshes.append(at())
    add("title", "full", TITLE_CARD, lambda d: card_events(d, word["full"], script.title), "still")
    for ci, ch in enumerate(script.chapters):
        if ci:
            sections.append(at())
        marks.append((ch.title, at()))
        whooshes.append(at())
        first = n
        add(first, "card", CHAPTER_CARD, lambda d, ci=ci, ch=ch: card_events(d, f"{word['chapter']} {ci + 1}", ch.title),
            "still")
        for s in ch.scenes:
            scene(n, s.line, said[n], s.label)
            n += 1
    last = len(sc) - 1
    scene(None, script.outro, said[n], pic=last)
    scene(None, script.question, said[n + 1], question=script.question, pic="title")
    add("end", "full", END_CARD, lambda d: end_events(d, handle or "", lang, mode), "still")
    sections.append(at())
    return segs, voices, whooshes, marks, sections, at()


WATCH_NEXT = {"urdu": "Aur kahaniyan:", "english": "More stories:"}
WATCH_NEXT_ROOM = 350


def watch_next(description, uploads, lang="urdu", n=2, now=None):
    """The description with links to the channel's best earlier long videos
    that are already public (a scheduled one is still private): a viewer who
    finishes one story finds the next. Goes before the hashtag line."""
    import credits
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)

    def public(r):
        try:
            return not r.get("publish_at") or datetime.fromisoformat(r["publish_at"]) <= now
        except ValueError:
            return False
    longs = [r for r in uploads if r.get("genre") in LONG_GENRES and r.get("status") == "done"
             and r.get("video_id") and public(r) and not r.get("blocked")     # Content ID blocked: nobody can watch it
             and r["video_id"] not in description]                           # a series part is linked already
    if not longs:
        return description
    longs.sort(key=lambda r: (r.get("views") or 0, r.get("created", 0)), reverse=True)
    lines = [f"- {_esc(r.get('title') or '')[:90]}: https://youtu.be/{r['video_id']}" for r in longs[:n]]
    block = WATCH_NEXT.get(lang, WATCH_NEXT["urdu"]) + "\n" + "\n".join(lines)
    return credits.insert(description, block[:WATCH_NEXT_ROOM - 4])


PART_WORD = {"urdu": ("Pichla hissa", "Agla hissa"), "english": ("Previous part", "Next part")}


def series_rows(uploads, series, genres=LONG_GENRES):
    """{part: upload row} of this series' long videos already uploaded (``genres``: the cartoon channel's two-part
    Shorts pass ("toons",))."""
    out = {}
    for r in uploads:
        if (r.get("genre") in genres and r.get("status") == "done" and r.get("video_id")
                and r.get("series") == series and r.get("series_part") and not r.get("blocked")):
            out[int(r["series_part"])] = r
    return out


def series_links(description, uploads, series, part, lang="urdu", genres=LONG_GENRES):
    """A series part's description with links to its earlier parts. They were
    scheduled before it, so they are public by the time it is."""
    import credits
    rows = series_rows(uploads, series, genres)
    before = [k for k in sorted(rows) if k < part]
    if not before:
        return description
    word = PART_WORD.get(lang, PART_WORD["urdu"])[0]
    lines = [f"{word} (Part {k}): https://youtu.be/{rows[k]['video_id']}" for k in before]
    return credits.insert(description, "\n".join(lines))


def next_part_line(video_id, part, lang="urdu"):
    return f"{PART_WORD.get(lang, PART_WORD['urdu'])[1]} (Part {part}): https://youtu.be/{video_id}"


def describe(script, marks, sources, credits, handle, lang, ai_used, stock_line="", mode="history"):
    """The YouTube description: summary, chapters, question, sources, picture credits, follow line."""
    import youtube_account
    word = dict(WORDS.get(lang, WORDS["urdu"]))
    slug = re.sub(r"[^A-Za-z0-9]+", "", (script.tags or ["history"])[0].title())[:30] or "History"
    tags = ["#history", "#urdu" if lang == "urdu" else "#documentary", f"#{slug}"]
    if mode == "explainer":
        import trend_explainer
        word["follow"] = trend_explainer.FOLLOW.get(lang, trend_explainer.FOLLOW["urdu"])
        tags = ["#explained", "#urdu" if lang == "urdu" else "#news", f"#{slug}"]
    if mode == "horror":
        import horror_stories
        word = words_for(lang, mode)
        tags = ["#horrorstory", "#urdu" if lang == "urdu" else "#scarystories", f"#{slug}"]
    head = [script.summary.strip(), "", "\n".join(f"{clock(t)} {_esc(title)}" for title, t in marks), "",
            script.question.strip()]
    if mode == "horror":
        # Fiction, said plainly: nothing here is a true event about real people or places.
        head += ["", horror_stories.describe_extra(lang)]
    if sources:
        head += ["", "Sources:"] + [f"- {n}: {u}" if n else f"- {u}" for n, u in sources[:8]]
    # A blank line before the hashtags: credits.insert puts later lines
    # (watch_next, series links) above them only then.
    tail = ["", f"{word['follow']}{(' ' + handle) if handle else ''}", "", " ".join(tags)]
    pics = ["", "Pictures: free-licence pictures from Wikimedia Commons"
            + ("; the other pictures are AI illustrations." if ai_used else ".")] if credits else (
        ["", "Pictures: AI illustrations."] if ai_used else [])
    if stock_line:
        pics = (pics or [""]) + [stock_line]
    # Room left for watch_next's links, added at upload time.
    budget = youtube_account.DESCRIPTION_MAX - len("\n".join(head + pics + tail)) - 60 - WATCH_NEXT_ROOM
    lines, left = [], len(credits)
    for c in credits:
        line = f"- {c}"
        if len(line) + 1 > budget:
            break
        lines.append(line)
        budget -= len(line) + 1
        left -= 1
    if left:
        lines.append(f"- and {left} more, credited on their Wikimedia Commons pages")
    return "\n".join(head + pics + lines + tail)


def _thumbnail(client, script, job_dir, fallback, mode="history"):
    """thumbnail.jpg: free by default, the video's opening picture with the
    hook text set by PIL over a dark fade on the left; HISTORY_AI_THUMBNAIL=1
    asks the image model for a new picture first (~$0.10). Path or None.
    Horror: red text, and the AI picture is one of its dark paintings."""
    import thumbnail as th
    out = os.path.join(job_dir, "thumbnail.jpg")
    text = script.thumb_text.upper()[:40]
    colour = "yellow"
    # The thumbnail A/B test (my_channels EXPERIMENTS["thumb"], judged by click rate): which side the text takes.
    side = "right" if os.environ.get("HISTORY_THUMB", "").lower() == "right" else "left"
    if mode == "horror":
        import horror_stories
        colour = horror_stories.thumb_colour()
    if AI_THUMBNAIL:
        scene = (f"{script.thumb_picture}. Epic and dramatic, historical, clearly a painting, never a photograph; "
                 "no blood, bodies or people dying. "
                 + (NO_PEOPLE if script.sacred else "Never show any prophet or revered religious figure."))
        if mode == "horror":
            scene = f"{script.thumb_picture}. {horror_stories.AI_STYLE}"
        try:
            return th._generate_one(client, {"scene": scene, "text": text, "text_position": side,
                                             "text_color": colour}, [], out, burn_text=True)
        except Exception as e:  # noqa: BLE001 — fall back to a free picture
            print(f"   ℹ️ AI thumbnail failed ({type(e).__name__}); using a picture from the video.")
    if not fallback:
        return None
    try:
        from PIL import Image, ImageDraw
        im = Image.open(fallback).convert("RGB")
        s = max(th.THUMB_W / im.width, th.THUMB_H / im.height)
        im = im.resize((max(th.THUMB_W, round(im.width * s)), max(th.THUMB_H, round(im.height * s))), Image.LANCZOS)
        x, y = (im.width - th.THUMB_W) // 2, (im.height - th.THUMB_H) // 2
        im = im.crop((x, y, x + th.THUMB_W, y + th.THUMB_H))
        shade = Image.new("L", im.size, 0)
        draw = ImageDraw.Draw(shade)
        fade_end = round(th.THUMB_W * 0.62)
        for col in range(fade_end):
            x = col if side == "left" else th.THUMB_W - 1 - col
            draw.line([(x, 0), (x, th.THUMB_H)], fill=round(190 * (1 - col / fade_end)))
        im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, shade)
        im = th.burn_thumbnail_text(im, text, side, colour).convert("RGB")
        im.save(out, "JPEG", quality=90)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"   ℹ️ No thumbnail ({type(e).__name__}).")
        return None


def _bed_tracks(sacred, kind="history"):
    """Music beds for the chapters: the documentary's, or the horror channel's dark drones (kind "horror")."""
    if sacred or os.environ.get("BG_MUSIC", "0") != "1":
        return []
    import music_beds
    music_beds.ensure(kind, music_beds.PER_KIND)
    music_beds.grow(kind)
    have = music_beds.beds(kind)
    folder = os.path.join(kit.MUSIC_DIR, kind)
    tracks = [os.path.join(folder, f) for f in have]
    random.shuffle(tracks)
    return tracks


def mix(job_dir, video, narration_wav, out, total, whooshes, sections, tracks, sting=False):
    """The final file: the joined video (copied), the narration, a whoosh per
    card and a music bed per chapter (looped, faded). ``sting``: a low horror hit on each card instead of the
    whoosh (horror_stories.STING)."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", video, "-i", narration_wav]
    duck = bool(tracks) and kit.ducking()
    # Ducked (short_kit.ducking): the beds sit at -28 LUFS and dip under the narration, as on the Shorts.
    graph = [f"[1:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo"
             + (",asplit=2[vo][vkey]" if duck else "[vo]")]
    mixin = ["[vo]"]
    idx = 2
    beds = []
    if tracks:
        for k in range(len(sections) - 1):
            a, b = sections[k], sections[k + 1]
            length = b - a
            if length < 2:
                continue
            cmd += ["-stream_loop", "-1", "-i", tracks[k % len(tracks)]]
            ms = int(a * 1000)
            graph.append(f"[{idx}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,"
                         f"{kit.BED_DUCKED_LOUDNORM if duck else kit.BED_LOUDNORM},"
                         f"afade=t=in:d=1.5,afade=t=out:st={max(0.0, length - 2):.3f}:d=2,"
                         f"aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[bed{k}]")
            beds.append(f"[bed{k}]")
            idx += 1
    if duck and beds:
        graph.append(f"{''.join(beds)}amix=inputs={len(beds)}:normalize=0[beds];[beds][vkey]{kit.DUCK}[bedd]")
        mixin.append("[bedd]")
    elif duck:
        graph.append("[vkey]anullsink")
    else:
        mixin += beds
    if sting:
        import horror_stories
        sound, secs = horror_stories.STING, 1.2
    else:
        sound, secs = kit.WHOOSH, 0.3
    for k, t in enumerate(whooshes):
        ms = int(t * 1000)
        graph.append(f"aevalsrc='{sound}':s=48000:d={secs},aformat=channel_layouts=stereo,adelay={ms}|{ms}[sx{k}]")
        mixin.append(f"[sx{k}]")
    graph.append(f"{''.join(mixin)}amix=inputs={len(mixin)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
                              *METADATA_SCRUB, "-movflags", "+faststart", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"mix failed: {r.stderr.strip()[-400:]}")
    kit.level(os.path.join(job_dir, out))     # the whole film to -14 LUFS, as the Shorts (short_kit.level)
    return out


def render(job_dir, segs, pics, title_pic, out_name, workers=3, log=print):
    """Every segment, then one concat (no second encode). ``pics``: scene index
    -> {"full", "close", "card"} canvases relative to job_dir."""
    os.makedirs(os.path.join(job_dir, ".hv_seg"), exist_ok=True)
    names = []

    def one(k):
        s = segs[k]
        name = f".hv_seg/s{k:04d}.mp4"
        if s["pic"] in ("title", "end"):
            picture = title_pic
        else:
            entry = pics[s["pic"]]
            if entry.get("map") and s["variant"] == "full":
                # An animated empire map (history_maps.py, Cliopatria) instead of the picture; the shot
                # still gets its captions, motion and grade through segment_video. Any failure: picture.
                import history_maps
                name_, y0, y1 = entry["map"]
                clip = history_maps.render(name_, y0, y1, os.path.join(job_dir, f".hv_seg/map{k:04d}.mp4"),
                                           seconds=s["frames"] / FPS + 0.2, size=(W, H), fps=FPS)
                if clip:
                    return segment_video(job_dir, os.path.relpath(clip, job_dir), name, s["frames"], 0.0, False,
                                         s["events"])
            if entry.get("video") and s["variant"] != "card":
                # Stock footage plays; the second shot of a scene starts later in the clip.
                secs = entry.get("seconds") or 0
                offset = 0.3 if s["variant"] == "full" else max(0.3, secs * 0.45)
                return segment_video(job_dir, entry["video"], name, s["frames"], offset,
                                     s["variant"] == "close", s["events"])
            picture = entry[s["variant"]]
        return segment(job_dir, picture, name, s["frames"], s["motion"], s["events"])
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name in pool.map(one, range(len(segs))):
            names.append(name)
            done += 1
            if done % 10 == 0 or done == len(segs):
                log(f"   🎞️ {done}/{len(segs)} shots rendered")
    with open(os.path.join(job_dir, ".hv_parts.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"file '{n}'\n" for n in names))
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", ".hv_parts.txt",
                        "-c", "copy", out_name], cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"join failed: {r.stderr.strip()[-300:]}")
    return out_name


# ------------------------------------------------------------------ the job

def pictures(client, script, topic, job_dir, log=print, mode="history"):
    """(scene index -> canvases, title canvas, credits, AI pictures used)."""
    sc = scenes_of(script)
    os.makedirs(os.path.join(job_dir, ".hv_pics"), exist_ok=True)
    articles = []
    for s in sc:
        a = (s.wiki or "").strip()
        if a and a.lower() not in {x.lower() for x in articles}:
            articles.append(a)
    if mode == "horror":
        articles = []           # fiction: dark footage and paintings only, never an encyclopaedia picture
    else:
        log(f"🖼️ Looking for free pictures in {min(len(articles), MAX_ARTICLES)} Wikipedia articles...")
    pool = candidates(articles, script.sacred)
    try:
        picks = pick(client, topic, sc, pool, script.sacred) if pool else {}
    except Exception as e:  # noqa: BLE001 — the video goes on with its own articles' pictures
        log(f"   ℹ️ Picture matching failed ({type(e).__name__}); each scene takes its own article's pictures.")
        picks = own_article_picks(sc, pool)
    log(f"   {len(pool)} free pictures found, {len(picks)} fit a scene.")
    files, credits = {}, []
    for scene_idx, p in sorted(picks.items()):
        info = pool[p]
        path = files.get(info["file"])
        if path is None:
            path = download(info["url"], os.path.join(job_dir, ".hv_pics", f"w{p:03d}"))
            files[info["file"]] = path
            if path:
                credits.append(f"{info['file'][:80]}: {info['artist'][:60]}, {info['licence']} ({info['page']})")
            time.sleep(0.3)
        if not path:
            picks[scene_idx] = None
    raw = {k: files.get(pool[p]["file"]) for k, p in picks.items() if p is not None}
    raw = {k: v for k, v in raw.items() if v}
    if script.sacred and raw:
        paths = sorted(set(raw.values()))
        try:
            drop = {paths[i] for i in artwork_with_people(client, paths)}
        except Exception as e:  # noqa: BLE001 — unsure means none of them
            log(f"   ℹ️ Could not look at the pictures ({type(e).__name__}); using AI pictures only.")
            drop = set(paths)
        if drop:
            log(f"   🚫 {len(drop)} artwork picture(s) with people dropped (sacred story).")
            raw = {k: v for k, v in raw.items() if v not in drop}
            names = {f for f, path in files.items() if path in drop}
            credits = [c for c in credits if not any(c.startswith(n[:80] + ":") for n in names)]
    log(f"   ✅ {len(raw)} of {len(sc)} scenes have a free picture ({len(credits)} pictures).")
    # Free stock footage (Pexels, Pixabay) for the scenes Wikipedia had nothing for.
    videos, stock = {}, []
    missing = [k for k in range(len(sc)) if k not in raw]
    if missing:
        import broll
        import stock_media
        if stock_media.available():
            if mode == "explainer":
                import trend_explainer
                rule = trend_explainer.FOOTAGE_RULE
            elif mode == "horror":
                import horror_stories
                rule = horror_stories.FOOTAGE_RULE
            else:
                rule = FOOTAGE_RULE
            rule += (NO_PEOPLE + " ") if script.sacred else ""
            try:
                lines = [sc[k].picture for k in missing]
                terms = broll.terms_for(client, topic, lines, rule)
                got = stock_media.for_scenes(client, topic, lines, terms, portrait=False, log=log, rule=rule)
            except Exception as e:  # noqa: BLE001 — footage is a bonus
                log(f"   ℹ️ No stock footage this time ({type(e).__name__}).")
                got = [None] * len(missing)
            for k, item in zip(missing, got):
                if item:
                    raw[k] = item["path"]
                    stock.append(item)
                    if item["kind"] == "video":
                        videos[item["path"]] = item
    style = None
    if mode == "horror":
        # The painted look the niche's channels have: the hook, each chapter's opening and the climax are
        # paintings (ai_order's order), above the footage they would otherwise get.
        import horror_stories
        style, budget = horror_stories.AI_STYLE, horror_stories.AI_IMAGES
        order_all = ai_order(len(script.hook), [len(c.scenes) for c in script.chapters])
        painted = set(order_all[:max(0, budget)])
        # The hook and each chapter's opening are paintings even where footage was found (the first live run
        # found footage for all 6 scenes and made no painting at all): the niche's look is painted art, with
        # the footage moving between them.
        for k in painted:
            raw.pop(k, None)
        kept = set(raw.values())
        stock = [item for item in stock if item["path"] in kept]      # credit only the footage shown
        want = [k for k in order_all if k not in raw][:max(0, budget)]
    else:
        want = [k for k in ai_order(len(script.hook), [len(c.scenes) for c in script.chapters]) if k not in raw]
        want = want[:max(0, AI_IMAGES)]
    ai_used = 0
    if want:
        log(f"🎨 Making {len(want)} AI picture(s)...")

        def make(k):
            out = os.path.join(job_dir, ".hv_pics", f"ai{k:03d}.jpg")
            for attempt in range(2):
                try:
                    return k, ai_picture(client, sc[k].picture, out, script.sacred, **({"style": style} if style else {}))
                except Exception as e:  # noqa: BLE001
                    if attempt:
                        print(f"   ℹ️ AI picture for scene {k + 1} failed ({type(e).__name__}).")
                    time.sleep(3)
            return k, None
        with ThreadPoolExecutor(max_workers=4) as pool_ex:
            for k, path in pool_ex.map(make, want):
                if path:
                    raw[k] = path
                    ai_used += 1
    if not raw:
        raise RuntimeError("No pictures could be found or made for this topic.")
    # Scenes still without a picture borrow the nearest one before them (after, at the start).
    order = sorted(raw)
    for k in range(len(sc)):
        if k not in raw:
            before = [j for j in order if j < k]
            raw[k] = raw[before[-1] if before else order[0]]
    pics, made = {}, {}
    for k in range(len(sc)):
        src = raw[k]
        if src not in made:
            base = os.path.join(".hv_pics", f"c{len(made):03d}")
            still = src
            if src in videos:
                # A frame of the clip for the chapter card and the title.
                still = frame_of(src, os.path.join(job_dir, base + "_frame.jpg")) or src
            made[src] = {"full": canvas(still, os.path.join(job_dir, base + "_full.jpg")) and base + "_full.jpg",
                         "close": canvas(still, os.path.join(job_dir, base + "_close.jpg"), close=True)
                         and base + "_close.jpg",
                         "card": canvas(still, os.path.join(job_dir, base + "_card.jpg"), dark=0.55, blur=6)
                         and base + "_card.jpg"}
            if src in videos:
                made[src].update(video=src, seconds=float(videos[src].get("seconds") or 0))
        pics[k] = made[src]
    first = raw[order[0]]
    if first in videos:
        first = os.path.join(job_dir, pics[order[0]]["full"])
    # The thumbnail wants a big, wide picture that fills 16:9 (the opening one
    # was a tall photo framed on its blurred copy: it looked home-made).
    from PIL import Image
    for k in sorted(raw):
        src = raw[k]
        if src in videos:
            continue
        try:
            with Image.open(src) as im:
                if im.width >= 1100 and im.width / max(1, im.height) >= 1.3:
                    thumb_src = src
                    break
        except OSError:
            continue
    else:
        thumb_src = first
    title = os.path.join(".hv_pics", "title.jpg")
    canvas(first, os.path.join(job_dir, title), dark=0.55, blur=8)
    return pics, title, credits, ai_used, thumb_src, stock


def frame_of(video, out, at=1.0):
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2",
                        out], capture_output=True, text=True, timeout=120)
    return out if r.returncode == 0 and os.path.isfile(out) else None


def _resume_path(*settings):
    import hashlib
    key = hashlib.sha1(json.dumps(settings, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]
    return os.path.join(RESUME_DIR, f"{key}.json")


def load_resume(path, now=None):
    """(script, facts, sources) a failed try of the same video saved, or None (none, too old or unreadable)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if (now or time.time()) - data["at"] > RESUME_HOURS * 3600:
            return None
        return Script.model_validate(data["script"]), data["facts"], [tuple(s) for s in data["sources"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_resume(path, script, facts, sources):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = time.time() - RESUME_HOURS * 3600
        for name in os.listdir(os.path.dirname(path)):          # the folder never grows past two days of tries
            p = os.path.join(os.path.dirname(path), name)
            if os.path.getmtime(p) < old:
                os.remove(p)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "script": script.model_dump(), "facts": facts,
                       "sources": [list(s) for s in sources]}, f, ensure_ascii=False)
    except OSError:
        pass                    # a cache: the video goes on without it


def run(output_dir, pipeline):
    from controversy_shorts import _real_url
    if os.environ.get("HISTORY_TEASER_OF"):
        return run_teaser(output_dir, pipeline)
    if os.environ.get("HISTORY_TODAY") == "1":
        import history_today        # the channel's daily "on this day" Short
        return history_today.run(output_dir, pipeline)
    topic = re.sub(r"\s+", " ", os.environ.get("HISTORY_TOPIC") or "").strip()[:200]
    if len(topic) < 3:
        raise RuntimeError("Write the story or topic of the video.")
    minutes = minutes_wanted(os.environ.get("HISTORY_MINUTES"))
    lang = (os.environ.get("HISTORY_LANG") or "urdu").lower()
    lang = lang if lang in LANGS else "urdu"
    captions = os.environ.get("HISTORY_CAPTIONS", "1") != "0"
    mode = mode_now()
    cfg = fl.settings()
    handle = cfg["handle"] or ""
    client = kit.gemini()
    started = time.time()
    print(f"📜 {MODE_NAME[mode]} video ({minutes} min, {lang}): "
          f"{'writing' if mode == 'horror' else 'researching'} \"{topic}\"...")
    series = series_env()
    if series:
        print(f"   📚 Part {series['part']} of {series['parts']} of the series \"{series['name']}\".")
    resume = _resume_path(topic, minutes, lang, mode, series, os.environ.get("OWNER_NOTES") or "")
    saved = load_resume(resume)
    if saved:
        script, facts, sources = saved
        print("   ♻️ The research and script of the last try (stopped by an outage) are reused.")
    else:
        script, facts, sources = write(client, series_topic(topic, series), handle or "this channel", minutes, lang,
                                       series_note=series_note(series, lang), mode=mode)
        if not script.sacred:
            # Sacred stories keep the writer's title: a tournament for clicks is the wrong tool there.
            script.title = craft.pick_title(client, script.title, facts,
                                            what={"explainer": "YouTube explainer", "horror": "YouTube horror story"}
                                            .get(mode, "YouTube documentary"),
                                            language="English" if lang == "english" else craft.ROMAN)
        if mode == "horror":
            import horror_stories
            script.title = horror_stories.search_title(script.title, lang)
        if series:
            script.title = part_title(script.title, series["part"])
        save_resume(resume, script, facts, sources)
    sc = scenes_of(script)
    print(f"   ✅ \"{script.title}\": {len(script.chapters)} chapters, {len(sc)} scenes, {word_count(script)} words, "
          f"{len(sources)} sources{', sacred: no people shown, no music' if script.sacred else ''}.")
    stem = kit.neutral_stem("History")
    texts = [s.line for s in sc] + [script.outro, script.question]
    print(f"🎙️ Voicing {len(texts)} paragraphs while the pictures are found...")
    # The two are independent and each takes a minute or more on a long video.
    with ThreadPoolExecutor(max_workers=1) as voicing:
        said_later = voicing.submit(voice_all, client, texts, output_dir, lang,
                                    os.environ.get("HISTORY_VOICE") or voice_for(mode), mode)
        pics, title_pic, credits, ai_used, first_pic, stock = pictures(client, script, topic, output_dir, mode=mode)
        maps_used = add_maps(script, pics) if mode == "history" else 0
        said = said_later.result()
    missing = sum(1 for p, _ in said if not p)
    if missing > 2:
        raise RuntimeError(f"The AI voice failed for {missing} paragraphs; try again later.")
    segs, voices, whooshes, marks, sections, total = plan(script, said, handle, lang, captions, mode)
    if minutes <= UNVERIFIED_MINUTES and total > UNVERIFIED_LIMIT:
        # A video meant for an unverified channel (<= 14 min) that the voice made too long would be refused.
        said = fit_voices(said, total, output_dir)
        segs, voices, whooshes, marks, sections, total = plan(script, said, handle, lang, captions, mode)
    srt = write_srt(os.path.join(output_dir, "captions.srt"), texts, said, voices, lang)
    # The English track is translated while the shots render (~40 s of calls
    # on the Rome script, which used to come before the render).
    en_later = None
    if srt and lang != "english" and os.environ.get("HISTORY_EN_CAPTIONS", "1").strip() != "0":
        en_pool = ThreadPoolExecutor(max_workers=1)
        en_later = en_pool.submit(translate_srt, client, srt, os.path.join(output_dir, "captions.en.srt"))
        en_pool.shutdown(wait=False)
    print(f"🎬 Rendering {len(segs)} shots ({clock(total)})...")
    video = render(output_dir, segs, pics, title_pic, ".hv_video.mp4")
    narration(os.path.join(output_dir, ".hv_voice.wav"), voices, total)
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    tracks = _bed_tracks(script.sacred, "horror" if mode == "horror" else "history")
    mix(output_dir, video, ".hv_voice.wav", os.path.basename(final), total, whooshes, sections, tracks,
        sting=mode == "horror")
    # A big wide picture of the video (pictures() chooses) under the thumbnail text.
    thumb = _thumbnail(client, script, output_dir, first_pic, mode)
    en_srt = None
    if en_later:
        try:
            en_srt = en_later.result(timeout=600)
        except Exception as e:  # noqa: BLE001 — the Urdu track is enough on its own
            print(f"⚠️ English subtitles skipped: {type(e).__name__}: {e}")
    real = [(name, _real_url(url)) for name, url in rank_sources(sources)[:8]]
    import stock_media
    stock_line = stock_media.credit_line(stock)
    if maps_used:
        import history_maps
        stock_line = (stock_line + "\n" if stock_line else "") + history_maps.CREDIT
    desc = describe(script, marks, real, credits, handle, lang, ai_used > 0, stock_line, mode)
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": script.title, "seo_title": script.title[:100],
            "seo_description": desc, "seo_tags": [t[:40] for t in script.tags][:15],
            "viral_hook_text": (script.hook[0].line if script.hook else "")[:200],
            "why": f"{MODE_NAME[mode]} video: {topic}", "predicted_score": 85,
            "genre": "history",
            "comment_question": script.question, "ai_voice": "AI voice", "ai_made": ai_used > 0,
            "thumbnail_file": os.path.basename(thumb) if thumb else None,
            # Uploaded as the video's own caption track (my_channels, captions.insert).
            "captions_file": os.path.basename(srt) if srt else None,
            "captions_language": "en" if lang == "english" else "ur",
            "captions_extra": [{"file": os.path.basename(en_srt), "language": "en"}] if en_srt else [],
            "chapters": [{"title": t, "at": round(a, 2)} for t, a in marks],
            "source_links": real, "photo_credit": "\n".join(credits),
            "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in stock],
            "history": {"topic": topic, "minutes": minutes, "lang": lang, "sacred": script.sacred, "series": series,
                        "mode": mode,
                        "pictures": {"free": len(credits), "stock": len(stock), "ai": ai_used},
                        "background_music": bool(tracks),
                        # The teaser Short (run_teaser) reuses the opening's voice and pictures.
                        "voices": [os.path.basename(p) if p else None for p, _s in said],
                        "scene_pictures": {str(k): v for k, v in pics.items()},
                        "script": script.model_dump()}}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "history", "format": "16:9"})
    try:
        os.remove(resume)           # made: a "make it again" must get a new script, not this one
    except OSError:
        pass
    print(f"   ⏱️ Made in {(time.time() - started) / 60:.1f} min.")


# ------------------------------------------------------------------ teaser Short

TEASER_MAX = 50.0           # seconds of the long video's opening, so the Short stays under a minute
TEASER_LINE = {"urdu": "Poori kahani hamare channel par dekhein, link description mein hai.",
               "english": "Watch the full story on our channel, the link is in the description."}
TEASER_PILL = {"urdu": "POORI VIDEO CHANNEL PAR", "english": "FULL VIDEO ON THE CHANNEL"}
TEASER_KICKER = {"urdu": "POORI KAHANI", "english": "THE FULL STORY"}


def teaser_plan(script, voices, src):
    """[(scene index, text, wav, seconds)]: the hook, plus the first chapter
    scenes while the total stays under TEASER_MAX."""
    out, total = [], 0.0
    for k, s in enumerate(scenes_of(script)):
        name = voices[k] if k < len(voices) else None
        wav = os.path.join(src, name) if name else None
        if not wav or not os.path.isfile(wav):
            break
        secs = kit.wav_seconds(wav)
        if k >= len(script.hook) and (total + secs > TEASER_MAX or total >= 25):
            break
        if total + secs > TEASER_MAX and out:
            break
        out.append((k, s.line, wav, secs))
        total += secs + GAP
    return out


# More Shorts from one long video: its best moments, each a run of one
# chapter's scenes with a new spoken line that sets it up for a stranger.
MOMENT_MAX = 44.0           # the chapter scenes; the set-up and closing lines take the rest of the minute
MOMENT_MIN = 15.0


class Moment(BaseModel):
    chapter: int
    first_scene: int
    hook: str
    title: str


class Moments(BaseModel):
    moments: List[Moment]


MOMENTS_PROMPT = """This is the script of our long history video "{title}". We cut its best
moments into separate YouTube Shorts that people who have NOT seen the video will
swipe to. Pick the {n} best moments: each a run of consecutive scenes from one
chapter that makes sense on its own and grips a stranger (a turning point, a
surprising fact, a dramatic scene, a decision that changed everything). Not the
opening hook (it has its own Short), and each moment from a different chapter.

For each moment:
- chapter: the chapter number as listed below
- first_scene: the scene number within that chapter where the moment starts
- hook: ONE spoken sentence of 8 to 16 words, said before the moment, that sets it up
  for a stranger (who, where, when) and makes them want to hear what happened. It is
  read aloud by a voice: no Roman numerals, no brackets. Language: {lang_rule}. {honour}
- title: a Short title under 70 characters about this moment (not the whole video),
  same language, no clickbait lies.

Script:
{script}"""


def _moment_script(script):
    out = []
    for c, ch in enumerate(script.chapters, 1):
        out.append(f"[Chapter {c}] {ch.title}")
        out += [f"  {k}. {s.line}" for k, s in enumerate(ch.scenes, 1)]
    return "\n".join(out)


def moment_start(script, m):
    """The moment's first scene as an index into scenes_of(script), or None."""
    if not 1 <= m.chapter <= len(script.chapters):
        return None
    if not 1 <= m.first_scene <= len(script.chapters[m.chapter - 1].scenes):
        return None
    return len(script.hook) + sum(len(c.scenes) for c in script.chapters[:m.chapter - 1]) + m.first_scene - 1


def moments_for(client, script, src, lang, teaser_end, n=2):
    """The long video's best moments, asked for once and kept in its folder
    (moments.json) so each moment Short reads the same list. Moments that
    start inside the teaser's opening, or twice in one chapter, are dropped."""
    path = os.path.join(src, "moments.json")
    try:
        with open(path, encoding="utf-8") as f:
            return [Moment(**m) for m in json.load(f)]
    except (OSError, ValueError, TypeError):
        pass
    from quiz_shorts import quiz_model
    got = kit.ask_json(client, Moments, MOMENTS_PROMPT.format(
        title=script.title, n=n, lang_rule=LANG_RULE.get(lang, LANG_RULE["urdu"]),
        honour=HONOUR.get(lang, HONOUR["urdu"]), script=_moment_script(script)), model=quiz_model())
    keep, chapters = [], set()
    for m in got.moments:
        start = moment_start(script, m)
        if start is None or start < teaser_end or m.chapter in chapters or not m.hook.strip():
            continue
        m.hook = _no_roman(m.hook.strip(), lang)
        m.title = m.title.strip()[:90] or script.title
        chapters.add(m.chapter)
        keep.append(m)
    keep = keep[:n]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump([m.model_dump() for m in keep], f, ensure_ascii=False)
    return keep


def _no_roman(text, lang="urdu"):
    """'Yazid I' was read as 'Yazid one'; a Roman Urdu set-up line has no
    regnal numbers. English is left alone: there "I" is the pronoun."""
    if lang != "urdu":
        return text
    return re.sub(r"\b([A-Z][a-z]+) (?:I{1,3}|IV|V|VI{0,3})\b", r"\1", text)


def moment_plan(script, voices, src, start):
    """[(scene index, text, wav, seconds)] from ``start`` while the total stays
    under MOMENT_MAX; into the next chapter only when the moment is short."""
    scenes = scenes_of(script)
    ends, n = set(), len(script.hook)
    for c in script.chapters:
        n += len(c.scenes)
        ends.add(n)
    out, total = [], 0.0
    for k in range(start, len(scenes)):
        name = voices[k] if k < len(voices) else None
        wav = os.path.join(src, name) if name else None
        if not wav or not os.path.isfile(wav):
            break
        secs = kit.wav_seconds(wav)
        if out and total + secs > MOMENT_MAX:
            break
        if k in ends and total >= MOMENT_MIN:
            break
        out.append((k, scenes[k].line, wav, secs))
        total += secs + GAP
    return out


def _reused_credits(long_clip, link, budget=1200):
    """The long video's picture and footage credits for a Short cut from it,
    trimmed to fit a Short's description; the full list is in the long video's."""
    import stock_media
    lines = [c for c in (long_clip.get("photo_credit") or "").split("\n") if c.strip()]
    keep, used = [], 0
    for c in lines:
        if used + len(c) + 3 > budget:
            break
        keep.append(f"- {c}")
        used += len(c) + 3
    out = ["Pictures: free-licence pictures from Wikimedia Commons"] + keep if lines else []
    if len(keep) < len(lines):
        out.append(f"- and {len(lines) - len(keep)} more, credited in the full video's description"
                   + (f" ({link})" if link else ""))
    footage = stock_media.credit_line(long_clip.get("footage") or [])
    return "\n".join(out + ([footage] if footage else []))


def _sentence_windows(windows, items):
    """Each voice line's window split at its sentences, time shared by words:
    a long-video scene is one picture for 15-25 s, too slow for a Short."""
    out_w, out_i = [], []
    for (a, b, text), item in zip(windows, items):
        parts = [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]
        if len(parts) < 2 or b - a < 6:
            out_w.append((a, b, text))
            out_i.append(item)
            continue
        weights = [len(p.split()) for p in parts]
        t = a
        for k, (p, wt) in enumerate(zip(parts, weights)):
            end = b if k == len(parts) - 1 else t + (b - a) * wt / sum(weights)
            out_w.append((t, end, p))
            out_i.append(item)
            t = end
    return out_w, out_i


def _short_footage(client, script, windows, items):
    """(windows, items) for a teaser or moment Short: one shot per sentence,
    free footage where a search finds a fit, the long video's own picture
    for the scene everywhere else. No keys or no matches: the pictures only."""
    import broll
    import stock_media
    windows, fallback = _sentence_windows(windows, items)
    if os.environ.get("STOCK_FOOTAGE", "1") == "0" or not stock_media.available():
        return windows, fallback, []
    if mode_now() == "horror":
        import horror_stories
        rule = horror_stories.FOOTAGE_RULE
    else:
        rule = FOOTAGE_RULE + ((NO_PEOPLE + " ") if script.sacred else "")
    try:
        lines = [w[2] for w in windows]
        terms = broll.terms_for(client, script.title, lines, rule)
        found = stock_media.for_scenes(client, script.title, lines, terms, portrait=True, rule=rule)
    except Exception as e:  # noqa: BLE001 — footage is a bonus over the pictures
        print(f"   ℹ️ No stock footage for this Short ({type(e).__name__}).")
        return windows, fallback, []
    print(f"   🎞️ Footage for {sum(1 for f in found if f)} of {len(windows)} sentences.")
    found = list(found) + [None] * len(windows)
    return windows, [f or fb for f, fb in zip(found, fallback)], [f for f in found if f]


def run_teaser(output_dir, pipeline):
    """A 9:16 teaser Short of a finished long video: its opening narration (the
    voice files are reused, no new voice cost but one closing line), its
    pictures and footage cut for a phone, and a closing line pointing to the
    full video, linked in the description. Long videos are found slowly;
    Shorts are pushed to new viewers, so each long video gets one."""
    import broll
    import cricket_shorts as cs
    from types import SimpleNamespace
    src = os.environ["HISTORY_TEASER_OF"]
    vid = (os.environ.get("HISTORY_VIDEO_ID") or "").strip()
    metas = glob.glob(os.path.join(src, "*_metadata.json"))
    if not metas:
        raise RuntimeError("The long video's files are gone; no teaser this time.")
    with open(metas[0], encoding="utf-8") as f:
        long_clip = (json.load(f).get("shorts") or [{}])[0]
    h = long_clip.get("history") or {}
    if not h.get("script") or not h.get("voices"):
        raise RuntimeError("This long video was made before teasers existed.")
    script = Script(**h["script"])
    lang = h.get("lang") if h.get("lang") in LANGS else "urdu"
    mode = h.get("mode") if h.get("mode") in MODES else "history"       # the long video's own subject
    plan_ = teaser_plan(script, h["voices"], src)
    if not plan_:
        raise RuntimeError("The long video's voice files are gone; no teaser this time.")
    cfg = fl.settings()
    handle = cfg["handle"] or ""
    client = kit.gemini()
    try:
        part = max(0, int(os.environ.get("HISTORY_TEASER_PART") or 0))
    except ValueError:
        part = 0
    title, setup = script.title, None
    if part:
        # A moment Short: one of the long video's best chapters, set up in one new line.
        moments = moments_for(client, script, src, lang, plan_[-1][0] + 1)
        if part > len(moments):
            raise RuntimeError("This long video has no more moments for a Short.")
        m = moments[part - 1]
        plan_ = moment_plan(script, h["voices"], src, moment_start(script, m))
        if not plan_:
            raise RuntimeError("The long video's voice files are gone; no Short this time.")
        title, setup = m.title, m.hook
        print(f"🎬 Moment Short {part} for \"{script.title}\": {len(plan_)} lines of chapter {m.chapter}.")
    else:
        print(f"🎬 Teaser Short for \"{script.title}\": {len(plan_)} opening lines.")
    # The new lines in the voice that read the long video (the free voice
    # leaves word timings next to its wavs), not today's setting: two
    # voices in one Short sound like two channels.
    os.environ["VOICE_ENGINE"] = "edge" if os.path.isfile(plan_[0][2] + ".words.json") else "gemini"
    voice = {"voice": os.environ.get("HISTORY_VOICE") or "Charon", "style": VOICE_STYLE[lang],
             "language": LANG_NAME[lang]}
    said = kit.voice_lines(client, ([{"text": setup, **voice}] if setup else [])
                           + [{"text": TEASER_LINE[lang], **voice}], output_dir, "tz")
    closing = said[-1:]
    pics = h.get("scene_pictures") or {}

    def item(k):
        # Absolute paths: broll runs ffmpeg INSIDE this teaser's folder, and src ("output\<long id>",
        # app.OUTPUT_DIR is relative) read from there was output\<teaser>\output\<long>\... ("footage shot
        # failed: Error opening input file output\...\.hv_pics\c007_full.jpg", server.log 4-nov-2026).
        entry = pics.get(str(k)) or {}
        if entry.get("video") and os.path.isfile(entry["video"]):
            return {"kind": "video", "path": os.path.abspath(entry["video"]), "seconds": entry.get("seconds") or 0}
        full = entry.get("full")
        return {"kind": "photo", "path": os.path.abspath(os.path.join(src, full)), "seconds": 0.0} \
            if full and os.path.isfile(os.path.join(src, full)) else None
    t, voices, caps, windows, items, sfx = 0.4, [], [], [], [], []
    if setup and said[0][0]:
        wav, secs = said[0]
        voices.append((wav, t))
        caps.append((setup, t, t + secs, wav))
        windows.append((0.0, t + secs + GAP, setup))
        items.append(item(plan_[0][0]))
        t += secs + GAP
    for k, text, wav, secs in plan_:
        voices.append((wav, t))
        caps.append((text, t, t + secs, wav))
        windows.append((t if windows else 0.0, t + secs + GAP, text))
        items.append(item(k))
        t += secs + GAP
    close_wav, close_secs = closing[0]
    close_secs = close_secs or 3.5
    c0 = t
    if close_wav:
        voices.append((close_wav, c0))
        caps.append((TEASER_LINE[lang], c0, c0 + close_secs, close_wav))
    body_end = c0 + close_secs + 0.6
    windows.append((c0, body_end, TEASER_LINE[lang]))
    items.append(item(plan_[0][0]))
    outro_s = cfg["outro_seconds"]
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)
    windows[-1] = (windows[-1][0], total, windows[-1][2])
    bg = None
    windows, items, stock = _short_footage(client, script, windows, items)
    shots = broll.plan_shots(windows, items)
    if shots:
        bg = broll.build(output_dir, shots)
    frame = SimpleNamespace(kicker=TEASER_KICKER[lang], title=title)
    events = cs.topic_frame_events(frame, body_end, handle)
    events.append(cs._flash(c0))
    events += cs._pill(c0 + 0.2, body_end, 1000, TEASER_PILL[lang])
    sfx.append((kit.WHOOSH, 0.3, max(0.0, c0 - 0.15)))
    track = None
    if not script.sacred and os.environ.get("BG_MUSIC", "0") == "1":
        track = kit.music_track("horror" if mode == "horror" else "history")
    stem = kit.neutral_stem("Teaser")
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    print(f"🎬 Rendering the {'moment' if part else 'teaser'} Short ({total:.0f}s)...")
    kit.render(final, total, [cfg["bg"], kit.blend("#7C5A2A", cfg["bg"], 0.3)],
               ([] if bg else kit.ambient_events(total)) + events + card_ev, cs.STYLES, voices=voices,
               sfx=sfx + card_sfx, bed=(track, body_end) if track else None, bg_video=bg, fast=True)
    word = words_for(lang, mode)
    link = f"https://youtu.be/{vid}" if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else ""
    desc = "\n".join(x for x in [((setup + " ") if setup else "") + script.summary.strip(), "",
                                 (("Poori video: " if lang == "urdu" else "Full video: ") + link) if link else "",
                                 "", f"{word['follow']}{(' ' + handle) if handle else ''}", "",
                                 ("#shorts #horrorstory " if mode == "horror" else "#shorts #history ")
                                 + ("#urdu" if lang == "urdu" else "#documentary")] if x is not None)
    import credits
    import stock_media
    if any(it and not any(it is s for s in stock) for it in items):
        # The long video's pictures are in it too, and their licences ask for credit.
        desc = credits.insert(desc, _reused_credits(long_clip, link))
    if stock:
        desc = credits.insert(desc, stock_media.credit_line(stock))
    transcript = kit.timed_transcript(caps)
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": title, "seo_title": title[:100],
            "seo_description": re.sub(r"\n{3,}", "\n\n", desc), "seo_tags": [x[:40] for x in script.tags][:15],
            "viral_hook_text": (setup or plan_[0][1])[:200], "why": f"Teaser of: {script.title}", "predicted_score": 80,
            "genre": "history", "comment_question": script.question, "ai_voice": "AI voice",
            "captions": transcript, "teaser_of": vid or None,
            "history": {"teaser": True, "part": part, "lang": lang,
                        "of_job": os.path.basename(os.path.normpath(src))}}
    kit.finish(output_dir, stem, [clip], transcript, pipeline, extra={"genre": "history", "format": "9:16"})
