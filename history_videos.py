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
HISTORY_CAPTIONS (default on).
"""
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
import short_kit as kit
from ffmpeg_utils import LOUDNORM_FILTER, METADATA_SCRUB, escape_filter_value

W, H, FPS = 1920, 1080, 30
SUPER = 2                      # the pan runs on a 2x canvas, then scales down: half-pixel steps
PAN = 1.15                     # the canvas is 15% larger than the frame: room to pan
CANVAS_W, CANVAS_H = round(W * PAN) * SUPER, round(H * PAN) * SUPER
MIN_MINUTES, MAX_MINUTES, DEFAULT_MINUTES = 2, 30, 10
WORDS_PER_MINUTE = 150
MIN_SOURCES = 3
SHOT_SECONDS = 11.0            # a new picture or a closer crop about this often
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


class Scene(BaseModel):
    line: str
    picture: str
    wiki: str
    label: str


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
  or "".
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
taking sides in current party politics. Small wording choices are fine.
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
            "numbers, captions, logos or watermarks anywhere. No modern objects.")

IDEAS_PROMPT = """Today is {today}. Plan the next {count} long YouTube videos ({minutes}-minute documentaries, in
{lang}) for a history and stories channel for Pakistani and Indian viewers. Topics like: the rise and fall of
empires (Rome, the Ottomans, the Mughals, the Abbasids), Islamic history told with respect (Karbala, the Caliphs,
Al-Andalus), famous wars and events, how countries work and why they got rich or poor (the US government, the US
economy, the dollar, China, the Gulf states), mysteries and turning points of history.
{owner}{trending}Use Google Search for what people search and talk about now: anniversaries this month, news
that makes an old story matter again.
Each idea is one clear story with a hook, e.g. "Roman Empire: how the greatest empire fell", "Karbala: what
happened in 680 AD", "How the US government really works", "Why America owes so much money".
Never: {rules}.
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "topic: ", at most 90 characters, no translation in brackets. Nothing else."""

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


def channel_ideas(client, count=2, avoid=(), best=(), worst=(), notes="", lang="urdu", minutes=DEFAULT_MINUTES):
    import cricket_shorts as cs
    learn = ""
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
    return [i for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen][:count * 3 + 2]


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


def research(client, topic, minutes):
    """(facts, extra facts, [(source name, url)])."""
    from google.genai import types
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
        main = pool.submit(ask, FACTS_PROMPT.format(today=today, minutes=minutes, topic=topic,
                                                    fact_words=max(600, min(3000, minutes * 120))))
        more = pool.submit(ask, EXTRA_PROMPT.format(today=today, topic=topic))
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


def write(client, topic, handle, minutes=DEFAULT_MINUTES, lang="urdu", research_fn=None):
    """(Script, facts, sources) that passed the fact check, or raises."""
    from quiz_shorts import quiz_model
    facts, extra, sources = (research_fn or research)(client, topic, minutes)
    if not facts or "NOT FOUND" in facts[:200].upper() or len(sources) < MIN_SOURCES:
        raise RuntimeError(f"Not enough reliable sources for this topic ({len(sources)}).")
    words, chapters, scenes = shape(minutes)
    fixes = ""
    for attempt in range(2):
        script = kit.ask_json(client, Script, SCRIPT_PROMPT.format(
            minutes=minutes, handle=handle, topic=topic, lang_rule=LANG_RULE.get(lang, LANG_RULE["urdu"]),
            fixes=fixes, facts=facts, extra=extra or "(none)", words=words, rules=RULES, sacred=SACRED,
            chapters=chapters, scenes=scenes, no_people=NO_PEOPLE,
            honour=HONOUR.get(lang, HONOUR["urdu"])), model=quiz_model())
        if not script.allowed:
            raise RuntimeError(f"Not made: {script.reason or 'the topic is not for this channel'}.")
        if len(script.chapters) < 2 or not script.hook:
            raise RuntimeError("The script came back without chapters; try again later.")
        notes = []
        got = word_count(script)
        if got < words * 0.75:
            notes.append(f"The script is too short: {got} words. Write about {words} words, with more scenes.")
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(
            facts=facts, extra=extra or "(none)", script=_narration_text(script),
            honour_short="\"Hazrat\", \"sallallahu alaihi wasallam\" / \"(SAW)\"" if lang == "urdu"
            else "\"peace be upon him\""), model=quiz_model())
        if not check.ok:
            notes += check.problems
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


def ai_picture(client, prompt, out, sacred):
    """One AI picture (16:9) for a scene; returns the path or raises."""
    from google.genai import types
    from PIL import Image
    import thumbnail
    rule = (NO_PEOPLE + " ") if sacred else "Never show any prophet or revered religious figure. "
    r = client.models.generate_content(
        model=thumbnail.IMAGE_MODEL, contents=[f"{AI_STYLE} {rule}Scene: {prompt}"],
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
    im = Image.open(src).convert("RGB")
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

def voice_all(client, texts, job_dir, lang, voice):
    """[(wav, seconds) | (None, 0)] per text; failed or odd lines get two more tries."""
    import ai_take
    language = LANG_NAME.get(lang, "Roman Urdu")
    style = VOICE_STYLE.get(lang, VOICE_STYLE["urdu"])
    said = kit.voice_lines(client, [{"text": t, "voice": voice, "style": style, "language": language}
                                    for t in texts], job_dir, "hv")

    def odd(k):
        path, secs = said[k]
        n = len(texts[k].split())
        # A voice that rambles on or cuts off is redone (seconds per word far off a narrator's).
        return not path or secs > n * 0.75 + 4 or secs < n * 0.15
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
            ev.append(kit.dialogue(6, a, b, "HvCap", rf"{{\an2\pos({W // 2},{H - 46})}}{_esc(text)}"))
    if question:
        a = max(0.0, question[1])
        ev.append(_rect(2, a, d, 0, 0, W, H, alpha="90", fade=(300, 0)))
        ev.append(kit.dialogue(4, a, d, "HvQ", rf"{{\an5\pos({W // 2},{H // 2 - 20})\fad(300,0)}}"
                                               rf"{_wrap(question[0], 36)}"))
    return ev


def card_events(d, kicker, title):
    return [_rect(1, 0, d, W // 2 - 90, H // 2 - 70, 180, 4, colour=fl.GOLD, alpha="00", fade=(400, 300)),
            kit.dialogue(3, 0, d, "HvKicker", rf"{{\an5\pos({W // 2},{H // 2 - 115})\fad(300,300)}}{_esc(kicker)}"),
            kit.dialogue(3, 0.15, d, "HvTitle", rf"{{\an8\pos({W // 2},{H // 2 - 40})\fad(400,300)"
                                                rf"\t(0,600,\fscx100\fscy100)\fscx92\fscy92}}{_wrap(title, 32)}")]


def end_events(d, handle, lang):
    return [kit.dialogue(3, 0, d, "HvBig", rf"{{\an5\pos({W // 2},{H // 2 - 80})\fad(300,0)"
                                           rf"\t(0,400,\fscx100\fscy100)\fscx80\fscy80}}SUBSCRIBE"),
            kit.dialogue(3, 0.3, d, "HvKicker", rf"{{\an5\pos({W // 2},{H // 2 + 50})\fad(300,0)}}{_esc(handle)}"),
            kit.dialogue(3, 0.6, d, "HvLabel", rf"{{\an5\pos({W // 2},{H // 2 + 130})\fad(300,0)}}"
                                               rf"{_esc(WORDS[lang]['next'])}")]


MOTIONS = ["right", "left", "down", "diag", "up", "left"]


def segment(job_dir, picture, out, frames, motion, events):
    """One shot: ``picture`` (a canvas, relative to job_dir) panned over
    ``frames`` frames under ``events``. Video only; same settings for all."""
    ass = out[:-4] + ".ass"
    with open(os.path.join(job_dir, ass), "w", encoding="utf-8") as f:
        f.write(_ass(events))
    d = frames / FPS
    cw, chh = W * SUPER, H * SUPER
    p = f"(t/{d:.4f})"
    x, y = {"right": (f"(iw-ow)*{p}", "(ih-oh)/2"), "left": (f"(iw-ow)*(1-{p})", "(ih-oh)/2"),
            "down": ("(iw-ow)/2", f"(ih-oh)*{p}"), "up": ("(iw-ow)/2", f"(ih-oh)*(1-{p})"),
            "diag": (f"(iw-ow)*{p}", f"(ih-oh)*{p}"), "still": ("(iw-ow)/2", "(ih-oh)/2")}[motion]
    vf = (f"loop=loop={frames - 1}:size=1:start=0,setpts=N/{FPS}/TB,crop={cw}:{chh}:x='{x}':y='{y}',"
          f"scale={W}:{H}:flags=bicubic,setsar=1,format=yuv420p,"
          f"ass=filename='{escape_filter_value(ass)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", picture, "-vf", vf, "-frames:v", str(frames),
                        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                        "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", "-an", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"shot failed: {r.stderr.strip()[-300:]}")
    os.remove(os.path.join(job_dir, ass))
    return out


def segment_video(job_dir, video, out, frames, offset, close, events):
    """One shot from a stock clip (looped if short), same encode settings as segment()."""
    ass = out[:-4] + ".ass"
    with open(os.path.join(job_dir, ass), "w", encoding="utf-8") as f:
        f.write(_ass(events))
    zoom = "crop=iw*0.86:ih*0.86," if close else ""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}scale={W}:{H},fps={FPS},"
          f"setsar=1,format=yuv420p,"
          f"ass=filename='{escape_filter_value(ass)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{offset:.2f}", "-stream_loop", "-1", "-i", video,
                        "-vf", vf, "-frames:v", str(frames), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "21", "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", "-an", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"footage shot failed: {r.stderr.strip()[-300:]}")
    os.remove(os.path.join(job_dir, ass))
    return out


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


def plan(script, said, handle, lang, captions=True):
    """The frame-exact timeline: (segments, voices, whooshes, chapter marks,
    bed sections, total seconds). ``said`` is one (wav, seconds) per voiced
    paragraph: hook scenes, chapter scenes, outro, question.

    A segment is {"pic": scene index | "title" | "end", "variant", "frames",
    "motion", "events"}; a scene index refers to scenes_of(script)."""
    segs, voices, whooshes, marks, sections = [], [], [], [], []
    frames, n = 0, 0
    word = WORDS.get(lang, WORDS["urdu"])

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
    add("end", "full", END_CARD, lambda d: end_events(d, handle or "", lang), "still")
    sections.append(at())
    return segs, voices, whooshes, marks, sections, at()


def describe(script, marks, sources, credits, handle, lang, ai_used, stock_line=""):
    """The YouTube description: summary, chapters, question, sources, picture credits, follow line."""
    import youtube_account
    word = WORDS.get(lang, WORDS["urdu"])
    slug = re.sub(r"[^A-Za-z0-9]+", "", (script.tags or ["history"])[0].title())[:30] or "History"
    tags = ["#history", "#urdu" if lang == "urdu" else "#documentary", f"#{slug}"]
    head = [script.summary.strip(), "", "\n".join(f"{clock(t)} {_esc(title)}" for title, t in marks), "",
            script.question.strip()]
    if sources:
        head += ["", "Sources:"] + [f"- {n}: {u}" if n else f"- {u}" for n, u in sources[:8]]
    tail = ["", f"{word['follow']}{(' ' + handle) if handle else ''}", " ".join(tags)]
    pics = ["", "Pictures: free-licence pictures from Wikimedia Commons"
            + ("; the other pictures are AI illustrations." if ai_used else ".")] if credits else (
        ["", "Pictures: AI illustrations."] if ai_used else [])
    if stock_line:
        pics = (pics or [""]) + [stock_line]
    budget = youtube_account.DESCRIPTION_MAX - len("\n".join(head + pics + tail)) - 60
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


def _thumbnail(client, script, job_dir, fallback):
    """thumbnail.jpg: free by default, the video's opening picture with the
    hook text set by PIL over a dark fade on the left; HISTORY_AI_THUMBNAIL=1
    asks the image model for a new picture first (~$0.10). Path or None."""
    import thumbnail as th
    out = os.path.join(job_dir, "thumbnail.jpg")
    text = script.thumb_text.upper()[:40]
    if AI_THUMBNAIL:
        scene = (f"{script.thumb_picture}. Epic and dramatic, historical. "
                 + (NO_PEOPLE if script.sacred else "Never show any prophet or revered religious figure."))
        try:
            return th._generate_one(client, {"scene": scene, "text": text, "text_position": "left",
                                             "text_color": "yellow"}, [], out, burn_text=True)
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
            draw.line([(col, 0), (col, th.THUMB_H)], fill=round(190 * (1 - col / fade_end)))
        im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, shade)
        im = th.burn_thumbnail_text(im, text, "left", "yellow").convert("RGB")
        im.save(out, "JPEG", quality=90)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"   ℹ️ No thumbnail ({type(e).__name__}).")
        return None


def _bed_tracks(sacred):
    if sacred or os.environ.get("BG_MUSIC", "0") != "1":
        return []
    import music_beds
    have = music_beds.ensure("history", music_beds.PER_KIND)
    folder = os.path.join(kit.MUSIC_DIR, "history")
    tracks = [os.path.join(folder, f) for f in have]
    random.shuffle(tracks)
    return tracks


def mix(job_dir, video, narration_wav, out, total, whooshes, sections, tracks):
    """The final file: the joined video (copied), the narration, a whoosh per
    card and a music bed per chapter (looped, faded)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", video, "-i", narration_wav]
    graph = [f"[1:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo[vo]"]
    mixin = ["[vo]"]
    idx = 2
    if tracks:
        for k in range(len(sections) - 1):
            a, b = sections[k], sections[k + 1]
            length = b - a
            if length < 2:
                continue
            cmd += ["-stream_loop", "-1", "-i", tracks[k % len(tracks)]]
            ms = int(a * 1000)
            graph.append(f"[{idx}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,{kit.BED_LOUDNORM},"
                         f"afade=t=in:d=1.5,afade=t=out:st={max(0.0, length - 2):.3f}:d=2,"
                         f"aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[bed{k}]")
            mixin.append(f"[bed{k}]")
            idx += 1
    for k, t in enumerate(whooshes):
        ms = int(t * 1000)
        graph.append(f"aevalsrc='{kit.WHOOSH}':s=48000:d=0.3,aformat=channel_layouts=stereo,adelay={ms}|{ms}[sx{k}]")
        mixin.append(f"[sx{k}]")
    graph.append(f"{''.join(mixin)}amix=inputs={len(mixin)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
                              *METADATA_SCRUB, "-movflags", "+faststart", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"mix failed: {r.stderr.strip()[-400:]}")
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
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", ".hv_parts.txt",
                        "-c", "copy", out_name], cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"join failed: {r.stderr.strip()[-300:]}")
    return out_name


