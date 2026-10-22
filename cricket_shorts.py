"""Cricket Shorts with no match footage (CONTENT_GENRE=cricket).

Broadcast footage is the most policed content on YouTube (JioStar, PTV/Myco,
Walee and Sony enforce every season; research of 8-oct-2026), while scores
and match facts belong to no one. So nothing from a broadcast is shown: the
picture is ours (animated badges, score cards that count up, fact cards,
drifting light on the channel colour), the voice is Gemini's, and the words
come from Google Search grounding.

Two kinds (CRICKET_MODE):
- ``match``: the user names a match OR pastes a link to a match video.
  Gemini watches a YouTube link itself (no download; a 1.5 min clip took
  17 s and ~9k tokens at low resolution, 8-oct-2026) to tell which match it
  is and what happened; Google Search then confirms the scores. Videos over
  WATCH_MAX_MINUTES are read from their title and description instead.
- ``topic``: anything else cricket (a rule explained, a player's stats,
  records, history, "did you know"): researched with Google Search, told as
  4-6 numbered fact cards.

No team or tournament logos: names and colours only. Player photos only
from Wikipedia's free-licence lead photo (player_photo.py, credited in the
description, CRICKET_PHOTOS=0 turns them off), shown as they are: never
edited, never put next to a product, never AI-made (the personality-rights
orders for Gavaskar and Yuvraj, 2025-26, were about misuse of that kind).

Env: CRICKET_MATCH (the match, link or topic typed), CRICKET_MODE,
BG_MUSIC (1: a bed from music/cricket/, made by music_beds.py when empty,
else the music folder), CRICKET_VOICE, CRICKET_PHOTOS.
"""
import os
import re
from typing import List

from pydantic import BaseModel

import script_craft as craft
import short_kit as kit
import framed_layout as fl

VOICE_STYLE = "like an excited Pakistani cricket commentator, natural Urdu accent, fast and energetic"
GAP = 0.25          # between voice lines
LEAD = 0.15         # before the first line (was 0.5: half a second of silence on the frame that decides the swipe)
MAX_BEATS = 8           # ~30 s: the Shorts that broke out in this niche run 14-35 s (research 22-oct-2026)
WATCH_MAX_MINUTES = 45


class Team(BaseModel):
    name: str
    short: str
    score: str
    overs: str
    color: str


class Star(BaseModel):
    name: str
    team: str
    figures: str
    note: str


class Moment(BaseModel):
    label: str
    text: str


class Beat(BaseModel):
    scene: str
    ref: int
    line: str


class Story(BaseModel):
    found: bool
    title: str
    match_line: str
    result_line: str
    winner: int
    teams: List[Team]
    stars: List[Star]
    moments: List[Moment]
    beats: List[Beat]
    question: str


WATCH_PROMPT = """Watch this cricket video and answer briefly in plain text:
1. Which match is it: teams, tournament, stage or match number, venue and date if shown.
2. The final scores, read from the on-screen scoreboards if shown.
3. Up to 6 key moments in order: what happened, who, the over if shown, and a short
   quote of what the commentators said.
4. Anything funny, unusual or record-breaking.
If it is not a cricket match, say NOT CRICKET."""

FACTS_PROMPT = """Today is {today}. Find the facts of this cricket match: {match}
{notes}Use Google Search; a match dated before today has been played. Report only what sources state: tournament and stage, venue,
date, both teams' final scores with overs, the result and margin, the player of the
match, the top 3 performers with exact figures (runs and balls, or wickets-runs), and
4 key moments (with the over when known). If the match has not been played, is
ambiguous, or you cannot find it, say NOT FOUND and why."""

STORY_PROMPT = """You make a 30-35 second animated YouTube Short about a cricket match for
Pakistani and Indian fans, voiced by the channel {handle}. Use ONLY the facts below:
never invent a score, figure, over or name. If the facts say NOT FOUND or do not
describe a finished match, return found=false and empty lists.

Facts:
{facts}

Return:
- found: true when the facts describe this finished match.
- title: max 45 characters, Roman Urdu hook for the top of the screen (no emoji).
- match_line: "Tournament stage · Venue · 28 Sep 2025" style, max 48 characters.
- result_line: Roman Urdu, max 40 characters ("India 5 wicket se jeet gaya").
- winner: 0 or 1 (index in teams), -1 for a tie or no result.
- teams: exactly 2, in batting order: name (country/franchise), short (2-4 capital
  letters), score ("146" or "150/5"), overs ("19.1"), color (the team's usual kit
  colour as #RRGGBB, readable on dark backgrounds).
- stars: the 1 to 2 best performers: name, team (short), figures ("69* (53)" or
  "4/30"), note (Roman Urdu, max 40 characters).
- moments: 1 to 3 turning points: label (max 14 characters, "OVER 17" or "POWERPLAY"),
  text (Roman Urdu, max 70 characters).
- beats: the voice-over in order, 5 to {max_beats} lines. Each has scene (intro,
  scores, star, moment or result), ref (index into stars or moments for those scenes,
  else 0) and line: Roman Urdu commentary in Latin letters, 7 to 13 words, excited like
  a TV commentator, every number exactly as in the facts. Order: 1 intro, 1 scores,
  one per star, one per moment, 1 result. The result line ends with the question.
  The intro line is the HOOK, not a welcome: it opens on the most dramatic fact of the
  match ("Sirf 3 gend mein 14 run chahiye the, aur phir..."). Never a greeting, never
  the channel's name, never "dosto" or "swagat": viewers swipe in the first second.
- question: a cheeky question for the comments, Roman Urdu, max 70 characters,
  ending with "comment mein batao" or similar.
Roman Urdu always in Latin letters, never Devanagari or Arabic script. No swear words."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is an animated cricket match summary "
               "(scores, stars, key moments, result) voiced by the channel, with no match "
               "footage. Ignore the comedy phrases and hashtags above: use cricket searches "
               "instead (the teams, tournament, players, 'match summary', 'scorecard', "
               "'cricket news'). Player and team names are welcome in every field; creator is \"\".")


def is_link(text):
    return bool(re.match(r"https?://\S+$", (text or "").strip()))


def watch_link(client, url):
    """(what to search for, notes) from a pasted match video link."""
    from google.genai import types
    import section_fetch
    try:
        info = section_fetch.video_info(url) or {}
    except Exception as e:  # noqa: BLE001 — Gemini can still watch the link itself
        print(f"   ℹ️ Could not read the video's details ({type(e).__name__}); watching it directly.")
        info = {}
    title = info.get("title") or ""
    about = (f"Video title: {title}\nDescription: {(info.get('description') or '')[:1200]}"
             if title else f"Video link: {url}")
    minutes = float(info.get("duration") or 0) / 60
    if title and ("youtu" not in url or minutes > WATCH_MAX_MINUTES):
        print(f"   ℹ️ Reading the video's title and description ({minutes:.0f} min video).")
        return title, about
    if "youtu" not in url:
        raise RuntimeError("Could not read this link. Paste a YouTube link, or type the match.")
    print(f"👀 Watching the video{f' ({minutes:.0f} min)' if minutes else ''} to see which match it is...")
    try:
        r = client.models.generate_content(
            model=kit.text_model(),
            contents=types.Content(parts=[types.Part(file_data=types.FileData(file_uri=url)),
                                          types.Part(text=WATCH_PROMPT)]),
            config=types.GenerateContentConfig(
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW))
        notes = (r.text or "").strip()
    except Exception as e:  # noqa: BLE001 — fall back to what the page says
        if not title:
            raise RuntimeError("Could not watch or read this video. Type the match instead "
                               "(teams, tournament and date).") from e
        print(f"   ℹ️ Watching failed ({type(e).__name__}); using the title and description.")
        return title, about
    if "NOT CRICKET" in notes[:100].upper():
        raise RuntimeError("This video does not look like a cricket match.")
    return title or notes.splitlines()[0][:120], f"{about}\nNotes from watching it:\n{notes}"


def grounded(client, prompt):
    """(answer text, source urls) from one Google-Search-grounded call."""
    from google.genai import types
    r = client.models.generate_content(
        model=kit.text_model(), contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    sources = [c.web.uri for c in (getattr(gm, "grounding_chunks", None) or []) if getattr(c, "web", None)]
    return (r.text or "").strip(), sources


def find_story(client, match, handle, notes=""):
    """(Story, facts, [source urls]) for what the user typed or pasted, or raises."""
    import time
    note = (f"The user pasted a video of this match. What we know from it:\n{notes}\n"
            if notes else "")
    # Twice at most: once the model answered NOT FOUND for a 2025 match while
    # saying the date was 2026 (8-oct-2026); the same question then worked.
    for attempt in range(2):
        facts, sources = grounded(client, FACTS_PROMPT.format(match=match, notes=note,
                                                              today=time.strftime("%d %B %Y")))
        if facts and "NOT FOUND" not in facts[:200].upper():
            break
    if not facts or "NOT FOUND" in facts[:200].upper():
        raise RuntimeError(f"Could not find this match ({facts[:160] or 'no answer'}). "
                           "Write the teams, tournament and date, e.g. 'Pakistan vs India, Asia Cup 2025 final'.")
    story = kit.ask_json(client, Story, STORY_PROMPT.format(handle=handle, facts=facts,
                                                            max_beats=MAX_BEATS) + "\n\n" + craft.short_rules(craft.FIXED_ORDER),
                         model=craft.writer_model())
    if not story.found or len(story.teams) != 2 or not story.beats:
        raise RuntimeError("The search did not return a finished match with both scores. "
                           "Write the teams, tournament and date.")
    story.beats = story.beats[:MAX_BEATS]
    craft.polish(client, story, facts, what="cricket match result YouTube Short", fields=("beats", "question"))
    return story, facts, sources


# ---------------------------------------------------------------- topics

class Fact(BaseModel):
    headline: str
    stat: str
    detail: str
    line: str


class TopicStory(BaseModel):
    found: bool
    title: str
    kicker: str
    hook_line: str
    facts: List[Fact]
    question: str
    player: str


TOPIC_FACTS_PROMPT = """Today is {today}. Research this cricket topic for a short video: {topic}
Use Google Search. Give 8-10 of the most interesting, accurate facts with exact numbers
and dates; stats must be current as of today. For a rule, explain the actual Law (its
number), what the umpire checks and one simple example. For a player, career numbers by
format and the records that stand out. Say NOT FOUND if nothing reliable comes up."""

# The rule-steps line is there because "LBW rule explained simply" first came
# back as LBW trivia (Sachin's 63, Kumble's 156) with no rule in it (8-oct-2026).
TOPIC_STORY_PROMPT = """You make a 25-30 second YouTube Short for Pakistani and Indian cricket
fans, voiced by the channel {handle}, about: {topic}
Use ONLY the facts below; never invent a number, date or name. If they say NOT FOUND,
return found=false and empty lists.

