"""Quiz and paheli Shorts with no source video (CONTENT_GENRE=quiz).

A channel kind of its own (my_channels.py): a question on screen, the
options swiping in, a 5-7 second countdown with ticks, then the answer lit
in green with a ding and one line of why. Viewers answer in the comments
before the reveal, which is the engagement these Shorts live on. Everything
is ours: the questions are written by Gemini, the picture is drawn (ASS on
the animated gradient), the voice is Gemini's, the bed is a Lyria
instrumental (music_beds.py), so nothing can be claimed.

A wrong answer is the one thing that sinks a quiz channel, so the questions
come from QUIZ_MODEL (the stronger text model) and a second call checks
every answer (with Google Search for general knowledge); a question the
check does not confirm is dropped, and the Short needs enough left.

Formats (QUIZ_FORMAT): ``mcq`` 3 general-knowledge questions with 4 options,
``riddle`` 2 paheliyan with the answer revealed, ``math`` 2 quick maths or
logic puzzles with 3 options, ``flags`` 4 real flags (flags.py, public
domain) with 4 countries of the same region each: the answer is known in
code, so only the fun fact comes from Gemini. QUIZ_TOPIC narrows the
questions, QUIZ_AVOID (a JSON list) holds questions already asked on the
channel ("flag:<country>" for flags), QUIZ_NUMBER is the channel's running
quiz number ("QUIZ #12"), which turns single videos into a daily series.
"""
import json
import os
import re
from typing import List

from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

CX = kit.OUT_W // 2
VOICE_STYLE = "like a friendly, energetic TV quiz show host, natural Urdu accent, clear and lively"
GAP = 0.25
TICK = "0.5*sin(2*PI*1500*t)*exp(-40*t)"
DING = "0.35*sin(2*PI*1046*t)*exp(-5*t)+0.25*sin(2*PI*1568*t)*exp(-6*t)"
FORMATS = {
    "mcq": {"count": 3, "options": 4, "timer": 5, "label": "SAWAL"},
    "riddle": {"count": 2, "options": 0, "timer": 7, "label": "PAHELI"},
    "math": {"count": 2, "options": 3, "timer": 6, "label": "DIMAGH LAGAO"},
    "flags": {"count": 4, "options": 4, "timer": 4, "label": "JHANDA"},
}
FLAG_QUESTIONS = ["Ye jhanda kis mulk ka hai?", "Aur ye wala jhanda?", "Ab ye pehchano!",
                  "Last one: ye kis mulk ka hai?"]
FLAG_Y = 470
TOPICS = ["Pakistan general knowledge", "world general knowledge", "science", "geography and capitals",
          "space and planets", "human body", "animals", "inventions and inventors", "history",
          "sports general knowledge", "food and fruits", "famous places of the world"]
GREEN, RED = "#22C55E", "#EF4444"


def quiz_model():
    return os.environ.get("QUIZ_MODEL") or os.environ.get("GEMINI_MODEL_THUMBNAIL") or "gemini-3.7-flash"


class Question(BaseModel):
    question: str
    options: List[str]
    answer: int
    answer_text: str
    explain: str


class Quiz(BaseModel):
    title: str
    hook_line: str
    questions: List[Question]
    outro_line: str


PROMPT = """You write a {seconds}-second YouTube Short quiz for Pakistani and Indian viewers,
voiced by the channel {handle}. Format: {format_text}
{topic_text}
Rules:
- Facts must be 100% correct and not open to argument; nothing that changed recently,
  nothing about religion, politics, or a living person's private life.
- Medium difficulty: most people should get the first one, few the last one.
- Never ask any of these, already used on the channel:
{avoid}
Return:
- title: max 45 characters, Roman Urdu hook for the top of the screen, no emoji, never
  revealing an answer. The Short asks {final} of the questions (the others are spares),
  so any score in it is out of {final} ("Sirf 1% log {final}/{final} kar paate hain").
- hook_line: the first voice line, Roman Urdu, 6-12 words, a challenge to the viewer.
- questions: exactly {count}. Each:
  question: Roman Urdu, max {q_chars} characters.
  options: {options_text}
  answer: {answer_text}
  answer_text: the correct answer in a few words (Roman Urdu or the usual English term).
  explain: Roman Urdu, max 70 characters, a fun one-line why.
- outro_line: Roman Urdu voice line, max 12 words, asking how many they got right, to
  comment.
Everyday spoken Roman Urdu in Latin letters, the way people talk; English words where
people say them in English. Never Devanagari or Arabic script."""

