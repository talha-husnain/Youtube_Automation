"""Trending explainers: the long-video channel's second mode (HISTORY_MODE=explainer).

Owner, 21-oct-2026: six history documentaries of 8-10 minutes had 0 views
each. A scan of the month's most viewed long videos in Urdu and Hindi that
day found current-affairs explainers far ahead: "Why Houthis want to destroy
Saudi Arabia?" (Abhi and Niyu, 1.9M), the Flydubai hijack (Ankit Inspires
India, 2.3M), "Israeli Spy Who Almost Became Syria's President" (Nitish
Rajput, 10M). History in Urdu was far behind, Pakistan economy explainers
had a median of ~40k.

So the channel follows what the big explainer channels are riding:
- planning: the latest uploads of RIVALS with their views, this week's most
  viewed explainers, and Google Search for the week's biggest stories. A few
  topics at a time; they go stale after IDEA_HOURS (news moves on).
- keywords: YouTube's own search suggestions for the topic (suggestqueries,
  no key) go into the title, the description and the tags.
- research: Google-Search-grounded facts, every claim labelled.
- the most viewed videos on the topic are STUDIED, not copied: their captions
  go to one call that describes their angles in English, the script writer
  never sees their words, and `copied_runs` fails a script that repeats
  COPY_RUN words in a row from any of them. Re-voicing another creator's
  script is a copyright claim waiting to happen, and YouTube's "reused
  content" rule takes monetisation away for it.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

import short_kit as kit

IDEA_HOURS = 36
COPY_RUN = 8
STUDY_VIDEOS = 3
# Top Urdu/Hindi explainer channels in the 21-oct-2026 scan (channel ids: handles break).
# World Affairs by Unacademy, StudyIQ IAS, Adda247 Skills and Nitish Rajput answer
# "This channel is not available" from this laptop in Pakistan: our viewers there
# cannot watch them either, so they are no guide.
RIVALS = {
    "Abhi and Niyu": "https://www.youtube.com/channel/UCsDTy8jvHcwMvSZf_JGi-FA",
    "Ankit Inspires India": "https://www.youtube.com/channel/UC2Nwwobsd0ctkzVieXZvyQA",
    "Raftar": "https://www.youtube.com/channel/UC6zIImBjDqtEsVZfQLPoQSw",
    "The Kohistani": "https://www.youtube.com/channel/UCCBGUffdWwRV0gUqgElkCfw",
    "Mapsnap": "https://www.youtube.com/channel/UCpNuKbCzuNQtVqJXa_Hc23A",
    "SAH - World Affairs": "https://www.youtube.com/channel/UC1Ry7F0dJcX0aYcHN2o8QHg",
    "Zem TV": "https://www.youtube.com/channel/UCs_ineLBnNTGjrArNzjSLZg",
    "HinExp": "https://www.youtube.com/channel/UCytiKJcsuKFARvAeUABvRBA",
}
NICHE_QUERIES = ["explained in hindi", "explained in urdu", "news analysis hindi", "world news explained urdu",
                 "AI news explained hindi", "geopolitics explained hindi", "untold story urdu",
                 "mystery documentary hindi"]
RULES = ("taking sides in Pakistani or Indian party politics or elections; criticising Pakistan's army, courts or "
         "state institutions; mocking or judging any religion, sect or revered religious figure; hate against any "
         "nation, ethnic group or religion; graphic violence or gore; rumours about a person's private life, body or "
         "health; leaked private photos or videos; claims no reliable source reports")
# The first real video (Riyadh airport attacks, 21-oct-2026) got a runway between
# snowy mountains: the pick matched "runway" and not the place.
FOOTAGE_RULE = ("This is a news explainer: modern footage is right, and it must look like the place the line is "
                "about (desert cities for the Gulf, never snow or green hills for a desert country). Never dead "
                "bodies, blood or people being hurt, never a recognisable person the line does not name, never "
                "burning flags or religious symbols. ")
FOLLOW = {"urdu": "Duniya ki har bari khabar, asaan zaban mein: subscribe karein 🔔",
          "english": "The world's biggest stories, explained simply: subscribe 🔔"}
CHECK_MORE = ("a claim the facts mark REPORTED or ALLEGED told as confirmed; an expert's prediction told as fact; "
              "criticism of Pakistan's army, courts or state institutions.")


# ------------------------------------------------------------------ what is hot

def _search(query, date="week", limit=8):
    import channel_tools
    out = []
    for duration in ("medium", "long"):
        try:
            out += channel_tools.search(query, cc=False, duration=duration, date=date, sort="views", limit=limit)
        except Exception:  # noqa: BLE001 — a hint, never needed
            pass
    return out


def _rows(videos, limit):
    seen, rows = set(), []
    for v in sorted(videos, key=lambda v: v.get("views") or 0, reverse=True):
        if v["id"] in seen or not v.get("views") or (v.get("seconds") or 0) < 240:
            continue
        seen.add(v["id"])
        rows.append(v)
    return rows[:limit]


def rising(limit=25):
    """This week's most viewed explainers, as "title (views, channel)"."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = [v for got in pool.map(_search, NICHE_QUERIES) for v in got]
    return [f"{v['title'][:90]} ({v['views']:,} views, {v['channel'][:30]})" for v in _rows(found, limit)]