Facts:
{facts}

Return:
- found
- title: max 45 characters, Roman Urdu hook for the top of the screen, no emoji.
- kicker: 1-3 English words for a small label: "CRICKET RULES", "PLAYER STATS",
  "RECORDS", "DID YOU KNOW", "HISTORY".
- hook_line: the first voice line, Roman Urdu, 8-14 words, a surprising fact or a
  question that stops the scroll.
- facts: 3 to 4 (5 only for a rule). When the topic asks how a RULE works, the facts ARE the rule, step
  by step in order (each condition the umpire checks, then a simple example), and at
  most the last one may be trivia. Otherwise the most surprising first (or a
  countdown). Each: headline (max 30
  characters, Roman Urdu or the English cricket term), stat (the number or short value
  to show big, max 10 characters, "" when there is none), detail (Roman Urdu, max 80
  characters, what the number means), line (the voice line, Roman Urdu, 8-14 words,
  excited, numbers exactly as in the facts).
- question: a cheeky question for the comments, Roman Urdu, max 70 characters, ending
  with "comment mein batao" or similar.
- player: the full name of the ONE player this Short is mainly about, as his
  Wikipedia article is titled ("Babar Azam", "Jasprit Bumrah"), or "" when it is not
  about one player.
Everyday spoken Roman Urdu in Latin letters, the way fans talk: never formal words like
"mutawatir", "wahid", "tareen" (say "lagatar", "akela", "sabse"). Never Devanagari or
Arabic script. No swear words."""

TOPIC_SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a cricket facts Short ({kind}) "
                     "about: {topic}, with animated fact cards and the channel's voice. Ignore "
                     "the comedy phrases and hashtags above and use cricket searches instead (the "
                     "players, teams, the rule or record, 'cricket facts', 'cricket stats'). Player "
                     "and team names are welcome everywhere, and the title opens on the main player's or team's "
                     "name when there is one (people search names); creator is \"\".")


def remix_note(topic):
    import viral_remix
    return viral_remix.note_for(topic)


def remix_guard(topic, story):
    import viral_remix
    viral_remix.guard(topic, " ".join(t for _p, t in craft.spoken(story)))


def find_topic(client, topic, handle):
    import time
    for attempt in range(2):
        facts, sources = grounded(client, TOPIC_FACTS_PROMPT.format(topic=topic,
                                                                    today=time.strftime("%d %B %Y")))
        if facts and "NOT FOUND" not in facts[:200].upper():
            break
    if not facts or "NOT FOUND" in facts[:200].upper():
        raise RuntimeError(f"Nothing reliable found on this topic ({facts[:160] or 'no answer'}). "
                           "Try it more specific, e.g. 'Babar Azam ODI stats' or 'LBW rule'.")
    story = kit.ask_json(client, TopicStory, TOPIC_STORY_PROMPT.format(handle=handle, topic=topic,
                                                                       facts=facts) + remix_note(topic)
                         + "\n\n" + craft.short_rules(), model=craft.writer_model())
    if not story.found or len(story.facts) < 2:
        raise RuntimeError("The research came back too thin for a video; try a more specific topic.")
    story.facts = story.facts[:6]
    craft.polish(client, story, facts, what="cricket facts YouTube Short")
    remix_guard(topic, story)
    return story, facts, sources


IDEAS_PROMPT = """Today is {today}. Suggest 8 YouTube Short ideas for a Pakistani cricket
channel this week, using Google Search for what is happening now. Mix: 3 matches played
in the last 7 days (exact "Team vs Team, tournament, stage" so they can be looked up),
and 5 topics (a player's stats in form right now, a record, a rule people argue about,
history on this date, a fun fact). One per line, each starting with "match: " or
"topic: ". Nothing else."""


def ideas(client):
    """[{"kind": "match"|"topic", "text"}] for the dashboard's idea chips."""
    import time
    text, _ = grounded(client, IDEAS_PROMPT.format(today=time.strftime("%d %B %Y")))
    return _idea_lines(text)[:10]


def _idea_lines(text):
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"\W*(match|topic|versus)\s*:\s*(.+)", line.strip(), re.I)
        if m:
            out.append({"kind": m.group(1).lower(), "text": _txt(m.group(2).strip(" *"), 120)})
    return out