FORMAT_TEXT = {
    "mcq": "3 general-knowledge multiple-choice questions, 4 options each.",
    "riddle": "2 paheliyan (riddles) with a clever one- or two-word answer; no options.",
    "math": "2 quick maths or logic puzzles anyone can solve in their head in 6 seconds, 3 options each.",
    "flags": "4 country flags to recognise, 4 country names each.",
}

CHECK_PROMPT = """Check this quiz carefully. For each question say if the marked answer is
correct and the only correct one{search}. Reply with one line per question:
"1: OK" or "1: WRONG - <why>". Nothing else.

{items}"""


def _avoid():
    try:
        got = json.loads(os.environ.get("QUIZ_AVOID") or "[]")
        return [str(x)[:140] for x in got if x][-80:]
    except ValueError:
        return []


class FlagCopy(BaseModel):
    title: str
    hook_line: str
    outro_line: str
    facts: List[str]


FLAG_PROMPT = """You write the words for a flag quiz YouTube Short for Pakistani and Indian viewers
({handle}). The countries, in order: {countries}.
Return:
- title: max 45 characters, Roman Urdu hook, no emoji, never naming a country
  ("Sirf geniuses {n}/{n} jhande pehchan paate hain").
- hook_line: Roman Urdu voice line, 6-12 words, a challenge.
- outro_line: Roman Urdu voice line, max 12 words, asking for their score in the comments.
- facts: one per country in the same order: a true, well-known fact about that
  country's flag (its colours, symbol or story), Roman Urdu, max 70 characters.
Everyday Roman Urdu in Latin letters, never Devanagari or Arabic script."""


def write_flags(client, handle, rnd=None):
    """(Quiz, [flag png per question]) from flags.py: four flags with pictures."""
    import random
    import flags
    rnd = rnd or random.Random()
    used = [a[5:] for a in _avoid() if a.lower().startswith("flag:")]
    picked = []
    for country, options, answer in flags.pick(8, used, rnd):
        path = flags.fetch(country)
        if path:
            picked.append((country, options, answer, path))
        if len(picked) == FORMATS["flags"]["count"]:
            break
    if len(picked) < FORMATS["flags"]["count"]:
        raise RuntimeError("Could not get enough flag pictures from Wikipedia; try again later.")
    n = len(picked)
    try:
        copy = kit.ask_json(client, FlagCopy, FLAG_PROMPT.format(
            handle=handle or "this channel", countries=", ".join(c for c, *_ in picked), n=n), model=quiz_model())
    except Exception as e:  # noqa: BLE001 — the quiz works without the facts
        print(f"   ℹ️ No flag facts ({type(e).__name__}); plain answers.")
        copy = FlagCopy(title=f"Sirf geniuses {n}/{n} jhande pehchan paate hain",
                        hook_line="Kitne jhande pehchan sakte ho? Chalo dekhte hain!",
                        outro_line="Kitne sahi hue? Apna score comment karo!", facts=[])
    questions = [Question(question=FLAG_QUESTIONS[min(k, len(FLAG_QUESTIONS) - 1)] if k < n - 1 else FLAG_QUESTIONS[-1],
                          options=options, answer=answer, answer_text=country,
                          explain=(copy.facts[k] if k < len(copy.facts) else ""))
                 for k, (country, options, answer, _p) in enumerate(picked)]
    return (Quiz(title=copy.title, hook_line=copy.hook_line, questions=questions, outro_line=copy.outro_line),
            [p for *_x, p in picked])


def write(client, fmt, topic, handle):
    """(Quiz, sources) with every answer checked, or raises."""
    f = FORMATS[fmt]
    extra = f["count"] + 2   # spares for the ones the check drops
    prompt = PROMPT.format(
        seconds=45 if fmt == "mcq" else 35, handle=handle or "this channel", format_text=FORMAT_TEXT[fmt],
        topic_text=f"Topic: {topic}." if topic and fmt == "mcq" else "",
        avoid="\n".join(f"  - {a}" for a in _avoid()) or "  (nothing yet)", count=extra, final=f["count"],
        q_chars=140 if fmt == "riddle" else 90,
        options_text=(f"exactly {f['options']}, each max 22 characters, one clearly right."
                      if f["options"] else "an empty list."),
        answer_text=(f"index 0-{f['options'] - 1} of the right option (vary its position)."
                     if f["options"] else "-1."))
    quiz = kit.ask_json(client, Quiz, prompt, model=quiz_model())
    good = [q for q in quiz.questions if _shape_ok(q, f)]
    good = _checked(client, fmt, good)
    if len(good) < f["count"]:
        raise RuntimeError(f"Only {len(good)} of the questions passed the answer check; try again.")
    quiz.questions = good[:f["count"]]
    return quiz


