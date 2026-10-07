"""Cricket match Shorts with no match footage (CONTENT_GENRE=cricket).

Broadcast footage is the most policed content on YouTube (JioStar, PTV/Myco,
Walee and Sony enforce every season; research of 8-oct-2026), while scores
and match facts belong to no one. So this mode never touches a video: the
user names a match, Gemini looks it up with Google Search and writes a Roman
Urdu commentary script plus the numbers, a Gemini voice reads it, and the
picture is ours: animated team badges, score cards that count up, the stars
of the match, key moments and the result, then the channel's end card.

No player photos or likeness (personality-rights orders for Gavaskar and
Yuvraj, 2025-26) and no team or tournament logos: names and colours only.

Env: CRICKET_MATCH (what the user typed), CRICKET_VOICE (default Fenrir).
"""
import os
import re
from typing import List

from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

VOICE_STYLE = "like an excited Pakistani cricket commentator, natural Urdu accent, fast and energetic"
GAP = 0.25          # between voice lines
LEAD = 0.5          # before the first line
MAX_BEATS = 9


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


FACTS_PROMPT = """Today is {today}. Find the facts of this cricket match: {match}
Use Google Search; a match dated before today has been played. Report only what sources state: tournament and stage, venue,
date, both teams' final scores with overs, the result and margin, the player of the
match, the top 3 performers with exact figures (runs and balls, or wickets-runs), and
4 key moments (with the over when known). If the match has not been played, is
ambiguous, or you cannot find it, say NOT FOUND and why."""