# ------------------------------------------------------------------ the job

def pictures(client, script, topic, job_dir, log=print):
    """(scene index -> canvases, title canvas, credits, AI pictures used)."""
    sc = scenes_of(script)
    os.makedirs(os.path.join(job_dir, ".hv_pics"), exist_ok=True)
    articles = []
    for s in sc:
        a = (s.wiki or "").strip()
        if a and a.lower() not in {x.lower() for x in articles}:
            articles.append(a)
    log(f"🖼️ Looking for free pictures in {min(len(articles), MAX_ARTICLES)} Wikipedia articles...")
    pool = candidates(articles, script.sacred)
    picks = pick(client, topic, sc, pool, script.sacred) if pool else {}
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
            rule = FOOTAGE_RULE + ((NO_PEOPLE + " ") if script.sacred else "")
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
    want = [k for k in ai_order(len(script.hook), [len(c.scenes) for c in script.chapters]) if k not in raw]
    want = want[:max(0, AI_IMAGES)]
    ai_used = 0
    if want:
        log(f"🎨 Making {len(want)} AI picture(s)...")

        def make(k):
            out = os.path.join(job_dir, ".hv_pics", f"ai{k:03d}.jpg")
            for attempt in range(2):
                try:
                    return k, ai_picture(client, sc[k].picture, out, script.sacred)
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
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2",
                        out], capture_output=True, text=True, timeout=120)
    return out if r.returncode == 0 and os.path.isfile(out) else None