def _shape_ok(q, f):
    if f["options"]:
        return len(q.options) == f["options"] and 0 <= q.answer < f["options"] and all(o.strip() for o in q.options)
    return bool(q.answer_text.strip())


def _checked(client, fmt, questions):
    """The questions a second look confirms; Google Search checks facts."""
    if not questions:
        return []
    items = []
    for k, q in enumerate(questions, 1):
        opts = "".join(f"\n   {'ABCD'[i]}) {o}" for i, o in enumerate(q.options))
        mark = f"{'ABCD'[q.answer]} ({q.options[q.answer]})" if q.options else q.answer_text
        items.append(f"{k}. {q.question}{opts}\n   Marked answer: {mark}")
    prompt = CHECK_PROMPT.format(items="\n".join(items),
                                 search=" (use Google Search for facts)" if fmt == "mcq" else "")
    try:
        if fmt == "mcq":
            from cricket_shorts import grounded
            text, _ = grounded(client, prompt)
        else:
            text = client.models.generate_content(model=quiz_model(), contents=prompt).text or ""
    except Exception as e:  # noqa: BLE001 — no check, no quiz: a wrong answer is worse than none
        raise RuntimeError(f"The answer check failed ({type(e).__name__}); try again.")
    ok = {int(m.group(1)) for m in re.finditer(r"(?m)^\W*(\d+)\s*[:.)-]\s*OK\b", text, re.I)}
    dropped = len(questions) - len(ok)
    if dropped:
        print(f"   ⚠️ The check dropped {dropped} question(s).")
    return [q for k, q in enumerate(questions, 1) if k in ok]


# ---------------------------------------------------------------- drawing

STYLES = [
    kit.style("QzSmall", "Montserrat ExtraBold", 34, "#FFFFFF"),
    kit.style("QzPill", "Montserrat ExtraBold", 36, "#14142B", spacing=2),
    kit.style("QzTitle", "Anton", 96, "#FFFFFF", outline=0, shadow=4),
    kit.style("QzQ", "Montserrat ExtraBold", 56, "#FFFFFF", outline=0, shadow=2),
    kit.style("QzOpt", "Montserrat ExtraBold", 46, "#FFFFFF", align=4),
    kit.style("QzLetter", "Anton", 50, "#14142B"),
    kit.style("QzNum", "Anton", 110, "#14142B"),
    kit.style("QzAns", "Anton", 120, fl.GOLD, outline=6, shadow=4),
    kit.style("QzNote", "Montserrat ExtraBold", 42, "#FFFFFF", outline=3),
    kit.style("QzBig", "Anton", 300, fl.GOLD, outline=8, shadow=6),
]


def _c(hex_color):
    return fl._ass_colour(hex_color)


def _t(text, limit):
    text = re.sub(r"\s*[·•–—]\s*", " | ", text or "")
    return fl.clean_title(text)[:limit]


def _shape(layer, t0, t1, drawing, colour, at, alpha="00", extra="", move=None):
    where = rf"\move({','.join(str(v) for v in move)})" if move else rf"\pos({at[0]},{at[1]})"
    return kit.dialogue(layer, t0, t1, "Shape",
                        rf"{{\an7{where}\1c{colour}\1a&H{alpha}&\bord0\shad0{extra}\p1}}{drawing}{{\p0}}")