def rival_uploads(per=4):
    """The newest uploads of each rival with their views, newest first."""
    import channel_tools

    def one(item):
        name, url = item
        try:
            return [(name, v) for v in channel_tools.channel_videos(url, per)]
        except Exception:  # noqa: BLE001 — a channel renamed or gone; the others still count
            return []
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [r for got in pool.map(one, RIVALS.items()) for r in got]
    return [f"{name}: {v['title'][:90]} ({v['views']:,} views)" for name, v in rows if v.get("views")]


def suggestions(query, limit=10):
    """What people type into YouTube search, starting with ``query``."""
    try:
        r = httpx.get("https://suggestqueries.google.com/complete/search",
                      params={"client": "firefox", "ds": "yt", "hl": "en", "q": query[:100]}, timeout=10)
        data = r.json()
        return [s for s in data[1] if isinstance(s, str)][:limit]
    except Exception:  # noqa: BLE001 — keywords are a bonus
        return []


SEEDS_PROMPT = """Topic of a YouTube video: {topic}
Write the 3 short searches (2 to 4 words, lowercase, English or Hinglish) people in Pakistan and India type into
YouTube to find a video about it, the most typed first. One per line, nothing else."""


def seeds(topic, client=None):
    """Searches to ask YouTube's suggestions for. Guessed from the topic's
    capitalised words they were junk on the first run (21-oct-2026: "Solved"
    gave "solved past paper", "AI's" gave "ai's got talent"), so a cheap model
    call writes what people type."""
    if client is None:
        return [" ".join(topic.split()[:3])]
    try:
        r = client.models.generate_content(model=kit.text_model(), contents=SEEDS_PROMPT.format(topic=topic))
        lines = [re.sub(r"^[\W\d]+", "", x).strip().lower() for x in (r.text or "").splitlines()]
        out = [x[:60] for x in lines if 2 <= len(x.split()) <= 5][:3]
    except Exception:  # noqa: BLE001
        out = []
    return out or [" ".join(topic.split()[:3])]


def keywords(topic, client=None, limit=12):
    """[the seeds, then YouTube's suggestions for them], deduplicated."""
    base = seeds(topic, client)
    with ThreadPoolExecutor(max_workers=3) as pool:
        got = base + [s for found in pool.map(suggestions, base) for s in found]
    out = []
    for s in got:
        if s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return out[:limit]


# ------------------------------------------------------------------ planning

IDEAS_PROMPT = """Today is {today}. Plan the next {count} long YouTube videos ({minutes}-minute explainers narrated in
{lang}) for a channel that explains what everyone is talking about, for Pakistani and Indian viewers.
Use Google Search for the biggest stories of the last 7 days in the world, Pakistan, India and the Gulf.
What the biggest explainer channels uploaded last (with their views so far; a big number on a new upload means
the topic is hot right now):
{rivals}
This week's most viewed explainers:
{rising}
Pick topics that are hot THIS WEEK, that people are searching for, that reliable sources cover well, and that both
Pakistani and Indian viewers (or the whole world) care about: wars and geopolitics explained without taking
sides, the Gulf and the Middle East, AI and technology, big money, business and scams (proven ones), disasters,
mysteries and true stories, a famous person's rise or fall, how something everyone uses really works.
At least half the ideas must be about the same news as a rival upload or a most viewed explainer above with a
big view count, told from our own angle; the rest are Google's biggest stories of the week. Skip slow evergreen
topics (nature, science curiosities, social issues) unless they are in the news this week.
Our own angle on a hot topic is better than a topic nobody searches. Write each idea in ENGLISH and make it
specific: name the event, country, company or person and what happened, the way top explainers title them
("Why Houthis attacked Saudi Arabia: the full story", "How Starlink works and why India said no"). Never a
vague theme ("AI ka kala sach", "the dark side of social media"): a viewer must know which news it is.
{owner}Never: {rules}.
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "topic: ", at most 100 characters. Nothing else."""