STORY_PROMPT = """You make a 40-50 second animated YouTube Short about a cricket match for
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
- stars: the 1 to 3 best performers: name, team (short), figures ("69* (53)" or
  "4/30"), note (Roman Urdu, max 40 characters).
- moments: 2 to 4 turning points: label (max 14 characters, "OVER 17" or "POWERPLAY"),
  text (Roman Urdu, max 70 characters).
- beats: the voice-over in order, 7 to {max_beats} lines. Each has scene (intro,
  scores, star, moment or result), ref (index into stars or moments for those scenes,
  else 0) and line: Roman Urdu commentary in Latin letters, 8 to 16 words, excited like
  a TV commentator, every number exactly as in the facts. Order: 1 intro, 1 scores,
  one per star, one per moment, 1 result. The result line ends with the question.
- question: a cheeky question for the comments, Roman Urdu, max 70 characters,
  ending with "comment mein batao" or similar.
Roman Urdu always in Latin letters, never Devanagari or Arabic script. No swear words."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is an animated cricket match summary "
               "(scores, stars, key moments, result) voiced by the channel, with no match "
               "footage. Ignore the comedy phrases and hashtags above: use cricket searches "
               "instead (the teams, tournament, players, 'match summary', 'scorecard', "
               "'cricket news'). Player and team names are welcome in every field; creator is \"\".")


def find_story(client, match, handle):
    """(Story, [source urls]) for what the user typed, or raises."""
    import time
    from google.genai import types
    # Twice at most: once the model answered NOT FOUND for a 2025 match while
    # saying the date was 2026 (8-oct-2026); the same question then worked.
    for attempt in range(2):
        r = client.models.generate_content(
            model=kit.text_model(),
            contents=FACTS_PROMPT.format(match=match, today=time.strftime("%d %B %Y")),
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        facts = (r.text or "").strip()
        if facts and "NOT FOUND" not in facts[:200].upper():
            break
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    sources = [c.web.uri for c in (getattr(gm, "grounding_chunks", None) or []) if getattr(c, "web", None)]
    if not facts or "NOT FOUND" in facts[:200].upper():
        raise RuntimeError(f"Could not find this match ({facts[:160] or 'no answer'}). "
                           "Write the teams, tournament and date, e.g. 'Pakistan vs India, Asia Cup 2025 final'.")
    story = kit.ask_json(client, Story, STORY_PROMPT.format(handle=handle, facts=facts,
                                                            max_beats=MAX_BEATS))
    if not story.found or len(story.teams) != 2 or not story.beats:
        raise RuntimeError("The search did not return a finished match with both scores. "
                           "Write the teams, tournament and date.")
    story.beats = story.beats[:MAX_BEATS]
    return story, facts, sources


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


def _pill(t0, t1, y, text, colour=fl.GOLD, text_colour="#14142B"):
    w = max(260, 26 * len(text) + 110)
    h = 78
    return [
        _shape(3, t0, t1, fl._round_rect(w, h, h // 2), _c(colour), at=(CX - w // 2, y - h // 2),
               extra=r"\fad(150,150)"),
        kit.dialogue(4, t0, t1, "CkPill", rf"{{\an5\pos({CX},{y})\1c{_c(text_colour)}\fad(150,150)}}{text}"),
    ]


def scene_events(beat, t0, t1, story):
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
    elif beat.scene == "star" and story.stars:
        star = story.stars[min(max(beat.ref, 0), len(story.stars) - 1)]
        ev += _pill(t0, t1, 640, "STAR OF THE MATCH" if beat.ref == 0 else "STAR PERFORMER")
        ev.append(kit.dialogue(4, t0 + 0.15, t1, "CkStar",
                               rf"{{\an5\pos({CX},800)\fscx80\fscy80\t(0,220,\fscx100\fscy100){out}}}"
                               rf"{_txt(star.name, 22)}"))
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


def frame_events(story, total, handle, title):
    """What stays up the whole time: handle, match line, title."""
    ev = []
    if handle:
        ev.append(kit.dialogue(1, 0, total, "CkSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{handle}"))
    ev += _pill(0.1, total, 190, _txt(story.match_line, 52), colour="#FFFFFF")
    if title:
        ev.append(kit.dialogue(1, 0, total, "CkTitle",
                               rf"{{\an5\pos({CX},380)\fad(150,0)\fscx70\fscy70\t(0,260,\fscx106\fscy106)"
                               rf"\t(260,400,\fscx100\fscy100)}}{fl.clean_title(title)}"))
    return ev


def run(match, output_dir, pipeline):
    import seo_copy
    match = re.sub(r"\s+", " ", match or "").strip()[:200]
    if len(match) < 3:
        raise RuntimeError("Write which match: teams, tournament and date.")
    cfg = fl.settings()
    handle = cfg["handle"]
    print(f"🏏 Cricket short: looking up \"{match}\"...")
    client = kit.gemini()
    story, facts, sources = find_story(client, match, handle or "this channel")
    print(f"   ✅ {story.teams[0].name} {story.teams[0].score} vs {story.teams[1].name} "
          f"{story.teams[1].score} · {story.result_line} ({len(sources)} sources)")

    stem = kit.neutral_stem("Cricket")
    print(f"🎙️ Voicing {len(story.beats)} commentary lines...")
    voice = os.environ.get("CRICKET_VOICE") or "Fenrir"
    said = kit.voice_lines(client, [{"text": b.line, "voice": voice, "style": VOICE_STYLE}
                                    for b in story.beats], output_dir, stem)
    if not any(p for p, _ in said):
        raise RuntimeError("The AI voice failed for every line; try again in a minute.")

    # Timeline: each beat's scene lasts as long as its line.
    t, windows, voices, lines = LEAD, [], [], []
    for beat, (path, secs) in zip(story.beats, said):
        secs = secs or max(2.5, len(beat.line.split()) / 2.8)  # a failed line still shows
        windows.append((beat, t, t + secs + GAP))
        if path:
            voices.append((path, t))
        lines.append((beat.line, t, t + secs))
        t += secs + GAP
    body_end = t + 0.6
    outro_s = cfg["outro_seconds"]
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)

    events = frame_events(story, body_end, handle, story.title)
    sfx = []
    for beat, a, b in windows:
        events += scene_events(beat, a, b, story)
        sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
    events += card_ev
    colors = [cfg["bg"], kit.blend(story.teams[0].color, cfg["bg"], 0.25),
              kit.blend(story.teams[1].color, cfg["bg"], 0.25)]
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    print(f"🎬 Rendering the cricket short ({total:.0f}s)...")
    kit.render(final, total, colors, events, STYLES, voices=voices, sfx=sfx + card_sfx)

    transcript = kit.timed_transcript(lines)
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": story.title,
            "viral_hook_text": story.result_line,
            "why": f"{story.teams[0].name} vs {story.teams[1].name}: {story.result_line}",
            "predicted_score": 90, "captions": transcript, "genre": "cricket",
            "ai_voice": "AI voice commentary", "sources": sources[:8],
            "cricket": story.model_dump()}
    seo_copy.apply([clip], transcript, source_title=story.match_line, context=SEO_CONTEXT,
                   text_limit=4000)
    kit.finish(output_dir, stem, [clip], transcript, pipeline, extra={"genre": "cricket"})