def _pill(t0, t1, y, text):
    w, h = max(260, 26 * len(text) + 110), 78
    return [_shape(3, t0, t1, fl._round_rect(w, h, h // 2), _c(fl.GOLD), (CX - w // 2, y - h // 2),
                   extra=r"\fad(150,150)"),
            kit.dialogue(4, t0, t1, "QzPill", rf"{{\an5\pos({CX},{y})\fad(150,150)}}{text}")]


def _flash(t0):
    return _shape(7, t0, t0 + 0.25, fl._round_rect(kit.OUT_W, kit.OUT_H, 0), "&HFFFFFF&", (0, 0),
                  alpha="C8", extra=r"\t(0,220,\1a&HFF&)")


def option_rows(n, picture=False):
    """Centre y of each option box (lower when a flag sits above them)."""
    if picture:
        return [820 + k * 130 for k in range(n)]
    return [700 + k * 140 for k in range(n)] if n == 4 else [720 + k * 160 for k in range(n)]


def question_events(k, n, label, q, q0, timer0, reveal0, end, picture=False):
    """One question: card (or the flag above, drawn by render), options
    swiping in, countdown, the reveal."""
    ev = [_flash(q0)]
    ev += _pill(q0, end, 190, f"{label} {k}/{n}")
    if picture:
        ev.append(kit.dialogue(4, q0 + 0.2, end, "QzNote", rf"{{\an5\pos({CX},735)\fad(200,200)}}{_t(q.question, 60)}"))
    else:
        ev.append(_shape(2, q0, end, fl._round_rect(980, 360, 40), "&H2B140E&", (50, 250), alpha="40",
                         extra=r"\fad(200,200)"))
        ev.append(kit.dialogue(4, q0, end, "QzQ", rf"{{\an5\pos({CX},430)\fad(200,200)\fscx90\fscy90"
                                                   rf"\t(0,220,\fscx100\fscy100)}}{_t(q.question, 140)}"))
    rows = option_rows(len(q.options), picture)
    timer_y = 1340 if picture else 1290
    for i, (opt, y) in enumerate(zip(q.options, rows)):
        a = q0 + 0.5 + 0.15 * i
        swipe = (90 + 1100, y - 59, 90, y - 59, 0, 280)
        ev.append(_shape(2, a, end, fl._round_rect(900, 118, 59), "&H3A2418&", None, alpha="30",
                         move=swipe, extra=r"\fad(0,200)"))
        ev.append(_shape(3, a, end, fl._circle(44), _c(fl.GOLD), None,
                         move=(110 + 1100, y - 44, 110, y - 44, 0, 280), extra=r"\fad(0,200)"))
        ev.append(kit.dialogue(4, a, end, "QzLetter",
                               rf"{{\an5\move({154 + 1100},{y},154,{y},0,280)\fad(0,200)}}{'ABCD'[i]}"))
        ev.append(kit.dialogue(4, a, end, "QzOpt",
                               rf"{{\an4\move({225 + 1100},{y},225,{y},0,280)\fad(0,200)}}{_t(opt, 24)}"))
        if i == q.answer:
            # The right one turns green at the reveal, with a little pop.
            ev.append(_shape(3, reveal0, end, fl._round_rect(900, 118, 59), _c(GREEN), (90, y - 59),
                             extra=r"\fad(120,200)"))
            ev.append(kit.dialogue(5, reveal0, end, "QzOpt",
                                   rf"{{\an4\pos(225,{y})\fad(0,200)\t(0,150,\fscx108\fscy108)"
                                   rf"\t(150,300,\fscx100\fscy100)}}{_t(opt, 24)}"))
            ev.append(_shape(4, reveal0, end, fl._circle(44), "&HFFFFFF&", (110, y - 44), extra=r"\fad(0,200)"))
            ev.append(kit.dialogue(5, reveal0, end, "QzLetter", rf"{{\an5\pos(154,{y})\1c{_c(GREEN)}\fad(0,200)}}"
                                                                rf"{'ABCD'[i]}"))
        else:
            ev.append(_shape(5, reveal0, end, fl._round_rect(900, 118, 59), "&H000000&", (90, y - 59),
                             alpha="70", extra=r"\fad(150,200)"))
    if not q.options:
        # A riddle: a big ? while they think, the answer in its place after.
        ev.append(kit.dialogue(4, q0 + 0.3, reveal0, "QzBig",
                               rf"{{\an5\pos({CX},900)\fad(200,150)\t(0,300,\frz-8)\t(300,600,\frz8)"
                               rf"\t(600,900,\frz0)}}?"))
        ev.append(kit.dialogue(5, reveal0, end, "QzAns",
                               rf"{{\an5\pos({CX},900)\fscx40\fscy40\t(0,250,\fscx100\fscy100)\fad(0,200)}}"
                               rf"{_t(q.answer_text, 22).upper()}"))
    # Countdown: the number pops each second in a gold circle.
    secs = max(1, round(reveal0 - timer0))
    for s in range(secs):
        a = timer0 + s * (reveal0 - timer0) / secs
        b = timer0 + (s + 1) * (reveal0 - timer0) / secs
        ev.append(_shape(5, a, b, fl._circle(70), _c(fl.GOLD), (CX - 70, timer_y - 70)))
        ev.append(kit.dialogue(6, a, b, "QzNum", rf"{{\an5\pos({CX},{timer_y + 2})\fscx140\fscy140"
                                                 rf"\t(0,180,\fscx100\fscy100)}}{secs - s}"))
    if q.explain.strip():
        ev.append(kit.dialogue(4, reveal0 + 0.2, end, "QzNote",
                               rf"{{\an5\pos({CX},{timer_y + 10})\fad(200,200)}}{_t(q.explain, 80)}"))
    return ev


def run(output_dir, pipeline):
    import seo_copy
    cfg = fl.settings()
    fmt = (os.environ.get("QUIZ_FORMAT") or "mcq").lower()
    fmt = fmt if fmt in FORMATS else "mcq"
    f = FORMATS[fmt]
    topic = (os.environ.get("QUIZ_TOPIC") or "").strip()[:80]
    print(f"🧠 Quiz short ({fmt}{', ' + topic if topic else ''}): writing and checking the questions...")
    client = kit.gemini()
    pictures = []
    if fmt == "flags":
        quiz, flag_pngs = write_flags(client, cfg["handle"])
        import flags
        pictures = [flags.card(p, os.path.join(output_dir, f".flag_{k}.png")) for k, p in enumerate(flag_pngs)]
        print(f"   ✅ {len(quiz.questions)} flags: {', '.join(q.answer_text for q in quiz.questions)}.")
    else:
        quiz = write(client, fmt, topic, cfg["handle"])
        print(f"   ✅ {len(quiz.questions)} questions passed the check.")
    try:
        number = max(0, int(os.environ.get("QUIZ_NUMBER") or 0))
    except ValueError:
        number = 0
    stem = kit.neutral_stem("Quiz")
    voice = os.environ.get("QUIZ_VOICE") or "Kore"
    lines = [quiz.hook_line]
    for k, q in enumerate(quiz.questions, 1):
        lines.append(q.question)
        lines.append(f"Sahi jawab: {q.answer_text}! {q.explain}")
    lines.append(quiz.outro_line)
    print(f"🎙️ Voicing {len(lines)} lines...")
    said = kit.voice_lines(client, [{"text": t, "voice": voice, "style": VOICE_STYLE} for t in lines],
                           output_dir, stem)
    if not any(p for p, _ in said):
        raise RuntimeError("The AI voice failed for every line; try again in a minute.")
    lens = [s or max(2.0, len(t.split()) / 2.6) for t, (_p, s) in zip(lines, said)]

    t, voices, caps, events, sfx, images = 0.4, [], [], [], [], []
    # Hook: the title pops in the middle.
    hook_end = t + lens[0] + GAP
    events.append(kit.dialogue(4, t, hook_end, "QzTitle",
                               rf"{{\an5\pos({CX},820)\fscx60\fscy60\t(0,260,\fscx105\fscy105)"
                               rf"\t(260,400,\fscx100\fscy100)\fad(0,200)}}{fl.clean_title(quiz.title)}"))
    events += _pill(t + 0.2, hook_end, 1040, (f"QUIZ #{number} | " if number else "") + f"{len(quiz.questions)} {f['label']}")
    if said[0][0]:
        voices.append((said[0][0], t))
    caps.append((lines[0], t, t + lens[0]))
    t = hook_end
    for k, q in enumerate(quiz.questions):
        qi, ri = 1 + 2 * k, 2 + 2 * k
        q0 = t
        sfx.append((kit.WHOOSH, 0.3, max(0.0, q0 - 0.15)))
        if said[qi][0]:
            voices.append((said[qi][0], q0 + 0.2))
        caps.append((lines[qi], q0 + 0.2, q0 + 0.2 + lens[qi]))
        timer0 = q0 + 0.2 + lens[qi] + 0.3
        reveal0 = timer0 + f["timer"]
        for s in range(f["timer"]):
            sfx.append((TICK, 0.12, timer0 + s))
        sfx.append((DING, 0.9, reveal0))
        if said[ri][0]:
            voices.append((said[ri][0], reveal0 + 0.15))
        caps.append((lines[ri], reveal0 + 0.15, reveal0 + 0.15 + lens[ri]))
        end = reveal0 + 0.15 + lens[ri] + 0.5
        events += question_events(k + 1, len(quiz.questions), f["label"], q, q0, timer0, reveal0, end,
                                  picture=bool(pictures))
        if pictures:
            images.append({"path": pictures[k], "t0": q0, "t1": end, "y": FLAG_Y, "zoom": 0.03})
        t = end
    o0 = t
    events.append(_flash(o0))
    events.append(kit.dialogue(4, o0, o0 + lens[-1] + 0.8, "QzTitle",
                               rf"{{\an5\pos({CX},800)\fs84\fscx60\fscy60\t(0,260,\fscx100\fscy100)}}"
                               rf"KITNE SAHI HUE?"))
    events += _pill(o0 + 0.3, o0 + lens[-1] + 0.8, 980, "COMMENT KARO")
    if said[-1][0]:
        voices.append((said[-1][0], o0 + 0.1))
    caps.append((lines[-1], o0 + 0.1, o0 + 0.1 + lens[-1]))
    body_end = o0 + lens[-1] + 0.8

    outro_s = cfg["outro_seconds"]
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)
    if total > 175:
        raise RuntimeError(f"The quiz came out {total:.0f}s long, over a Short's 3 minutes.")
    track = _bed()
    frame = []
    if cfg["handle"]:
        frame.append(kit.dialogue(1, 0, total, "QzSmall", rf"{{\an5\pos({CX},70)\alpha&H40&}}{cfg['handle']}"))
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    print(f"🎬 Rendering the quiz short ({total:.0f}s"
          + (f", music: {os.path.basename(track)}" if track else "") + ")...")
    kit.render(final, total, [cfg["bg"], kit.blend("#4C1D95", cfg["bg"], 0.35), kit.blend("#1E3A8A", cfg["bg"], 0.3)],
               kit.ambient_events(total) + frame + events + card_ev, STYLES, voices=voices,
               sfx=sfx + card_sfx, bed=(track, body_end) if track else None, images=images)
    transcript = kit.timed_transcript(caps)
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": quiz.title, "viral_hook_text": quiz.hook_line,
            "why": f"Quiz ({fmt}): {topic or 'mixed'}", "predicted_score": 85, "genre": "quiz",
            "ai_voice": "AI voice", "background_music": os.path.basename(track) if track else None,
            "comment_question": quiz.outro_line,
            "quiz": {"format": fmt, "topic": topic, "number": number,
                     "questions": ([f"flag:{q.answer_text}" for q in quiz.questions] if fmt == "flags"
                                   else [q.question for q in quiz.questions]),
                     "answers": [q.answer_text for q in quiz.questions]}}
    seo_copy.apply([clip], transcript, source_title=quiz.title,
                   context=SEO_CONTEXT.format(kind=FORMAT_TEXT[fmt], topic=topic or "mixed", n=len(quiz.questions))
                   + (f" It is the channel's daily quiz number {number}: start the title with \"Quiz #{number}:\"."
                      if number else ""),
                   text_limit=4000)
    # The question is on screen already: no burned captions.
    clip["captions"] = None
    kit.finish(output_dir, stem, [clip], transcript, pipeline, extra={"genre": "quiz"})


SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a quiz Short ({kind}, topic: {topic}) with "
               "exactly {n} questions (a score is out of {n}) and a countdown before each answer. Ignore the comedy phrases and hashtags above: use quiz "
               "searches instead ('gk quiz', 'general knowledge', 'quiz in urdu', 'paheliyan', 'riddles', "
               "'test your brain'). NEVER give away an answer in the title, description or tags: people "
               "must watch to find out. Ask viewers to comment their score. creator is \"\".")


def _bed():
    if os.environ.get("BG_MUSIC", "0") != "1":
        return None
    track = kit.music_track("quiz")
    if not track:
        import music_beds
        music_beds.ensure("quiz", 1)
        track = kit.music_track("quiz")
    return track