CHANNEL_IDEAS_PROMPT = """Today is {today}. Plan the next {count} YouTube Shorts of a cricket facts
and updates channel for Pakistani and Indian fans. Use Google Search for what is
happening in cricket right now.
Mix: about a quarter are matches finished in the last 3 days (exact "Team vs Team,
tournament, stage" so they can be looked up); one or two are "who is better" fights
fans argue about, two players of the same role by numbers ("Babar Azam vs Virat Kohli
ODI", "Shaheen Afridi vs Jasprit Bumrah T20I"); the rest are catchy facts that promise
a surprise: one star player's stats or records (name the player), a crazy record, a
"did you know", a rule people argue about, history on this date.
Most fact ideas should be about ONE named player people love or argue about.
If a famous Pakistani or Indian cricketer (current or legend) was born on today's day and month, make
one idea about them, written like "Shoaib Akhtar's birthday today: his fastest records" (check the date
with Google Search; no birthday idea when nobody well known was born today).
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "match: ", "versus: " or "topic: ". Nothing else."""


def channel_ideas(client, count=8, avoid=(), best=(), worst=(), requests=()):
    """Today's ideas for the cricket channel (my_channels.py), steered by what
    did best and worst there and what viewers asked for."""
    import time
    import engage
    import trends
    learn = trends.searches_hint() + trends.wiki_hint() + trends.hint("cricket") + engage.request_hint(requests)
    if best:
        learn += "These did BEST on the channel, make more like them:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    text, _ = grounded(client, CHANNEL_IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=count, learn=learn,
        avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    ideas = [i for i in _idea_lines(text) if i["text"].lower() not in seen]
    return [i for i in ideas if birthday_ok(i["text"])][:count + 2]


BIRTHDAY = re.compile(r"^(.+?)['\u2019]s\s+(?:\d+\w*\s+)?birthday", re.I)


def birthday_ok(text, now=None, born_fn=None):
    """A "<player>'s birthday" idea only when Wikipedia says they were born
    on today's day and month. On its first real run (15-oct-2026) both of
    its birthdays were right (Babar Azam, Umar Gul), but a wrong date would
    be a whole Short about the wrong day, and nothing else checks it."""
    m = BIRTHDAY.search(text)
    if not m:
        return True
    import datetime as _dt
    import player_photo
    d = now or _dt.date.today()
    try:
        got = (born_fn or player_photo.born)(m.group(1).strip())
    except Exception:  # noqa: BLE001 — unchecked is dropped, never posted
        got = None
    return bool(got) and (got[0], got[1]) == (d.day, d.month)


# ---------------------------------------------------------------- drawing

STYLES = [
    kit.style("CkTitle", "Montserrat ExtraBold", 70, outline=0, shadow=3),
    kit.style("CkSmall", "Montserrat ExtraBold", 34, "#FFFFFF"),
    kit.style("CkPill", "Montserrat ExtraBold", 36, "#14142B", spacing=2),
    kit.style("CkBadge", "Anton", 92, "#FFFFFF", outline=0, shadow=4),
    kit.style("CkVs", "Anton", 150, fl.GOLD, outline=6, shadow=5),
    kit.style("CkName", "Montserrat ExtraBold", 44, "#FFFFFF", outline=3),
    kit.style("CkScore", "Anton", 120, "#FFFFFF", outline=0, shadow=3, align=6),
    kit.style("CkTeam", "Montserrat ExtraBold", 50, "#FFFFFF", align=4),
    kit.style("CkOvers", "Montserrat ExtraBold", 32, "#D8D8E8", align=6),
    kit.style("CkBig", "Anton", 160, fl.GOLD, outline=6, shadow=5),
    kit.style("CkStar", "Montserrat ExtraBold", 74, "#FFFFFF", outline=4, shadow=3),
    kit.style("CkText", "Montserrat ExtraBold", 60, "#FFFFFF", outline=5, shadow=3),
    kit.style("CkNote", "Montserrat ExtraBold", 42, "#FFFFFF", outline=3),
    kit.style("CkBadgeDark", "Anton", 70, "#14142B"),
    kit.style("CkBigC", "Anton", 170, fl.GOLD, outline=6, shadow=5, align=5),
]
CX = kit.OUT_W // 2


def _c(hex_color):
    return fl._ass_colour(hex_color if re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_color or "") else "#8B5CF6")


def _txt(text, limit):
    """On-screen text the fonts can draw: Montserrat here has no "·" or dashes."""
    text = re.sub(r"\s*[·•–—]\s*", " | ", text or "")
    return fl.clean_title(text)[:limit]


def _shape(layer, t0, t1, drawing, colour, at=None, move=None, alpha="00", extra="", an=7):
    """An ASS drawing placed at ``at`` (x, y) or moved along ``move`` (x1,y1,x2,y2,t1,t2)."""
    where = rf"\move({','.join(str(v) for v in move)})" if move else rf"\pos({at[0]},{at[1]})"
    return kit.dialogue(layer, t0, t1, "Shape",
                        rf"{{\an{an}{where}\1c{colour}\1a&H{alpha}&\bord0\shad0{extra}\p1}}"
                        rf"{drawing}{{\p0}}")


def _runs(score):
    m = re.match(r"\s*(\d+)", score or "")
    return int(m.group(1)) if m else None


def _count_up(t0, t1, x, y, score, style_name="CkScore", steps=12, secs=0.9):
    """The score climbs from 0 to its value, then holds."""
    runs = _runs(score)
    if runs is None:
        return [kit.dialogue(6, t0, t1, style_name, rf"{{\pos({x},{y})}}{score}")]
    tail = score.strip()[len(str(runs)):]
    ev = []
    for k in range(steps):
        a = t0 + secs * k / steps
        ev.append(kit.dialogue(6, a, a + secs / steps, style_name,
                               rf"{{\pos({x},{y})}}{round(runs * (k + 1) / (steps + 1))}"))
    ev.append(kit.dialogue(6, t0 + secs, t1, style_name,
                           rf"{{\pos({x},{y})\t(0,150,\fscx115\fscy115)\t(150,300,\fscx100\fscy100)}}"
                           rf"{runs}{tail}"))
    return ev


PILL_MAX = 1000