def channel_ideas(client, count=2, avoid=(), best=(), worst=(), notes="", lang="urdu", minutes=10, requests=()):
    import cricket_shorts as cs
    import engage
    import trends
    learn = trends.searches_hint() + engage.request_hint(requests)
    if best:
        learn += "These did BEST on our channel, make more like them:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    owner = f"The channel owner also likes: {notes}\n" if (notes or "").strip() else ""
    with ThreadPoolExecutor(max_workers=2) as pool:
        up, hot = pool.submit(rival_uploads), pool.submit(rising)
        up, hot = up.result(), hot.result()
    text, _ = cs.grounded(client, IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=count + 2, minutes=minutes,
        lang="Roman Urdu" if lang != "english" else "English",
        rivals="\n".join(up[:50]) or "(not reachable now)", rising="\n".join(hot) or "(not reachable now)",
        owner=owner, rules=RULES, learn=learn, avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    now = time.time()
    ideas = [dict(i, at=now) for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen]
    return ideas[:count + 2]


def fresh(ideas, now=None):
    """Ideas planned within IDEA_HOURS; older news (or a history idea from
    before the switch, which has no time) is dropped. The owner's own ideas
    (Up next) always stay."""
    now = now or time.time()
    return [i for i in ideas or [] if i.get("owner") or now - (i.get("at") or 0) < IDEA_HOURS * 3600]


# ------------------------------------------------------------------ research

FACTS_PROMPT = """Today is {today}. Research this topic for a {minutes}-minute YouTube explainer: {topic}
Use Google Search and reliable sources (Reuters, AP, BBC, Al Jazeera, Dawn, The Hindu, official statements,
experts). Write a detailed, dated account: what happened most recently and what started it; the background that
explains it; who is involved and what each side says; the key numbers; why it matters to people in Pakistan and
India; what experts say may happen next (as their opinion, named). Label every claim CONFIRMED, REPORTED,
ALLEGED or OPINION. Be thorough: about {fact_words} words, enough for every chapter of the video.
If fewer than three reliable sources cover it, answer only "NOT FOUND"."""

EXTRA_PROMPT = """Today is {today}. For a YouTube explainer about: {topic}
Use Google Search. List 8 to 12 surprising, well sourced facts, numbers and short quotes (with who said them and
when) that make viewers say "I never knew that": the detail most coverage skipped, a number made real, a
little-known part of the background. One per line, each with its source's name."""

STUDY_PROMPT = """These are the captions of the most viewed YouTube videos about: {topic}
Describe them for a writer who will make an ORIGINAL video on the same topic. Write in English, in your own words,
and quote nothing. Max 250 words:
- the questions they answer, in the order they answer them;
- how they open (describe the hook, do not quote it) and what they promise;
- the facts, numbers or reveals they lean on most;
- what they leave out, get wrong or tell from one side only (our chance to be better).

{videos}"""


def top_videos(queries, limit=STUDY_VIDEOS):
    """The most viewed long videos for the first of ``queries`` that finds
    any. A whole Hinglish topic sentence found nothing on the first real run
    (21-oct-2026); the short phrases people type do."""
    for q in queries:
        found = _search(q, date="month", limit=6) or _search(q, date="any", limit=6)
        rows = _rows(found, limit)
        if rows:
            return rows
    return []


def study(client, topic, log=print):
    """{"titles": [...], "notes": str, "texts": [caption text]} of the most
    viewed videos on the topic. Never raises: the video is made without it."""
    import youtube_captions
    try:
        vids = top_videos(seeds(topic, client) + [topic])
    except Exception:  # noqa: BLE001
        vids = []

    def caps(v):
        try:
            t = youtube_captions.fetch(v["url"], max_seconds=1800)
        except Exception:  # noqa: BLE001
            t = None
        return v, ((t or {}).get("text") or "")[:20000]
    with ThreadPoolExecutor(max_workers=3) as pool:
        got = list(pool.map(caps, vids))
    titles = [f"{v['title'][:100]} ({v['views']:,} views, {int(v.get('seconds') or 0) // 60} min)" for v, _t in got]
    texts = [t for _v, t in got if t]
    notes = ""
    if texts:
        try:
            r = client.models.generate_content(model=kit.text_model(), contents=STUDY_PROMPT.format(
                topic=topic, videos="\n\n".join(f"VIDEO: {v['title']}\n{t}" for v, t in got if t)))
            notes = (r.text or "").strip()
        except Exception as e:  # noqa: BLE001
            log(f"   ℹ️ Could not study the top videos ({type(e).__name__}).")
    log(f"   🔎 Studied {len(texts)} of the {len(vids)} most viewed videos on the topic.")
    return {"titles": titles, "notes": notes, "texts": texts}


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def copied_runs(text, others, n=COPY_RUN):
    """Runs of ``n`` words our script shares with any of ``others`` (their
    captions in Latin letters; Devanagari or Urdu script never matches)."""
    mine = _words(text)
    grams = {tuple(mine[i:i + n]) for i in range(len(mine) - n + 1)}
    hits = []
    for other in others or []:
        w = _words(other)
        for i in range(len(w) - n + 1):
            g = tuple(w[i:i + n])
            if g in grams:
                hits.append(" ".join(g))
    return sorted(set(hits))


# ------------------------------------------------------------------ the script

SCRIPT_PROMPT = """You write the full script of a {minutes}-minute YouTube explainer for the channel {handle}.
Topic: {topic}
Audience: Pakistani and Indian viewers who want to understand what everyone is talking about. Every spoken line,
chapter title, label and the question are in {lang_rule}.
Use ONLY the facts below; never invent a date, number, name or quote. Say "reports ke mutabiq" for what is
REPORTED and "ilzaam hai" for what is ALLEGED, give each side's view, and tell experts' predictions as opinions.
{fixes}
FACTS:
{facts}

MORE FACTS:
{extra}

WHAT THE MOST VIEWED VIDEOS ON THIS TOPIC COVER (a study of them: learn what viewers want and cover what they
missed; never copy their wording or the order of their sentences):
{study}

THEIR TITLES:
{rival_titles}

WHAT PEOPLE TYPE INTO YOUTUBE SEARCH ABOUT IT:
{keywords}

Write about {words} spoken words in total: this sets the video's length, so do not stop short.
Hold attention the way the best explainers do:
- the first 15 seconds: the most surprising fact or the stakes, then the question this video answers and what the
  viewer will know by the end; never "hello friends", never a channel intro;
- every chapter opens with a question the viewer wants answered and ends on a reason to keep watching;
- numbers made real (compared with things people know), short sentences, one idea per scene, talk to the viewer;
- around the middle, one line asks viewers to write their view in the comments;
- the outro sums up in three lines, says what to watch for next, and asks viewers to subscribe.
Return:
- allowed: false if the topic can only be told with {rules}. reason: why, or "".
- sacred: true if the story involves {sacred}.
- title: max 70 characters. Start with the phrase people search for (from the list above when one fits), then the
  curiosity: a question or a reveal. English or Hinglish, the way the top titles above are written. True, no
  clickbait lies, no emoji, at most one word in capitals.
- thumb_text: 2 to 4 words, big and punchy, the emotion or the stakes, not the title repeated.
- thumb_picture: English, one dramatic picture for the thumbnail (place, objects, map, light; no text).
- summary: 2 or 3 sentences for the top of the description, the main search phrase in the first sentence.
- hook: 2 or 3 scenes, the first 30-45 seconds, as above.
- chapters: {chapters} chapters in order, each with a title (max 40 characters) and about {scenes} scenes.
- each scene: line = what the narrator says, one paragraph of 35-70 words, simple and spoken;
  picture = English, what the screen shows: a concrete place, map, building, object, a crowd or scene seen from
  far, or a leader the line names;
  wiki = the exact English Wikipedia article title whose pictures fit this scene ("Houthi movement", "Strait of
  Hormuz", "Starlink"), or "";
  label = an on-screen label of at most 32 characters: a date, place, name or number, or "".
- outro: one paragraph, as above.
- question: max 90 characters, asks viewers' opinion in the comments.
- tags: 10 to 15 YouTube search tags: the search phrases above that fit, names, places, "explained in hindi",
  "urdu".
{no_people} {honour}
Never mock or judge any religion, sect, nation or people; never take sides in Pakistani or Indian party politics;
never criticise Pakistan's army, courts or state institutions; no graphic violence. Spoken lines are read aloud by
a voice: no Roman numerals, numbers as digits."""