def run(output_dir, pipeline):
    from controversy_shorts import _real_url
    topic = re.sub(r"\s+", " ", os.environ.get("HISTORY_TOPIC") or "").strip()[:200]
    if len(topic) < 3:
        raise RuntimeError("Write the story or topic of the video.")
    minutes = minutes_wanted(os.environ.get("HISTORY_MINUTES"))
    lang = (os.environ.get("HISTORY_LANG") or "urdu").lower()
    lang = lang if lang in LANGS else "urdu"
    captions = os.environ.get("HISTORY_CAPTIONS", "1") != "0"
    cfg = fl.settings()
    handle = cfg["handle"] or ""
    client = kit.gemini()
    started = time.time()
    print(f"📜 History video ({minutes} min, {lang}): researching \"{topic}\"...")
    script, facts, sources = write(client, topic, handle or "this channel", minutes, lang)
    sc = scenes_of(script)
    print(f"   ✅ \"{script.title}\": {len(script.chapters)} chapters, {len(sc)} scenes, {word_count(script)} words, "
          f"{len(sources)} sources{', sacred: no people shown, no music' if script.sacred else ''}.")
    stem = kit.neutral_stem("History")
    texts = [s.line for s in sc] + [script.outro, script.question]
    print(f"🎙️ Voicing {len(texts)} paragraphs while the pictures are found...")
    # The two are independent and each takes a minute or more on a long video.
    with ThreadPoolExecutor(max_workers=1) as voicing:
        said_later = voicing.submit(voice_all, client, texts, output_dir, lang,
                                    os.environ.get("HISTORY_VOICE") or "Charon")
        pics, title_pic, credits, ai_used, first_pic, stock = pictures(client, script, topic, output_dir)
        said = said_later.result()
    missing = sum(1 for p, _ in said if not p)
    if missing > 2:
        raise RuntimeError(f"The AI voice failed for {missing} paragraphs; try again later.")
    segs, voices, whooshes, marks, sections, total = plan(script, said, handle, lang, captions)
    print(f"🎬 Rendering {len(segs)} shots ({clock(total)})...")
    video = render(output_dir, segs, pics, title_pic, ".hv_video.mp4")
    narration(os.path.join(output_dir, ".hv_voice.wav"), voices, total)
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    tracks = _bed_tracks(script.sacred)
    mix(output_dir, video, ".hv_voice.wav", os.path.basename(final), total, whooshes, sections, tracks)
    # A big wide picture of the video (pictures() chooses) under the thumbnail text.
    thumb = _thumbnail(client, script, output_dir, first_pic)
    real = [(name, _real_url(url)) for name, url in rank_sources(sources)[:8]]
    import stock_media
    desc = describe(script, marks, real, credits, handle, lang, ai_used > 0, stock_media.credit_line(stock))
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": script.title, "seo_title": script.title[:100],
            "seo_description": desc, "seo_tags": [t[:40] for t in script.tags][:15],
            "viral_hook_text": (script.hook[0].line if script.hook else "")[:200],
            "why": f"History video: {topic}", "predicted_score": 85, "genre": "history",
            "comment_question": script.question, "ai_voice": "AI voice", "ai_made": ai_used > 0,
            "thumbnail_file": os.path.basename(thumb) if thumb else None,
            "chapters": [{"title": t, "at": round(a, 2)} for t, a in marks],
            "source_links": real, "photo_credit": "\n".join(credits),
            "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in stock],
            "history": {"topic": topic, "minutes": minutes, "lang": lang, "sacred": script.sacred,
                        "pictures": {"free": len(credits), "stock": len(stock), "ai": ai_used},
                        "background_music": bool(tracks),
                        "script": script.model_dump()}}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "history", "format": "16:9"})
    print(f"   ⏱️ Made in {(time.time() - started) / 60:.1f} min.")