def _pill(t0, t1, y, text, colour=fl.GOLD, text_colour="#14142B", layer=3, fade_in=150):
    # A long match line made a bar wider than the screen (1202 px for 42
    # characters): the pill stops at PILL_MAX and the text shrinks to fit.
    need = 26 * len(text) + 110
    w, h = min(PILL_MAX, max(260, need)), 78
    size = rf"\fs{max(22, int(36 * PILL_MAX / need))}" if need > PILL_MAX else ""
    return [
        _shape(layer, t0, t1, fl._round_rect(w, h, h // 2), _c(colour), at=(CX - w // 2, y - h // 2),
               extra=rf"\fad({fade_in},150)"),
        kit.dialogue(layer + 1, t0, t1, "CkPill",
                     rf"{{\an5\pos({CX},{y})\1c{_c(text_colour)}{size}\fad({fade_in},150)}}{text}"),
    ]


def _name(name):
    """A player's full name, smaller when long ("Mohammad Imran Randhawa" was cut to 22)."""
    text = _txt(name, 34)
    return (rf"\fs{54 if len(text) <= 26 else 44}" if len(text) > 18 else ""), text


def scene_events(beat, t0, t1, story, with_photo=False):
    teams, ev = story.teams, []
    out = r"\fad(180,200)"
    if beat.scene == "intro":
        for k, (team, x, frm) in enumerate(((teams[0], 290, -300), (teams[1], 790, 1380))):
            ev.append(_shape(3, t0, t1, fl._circle(170), _c(team.color), move=(frm, 860, x, 860, 0, 350),
                             extra=out, an=5))
            ev.append(kit.dialogue(4, t0, t1, "CkBadge",
                                   rf"{{\an5\move({frm},860,{x},860,0,350){out}}}{_txt(team.short, 4).upper()}"))
            ev.append(kit.dialogue(4, t0 + 0.3, t1, "CkName", rf"{{\an5\pos({x},1100){out}}}{_txt(team.name, 16)}"))
        ev.append(kit.dialogue(5, t0 + 0.35, t1, "CkVs",
                               rf"{{\an5\pos({CX},860)\fscx300\fscy300\alpha&HFF&"
                               rf"\t(0,200,\fscx100\fscy100\alpha&H00&){out}}}VS"))
    elif beat.scene == "scores":
        for k, team in enumerate(teams):
            y = 700 + k * 290
            win = story.winner == k
            slide = (-1000, y, 80, y, k * 120, k * 120 + 320)
            ev.append(_shape(2, t0, t1, fl._round_rect(920, 240, 36), "&H2B140E&", move=slide,
                             alpha="50", extra=out))
            ev.append(_shape(3, t0, t1, fl._round_rect(26, 240, 13), _c(team.color), move=slide,
                             extra=out))
            ev.append(kit.dialogue(4, t0 + 0.2, t1, "CkTeam",
                                   rf"{{\pos(140,{y + 120}){out}}}{_txt(team.name, 14)}"))
            ev += _count_up(t0 + 0.45 + k * 0.25, t1, 960, y + 105, team.score)
            ev.append(kit.dialogue(4, t0 + 0.5, t1, "CkOvers",
                                   rf"{{\pos(960,{y + 190}){out}}}{team.overs} overs"))
            if win:
                ev += _pill(t0 + 1.2, t1, y - 10, "WINNER")
    elif beat.scene == "star" and story.stars and with_photo:
        # His round photo sits at y 815 (short_kit images); the text moves below it.
        star = story.stars[min(max(beat.ref, 0), len(story.stars) - 1)]
        ev += _pill(t0, t1, 600, "STAR OF THE MATCH" if beat.ref == 0 else "STAR PERFORMER")
        fs, name = _name(star.name)
        ev.append(kit.dialogue(4, t0 + 0.15, t1, "CkStar",
                               rf"{{\an5\pos({CX},1010){fs}\fscx80\fscy80\t(0,220,\fscx100\fscy100){out}}}"
                               rf"{name}"))
        ev.append(kit.dialogue(5, t0 + 0.4, t1, "CkBig",
                               rf"{{\an5\pos({CX},1170)\fs120\fscx250\fscy250\alpha&HFF&"
                               rf"\t(0,220,\fscx100\fscy100\alpha&H00&){out}}}{_txt(star.figures, 12)}"))
        ev.append(kit.dialogue(4, t0 + 0.7, t1, "CkNote", rf"{{\an5\pos({CX},1300){out}}}{_txt(star.note, 44)}"))
    elif beat.scene == "star" and story.stars:
        star = story.stars[min(max(beat.ref, 0), len(story.stars) - 1)]
        ev += _pill(t0, t1, 640, "STAR OF THE MATCH" if beat.ref == 0 else "STAR PERFORMER")
        fs, name = _name(star.name)
        ev.append(kit.dialogue(4, t0 + 0.15, t1, "CkStar",
                               rf"{{\an5\pos({CX},800){fs}\fscx80\fscy80\t(0,220,\fscx100\fscy100){out}}}"
                               rf"{name}"))
        ev.append(kit.dialogue(4, t0 + 0.2, t1, "CkSmall", rf"{{\an5\pos({CX},880){out}}}{_txt(star.team, 6)}"))
        ev.append(kit.dialogue(5, t0 + 0.4, t1, "CkBig",
                               rf"{{\an5\pos({CX},1040)\fscx250\fscy250\alpha&HFF&"
                               rf"\t(0,220,\fscx100\fscy100\alpha&H00&){out}}}{_txt(star.figures, 12)}"))
        ev.append(kit.dialogue(4, t0 + 0.7, t1, "CkNote", rf"{{\an5\pos({CX},1220){out}}}{_txt(star.note, 44)}"))
    elif beat.scene == "moment" and story.moments:
        mo = story.moments[min(max(beat.ref, 0), len(story.moments) - 1)]
        ev += _pill(t0, t1, 660, _txt(mo.label, 14).upper())
        ev.append(kit.dialogue(4, t0 + 0.2, t1, "CkText",
                               rf"{{\an5\pos({CX},940)\fad(200,200)\fscx90\fscy90"
                               rf"\t(0,250,\fscx100\fscy100)}}{_txt(mo.text, 80)}"))
        # A ball flies across, spinning.
        ev.append(_shape(5, t0 + 0.1, t0 + 1.1, fl._circle(34), "&H2020C8&",
                         move=(-80, 1160, 1160, 700), extra=r"\t(\frz-720)", an=5))
    elif beat.scene == "result":
        win = story.teams[story.winner].name if 0 <= story.winner < 2 else ""
        ev += _pill(t0, t1, 640, "RESULT")
        if win:
            ev.append(kit.dialogue(5, t0 + 0.2, t1, "CkBig",
                                   rf"{{\an5\pos({CX},820)\fscx40\fscy40\t(0,260,\fscx100\fscy100){out}}}"
                                   rf"{_txt(win, 12).upper()}"))
        ev.append(kit.dialogue(4, t0 + 0.4, t1, "CkText", rf"{{\an5\pos({CX},1000){out}}}{_txt(story.result_line, 44)}"))
        ev.append(kit.dialogue(4, t0 + 0.9, t1, "CkNote",
                               rf"{{\an5\pos({CX},1180)\1c{_c(fl.GOLD)}{out}}}{_txt(story.question, 72)}"))
    return ev


# Visible on frame 0 (no fade from nothing), still a small pop.
TITLE_POP = r"\fscx92\fscy92\t(0,180,\fscx104\fscy104)\t(180,300,\fscx100\fscy100)"


def frame_events(story, total, handle, title):
    """What stays up the whole time: handle, match line, title."""
    ev = []
    if handle:
        ev.append(kit.dialogue(1, 0, total, "CkSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{handle}"))
    ev += _pill(0, total, 190, _txt(story.match_line, 52), colour="#FFFFFF", fade_in=0)
    if title:
        ev.append(kit.dialogue(1, 0, total, "CkTitle", rf"{{\an5\pos({CX},380){TITLE_POP}}}{fl.clean_title(title)}"))
    return ev


SWIPE = 1100     # fact cards swipe in from this far right
SWIPE_MS = 300


def _swipe(x, y, delay=0):
    """\\move from off-screen right to (x, y): every part of a card arrives
    together, ``delay`` ms after the card starts."""
    return rf"\move({x + SWIPE},{y},{x},{y},{delay},{delay + SWIPE_MS})"


def _flash(t0):
    """A soft white flash as a new card swipes in: the cut reads as a transition."""
    return _shape(7, t0, t0 + 0.25, fl._round_rect(kit.OUT_W, kit.OUT_H, 0), "&HFFFFFF&",
                  at=(0, 0), alpha="C8", extra=r"\t(0,220,\1a&HFF&)")


def fact_events(k, n, fact, t0, t1, count=True):
    """One numbered fact card: badge, headline, big stat, what it means, progress.
    The whole card swipes in from the right with a flash, then fades out."""
    out = r"\fad(0,200)"
    ev = [
        _flash(t0),
        _shape(2, t0, t1, fl._round_rect(920, 680, 44), "&H2B140E&", alpha="40",
               move=(80 + SWIPE, 600, 80, 600, 0, SWIPE_MS), extra=out),
        _shape(3, t0, t1, fl._circle(64), _c(fl.GOLD), move=(CX - 64 + SWIPE, 536, CX - 64, 536, 0, SWIPE_MS),
               extra=out),
        kit.dialogue(4, t0, t1, "CkBadgeDark", rf"{{\an5{_swipe(CX, 600)}{out}}}{k}"),
        # Long headlines shrink instead of being cut ("...Sabse Ziada Centur", first render).
        kit.dialogue(4, t0, t1, "CkStar",
                     rf"{{\an5{_swipe(CX, 760, 60)}\fs{74 if len(fact.headline) <= 22 else 54}\fscx85\fscy85"
                     rf"\t(150,370,\fscx100\fscy100){out}}}{_txt(fact.headline, 44)}"),
        kit.dialogue(4, t0 + 0.6, t1, "CkNote", rf"{{\an5\pos({CX},1130)\fad(180,200)}}{_txt(fact.detail, 130)}"),
    ]
    if fact.stat.strip():
        if count and re.fullmatch(r"\d{1,6}", fact.stat.strip()):
            ev += _count_up(t0 + 0.35, t1, CX, 950, fact.stat.strip(), style_name="CkBigC")
        else:
            ev.append(kit.dialogue(5, t0 + 0.35, t1, "CkBigC",
                                   rf"{{\an5\pos({CX},950)\fscx250\fscy250\alpha&HFF&"
                                   rf"\t(0,220,\fscx100\fscy100\alpha&H00&){out}}}{_txt(fact.stat, 10)}"))
    for j in range(n):  # progress dots
        x = CX - (n - 1) * 22 + j * 44
        ev.append(_shape(4, t0, t1, fl._circle(9 if j == k - 1 else 6),
                         _c(fl.GOLD if j < k else "#FFFFFF"), at=(x, 1290), an=5,
                         alpha="00" if j < k else "80", extra=out))
    return ev


def topic_frame_events(story, total, handle):
    ev = []
    if handle:
        ev.append(kit.dialogue(1, 0, total, "CkSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{handle}"))
    ev += _pill(0, total, 190, _txt(story.kicker.upper(), 24), fade_in=0)
    ev.append(kit.dialogue(1, 0, total, "CkTitle", rf"{{\an5\pos({CX},380){TITLE_POP}}}{fl.clean_title(story.title)}"))
    return ev


def says(text, name):
    """True when a line names the player: any part of his name of 3+ letters ("Villiers", "Babar")."""
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in re.findall(r"[a-z]{3,}", (name or "").lower()))


def reveal_at(lines, windows, name, n_facts):
    """Index of the line where a hidden player is first named; the last fact when no line names him."""
    return next((k for k, _a, _b in windows if k and says(lines[k], name)), n_facts)


# Stadium pictures of other sports passed as "a stadium at night": a hockey
# arena under a World Cup line and an American-football ground under Afridi
# (15-oct-2026, Wikipedia pictures).
CRICKET_FOOTAGE = ("This is a cricket channel: only cricket grounds, cricket players, bats, balls, stumps and "
                   "cricket crowds; never another sport's ground, game or gear (football, baseball, ice hockey, "
                   "American football, basketball, tennis). ")


def _voice_timeline(client, lines, output_dir, stem, voice=None, style=None, broll_rule=None):
    """Voice every line; (windows [(k, start, end)], voices, caption lines, end).
    The background footage for the same lines is searched meanwhile (broll)."""
    import broll
    voice = voice or os.environ.get("CRICKET_VOICE") or "Fenrir"
    broll_rule = CRICKET_FOOTAGE if broll_rule is None else broll_rule
    broll.prefetch(output_dir, lines[0] if lines else "", [t for t in lines if (t or "").strip()], broll_rule, client)
    said = kit.voice_all(client, [{"text": t, "voice": voice, "style": style or VOICE_STYLE} for t in lines],
                           output_dir, stem)
    if not any(p for p, _ in said):
        raise RuntimeError("The AI voice failed for every line; try again in a minute.")
    t, windows, voices, caps = LEAD, [], [], []
    for k, (text, (path, secs)) in enumerate(zip(lines, said)):
        secs = secs or max(2.5, len(text.split()) / 2.8)  # a failed line still shows
        windows.append((k, t, t + secs + GAP))
        if path:
            voices.append((path, t))
        caps.append((text, t, t + secs, path))
        t += secs + GAP
    return windows, voices, caps, t + 0.6


def _bed(kind="cricket"):
    """A background track for the voice, or None (BG_MUSIC off)."""
    if os.environ.get("BG_MUSIC", "0") != "1":
        return None
    track = kit.music_track(kind)
    if not track:
        import music_beds
        music_beds.ensure(kind, 1)
        track = kit.music_track(kind)
    if not track:
        print("   ℹ️ Background music is on but none could be found or made: no music this time.")
    return track


def _photo(name, output_dir, kind="cricket"):
    """{"card", "avatar", "info"} for a player's (or, kind "person", anyone
    famous's) free photo, or None."""
    if not (name or "").strip() or os.environ.get("CRICKET_PHOTOS", "1") == "0":
        return None
    import player_photo
    got = player_photo.fetch(name.strip(), output_dir, kind=kind)
    if got:
        print(f"   🖼️ Photo of {got['info']['player']} ({got['info']['licence']}, Wikimedia Commons).")
    return got


def _search_hint(topic, suggest=None):
    """What people really type into YouTube about this topic (its autocomplete, free, no key) as a
    line for the SEO writer, or "". Shorts titles and tags were the model's guesses; the explainer
    channel already used these (trend_explainer.keywords). Names lead most topics, so the first two
    words, then the first four. Off with TRENDS=0 (tests) or SEARCH_HINT=0."""
    if os.environ.get("TRENDS", "1") == "0" or os.environ.get("SEARCH_HINT", "1") == "0":
        return ""
    if suggest is None:
        import trend_explainer
        suggest = trend_explainer.suggestions
    words = re.sub(r"'s\b|[^\w\s]", " ", (topic or "").lower()).split()
    seen, out = set(), []
    for q in (" ".join(words[:2]), " ".join(words[:4])):
        if len(q) < 4 or q in seen:
            continue
        seen.add(q)
        for s in suggest(q)[:8]:
            if s not in out:
                out.append(s)
    if not out:
        return ""
    return ("\nWHAT PEOPLE TYPE INTO YOUTUBE SEARCH about this (YouTube's own suggestions): " + "; ".join(out[:14])
            + ". Put the best fitting phrase in the title's first words and use others in the tags and the "
              "description, only where they are true for this video.")


def _stickers(clip, seconds):
    """Animated emoji (stickers.py, Noto, CC BY 4.0) on a few voice lines: one Gemini pick, code keeps
    them apart and off lines about a death, a tragedy, religion or an allegation. [] when off or on any
    failure."""
    import stickers
    if not stickers.available():
        return []
    segs = [s for s in ((clip.get("captions") or {}).get("segments") or []) if (s.get("text") or "").strip()]
    if not segs:
        return []
    try:
        picks = stickers.pick(kit.gemini(), [s["text"] for s in segs])
        return stickers.place(picks, [(s["start"], s["end"]) for s in segs], seconds=seconds)
    except Exception as e:  # noqa: BLE001 — a Short without stickers is still a Short
        print(f"   ℹ️ No stickers ({type(e).__name__}).")
        return []


def _finish(output_dir, stem, pipeline, cfg, events, colors, voices, sfx, body_end, clip, seo,
            images=(), photos=(), genre="cricket", after_seo=None, broll_rule=None):
    import broll
    if broll_rule is None:
        broll_rule = CRICKET_FOOTAGE if genre == "cricket" else ""
    import seo_copy
    outro_s = kit.outro_seconds(cfg)
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)
    track = _bed(genre)
    # Free stock footage behind the cards, one clip per voice line (broll.py);
    # without keys or results the gradient stays.
    bg, footage = broll.background_for(seo.get("source_title") or clip.get("video_title_for_youtube_short") or genre,
                                       clip["captions"]["segments"], total, output_dir, rule=broll_rule)
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    stuck = _stickers(clip, body_end)
    print(f"🎬 Rendering the {genre} short ({total:.0f}s"
          + (f", music: {os.path.basename(track)}" if track else "")
          + (f", stickers: {' '.join(s['name'] for s in stuck)}" if stuck else "") + ")...")
    kit.render(final, total, colors, ([] if bg else kit.ambient_events(total)) + events + card_ev, STYLES,
               voices=voices, sfx=sfx + card_sfx, bed=(track, body_end) if track else None, images=images,
               bg_video=bg, fast=bool(clip.get("captions")), stickers=stuck)
    clip.update({"end": round(total, 3), "seconds": round(total, 3), "file": final,
                 "background_music": os.path.basename(track) if track else None,
                 "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in footage]})
    hint = _search_hint(seo.get("source_title") or "")
    if hint and seo.get("context"):
        seo = {**seo, "context": seo["context"] + hint}
    kit.seo_or_fail([clip], clip["captions"], **seo)
    if after_seo:
        after_seo(clip)
    if footage:
        import credits
        import stock_media
        for field in ("seo_description", "video_description_for_instagram"):
            if clip.get(field):
                clip[field] = credits.insert(clip[field], stock_media.credit_line(footage))
    if stuck:
        import credits
        import stickers
        for field in ("seo_description", "video_description_for_instagram"):
            if clip.get(field):
                clip[field] = credits.insert(clip[field], stickers.CREDIT)
    if photos:
        # Free licences ask for credit: in the copy, never on screen.
        import credits
        import player_photo
        credit = "\n".join(player_photo.credit_line(p) for p in photos)
        clip["photo_credit"] = credit
        for field in ("seo_description", "video_description_for_instagram"):
            if clip.get(field):
                clip[field] = credits.insert(clip[field], credit)
    kit.finish(output_dir, stem, [clip], clip["captions"], pipeline, extra={"genre": genre})


def run_topic(topic, output_dir, pipeline):
    cfg = fl.settings()
    print(f"🏏 Cricket facts short: researching \"{topic}\"...")
    client = kit.gemini()
    story, facts, sources = find_topic(client, topic, cfg["handle"] or "this channel")
    print(f"   ✅ {story.kicker}: {len(story.facts)} facts ({len(sources)} sources)")
    stem = kit.neutral_stem("Cricket")
    photo = _photo(story.player, output_dir)
    lines = [story.hook_line] + [f.line for f in story.facts] + [story.question]
    print(f"🎙️ Voicing {len(lines)} lines...")
    windows, voices, caps, body_end = _voice_timeline(client, lines, output_dir, stem)
    events, sfx, n = topic_frame_events(story, body_end, cfg["handle"]), [], len(story.facts)
    images = []
    name = photo["info"]["player"] if photo else ""
    # A hook that asks who ("Fastest ODI century kisne banayi?") keeps him hidden until a line names him.
    hidden = bool(photo) and not says(story.hook_line, name) and not says(story.title, name)
    reveal = reveal_at(lines, windows, name, n) if hidden else 0
    reveal_t = next((a for k, a, _b in windows if k == reveal), body_end)
    for k, a, b in windows:
        sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
        if hidden and k == reveal and k:
            events += _pill(a, min(b, a + 2.5), 1385, _txt(name, 26).upper())
        if k == 0 and photo:
            # The player opens the Short (or his silhouette does), on frame 0.
            import player_photo
            card, label = photo["card"], _txt(name, 26).upper()
            if hidden:
                card, label = player_photo.mystery(photo["card"], os.path.join(output_dir, ".mystery_card.png")), "KAUN?"
            images.append({"path": card, "t0": 0.0, "t1": b, "y": 850, "zoom": 0.06, "fade_in": 0})
            events += _pill(0.0, b, 1290, label, fade_in=0)
            # Then a round badge of him next to the label for the rest ("?" until he is named).
            if hidden and reveal_t > b:
                images.append({"path": player_photo.mystery(photo["badge"], os.path.join(output_dir, ".mystery_badge.png")),
                               "t0": b, "t1": reveal_t, "y": 200, "zoom": 0.0, "x": kit.OUT_W - 150})
            images.append({"path": photo["badge"], "t0": max(b, reveal_t), "t1": body_end, "y": 200, "zoom": 0.0,
                           "x": kit.OUT_W - 150})
        elif k == 0:
            events.append(kit.dialogue(4, 0.0, b, "CkText",
                                       rf"{{\an5\pos({CX},900)\fad(0,200)\fscx90\fscy90"
                                       rf"\t(0,250,\fscx100\fscy100)}}{_txt(story.hook_line, 90)}"))
        elif k <= n:
            events += fact_events(k, n, story.facts[k - 1], a, b)
        else:
            events.append(kit.dialogue(4, a, b, "CkText",
                                       rf"{{\an5\pos({CX},900)\1c{_c(fl.GOLD)}\fad(200,200)}}"
                                       rf"{_txt(story.question, 72)}"))
    transcript = kit.timed_transcript(caps)
    clip = {"start": 0.0, "video_title_for_youtube_short": story.title,
            "viral_hook_text": story.hook_line, "why": f"{story.kicker}: {topic}",
            "predicted_score": 90, "captions": transcript, "genre": "cricket",
            "ai_voice": "AI voice", "sources": sources[:8], "cricket_topic": story.model_dump()}
    _finish(output_dir, stem, pipeline, cfg, events, [cfg["bg"], kit.blend("#0B6E4F", cfg["bg"], 0.3)],
            voices, sfx, body_end, clip,
            {"source_title": topic, "context": TOPIC_SEO_CONTEXT.format(kind=story.kicker, topic=topic),
             "text_limit": 4000}, images=images, photos=[photo["info"]] if photo else [])


# ---------------------------------------------------------------- player vs player

class Side(BaseModel):
    name: str
    team: str


class Row(BaseModel):
    label: str
    a: str
    b: str
    better: int
    line: str


class Versus(BaseModel):
    found: bool
    title: str
    format_label: str
    players: List[Side]
    hook_line: str
    rows: List[Row]
    verdict_line: str
    question: str


VERSUS_FACTS_PROMPT = """Today is {today}. Compare these two cricketers by numbers: {topic}
Use Google Search. For the format named (ODI when none is named), give each player's
current career numbers as of today: matches, runs or wickets, average, strike rate or
economy, hundreds and fifties (or 5-wicket hauls), highest score or best figures, and
ICC titles won. Exact numbers only. Say NOT FOUND if either player or the numbers are
unclear."""

VERSUS_PROMPT = """You make a 30-40 second "who is better?" YouTube Short comparing two
cricketers by numbers, for Pakistani and Indian fans, voiced by the channel {handle}.
Topic: {topic}. Use ONLY the facts below; never invent a number. If they say NOT FOUND,
return found=false and empty lists.

Facts:
{facts}

Return:
- found
- title: max 45 characters, Roman Urdu hook ("Babar ya Kohli: ODI mein kaun aage?"), no emoji.
- format_label: 1-3 words like "ODI CAREER", "T20I CAREER", "TEST CAREER".
- players: exactly 2: name (full name as the Wikipedia article title), team (2-4 capital letters).
- hook_line: first voice line, Roman Urdu, 8-14 words, sets up the fight.
- rows: 4 to 6 stats that fit both players' roles (two batters: never wickets; two
  bowlers: never runs scored; never matches or innings played, they are not a win),
  mostly rates and per-innings numbers (average, strike
  rate, 100s per innings, economy) so a longer career does not win by length alone,
  plus one or two totals; the most telling first. Each: label (max 12 characters, English
  cricket term in capitals: "RUNS", "AVERAGE", "STRIKE RATE", "100s", "WICKETS",
  "ECONOMY"), a (first player's value, max 8 characters), b (second player's value),
  better (0 first, 1 second, -1 level; for economy and bowling average lower is
  better), line (Roman Urdu voice line, 8-16 words, numbers exactly as in the facts).
- verdict_line: Roman Urdu, 10-18 words: who leads on these numbers and by how many
  stats, respectful to both, no insults.
- question: Roman Urdu, max 70 characters, asking fans who is better, ending with
  "comment mein batao" or similar.
Everyday spoken Roman Urdu in Latin letters, never Devanagari or Arabic script."""

VERSUS_SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a cricket 'who is better' Short "
                      "comparing two players by their numbers: {topic}. Ignore the comedy phrases and "
                      "hashtags above: use the two players' names, 'vs', 'comparison', 'stats', "
                      "'who is better'. Never insult either player. creator is \"\".")
POP = "0.3*sin(2*PI*880*t)*exp(-12*t)"   # a row's winner lights up
LOWER_IS_BETTER = re.compile(r"ECON|BOWL(ING)? ?AV|BALLS PER|RUNS CONCEDED", re.I)
# A bowler's strike rate is balls per wicket: lower wins. A batter's is runs
# per 100 balls: higher wins. Shaheen vs Bumrah (15-oct-2026) had it the
# batter's way round, so the label alone cannot decide.
BOWLING = re.compile(r"ECON|BOWL|WICKET|5W|FIVE|MAIDEN|BEST FIG", re.I)
BATTING = re.compile(r"RUNS|100|50|HUNDRED|FIFT|HIGHEST|\bHS\b|SIX|FOUR", re.I)
# Played, not won: more matches is not "better" (Shaheen 103 vs Bumrah 100
# counted as a win for Shaheen, 15-oct-2026).
NEUTRAL = re.compile(r"MATCH|INNINGS|\bINNS\b|CAPS|YEARS|SPAN|DEBUT|\bAGE\b", re.I)
RATE = re.compile(r"AVERAGE|\bAVG\b|STRIKE", re.I)
FIGURES = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def _number(text):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return float(m.group(1)) if m else None


def context(rows):
    """"bowling", "batting" or "mixed" (all-rounders, or labels that say both)."""
    bowl = sum(1 for r in rows if BOWLING.search(r.label or ""))
    bat = sum(1 for r in rows if BATTING.search(r.label or ""))
    return "bowling" if bowl and not bat else "batting" if bat and not bowl else "mixed"


def fix_better(row, bowling=False, mixed=False):
    """Who wins a row, worked out from the numbers when both are numbers
    (the model is told the rule, the code makes sure of it). ``bowling``:
    the comparison is between bowlers; ``mixed``: batting and bowling rows
    together, where a bare "AVERAGE" could be either and the model decides."""
    if NEUTRAL.search(row.label or ""):
        return -1
    fa, fb = FIGURES.match(row.a or ""), FIGURES.match(row.b or "")
    if fa and fb:
        # Best figures: more wickets, then fewer runs ("4/15" beats "4/22").
        a = (int(fa.group(1)), -int(fa.group(2)))
        b = (int(fb.group(1)), -int(fb.group(2)))
        return -1 if a == b else 0 if a > b else 1
    a, b = _number(row.a), _number(row.b)
    if a is None or b is None:
        return row.better if row.better in (-1, 0, 1) else -1
    if a == b:
        return -1
    label = row.label or ""
    if LOWER_IS_BETTER.search(label):
        low = True
    elif RATE.search(label):
        if mixed:
            return row.better if row.better in (-1, 0, 1) else -1
        low = bowling
    else:
        low = False
    return 0 if (a < b) == low else 1


def _score(rows, key):
    s = [0, 0]
    for r in rows:
        w = key(r)
        if w in (0, 1):
            s[w] += 1
    return s


def find_versus(client, topic, handle):
    import time
    for attempt in range(2):
        facts, sources = grounded(client, VERSUS_FACTS_PROMPT.format(topic=topic, today=time.strftime("%d %B %Y")))
        if facts and "NOT FOUND" not in facts[:200].upper():
            break
    if not facts or "NOT FOUND" in facts[:200].upper():
        raise RuntimeError(f"Could not find both players' numbers ({facts[:160] or 'no answer'}).")
    story = kit.ask_json(client, Versus, VERSUS_PROMPT.format(handle=handle, topic=topic, facts=facts)
                         + remix_note(topic) + "\n\n" + craft.short_rules(craft.FIXED_ORDER), model=craft.writer_model())
    # Rows say who is ahead and code checks that against the numbers below: only the hook
    # and the question are polished.
    craft.polish(client, story, facts, what="cricket player comparison YouTube Short",
                 fields=("hook_line", "question"))
    remix_guard(topic, story)
    if not story.found or len(story.players) != 2 or len(story.rows) < 3:
        raise RuntimeError("The comparison came back too thin for a video; try two better-known players.")
    story.rows = story.rows[:6]
    ctx = context(story.rows)
    said = _score(story.rows, lambda r: r.better)
    for r in story.rows:
        r.better = fix_better(r, bowling=ctx == "bowling", mixed=ctx == "mixed")
    shown = _score(story.rows, lambda r: r.better)
    if shown != said:
        # The voice must say what the screen shows.
        a, b = story.players[0].name, story.players[1].name
        lead, other = ((a, b) if shown[0] > shown[1] else (b, a))
        hi, lo = max(shown), min(shown)
        story.verdict_line = (f"Numbers barabar hain: dono {hi} {hi} stats mein aage. Faisla aap ka!"
                              if hi == lo else
                              f"In numbers ke hisaab se {lead} {hi} stats mein aage hain, aur {other} {lo} mein.")
    return story, facts, sources


VS_X = (270, 810)
VS_Y = 640
ROW_Y0, ROW_GAP = 965, 86


def versus_events(story, windows, body_end, handle, photos):
    """Two players face each other; each stat row slides in and its winner
    lights up; a running score, then the verdict."""
    ev = []
    if handle:
        ev.append(kit.dialogue(1, 0, body_end, "CkSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{handle}"))
    ev += _pill(0.1, body_end, 190, _txt(story.format_label.upper(), 24))
    ev.append(kit.dialogue(1, 0, body_end, "CkTitle",
                           rf"{{\an5\pos({CX},380)\fad(150,0)\fscx70\fscy70\t(0,260,\fscx106\fscy106)"
                           rf"\t(260,400,\fscx100\fscy100)}}{fl.clean_title(story.title)}"))
    for k, (side, x) in enumerate(zip(story.players, VS_X)):
        if not photos[k]:
            ev.append(_shape(3, 0.2, body_end, fl._circle(130), _c(fl.GOLD if k == 0 else "#38BDF8"),
                             move=(x + (-600 if k == 0 else 600), VS_Y, x, VS_Y, 0, 350), an=5))
            initials = "".join(w[0] for w in side.name.split()[:2]).upper()
            ev.append(kit.dialogue(4, 0.2, body_end, "CkBadgeDark",
                                   rf"{{\an5\move({x + (-600 if k == 0 else 600)},{VS_Y},{x},{VS_Y},0,350)}}{initials}"))
        name = _txt(side.name, 34)
        # Two names side by side: each has about 500 px.
        fs = "" if len(name) <= 14 else r"\fs38" if len(name) <= 20 else r"\fs30"
        ev.append(kit.dialogue(4, 0.4, body_end, "CkName", rf"{{\an5\pos({x},{VS_Y + 200}){fs}\fad(200,0)}}{name}"))
        ev.append(kit.dialogue(4, 0.5, body_end, "CkSmall", rf"{{\an5\pos({x},{VS_Y + 250})\fad(200,0)}}{_txt(side.team, 6)}"))
    ev.append(kit.dialogue(5, 0.45, body_end, "CkVs",
                           rf"{{\an5\pos({CX},{VS_Y})\fs110\fscx300\fscy300\alpha&HFF&"
                           rf"\t(0,200,\fscx100\fscy100\alpha&H00&)}}VS"))
    score = [0, 0]
    n = len(story.rows)
    for k, row in enumerate(story.rows):
        _k, a, b = windows[1 + k]
        y = ROW_Y0 + k * ROW_GAP
        slide = r"\fad(0,0)"
        ev.append(_shape(2, a, body_end, fl._round_rect(960, 74, 37), "&H2B140E&", alpha="40",
                         move=(60 + 1100, y - 37, 60, y - 37, 0, 280)))
        ev.append(kit.dialogue(4, a, body_end, "CkSmall",
                               rf"{{\an5\move({CX + 1100},{y},{CX},{y},0,280)\1c{_c(fl.GOLD)}}}{_txt(row.label, 14).upper()}"))
        for side, x in ((0, VS_X[0]), (1, VS_X[1])):
            val = _txt(row.a if side == 0 else row.b, 10)
            win = row.better == side
            # White with an outline while it slides in; the winner then turns
            # dark on a gold pill with no outline (dark + black outline on
            # gold smudged, first render 15-oct-2026).
            ev.append(kit.dialogue(5, a + 0.15, a + 0.6 if win else body_end, "CkNote",
                                   rf"{{\an5\move({x + 1100},{y},{x},{y},0,280)\fs50}}{val}"))
            if win:
                ev.append(_shape(3, a + 0.6, body_end, fl._round_rect(220, 62, 31), _c(fl.GOLD),
                                 at=(x - 110, y - 31), extra=r"\fad(120,0)"))
                ev.append(kit.dialogue(5, a + 0.6, body_end, "CkNote",
                                       rf"{{\an5\pos({x},{y})\fs50\bord0\shad0\1c{_c('#14142B')}"
                                       rf"\fscx125\fscy125\t(0,180,\fscx100\fscy100)}}{val}"))
        if row.better in (0, 1):
            score[row.better] += 1
        # The running score under VS, changing as each row is won.
        nxt = windows[2 + k][1] if k < n - 1 else body_end
        ev.append(kit.dialogue(5, a + 0.6, nxt, "CkStar",
                               rf"{{\an5\pos({CX},{VS_Y + 110})\fs56}}{score[0]} - {score[1]}"))
    # The verdict covers the table: who leads, and by how much.
    _k, va, vb = windows[1 + n]
    lead = 0 if score[0] > score[1] else 1 if score[1] > score[0] else -1
    ev.append(_shape(6, va, body_end, fl._round_rect(980, 330, 40), "&H1A0E08&", at=(50, 1015), alpha="08",
                     extra=r"\fad(200,0)"))
    ev += _pill(va + 0.1, body_end, 1090, "AAGE: " + (_txt(story.players[lead].name.split()[-1], 14).upper()
                                                       if lead >= 0 else "BARABAR"), layer=7)
    ev.append(kit.dialogue(8, va + 0.2, body_end, "CkBigC",
                           rf"{{\an5\pos({CX},1240)\fs130\fscx40\fscy40\t(0,260,\fscx100\fscy100)}}"
                           rf"{score[0]} - {score[1]}"))
    return ev


def run_versus(topic, output_dir, pipeline):
    cfg = fl.settings()
    client = kit.gemini()
    print(f"🏏 Player vs player short: researching \"{topic}\"...")
    story, facts, sources = find_versus(client, topic, cfg["handle"] or "this channel")
    print(f"   ✅ {story.players[0].name} vs {story.players[1].name}: {len(story.rows)} stats ({len(sources)} sources)")
    stem = kit.neutral_stem("Cricket")
    photos = [_photo(p.name, output_dir) for p in story.players]
    lines = [story.hook_line] + [r.line for r in story.rows] + [story.verdict_line, story.question]
    print(f"🎙️ Voicing {len(lines)} lines...")
    windows, voices, caps, body_end = _voice_timeline(client, lines, output_dir, stem)
    events = versus_events(story, windows, body_end, cfg["handle"], photos)
    images = [{"path": p["avatar"], "t0": 0.2, "t1": body_end, "x": x, "y": VS_Y, "zoom": 0.04}
              for p, x in zip(photos, VS_X) if p]
    sfx = [(kit.WHOOSH, 0.3, max(0.0, a - 0.15)) for _k, a, _b in windows]
    sfx += [(POP, 0.4, windows[1 + k][1] + 0.6) for k, r in enumerate(story.rows) if r.better in (0, 1)]
    clip = {"start": 0.0, "video_title_for_youtube_short": story.title, "viral_hook_text": story.hook_line,
            "why": f"Who is better: {topic}", "predicted_score": 92, "captions": kit.timed_transcript(caps),
            "genre": "cricket", "ai_voice": "AI voice", "sources": sources[:8], "cricket_versus": story.model_dump(),
            "comment_question": story.question}
    _finish(output_dir, stem, pipeline, cfg, events, [cfg["bg"], kit.blend("#1E3A8A", cfg["bg"], 0.3)],
            voices, sfx, body_end, clip,
            {"source_title": topic, "context": VERSUS_SEO_CONTEXT.format(topic=topic), "text_limit": 4000},
            images=images, photos=[p["info"] for p in photos if p])


def run(match, output_dir, pipeline):
    """A cricket short for what the user typed or pasted (CRICKET_MODE)."""
    match = re.sub(r"\s+", " ", match or "").strip()[:300]
    if len(match) < 3:
        raise RuntimeError("Write which match (or paste its link), or a cricket topic.")
    mode = (os.environ.get("CRICKET_MODE") or "match").lower()
    if mode == "topic":
        return run_topic(match, output_dir, pipeline)
    if mode == "versus":
        return run_versus(match, output_dir, pipeline)
    return run_match(match, output_dir, pipeline)


def run_match(match, output_dir, pipeline):
    cfg = fl.settings()
    handle = cfg["handle"]
    client = kit.gemini()
    notes = ""
    if is_link(match):
        match, notes = watch_link(client, match)
    print(f"🏏 Cricket short: looking up \"{match[:80]}\"...")
    story, facts, sources = find_story(client, match, handle or "this channel", notes)
    print(f"   ✅ {story.teams[0].name} {story.teams[0].score} vs {story.teams[1].name} "
          f"{story.teams[1].score} · {story.result_line} ({len(sources)} sources)")

    stem = kit.neutral_stem("Cricket")
    print(f"🎙️ Voicing {len(story.beats)} commentary lines...")
    windows, voices, caps, body_end = _voice_timeline(client, [b.line for b in story.beats],
                                                      output_dir, stem)
    events, sfx, images, photos = frame_events(story, body_end, handle, story.title), [], [], {}
    for k, a, b in windows:
        beat = story.beats[k]
        star = (story.stars[min(max(beat.ref, 0), len(story.stars) - 1)]
                if beat.scene == "star" and story.stars else None)
        if star and star.name not in photos:
            photos[star.name] = _photo(star.name, output_dir) if len(photos) < 3 else None
        got = photos.get(star.name) if star else None
        if got:
            images.append({"path": got["avatar"], "t0": a, "t1": b, "y": 815, "zoom": 0.08})
        events += scene_events(beat, a, b, story, with_photo=bool(got))
        sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
    colors = [cfg["bg"], kit.blend(story.teams[0].color, cfg["bg"], 0.25),
              kit.blend(story.teams[1].color, cfg["bg"], 0.25)]
    transcript = kit.timed_transcript(caps)
    clip = {"start": 0.0, "video_title_for_youtube_short": story.title,
            "viral_hook_text": story.result_line,
            "why": f"{story.teams[0].name} vs {story.teams[1].name}: {story.result_line}",
            "predicted_score": 90, "captions": transcript, "genre": "cricket",
            "ai_voice": "AI voice commentary", "sources": sources[:8],
            "cricket": story.model_dump()}
    _finish(output_dir, stem, pipeline, cfg, events, colors, voices, sfx, body_end, clip,
            {"source_title": story.match_line, "context": SEO_CONTEXT, "text_limit": 4000},
            images=images, photos=[p["info"] for p in photos.values() if p])
