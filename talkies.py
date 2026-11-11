"""Talking characters: lifelike talking babies and animals, and talking food and body organs, as YouTube Shorts and
Instagram Reels for Pakistani and Indian viewers. Owner, 10-nov-2026: one main channel, "real lifelike talking cats
and dogs", "animal or vegetables or organs speaking videos ... people making on insta", and "main issue is script ...
it must have hook and ending curiosity with a properly well organised story".

The script is made the way a writers' room works, never in one call:
1. PITCH: five different stories for the format, each a hook line, the unusual first picture, a twist and a curiosity
   ending.
2. RANK: an editor ranks them (scroll-stopping hook, curiosity, story, relatability); the top two are written.
3. WRITE: each becomes 2-3 shots (14-28 s) on a fixed beat sheet: HOOK (0-2 s) > SETUP > ESCALATION > TWIST >
   CURIOSITY ENDING.
4. CRITIC: a strict script editor scores each on seven points (hook, clarity, story, dialogue, ending, originality,
   visual) with line-level fixes. The best one is revised with those fixes while it misses the bar (BAR rounds).
5. CHECK: the safety rules, and for organs that every health statement is mainstream and harmless.

The video: one reference picture per character (OpenAI's image model while Gemini has no credit), then each shot is
one Gemini Omni 1.2 Flash reference-to-video call on fal.ai: the characters move and say their Roman-Urdu lines
aloud in Hindi-Urdu with lip-sync and natural sound. 360p is $0.0273 a second (fal's model page, 10-nov-2026), so a
20-second video is about $0.55; the shots are joined and made 1080x1920 on this laptop (Real-ESRGAN, free).

``python talkies.py sample <baby|pet|food|organ> [premise]`` makes one finished sample in output/samples/talkies
without uploading anything.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from typing import List

import httpx
from pydantic import BaseModel

import short_kit as kit
import toon_shorts as ts

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "talkies")
VIDEO_MODEL = os.environ.get("TALKIES_VIDEO_MODEL") or "google/gemini-omni-flash/v1.2/reference-to-video"
PRICE = {"360p": 0.0273, "720p": 0.0819, "1080p": 0.1229}  # $ per second on fal (model page, 10-nov-2026)
SIZE = {"360p": (360, 640), "720p": (720, 1280), "1080p": (1080, 1920)}
MIN_SHOTS, MAX_SHOTS = 2, 3
MIN_SECONDS, MAX_SECONDS = 14, 28           # the whole video: the talking-character Reels that spread are short
SHOT_MIN, SHOT_MAX = 4, 10                  # one shot (Omni keeps references for up to 10 s)
WORDS_PER_SECOND = 2.4                      # everyday Urdu speech, a little brisk
SHOT_WORDS = 20
LINE_WORDS = 12
HOOK_WORDS = 8
MAX_IN_SHOT = 2                             # characters seen in one shot (more and faces drift)
BAR_ROUNDS = 1                              # revisions of the chosen script while it misses the bar
FAL_QUEUE = "https://queue.fal.run/"
POLL = 8
WAIT = 20 * 60
PALETTE = ["#FFD23F", "#4FC3F7", "#FF8A65", "#A5D6A7"]

PHOTO_LOOK = ("Photorealistic, like real smartphone footage filmed by someone in the family: natural light, real "
              "skin, fur and fabric detail, shallow depth of field, a slight handheld feel. Real places in Pakistan. "
              "Mouths move naturally and exactly with the spoken words; bodies and faces react like real ones.")
CGI_LOOK = ("Hyper-realistic, glossy, high-end commercial look: real textures with a small expressive face (eyes, "
            "eyebrows, a mouth that moves exactly with the words) and tiny arms; filmed at the characters' scale with "
            "a macro lens; cinematic soft light. Never gory, no blood.")

FORMATS = {
    "baby": {
        "label": "lifelike talking babies",
        "world": ("A real-looking Pakistani baby or toddler (8-24 months) who talks and thinks like a grown-up desi "
                  "uncle or aunty, in a real middle-class Pakistani home, street, wedding or bazaar. Grown-ups (Ammi, "
                  "Abbu, Dadi, Chachu, the doodh wala) may be on screen and may speak."),
        "ideas": ("the baby's grown-up opinions on family life: rishta aunties, Abbu's cricket obsession, Ammi's rules, "
                  "load-shedding, wedding food, guests who never leave, cricket, older siblings' exams, grown-ups on "
                  "their phones, being blamed for things, money and pocket money"),
        "look": PHOTO_LOOK,
        "ref": "A photorealistic photo, like a sharp smartphone picture",
        "rules": "",
    },
    "pet": {
        "label": "lifelike talking animals",
        "world": ("Real-looking animals (a cat, a dog, a goat, a parrot, a hen, a cow, a buffalo, a donkey...) who "
                  "talk like desi family members about their life with the humans of the house. Humans may be on "
                  "screen and may speak."),
        "ideas": ("a pet's view of the family: who really runs the house, the fish in the fridge, Eid and the "
                  "goat's worry, the parrot that repeats secrets, the cat vs the new baby, the dog guarding the "
                  "gate from the doodh wala, the rooftop rivalry with the neighbour's cat"),
        "look": PHOTO_LOOK,
        "ref": "A photorealistic photo, like a sharp smartphone picture",
        "rules": "Animals are never hurt, sick, starving, caged cruelly or slaughtered; Eid jokes stay light.",
    },
    "food": {
        "label": "talking food, fruits and vegetables",
        "world": ("Talking fruits, vegetables and desi foods (aloo, pyaaz, tamatar, karela, bhindi, mirch, samosa, "
                  "jalebi, roti, chai, aam, kela...) living their own soap-opera lives in a Pakistani kitchen, "
                  "fridge, sabzi mandi or dastarkhwan."),
        "ideas": ("rivalries and drama among foods: aloo who is in every dish, karela nobody loves, pyaaz who makes "
                  "everyone cry, the samosa's secret, the last roti, the mango's summer fame, the chai's addiction "
                  "drama, the forgotten sabzi at the back of the fridge"),
        "look": CGI_LOOK,
        "ref": "A hyper-realistic character render",
        "rules": "",
    },
    "organ": {
        "label": "talking body organs",
        "world": ("A human body organ (heart, liver, kidney, stomach, lungs, brain, teeth, skin, eyes, gut, bones) "
                  "talks to 'you', the person it lives in, about ONE everyday desi habit (chai on an empty stomach, "
                  "late nights on the phone, too much sugar, oily paratha breakfasts, too little water, smoking, "
                  "sitting all day). The organ is dramatic, tired, sarcastic and funny, and what it says is true."),
        "ideas": "one everyday habit per episode, seen from the organ that pays for it",
        "look": CGI_LOOK + " The organ lives inside a stylised, warm-lit body interior.",
        "ref": "A hyper-realistic character render",
        "rules": ("Every health statement is mainstream advice that doctors everywhere agree on, general and "
                  "harmless: no statistics or numbers unless common knowledge, no diagnosis, no cure claims, no "
                  "medicine names, never telling anyone to stop or start a medicine or treatment, no scare tactics. "
                  "The organ never says it is dying or that the viewer will die."),
    },
}

# The series casts: the same faces and personalities every episode (one face builds a following, owner 10-nov-2026:
# baby, organ and food were liked). Looks follow the approved samples. Guests are made per episode.
RECURRING = {
    "guddu": {"name": "Guddu", "what": "a real 1-year-old Pakistani baby boy",
              "look": "chubby cheeks, big dark eyes, a small tuft of black hair, a white cotton kurta",
              "voice": "a cute toddler's voice that talks with the attitude of a grumpy 50-year-old uncle",
              "role": ("the star: a baby with a 50-year-old uncle's mind. Thinks he runs the family, guards his "
                       "'haq' (food, the remote, Ammi's lap), negotiates like a businessman, exposes grown-ups' "
                       "double standards, and is always one step ahead of them")},
    "ammi": {"name": "Ammi", "what": "a real Pakistani mother in her early thirties",
             "look": "long black hair in a low bun, a maroon cotton shalwar kameez with a printed dupatta, thin gold "
                     "bangles",
             "voice": "a warm but fed-up Pakistani mother's voice",
             "role": "Guddu's mother: busy, sharp, the only one who sometimes sees through him"},
    "abbu": {"name": "Abbu", "what": "a real Pakistani father in his mid thirties",
             "look": "short black hair, a neat beard, rectangular glasses, a light blue kurta",
             "voice": "a calm, tired Pakistani father's voice",
             "role": "Guddu's father: glued to cricket and his evening chai, always outsmarted by Guddu"},
    "dadi": {"name": "Dadi", "what": "a real Pakistani grandmother in her seventies",
             "look": "silver hair under a white dupatta, round gold glasses, a soft grey shalwar kameez",
             "voice": "a sweet, sly old woman's voice",
             "role": "Guddu's grandmother and secret partner in crime; spoils him and outplays everyone"},
    "dimagh": {"name": "Dimagh", "what": "a cute talking human brain character",
               "look": "a pink, glossy brain with tiny arms and legs, round black glasses, a blue polka-dot nightcap",
               "voice": "a fast-talking, nerdy, overthinking man's voice",
               "role": "the body's manager: overthinks everything, blames the other organs, secretly loves memes"},
    "dil": {"name": "Dil", "what": "a cute talking human heart character",
            "look": "a glossy red heart with tiny arms and legs, big expressive eyes, a small gold chain",
            "voice": "a dramatic, emotional filmi voice",
            "role": "the drama queen of the body: takes every habit personally, filmi dialogues, big feelings"},
    "liver": {"name": "Liver", "what": "a cute talking human liver character",
              "look": "a glossy reddish-brown liver with tiny arms and legs, a yellow hard hat, a tiny clipboard",
              "voice": "a tired, sarcastic factory-worker's voice",
              "role": "the overworked filter-factory worker: does all the dirty work, never thanked, deadpan"},
    "maida": {"name": "Maida", "what": "a cute talking human stomach character",
              "look": "a soft pink stomach with tiny arms and legs, a chef's apron, a wooden spoon",
              "voice": "a loud, hungry, cheeky aunty's voice",
              "role": "the stomach: loves desi food, hates timing mistakes (chai on an empty stomach, 2 am paratha)"},
    "tum": {"name": "Tum", "what": "a real young Pakistani man in his twenties",
            "look": "messy black hair, light stubble, a dark grey t-shirt, a phone always in hand",
            "voice": "a young man's lazy, guilty voice",
            "role": "'you', the body's owner: the habit-maker the organs talk to and about"},
    "samosa": {"name": "Shaan Samosa", "what": "a crispy talking samosa character",
               "look": "a golden-brown bubbly triangular samosa with a small face, tiny arms, black sunglasses",
               "voice": "a smooth, smug filmi hero's voice",
               "role": "the celebrity of every dastarkhwan: vain, loves attention, scared of the healthy food"},
    "aloo": {"name": "Aloo", "what": "a talking potato character",
             "look": "a round dusty-brown potato with a small face, tiny arms, a tiny gold crown",
             "voice": "a proud, bossy uncle's voice",
             "role": "in every dish and proud of it; thinks the kitchen is his kingdom"},
    "karela": {"name": "Karela", "what": "a talking bitter-gourd character",
               "look": "a bumpy bright-green karela with a small grumpy face, tiny arms, a tiny woollen cap",
               "voice": "a bitter, sarcastic old man's voice",
               "role": "nobody's favourite and knows it; bitter, honest, secretly the healthiest and wisest"},
    "pyaaz": {"name": "Pyaaz", "what": "a talking onion character",
              "look": "a shiny purple-red onion with a small face, tiny arms, teary sparkling eyes",
              "voice": "a dramatic, weepy soap-opera actress's voice",
              "role": "the drama queen: makes everyone cry, then cries the most herself"},
    "jalebi": {"name": "Jali Jalebi", "what": "a talking jalebi character",
               "look": "a bright-orange glossy jalebi spiral with a small face, tiny arms, a white paper bandana",
               "voice": "a squeaky, sugar-rush kid's voice",
               "role": "sweet, twisty and never straight with anyone; always has a secret"},
    "billo": {"name": "Billo", "what": "a real ginger tabby cat",
              "look": "bright orange-and-cream striped fur, green eyes, a white chest, a little bell on a red collar",
              "voice": "a sassy, dramatic young woman's voice", "role": "the cat who thinks she owns the house"},
    "sheru": {"name": "Sheru", "what": "a real desi street dog",
              "look": "short tan fur, a black muzzle, floppy ears, a blue collar",
              "voice": "a slow, deep, sleepy, goofy man's voice", "role": "the loyal, slow, lovable guard dog"},
}
RECURRING_IN = {"baby": ["guddu", "ammi", "abbu", "dadi"], "pet": ["billo", "sheru"],
                "food": ["samosa", "aloo", "karela", "pyaaz", "jalebi"],
                "organ": ["dimagh", "dil", "liver", "maida", "tum"]}
CHARACTER_FIELDS = ("name", "what", "look", "voice")

# Story angles that suit each series (a menu for the pitches, never a script).
ANGLES = {
    "baby": ["Guddu negotiates a deal with a grown-up and wins", "Guddu exposes a grown-up's double standard",
             "Guddu reviews a grown-up thing like a harsh critic", "Guddu vs a guest (rishta aunty, a visiting "
             "chachu, the neighbour)", "Guddu's secret business or plan in the house", "Guddu at a family event "
             "(shaadi, Eid, a birthday, a picnic)", "Guddu catches someone red-handed"],
    "organ": ["an organ complains to 'you' about one habit, and pays you back in a funny way",
              "the organs hold an office meeting and blame each other for a symptom", "an organ gives live "
              "commentary on what you are eating or doing right now", "an organ's revenge for a habit",
              "a rare thank-you: an organ is shocked you did something good, with a twist"],
    "food": ["a kitchen rivalry: two foods fight over who is the real star", "a food on trial in a kitchen court",
             "a dastarkhwan reality show where one dish gets eliminated", "the sabzi mandi gossip about a "
             "newcomer", "a food's secret is about to be exposed", "the last piece: who gets eaten first"],
    "pet": ["a pet's view of who really runs the house", "two pets plot against a new arrival"],
}
RECURRING["reporter"] = {"name": "Sana", "what": "a real young Pakistani TV reporter in her late twenties",
                         "look": "shoulder-length black hair, a pastel pink shirt, a black handheld microphone",
                         "voice": "a bright, fast TV reporter's voice",
                         "role": "the reporter who interviews Guddu and always loses the argument"}
RECURRING["pinky"] = {"name": "Pinky", "what": "a real 1-year-old Pakistani baby girl",
                      "look": "round cheeks, curly black hair with a small pink clip, a pink frock with white dots",
                      "voice": "a cute toddler girl's voice with the confidence of a TV anchor",
                      "role": "Guddu's cousin and podcast co-host: smarter than Guddu and loves to prove it"}
RECURRING_IN["baby"] += ["reporter", "pinky"]


def rules_for(fmt):
    """The channel's NEVER list. TALKIES_FOOD_ROMANCE=1 (the owner's call, asked 10-nov-2026: the biggest food hits
    are filmi love-triangle soaps) lets the food series use innocent filmi romance; everything sexual stays out."""
    if fmt == "food" and os.environ.get("TALKIES_FOOD_ROMANCE", "0") == "1":
        return re.sub(r"swearing, adult or romantic content \([^)]*\)", "swearing, adult content, anything sexual or "
                      "physical (innocent filmi romance, rishtas and family disapproval are fine)", RULES)
    return RULES

# The shapes the big talking-character Shorts use (research 10-nov-2026, YouTube sorted by views): babies are mostly
# Q&A punchlines ("Cute Baby Vs Reporter", 3.2M and 6.8M views, ~10 jokes a minute; a 10-second Urdu ice-cream joke,
# 2.3M); organs are an office comedy inside the body reacting to one habit ("Your Organs When You Eat Too Much
# Sugar", 5.4M; "Your Organs React to Late Night Snacks", 0.8M); food is filmi soap with Part 1/2/3 ("Kadhi Ka Dil
# Kachori Par Aaya ... Part 1", 3.2M) and pun banter on what each food is ("Tamatar aur bhindi ki ladai", 2.1M).
# shots and seconds are (min, max); beats replace the generic beat sheet for that shape.
SHAPES = {
    "baby": {
        "joke": {"shots": (1, 1), "seconds": (6, 12), "how": (
            "ONE shot, ONE joke: a grown-up (Ammi, Abbu, Dadi, a shopkeeper, a doctor, a reporter) asks Guddu "
            "something ordinary or says something ordinary to him, and Guddu answers with one punchline nobody saw "
            "coming."), "beats": (
            "1. SETUP (the first line, in the very first second): the ordinary question or remark; it is the hook, "
            "so make it a question every viewer has heard at home.\n2. PUNCHLINE (the last line, Guddu): the "
            "surprise answer, the funniest word at the very end. At most one short reaction line may follow it.")},
        "interview": {"shots": (3, 3), "seconds": (18, 28), "how": (
            "'Guddu ka interview': a reporter with a microphone (or a guest) asks Guddu three quick questions, one "
            "per shot; every answer is a punchline, each bigger than the last."), "beats": (
            "1. Shot 1: question 1 in the first second (the hook), Guddu's answer: a laugh.\n2. Shot 2: question 2, "
            "a bigger laugh.\n3. Shot 3: question 3, the biggest answer of all; it ends the video (a reveal or a "
            "question to the viewer).")},
        "podcast": {"shots": (2, 3), "seconds": (16, 28), "how": (
            "'Guddu Podcast': Guddu and his baby cousin Pinky sit with big podcast microphones and discuss one "
            "grown-up topic (rishta, school fees, petrol prices, the electricity bill) like serious experts; every line is a "
            "punchline; original dialogue only (never a real podcast's words)."), "beats": (
            "1. HOOK (the first second): the topic as an outrageous opinion.\n2. The other baby tops it.\n3. The "
            "final line flips it (often on the grown-ups) and ends the video.")},
        "story": {"shots": (2, 3), "seconds": (16, 26), "how": (
            "a mini story: Guddu wants something, a grown-up stands in the way, Guddu outsmarts them."),
            "beats": ""},
    },
    "organ": {
        "office": {"shots": (2, 3), "seconds": (16, 28), "how": (
            "the body is an office and Dimagh is the manager: one habit of Tum's arrives like a problem file; the "
            "organs it hits complain, blame each other and say what it really does to them in office talk (night "
            "shift, overtime, a complaint to HR, a salary cut); one or two true facts ride inside the jokes."),
            "beats": (
            "1. HOOK (the first second): the habit lands, an organ reacts in outrage.\n2. The complaint grows: a "
            "second organ joins or blames another; a true fact inside a joke.\n3. TWIST: the blame lands somewhere "
            "unexpected (often on Tum, or on Dimagh himself).\n4. CURIOSITY ENDING: the next problem arrives, or a "
            "question to the viewer.")},
        "timeline": {"shots": (3, 3), "seconds": (18, 28), "how": (
            "'what happens if you keep doing it': one habit of Tum's, three time jumps (aaj, ek hafta, ek mahina), "
            "one per shot; the organ it hits reacts more dramatically at each jump; true, mainstream facts only."),
            "beats": (
            "1. HOOK (the first second): the organ speaks straight to 'you' about the habit (day one).\n2. One "
            "week: worse, funnier, with one true fact.\n3. One month: the biggest reaction, then a one-line, "
            "harmless takeaway or a question to the viewer as the last line.")},
        "live": {"shots": (2, 3), "seconds": (16, 26), "how": (
            "live commentary: Tum does the habit right now, shot by shot, and the organ it hits reacts like a cricket "
            "commentator or a filmi victim; the true facts come out as the commentary."), "beats": ""},
    },
    "food": {
        "soap": {"shots": (3, 3), "seconds": (20, 28), "how": (
            "a filmi soap-opera episode among foods: rivalry, jealousy over who is the star, a secret, a lie found "
            "out, a dramatic reveal, with puns built from what each food really is (pyaaz makes everyone cry, aloo "
            "is in every dish, karela is bitter, bhindi is slim, the pressure cooker, the tawa); it ends on a part "
            "2 cliffhanger."), "beats": (
            "1. HOOK (the first second): a line from the middle of the drama.\n2. The secret or the lie, with a "
            "pun.\n3. The reveal: someone finds out.\n4. CLIFFHANGER: the next shock begins and the video cuts.")},
        "banter": {"shots": (1, 2), "seconds": (8, 18), "how": (
            "two foods trade quick taunts; every line is a pun on what the other one really is; the last line is "
            "the best burn."), "beats": (
            "1. The first taunt in the first second (the hook).\n2. The comeback, bigger.\n3. The final burn (the "
            "last line) that wins it.")},
        "court": {"shots": (3, 3), "seconds": (20, 28), "how": (
            "a kitchen court case: one food is accused of what it really does to people (chai keeps you up, mirch "
            "burns, jalebi's sugar), another food argues for it, Karela is the judge; funny arguments with true "
            "facts; a twist verdict."), "beats": (
            "1. HOOK: the charge, in the first second.\n2. The defence and the counter-attack.\n3. The twist "
            "verdict (the last line).")},
    },
    "pet": {"story": {"shots": (2, 3), "seconds": (16, 26), "how": "a pet's little story with a twist.",
                      "beats": ""}},
}

LAUGHS = """LAUGHS (the hits are joke machines, not short films):
- A laugh at least every 5-6 seconds; every shot ends on a laugh line or a reveal.
- Joke mechanisms that work for desi viewers:
  * a grown-up worry in a small mouth (prices, EMI, salary, rishta, exams, the electricity bill);
  * innocent literal logic: a word taken literally leads to a surprising, sweet conclusion;
  * a modern metaphor for an old thing (slow internet, downloading, battery low, WiFi password, an app update);
  * the savage comeback that turns the question back on the one who asked;
  * a pun on what a food or an organ really is or does (the onion's tears, the bitter karela, the liver's filter,
    the pressure cooker);
  * filmi melodrama over something tiny ("yeh shaadi nahi ho sakti" energy for a missing biscuit);
  * office or court language for the body or the kitchen (overtime, HR complaint, salary cut, objection, case)."""

CRAFT = """COMEDY CRAFT (how the best Reels writers work):
- The main character's personality drives every beat (what they want, their flaw); the plot comes from it.
- Rule of three: two beats set a pattern, the third breaks it.
- Specific beats generic: real desi details (the shaadi buffet's last gulab jamun, the UPS beep in load-shedding,
  Ammi's chappal, the cutting chai, the cricket score) instead of "food" or "a phone".
- End-weight: the funniest or most surprising word sits at the END of the line.
- Every line is a setup or a payoff; nothing explains the joke; no line repeats what we can see.
- The ending answers the hook's question in a way nobody expected, or opens a bigger one.
- Speech, not writing: short bursts, interruptions, "oye", "uff", "yaar", "acha?", English words as people use them
  (tension, scene, full, sorry, please); never bookish Urdu ("kyunkay", "lehaza", "albatta", "nihayat").
""" + LAUGHS

ENDINGS = {
    "cliffhanger": ("cut at the exact moment a reveal begins: the last line starts the reveal and the video ends "
                    "before it lands"),
    "part2": ("the story's big question stays open and the last line promises its answer in the next episode, in a "
              "specific way that names what will be revealed; never a vague 'part 2 dekho'"),
    "reveal": "the last line flips what we believed (the payoff) and at the same moment opens a new question",
    "loop": "the last line leads straight back into the first line, so the replay feels like the story going on",
    "verdict": ("a character turns to the viewer with a split-opinion question about the situation, one viewers "
                "will argue over in the comments"),
}

# Shapes only: with example sentences here, three of four sample scripts (10-nov-2026) opened on an example word for
# word ("Tum roz raat do baje mujhe jagate ho", a fridge with a missing egg). COPIED catches any that slip back.
HOOKS = """  - a confession: the character admits something they did that they should not have
  - an accusation, aimed at the viewer or at another character
  - a boast or claim that sounds impossible
  - a threat or an ultimatum
  - the middle of a fight: the first word is already angry
  - a mystery: something keeps happening and nobody knows why
  - straight at the viewer, calling out what they are doing right now"""
COPIED = ("uncle ice cream itni thandi kyun hoti hai", "phir isay bhi sardi lagti hogi",
          "internet slow tha late download hua hoon", "sirf rone se ghar nahi chalta",
          "maine aaj abbu ka phone pani mein phenk diya", "tum roz raat do baje mujhe jagate ho",
          "is ghar mein sab se ameer main hoon", "aaj agar karela bana main ghar chhod dunga",
          "bas remote ab mera hai", "fridge se roz ek anda ghaib hota hai", "haan tum jo chai pe chai pi rahe ho")

RULES = ("an animal or a baby hurt, sick, starving, abandoned, beaten, crying in pain or in real danger; gore or "
         "blood; a sad tear-jerker built to make viewers cry; real people, celebrities, politicians, cricketers or "
         "brands named or made fun of; religion, sects, prayers or holy things as a joke; politics, the army, "
         "India-Pakistan fights; jokes about any ethnic group, region, caste, skin colour, weight or disability; "
         "swearing, adult or romantic content (love affairs, flirting, dating, kissing; family rishta and shaadi "
         "comedy such as rishta aunties, wedding food or a chachu's rishta is fine, it is everyday family humour); "
         "violence beyond slapstick; copying any known show's characters, names or catchphrases")


def _int_env(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def resolution():
    r = (os.environ.get("TALKIES_VIDEO_RES") or "360p").strip().lower()
    return r if r in PRICE else "360p"


# ------------------------------------------------------------------ the script

class Character(BaseModel):
    key: str
    name: str
    what: str
    look: str
    voice: str


class Line(BaseModel):
    speaker: str
    text: str
    delivery: str


class Shot(BaseModel):
    who: List[str]
    setting: str
    action: str
    lines: List[Line]
    sound: str = ""


class Talkie(BaseModel):
    title: str
    hook_caption: str
    premise: str
    point: str
    characters: List[Character]
    shots: List[Shot]
    twist: str
    ending: str
    ending_note: str
    question: str
    shape: str = ""


class Pitch(BaseModel):
    premise: str
    hook_line: str
    hook_picture: str
    twist: str
    ending: str
    ending_line: str
    shape: str = ""


class Pitches(BaseModel):
    pitches: List[Pitch]


class Rank(BaseModel):
    order: List[int]
    why: str


class Scores(BaseModel):
    hook: int
    clarity: int
    story: int
    dialogue: int
    ending: int
    originality: int
    visual: int
    weakest: str
    fixes: List[str]


class Check(BaseModel):
    ok: bool
    problems: List[str]


class Joke(BaseModel):
    asker: str
    setup: str
    punchline: str
    mechanism: str


class Jokes(BaseModel):
    jokes: List[Joke]


class JokePitch(Pitch):
    """A pitch built from the joke bank: its jokes go into the script word for word."""
    jokes: List[Joke] = []


class JokePick(BaseModel):
    best: List[int]
    why: str


JOKE_SHAPES = ("joke", "interview")      # written from a joke bank, not from a story pitch

JOKES_PROMPT = """You are the sharpest joke writer of a hit Reels/Shorts channel for Pakistani and Indian viewers.
The star: Guddu, a real 1-year-old Pakistani baby with the mind of a grumpy 50-year-old uncle.
Write {n} DIFFERENT question-and-answer jokes. In each one a grown-up ({askers}) says or asks something ordinary that
every desi child hears at home (setup: Roman Urdu, {hook_words} words or fewer), and Guddu answers with ONE punchline
(Roman Urdu, {line_words} words or fewer). Build the punchline so its surprise lands at the end of the sentence, as
natural speech: never a word tacked on after the sentence. The laugh comes from the gap between his baby face and his
answer.
The quality bar: punchlines from Shorts with millions of views (NEVER reuse them, only match their level):
  "Uncle, ice cream itni thandi kyun hoti hai?" / "Freezer mein rakhte hain, beta." / "Phir isay bhi sardi lagti hogi."
  "Paida hone mein itna time kyun laga?" / "Internet slow tha, late download hua hoon."
  "Itne chhote ho, kaam kyun kar rahe ho?" / "Pampers ki keemat dekhi hai? Sirf rone se ghar nahi chalta."
Use these mechanisms, at least two jokes for each:
{mechanisms}
Setups people recognise at once work best: lines every desi child hears at home, such as {home_lines} (use them or
lines like them; the joke is Guddu's surprising flip of a familiar line).
Each joke: asker (the character key or a short English description of a guest), setup, punchline, mechanism.
Rules: original jokes only (never a known joke or a meme line), clean and family-friendly, never: {rules}.
Never repeat or rephrase these earlier jokes: {earlier}"""

JOKE_RANK_PROMPT = """You are the toughest comedy editor in Lahore. These are candidate jokes for a Reel of a talking
1-year-old Pakistani baby. Pick the {k} that would make the most desi viewers laugh out loud and send it to a friend:
a surprising punchline that lands at its end, instantly understood, relatable, not a stale joke. Never pick a joke
that needs explaining, sounds unnatural, or has a word stuck on after the sentence. Return best (joke numbers, best
first) and why (one sentence).

{jokes}"""

# Everyday lines every desi child hears: the setups people recognise at once (the joke is Guddu's flip of them).
HOME_LINES = ("Bara ho kar kya banoge?", "Doodh piyo, taaqat aayegi.", "Mehmanon ke saamne tameez se.",
              "Homework kar liya?", "Itna kyun rote ho?", "Salaam karo Phuppo ko.", "Sab kuch kha lo, plate saaf.",
              "Phone rakh do, aankhen kharab hongi.", "Jaldi so jao, subah school hai.", "Kisne toda yeh glass?",
              "Paise ped par nahi ugte.", "Tumhari umar mein hum...", "Chachu ke liye rishta dekh rahe hain.",
              "Bijli ka bill dekha hai?", "Naye kapde khud sambhal ke pehno.", "Bari Ammi ki dua lo.")

MECHANISMS = """- a grown-up worry in a small mouth (prices, EMI, salary, rishta, exams, the electricity bill)
- innocent literal logic: a word taken literally leads to a surprising, sweet conclusion
- a modern metaphor for an old thing (slow internet, downloading, battery low, WiFi password, an app update)
- the savage comeback that turns the question back on the one who asked"""


SCORE_KEYS = ("hook", "clarity", "story", "dialogue", "ending", "originality", "visual")

PITCH_PROMPT = """You are the head writer of a hit Instagram Reels / YouTube Shorts channel for Pakistani and Indian
viewers: {label}. {world}

Pitch FIVE different videos. Each one uses one of this series' SHAPES (spread the five across the shapes):
{shapes}
A story shape is a real little story (someone wants something, something stands in the way, it gets bigger, it
turns); a joke shape is one sharp setup and a punchline nobody sees coming. For each:
- shape: the shape's key.
- premise: one sentence: the situation (who wants what and what stands in the way, or the joke's setup).
- hook_line: the FIRST spoken line, Roman Urdu, {hook_words} words or fewer, said in the first second. It opens a
  question in the viewer's head that only the rest of the video answers. Shapes that work (never copy these words):
{hooks}
  Never a greeting, a name introduction or setting the scene.
- hook_picture: what the very first frame shows that is already unusual or funny (English, one sentence).
- twist: the turn nobody expects that still makes sense (one sentence).
- ending: one of {ending_keys}; ending_line: the last spoken line (Roman Urdu, {line_words} words or fewer).
Make the five truly different from each other (different situations, hooks and endings).
Ideas live in: {ideas}
Angles that work for this series (use different ones): {angles}
{format_rules}
{cast}
Earlier episodes (never repeat one): {earlier}
{premise_note}"""

RANK_PROMPT = """You are the editor of a Reels/Shorts channel for Pakistani and Indian viewers ({label}). Rank these
pitches for a 6-28 second video, best first, by: (1) would a fast scroller stop at the hook line and first picture
within 1.5 seconds; (2) the laugh: how funny is the punchline or twist, and would people send it to a friend;
(3) curiosity: does the viewer NEED to see how it ends, and does the ending make them replay, comment or follow;
(4) instantly relatable for desi viewers; (5) possible to show in its shape's continuous shots.
Return order (all pitch numbers 1-{n}, best first) and why (one sentence on the winner).

{pitches}"""

WRITE_PROMPT = """You are the head writer of a hit Reels/Shorts channel for Pakistani and Indian viewers: {label}.
{world}

Write this as a finished script.
THE PITCH: {pitch}
THE SHAPE ({shape}): {shape_how}

BEAT SHEET (organised exactly like this, every beat in order):
{beats}
The ending ("{ending}"): {ending_rule}. Never a moral, never "like aur subscribe", never "follow karo".

SHOTS: {lo}-{hi} shots, each ONE continuous shot of 4-10 seconds; {total} seconds in all.
- who: the 1-{max_in} characters SEEN in the shot (character keys). A character may speak from off screen.
- setting: where, specific (English: "a Lahore rooftop at sunset, laundry on the lines").
- action: 1-3 English sentences of what we SEE: movement, reactions, props, the camera (close-up for a punchline,
  push-in for a reveal). Physical comedy and real reactions; never two characters just standing and talking.
- lines: 0-3 spoken lines: speaker (a character key), text (natural spoken Roman Urdu / Hinglish in Latin letters, the
  way people in Lahore or Karachi really talk, everyday words Indians understand too; {line_words} words or fewer;
  specific and sharp, no filler like "arey yaar suno"), delivery (English: how it is said). At most {sw} words in a
  shot.
- sound: the sound effects in English (no music).
CHARACTERS: 1-3, each: key (one lowercase word), name, what (English, e.g. "a real ginger street cat"), look (English:
the details that keep them identical in every shot: colours, size, clothes, marks), voice (English, e.g. "a sleepy
deep man's voice").
{cast}
{craft}
{format_rules}
NEVER: {rules}.
Return: title (Roman Urdu, 4-9 words: the situation that makes people click, may end with one emoji; never giving
away the punchline), hook_caption (2-5 words of on-screen text for sound-off viewers, not the hook line itself and
never giving away the punchline or the twist), premise, point (the small truth the
story shows, one sentence), characters, shots, twist, ending (the key "{ending}"), ending_note (what the ending leaves
open, one sentence), question (a comment question with a one-word answer people will argue about, Roman Urdu).
{revise}"""

CRITIC_PROMPT = """You are the toughest script editor of a Reels/Shorts channel with millions of views among
Pakistani and Indian viewers ({label}). Score this script 1-10 on each point, honestly: 9-10 only for a script that
would go viral exactly as it is.
- hook: would a fast scroller stop within 1.5 seconds because of the first line AND the first picture? A greeting,
  an introduction or scene-setting scores 2. For the joke and interview shapes the hook is the first picture (a baby
  doing a grown-up thing) plus a setup line every viewer knows from home: judge whether it makes them wait for the
  answer, not whether the setup itself is dramatic (the hits open exactly like this).
- clarity: understood at once, one idea, clear who is who, works for sound-off viewers reading captions.
- story: well organised for its shape ({shape}): a story has want, obstacle, escalation and twist in order; a joke
  has a clean setup and a punchline that lands on the last word; no filler beat.
- dialogue: the LAUGHS: count the real laughs (fewer than one per shot is 6 at most); natural Roman Urdu as people
  really speak; short, specific, sharp; every line earns its place.
- ending: the last 2-3 seconds make viewers replay, comment or wait for the next part; no moral, no flat ending.
- originality: not a stale or obvious joke.
- visual: every shot is a strong picture with movement and reaction (not talking heads), possible as one continuous
  shot.
Then weakest (the single biggest problem) and fixes: 2-6 concrete, line-level changes ("shot 1's first line becomes:
...", "cut the second line of shot 2", "end on ... instead").
{format_rules}

SCRIPT:
{script}"""

PUNCH_PROMPT = """You are the dialogue doctor of a hit Reels/Shorts channel for Pakistani and Indian viewers ({label}):
the sharpest comedy dialogue writer in Lahore. The story below is LOCKED: the same shots, the same speakers in the
same order, the same number of lines in every shot, the same jokes, twist and ending. Rewrite ONLY the spoken lines
(text and delivery) so they sound exactly like real people talk and hit twice as hard:
- Shot 1's first line is the strongest scroll-stopping hook you can write ({hook_words} words or fewer): it opens a
  question the viewer needs answered.
- The last line lands the ending ("{ending}": {ending_rule}).
- Every line: {line_words} words or fewer, at most {sw} words in a shot, Roman Urdu in Latin letters.
{craft}
The editor's notes on the last version: {notes}
Return the whole script in the same JSON shape, everything except the lines unchanged.

SCRIPT:
{script}"""

CHECK_PROMPT = """You check a script for a family-friendly Reels/Shorts channel for Pakistani and Indian viewers.
Answer ok=false and list the problems if any line, picture or idea has: {rules}.{facts}
Otherwise ok=true and problems=[].

SCRIPT:
{script}"""


DEFAULT_BEATS = """1. HOOK (0-2 s, the first line of shot 1): spoken in the first second over an arresting first picture.
2. SETUP (by about 5 s): who wants what and what stands in the way, shown more than said.
3. ESCALATION (1-2 beats): each makes it bigger or reveals something new; never the same joke twice.
4. TWIST: the turn that changes what we thought.
5. CURIOSITY ENDING (the last 2-3 s)."""


def shape_of(fmt, key):
    """(key, shape) of ``fmt``: the named one, else the series' first shape."""
    shapes = SHAPES.get(fmt) or {"story": {"shots": (MIN_SHOTS, MAX_SHOTS), "seconds": (MIN_SECONDS, MAX_SECONDS),
                                           "how": "a little story with a twist.", "beats": ""}}
    key = (key or "").strip().lower()
    if key not in shapes:
        key = next(iter(shapes))
    return key, shapes[key]


def shapes_text(fmt):
    return "\n".join(f"- {k}: {v['how']} ({v['shots'][0]}-{v['shots'][1]} shots, {v['seconds'][0]}-"
                     f"{v['seconds'][1]} seconds)" for k, v in (SHAPES.get(fmt) or {}).items())


def seconds_of(shot):
    words = sum(len(l.text.split()) for l in shot.lines)
    return max(SHOT_MIN, min(SHOT_MAX, math.ceil(words / WORDS_PER_SECOND + 2.0)))


def total_seconds(ep):
    return sum(seconds_of(s) for s in ep.shots)


def script_text(ep):
    out = [f"SHAPE: {ep.shape or 'story'}", f"TITLE: {ep.title}", f"HOOK CAPTION: {ep.hook_caption}",
           f"PREMISE: {ep.premise}", f"POINT: {ep.point}",
           "CHARACTERS: " + "; ".join(f"{c.key} = {c.name}, {c.what} ({c.look}; voice: {c.voice})"
                                      for c in ep.characters)]
    for k, s in enumerate(ep.shots):
        out.append(f"SHOT {k + 1} ({seconds_of(s)} s) [{s.setting}; seen: {', '.join(s.who)}]: {s.action}"
                   + (f" SOUND: {s.sound}" if s.sound else ""))
        out += [f"   {l.speaker} ({l.delivery}): {l.text}" for l in s.lines]
    out += [f"TWIST: {ep.twist}", f"ENDING ({ep.ending}): {ep.ending_note}", f"QUESTION: {ep.question}"]
    return "\n".join(out)


def pitch_text(pitches):
    return "\n\n".join(f"PITCH {i + 1} ({p.shape or 'story'}): {p.premise}\n  hook line: {p.hook_line}\n"
                       f"  first picture: {p.hook_picture}\n"
                       f"  twist: {p.twist}\n  ending ({p.ending}): {p.ending_line}" for i, p in enumerate(pitches))


def tidy(ep, fmt):
    for c in ep.characters:
        c.key = re.sub(r"[^a-z0-9]", "", (c.key or "").lower()) or "x"
        if c.key in RECURRING:
            for f in CHARACTER_FIELDS:
                setattr(c, f, RECURRING[c.key][f])
    for s in ep.shots:
        s.who = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in s.who if (w or "").strip()]
        lines = []
        for l in s.lines:
            l.speaker = re.sub(r"[^a-z0-9]", "", (l.speaker or "").lower())
            l.text = re.sub(r"\s+", " ", l.text or "").strip()
            l.delivery = re.sub(r"\s+", " ", l.delivery or "").strip()[:80]
            if l.text:
                lines.append(l)
        s.lines = lines
    ep.ending = (ep.ending or "").strip().lower()
    return ep


def problems(ep):
    """What the code finds wrong: [] means it can be filmed."""
    import script_craft as craft
    out = []
    keys = [c.key for c in ep.characters]
    if not 1 <= len(keys) <= 3 or len(set(keys)) != len(keys):
        out.append(f"it has {len(keys)} characters (or a key twice): 1-3 different ones")
    (lo, hi), (s_lo, s_hi) = (MIN_SHOTS, MAX_SHOTS), (MIN_SECONDS, MAX_SECONDS)
    for shapes in SHAPES.values():
        if ep.shape in shapes:
            (lo, hi), (s_lo, s_hi) = shapes[ep.shape]["shots"], shapes[ep.shape]["seconds"]
            break
    if not lo <= len(ep.shots) <= hi:
        out.append(f"it has {len(ep.shots)} shots: the {ep.shape or 'story'} shape takes {lo}-{hi}")
    total = total_seconds(ep)
    if not s_lo <= total <= s_hi:
        out.append(f"it runs ~{total} s: the {ep.shape or 'story'} shape takes {s_lo}-{s_hi} s of shots")
    if ep.ending not in ENDINGS:
        out.append(f"ending '{ep.ending}' is not one of {', '.join(ENDINGS)}")
    speakers = set()
    for k, s in enumerate(ep.shots):
        tag = f"shot {k + 1}"
        if not 1 <= len(s.who) <= MAX_IN_SHOT or len(set(s.who)) != len(s.who):
            out.append(f"{tag} shows {len(s.who)} characters: 1-{MAX_IN_SHOT} different ones")
        bad = [w for w in s.who if w not in keys]
        if bad:
            out.append(f"{tag} shows {', '.join(bad)}, who is not in the characters")
        if len((s.action or "").split()) < 6:
            out.append(f"{tag}: the action says too little of what we see")
        if len(s.lines) > 3:
            out.append(f"{tag} has {len(s.lines)} lines: 3 at most")
        words = sum(len(l.text.split()) for l in s.lines)
        if words > SHOT_WORDS:
            out.append(f"{tag} has {words} words: {SHOT_WORDS} at most (it must fit 10 seconds)")
        for l in s.lines:
            if l.speaker not in keys:
                out.append(f"{tag}: speaker '{l.speaker}' is not a character key")
                continue
            speakers.add(l.speaker)
            if len(l.text.split()) > LINE_WORDS:
                out.append(f"{tag}: a line has {len(l.text.split())} words: {LINE_WORDS} or fewer")
            if ts.NON_LATIN.search(l.text):
                out.append(f"{tag}: a line is not in Latin letters")
            hits = craft.banned_hits(l.text)
            if hits:
                out.append(f"{tag}: stale phrases {', '.join(hits)}")
    first = ep.shots[0].lines[0].text if ep.shots and ep.shots[0].lines else ""
    if not first:
        out.append("shot 1 has no line: the hook is spoken in the first second")
    elif len(first.split()) > HOOK_WORDS:
        out.append(f"the hook line has {len(first.split())} words: {HOOK_WORDS} or fewer")
    for s in ep.shots:
        for l in s.lines:
            said = re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", l.text.lower())).strip()
            if said and any(c in said for c in COPIED):
                out.append(f"'{l.text}' copies an example from the brief: write a new, original line")
    if ep.shots and not ep.shots[-1].lines:
        out.append("the last shot has no line: the curiosity ending is spoken")
    if ts.NON_LATIN.search(ep.title + " " + ep.hook_caption + " " + ep.question):
        out.append("the title, hook caption or question is not in Latin letters")
    if first and ep.hook_caption.strip().lower() == first.strip().lower():
        out.append("the hook caption repeats the hook line: write a different 2-5 word caption")
    if ep.shape in JOKE_SHAPES and ep.shots and ep.shots[-1].lines:
        # "Diapers on EMI?" over "... warna diapers EMI par leni padengi" told the joke before it was told (10-nov).
        names = {w.lower() for c in ep.characters for w in c.name.split()}
        cap = {w for w in re.findall(r"[a-z]{4,}", ep.hook_caption.lower()) if w not in names}
        if cap & set(re.findall(r"[a-z]{4,}", ep.shots[-1].lines[-1].text.lower())):
            out.append("the hook caption gives away the punchline: tease the situation instead")
    return out


def passes(sc):
    # Raised 10-nov-2026 after the first samples (all 7+ was met by scripts the owner still found weak).
    return min(getattr(sc, k) for k in SCORE_KEYS) >= 8 and sc.hook >= 8 and sc.ending >= 8


def total_score(sc):
    return sum(getattr(sc, k) for k in SCORE_KEYS)


def _ask(client, schema, prompt, best=True):
    import ai_fallback
    if best:
        with ai_fallback.best_writer():
            return kit.ask_json(client, schema, prompt, model=ts._model())
    return kit.ask_json(client, schema, prompt, model=ts._model())


def _common(fmt):
    f = FORMATS[fmt]
    stars = RECURRING_IN.get(fmt) or []
    cast = ("THE SERIES CAST (build every story around 1-2 of them, with these exact keys; their looks and voices "
            "are fixed; at most one new guest character per episode):\n"
            + "\n".join(f"- {k} = {RECURRING[k]['name']}, {RECURRING[k]['what']}: {RECURRING[k]['role']}"
                        for k in stars)) if stars else ""
    rules = ("FORMAT RULES: " + f["rules"]) if f["rules"] else ""
    return f, cast, rules


def pitches(client, fmt, premise="", earlier=()):
    f, cast, rules = _common(fmt)
    note = (f"Build all five around this idea from the owner: {premise}" if premise else "")
    got = _ask(client, Pitches, PITCH_PROMPT.format(
        label=f["label"], world=f["world"], hook_words=HOOK_WORDS, hooks=HOOKS, ending_keys=", ".join(ENDINGS),
        line_words=LINE_WORDS, ideas=f["ideas"], angles="; ".join(ANGLES.get(fmt, [])) or "any",
        shapes=shapes_text(fmt) or "- story: a little story with a twist",
        format_rules=rules, cast=cast,
        earlier="; ".join(list(earlier)[-30:]) or "none yet", premise_note=note), best=False)
    return [p for p in got.pitches if p.premise and p.hook_line][:5]


def rank(client, fmt, ps):
    if len(ps) < 2:
        return ps
    try:
        r = _ask(client, Rank, RANK_PROMPT.format(label=FORMATS[fmt]["label"], n=len(ps), pitches=pitch_text(ps)))
        order = [i - 1 for i in r.order if 1 <= i <= len(ps)]
        order += [i for i in range(len(ps)) if i not in order]
        return [ps[i] for i in dict.fromkeys(order)]
    except Exception:  # noqa: BLE001 — the writer's order then
        return ps


def joke_pitch(client, fmt, shape, earlier=(), log=print):
    """A Pitch for a joke shape built from a bank of 12 jokes and an editor's pick (comedy is written by volume:
    the joke-shape baby script written straight from a pitch scored 49/70 on 10-nov-2026, its punchline mid-shot)."""
    k = 3 if shape == "interview" else 1
    # An interview has one asker, the reporter (like the "Baby vs Reporter" hits); three askers broke the cast limit.
    askers = ("Sana the TV reporter, always her" if shape == "interview" else
              "Ammi, Abbu, Dadi, Sana the TV reporter, or a guest such as a doctor, a shopkeeper or a teacher")
    prompt = JOKES_PROMPT.format(
        n=12, askers=askers, hook_words=HOOK_WORDS, line_words=LINE_WORDS, mechanisms=MECHANISMS,
        home_lines="; ".join(f'"{h}"' for h in HOME_LINES), rules=rules_for(fmt),
        earlier="; ".join(list(earlier)[-40:]) or "none yet")
    # The jokes are the whole video: they get the model's deepest thinking (a few cents more, one call).
    old = os.environ.get("OPENAI_REASONING")
    os.environ["OPENAI_REASONING"] = os.environ.get("TALKIES_JOKE_REASONING") or "high"
    try:
        bank = _ask(client, Jokes, prompt).jokes
    finally:
        if old is None:
            os.environ.pop("OPENAI_REASONING", None)
        else:
            os.environ["OPENAI_REASONING"] = old
    bank = [j for j in bank if j.setup.strip() and j.punchline.strip()]
    if len(bank) < k:
        return None
    listing = "\n".join(f"{i + 1}. ({j.asker}) {j.setup} / Guddu: {j.punchline}" for i, j in enumerate(bank))
    try:
        pick = _ask(client, JokePick, JOKE_RANK_PROMPT.format(k=k, jokes=listing))
        order = [i - 1 for i in pick.best if 1 <= i <= len(bank)]
    except Exception:  # noqa: BLE001 — the writer's order then
        order = []
    order = list(dict.fromkeys(order + list(range(len(bank)))))[:k]
    chosen = [bank[i] for i in order]
    if shape == "interview":
        chosen = chosen[1:] + chosen[:1]                     # the best answer last: it ends the video
    log("   😂 Jokes picked: " + " | ".join(f"{j.setup} / {j.punchline}" for j in chosen))
    lines = " ".join(f"Q{i + 1} ({j.asker}): \"{j.setup}\" Guddu: \"{j.punchline}\"" for i, j in enumerate(chosen))
    return JokePitch(shape=shape, premise=f"Use these exact lines, word for word, in this order, one question and "
                     f"answer per shot: {lines}", hook_line=chosen[0].setup,
                     hook_picture=f"Guddu facing {chosen[0].asker}, a serious grown-up look on his baby face",
                     twist=chosen[-1].punchline, ending="reveal", ending_line=chosen[-1].punchline, jokes=chosen)


def _asker_key(asker, ep, shot):
    """The character key who says the setup: named in ``asker``, else the shot's grown-up, else any grown-up."""
    keys = [c.key for c in ep.characters]
    words = re.sub(r"[^a-z ]", " ", (asker or "").lower()).split()
    for k in keys:
        if k != "guddu" and (k in words or any(w in k for w in words if len(w) > 3)):
            return k
    for c in ep.characters:
        if c.key != "guddu" and any(w in (c.name + " " + c.what).lower() for w in words if len(w) > 3):
            return c.key
    return next((w for w in shot.who if w != "guddu"), next((k for k in keys if k != "guddu"), None))


def with_jokes(ep, jp):
    """``ep`` with the bank's jokes as its lines, word for word (one Q&A per shot), or None when its shape does not
    fit them."""
    if len(ep.shots) != len(jp.jokes) or "guddu" not in [c.key for c in ep.characters]:
        return None
    out = ep.model_copy(deep=True)
    for s, j in zip(out.shots, jp.jokes):
        who = _asker_key(j.asker, out, s)
        if who is None:
            return None
        if "guddu" not in s.who and len(s.who) < MAX_IN_SHOT:
            s.who.append("guddu")
        ask = next((l.delivery for l in s.lines if l.speaker == who), "asking, an ordinary grown-up tone")
        ans = next((l.delivery for l in s.lines if l.speaker == "guddu"), "deadpan, a grumpy uncle's timing")
        s.lines = [Line(speaker=who, text=j.setup.strip(), delivery=ask),
                   Line(speaker="guddu", text=j.punchline.strip(), delivery=ans)]
    out.ending = "reveal"
    return out


def write_joke(client, fmt, jp, log=print):
    """(script, scores) of a joke-bank pitch: the scene is written around the jokes, which stay word for word (no
    revision or polish pass that could rewrite them)."""
    ep = None
    for attempt in range(3):
        base = ts._safe(lambda: draft(client, fmt, jp, _revision(ep, found=problems(ep)[:8]) if ep else ""))
        new = with_jokes(base, jp) if base is not None else None
        if new is not None:
            ep = new
            if not problems(ep):
                break
            log(f"   ✏️ Joke scene has {len(problems(ep))} problem(s): {problems(ep)[0][:90]}")
    if ep is None or problems(ep):
        raise RuntimeError("The joke's scene did not pass the checks; made again later.")
    sc = critique(client, fmt, ep)
    log(f"   🧐 Joke script scored {total_score(sc)}/70 (hook {sc.hook}, ending {sc.ending}): {ep.title}")
    return ep, sc


def draft(client, fmt, p, revise=""):
    f, cast, rules = _common(fmt)
    ending = p.ending if p.ending in ENDINGS else "reveal"
    story = (f"{p.premise} Hook line: \"{p.hook_line}\". First picture: {p.hook_picture}. Twist: {p.twist}. "
             f"Ending line: \"{p.ending_line}\".")
    shape, sh = shape_of(fmt, p.shape)
    ep = _ask(client, Talkie, WRITE_PROMPT.format(
        label=f["label"], world=f["world"], pitch=story, shape=shape, shape_how=sh["how"],
        beats=sh.get("beats") or DEFAULT_BEATS, ending=ending, ending_rule=ENDINGS[ending],
        lo=sh["shots"][0], hi=sh["shots"][1], max_in=MAX_IN_SHOT, total=f"{sh['seconds'][0]}-{sh['seconds'][1]}",
        line_words=LINE_WORDS, sw=SHOT_WORDS, cast=cast, craft=CRAFT, format_rules=rules, rules=rules_for(fmt),
        revise=revise))
    ep = tidy(ep, fmt)
    ep.shape = shape
    if ep.ending not in ENDINGS:
        # The writer put a sentence there (sample 10-nov-2026: "part 2: billo batayegi ..."): the pitch's key wins and
        # the sentence still says what is left open.
        ep.ending_note = ep.ending_note or ep.ending
        ep.ending = next((k for k in ENDINGS if ep.ending.replace(" ", "").startswith(k)), ending)
    return ep


def critique(client, fmt, ep):
    _f, _cast, rules = _common(fmt)
    # TALKIES_CRITIC=mini scores on the small model: about a quarter of the writing cost (a GPT-5 call averaged
    # $0.04 on 10-nov-2026, mostly its thinking), with a less reliable editor.
    return _ask(client, Scores, CRITIC_PROMPT.format(label=FORMATS[fmt]["label"], format_rules=rules,
                                                     shape=ep.shape or "story", script=script_text(ep)),
                best=os.environ.get("TALKIES_CRITIC", "best") != "mini")


def punch_up(client, fmt, ep, sc=None):
    """``ep`` with only its spoken lines rewritten by the dialogue doctor (the editor's most common note on the
    first samples, 10-nov-2026: the dialogue reads written, not spoken), or None when the shape changed."""
    f, _cast, _rules = _common(fmt)
    notes = "; ".join([sc.weakest] + list(sc.fixes)) if sc is not None else "none"
    new = _ask(client, Talkie, PUNCH_PROMPT.format(
        label=f["label"], hook_words=HOOK_WORDS, ending=ep.ending, ending_rule=ENDINGS.get(ep.ending, ""),
        line_words=LINE_WORDS, sw=SHOT_WORDS, craft=CRAFT, notes=notes, script=script_text(ep)))
    new = tidy(new, fmt)
    if len(new.shots) != len(ep.shots) or any(len(a.lines) != len(b.lines) for a, b in zip(new.shots, ep.shots)):
        return None
    out = ep.model_copy(deep=True)
    for s, n in zip(out.shots, new.shots):
        for old, line in zip(s.lines, n.lines):
            old.text, old.delivery = line.text, line.delivery or old.delivery
    return out


def _revision(ep, sc=None, found=()):
    notes = list(found)
    if sc is not None:
        notes = [f"The biggest problem: {sc.weakest}"] + list(sc.fixes) + notes
    return ("\nREVISE THE LAST VERSION (keep what works, fix exactly these):\n" + script_text(ep)
            + "\nNOTES:\n- " + "\n- ".join(n for n in notes if n))


def _fixed(client, fmt, p, ep, log):
    """``ep`` with the code's problems fixed (up to two more drafts), or None."""
    for _ in range(2):
        if ep is None or not problems(ep):
            break
        log(f"   ✏️ Draft has {len(problems(ep))} problem(s); fixing: {problems(ep)[0][:90]}")
        ep = ts._safe(lambda ep=ep: draft(client, fmt, p, _revision(ep, found=problems(ep)[:10])))
    return ep if ep is not None and not problems(ep) else None


def part2_note(prev):
    """The brief for the episode that keeps the last one's "part 2" promise."""
    cast = "; ".join(f"{c.key} = {c.name}, {c.what} ({c.look}; voice: {c.voice})" for c in prev.characters)
    return (f"THIS IS PART 2 of the last episode, \"{prev.title}\" ({prev.premise} It ended: {prev.ending_note}). "
            f"Use exactly the same characters with the same keys: {cast}. The hook pays off the open question at "
            "once (in the first 2 seconds), then the story takes a NEW turn and ends on a fresh curiosity ending "
            "that is not another part 2.")


def _same_cast(ep, prev):
    """Part 2's characters look and sound exactly as in part 1."""
    if prev is None:
        return ep
    old = {c.key: c for c in prev.characters}
    for c in ep.characters:
        if c.key in old:
            c.name, c.what, c.look, c.voice = old[c.key].name, old[c.key].what, old[c.key].look, old[c.key].voice
    if ep.ending == "part2":
        ep.ending = "reveal"
    if "part 2" not in ep.title.lower():
        ep.title = f"{ep.title} (Part 2)"
    return ep


def write(client, fmt, premise="", earlier=(), log=print, follow=None):
    """(script, scores): pitches, ranked, the top two written, critiqued, the best revised to the bar, checked.
    ``follow``: the earlier episode whose part-2 promise this one keeps. Raises when nothing passes."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt}: {', '.join(FORMATS)}")
    if follow is not None:
        premise = part2_note(follow)
    ps = pitches(client, fmt, premise, earlier)
    if follow is not None:
        for p in ps:
            if p.ending == "part2":
                p.ending = "reveal"
    if not ps:
        raise RuntimeError("No story pitches came back (or the AI is down); made again later.")
    ps = rank(client, fmt, ps)
    forced = (os.environ.get("TALKIES_SHAPE") or "").strip().lower()
    if forced in (SHAPES.get(fmt) or {}):
        for p in ps:
            p.shape = forced
    top = ps[:2]
    if fmt == "baby" and follow is None:
        for i, p in enumerate(top):
            if p.shape in JOKE_SHAPES:
                jp = ts._safe(lambda p=p: joke_pitch(client, fmt, p.shape, earlier, log))
                if jp is not None:
                    top[i] = jp
                break
    log(f"   💡 Best pitch: {top[0].premise[:120]}")
    jp = next((p for p in top if isinstance(p, JokePitch)), None)
    if jp is not None:
        ep, sc = write_joke(client, fmt, jp, log)
        check = _ask(client, Check, CHECK_PROMPT.format(rules=rules_for(fmt), facts="", script=script_text(ep)))
        if not check.ok:
            # The scene is rewritten once on the check's notes; the jokes stay word for word (10-nov-2026: a baby
            # holding loose remote batteries, a choking risk, stopped a joke script).
            log(f"   🛡️ The safety check found: {'; '.join(check.problems[:2])[:160]}; rewriting the scene.")
            base = ts._safe(lambda: draft(client, fmt, jp, _revision(
                ep, found=["SAFETY (must be fixed): " + x for x in check.problems[:5]])))
            safe = with_jokes(base, jp) if base is not None else None
            if safe is not None and not problems(safe):
                check = _ask(client, Check, CHECK_PROMPT.format(rules=rules_for(fmt), facts="",
                                                               script=script_text(safe)))
                if check.ok:
                    return safe, sc
            raise RuntimeError("The script check found: " + "; ".join(check.problems[:3])[:300])
        return ep, sc
    done = []
    for p in top:
        ep = _fixed(client, fmt, p, ts._safe(lambda p=p: draft(client, fmt, p)), log)
        if ep is None:
            continue
        sc = ts._safe(lambda ep=ep: critique(client, fmt, ep))
        if sc is not None:
            done.append((p, ep, sc))
            log(f"   🧐 Draft scored {total_score(sc)}/70 (hook {sc.hook}, ending {sc.ending}): {ep.title}")
    if not done:
        raise RuntimeError("No script passed the checks (or the AI is down); made again later.")
    p, ep, sc = max(done, key=lambda d: total_score(d[2]))
    for _ in range(BAR_ROUNDS):
        if passes(sc):
            break
        log(f"   ✏️ Revising (weakest: {sc.weakest[:100]})")
        new = _fixed(client, fmt, p, ts._safe(lambda: draft(client, fmt, p, _revision(ep, sc))), log)
        new_sc = ts._safe(lambda: critique(client, fmt, new)) if new is not None else None
        if new_sc is None:
            break
        log(f"   🧐 Revision scored {total_score(new_sc)}/70 (hook {new_sc.hook}, ending {new_sc.ending})")
        if total_score(new_sc) >= total_score(sc):
            ep, sc = new, new_sc
    polished = ts._safe(lambda: punch_up(client, fmt, ep, sc))
    if polished is not None and not problems(polished):
        p_sc = ts._safe(lambda: critique(client, fmt, polished))
        if p_sc is not None:
            log(f"   🎤 Dialogue polish scored {total_score(p_sc)}/70 (dialogue {sc.dialogue} > {p_sc.dialogue})")
            if total_score(p_sc) >= total_score(sc):
                ep, sc = polished, p_sc
    ep = _same_cast(ep, follow)
    facts = (" For health content also: " + FORMATS[fmt]["rules"]) if fmt == "organ" else ""
    check = _ask(client, Check, CHECK_PROMPT.format(rules=rules_for(fmt), facts=facts, script=script_text(ep)))
    if not check.ok:
        # One revision on the check's notes before giving up (sample 10-nov-2026: a baby sniffing a hot cup of tea
        # and "Sherlock-style" stopped a 57/70 script).
        log(f"   🛡️ The safety check found: {'; '.join(check.problems[:2])[:160]}; revising.")
        safe = _fixed(client, fmt, p, ts._safe(lambda: draft(client, fmt, p, _revision(
            ep, found=["SAFETY (must be fixed): " + x for x in check.problems[:5]]))), log)
        if safe is not None:
            safe = _same_cast(safe, follow)
            again = _ask(client, Check, CHECK_PROMPT.format(rules=rules_for(fmt), facts=facts, script=script_text(safe)))
            if again.ok:
                return safe, ts._safe(lambda: critique(client, fmt, safe)) or sc
            check = again
        raise RuntimeError("The script check found: " + "; ".join(check.problems[:3])[:300])
    return ep, sc


# ------------------------------------------------------------------ fal.ai

def fal_key():
    import ai_influencer
    return ai_influencer.key()


def _fal_error(status, text):
    t = (text or "")[:300]
    if status in (401, 403) and re.search(r"balance|locked|billing|credit", t, re.I):
        return RuntimeError("fal.ai has no credit left: top up at fal.ai (Billing). " + t[:120])
    return RuntimeError(f"fal said {status}: {t}")


def _download(url, out):
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as v:
        v.raise_for_status()
        with open(out, "wb") as f:
            for block in v.iter_bytes(1 << 20):
                f.write(block)
    return out


def fal_video(endpoint, payload, out, sleep=time.sleep):
    """Runs one fal video job and saves its video at ``out``."""
    body = fal_job(endpoint, payload, sleep)
    url = (body.get("video") or {}).get("url") if isinstance(body, dict) else None
    if not url:
        raise _fal_error(200, f"no video in the answer: {str(body)[:200]}")
    return _download(url, out)


def fal_image(prompt, out, sleep=time.sleep):
    """A 9:16 picture from fal's image model (Flux 2 Flash, $0.005 a megapixel, 10-nov-2026) saved as PNG at
    ``out``: the reference pictures' fallback when OpenAI's image filter refuses a character (a cartoon eye, 10-nov)."""
    from PIL import Image
    endpoint = os.environ.get("TALKIES_IMAGE_MODEL") or "fal-ai/flux-2/flash"
    body = fal_job(endpoint, {"prompt": prompt, "image_size": {"width": 768, "height": 1344}, "num_images": 1,
                              "output_format": "png"}, sleep)
    images = body.get("images") if isinstance(body, dict) else None
    if not images or not images[0].get("url"):
        raise _fal_error(200, f"no picture in the answer: {str(body)[:200]}")
    _download(images[0]["url"], out + ".dl")
    Image.open(out + ".dl").convert("RGB").save(out, "PNG")
    os.remove(out + ".dl")
    return out


def fal_job(endpoint, payload, sleep=time.sleep):
    """Submits one fal queue job, waits for it, returns its answer (a dict)."""
    auth = {"Authorization": f"Key {fal_key()}"}
    r = httpx.post(FAL_QUEUE + endpoint, headers={**auth, "Content-Type": "application/json"}, json=payload,
                   timeout=60)
    if r.status_code >= 400:
        raise _fal_error(r.status_code, r.text)
    job = r.json()
    status_url, response_url = job["status_url"], job["response_url"]
    waited = 0
    while True:
        s = httpx.get(status_url, headers=auth, timeout=60)
        if s.status_code >= 400:
            raise _fal_error(s.status_code, s.text)
        state = s.json()
        if state.get("status") == "COMPLETED":
            break
        if waited >= WAIT:
            httpx.put(job.get("cancel_url") or status_url, headers=auth, timeout=30)
            raise TimeoutError(f"fal did not finish in {WAIT // 60} min")
        sleep(POLL)
        waited += POLL
    res = httpx.get(response_url, headers=auth, timeout=60)
    body = res.json() if res.content else {}
    # A failed job also says COMPLETED; the error is in the answer.
    if res.status_code >= 400 or state.get("error"):
        raise _fal_error(res.status_code, str(state.get("error") or body))
    return body


def fal_upload(path):
    import ai_influencer
    return ai_influencer.upload(path, "image/png")


# ------------------------------------------------------------------ budget

def _spend_file():
    return os.path.join(STATE_DIR, "video_spend.json")


def _spend():
    try:
        with open(_spend_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def spent_today():
    return float((_spend().get(time.strftime("%Y-%m-%d")) or {}).get("seconds", 0))


def _add_spend(seconds):
    d = _spend()
    day = time.strftime("%Y-%m-%d")
    row = d.get(day) or {"seconds": 0, "usd": 0.0, "clips": 0}
    d[day] = {"seconds": row["seconds"] + seconds, "clips": row.get("clips", 0) + 1,
              "usd": round(row["usd"] + seconds * PRICE[resolution()], 3)}
    d = {k: d[k] for k in sorted(d)[-60:]}
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _spend_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, _spend_file())


# ------------------------------------------------------------------ the video

def cast_dir():
    return os.path.join(STATE_DIR, "cast")


def ref_picture(client, fmt, c, work, kept=None):
    """The character's reference picture: kept for the recurring stars, reused from part 1 (``kept``), else made
    for this video."""
    if kept and c.key not in RECURRING and os.path.isfile(os.path.join(kept, f"{c.key}.png")):
        return os.path.join(kept, f"{c.key}.png")
    path = os.path.join(cast_dir(), f"{c.key}.png") if c.key in RECURRING else os.path.join(work, f"ref_{c.key}.png")
    if os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tail = ("The whole character is in frame, facing the camera, on a plain, softly lit neutral background. Vertical "
            "9:16. No text, no logo, no watermark. Not a real or famous person.")
    prompt = f"{FORMATS[fmt]['ref']} of {c.what}: {c.look}. {tail}"
    # Gentler words for the second try: OpenAI refused "a giant cartoon eye organ ... red bags" (10-nov-2026).
    soft = (f"A friendly, cute, wholesome character with realistic textures, inspired by {c.what}: {c.look}. Clean "
            f"and family-friendly: no blood, no veins, no wounds, no realistic anatomy. {tail}")
    tmp = path + ".new.png"
    try:
        ts._image(client, prompt, tmp)
    except Exception as e:  # noqa: BLE001 — fal draws it instead
        refused = re.search(r"moderation|safety", str(e), re.I)
        print(f"   ⚠️ The picture of {c.name} failed ({'refused by the image filter' if refused else type(e).__name__});"
              " drawing it on fal.")
        fal_image(soft if refused else prompt, tmp)
    os.replace(tmp, path)
    return path


def shot_prompt(ep, k, fmt):
    """The text of shot ``k``: its references are passed as pictures, in the order of ``s.who``."""
    s = ep.shots[k]
    chars = {c.key: c for c in ep.characters}
    refs = "; ".join(f"picture {i + 1} is {chars[w].name}, {chars[w].what}" for i, w in enumerate(s.who))
    talk = []
    for l in s.lines:
        c = chars[l.speaker]
        where = " (from off screen, not seen)" if l.speaker not in s.who else ""
        talk.append(f'- {c.name}{where}, in {c.voice}, {l.delivery}: "{l.text}"')
    speech = ("Dialogue, spoken aloud in Hindi-Urdu (Hindustani) with a natural Pakistani accent, word for word, in "
              "this order; each speaker's mouth moves in sync with their own words only, the others listen and "
              "react:\n" + "\n".join(talk)) if talk else "No one speaks in this shot."
    first = "\nThe first words are spoken at once, in the very first second." if k == 0 and s.lines else ""
    return (f"{FORMATS[fmt]['look']}\nThe reference pictures show the characters; keep each exactly as in its "
            f"picture: {refs}.\nSetting: {s.setting}.\nOne continuous vertical 9:16 shot of {seconds_of(s)} seconds: "
            f"{s.action}\n{speech}{first}\nSound: the natural sound of the place"
            f"{', ' + s.sound if s.sound else ''}; no background music, no narrator. No text, subtitles, captions, "
            "logos or watermarks on screen.")


def make_shot(ep, k, fmt, urls, out, log=print):
    s = ep.shots[k]
    secs = seconds_of(s)
    payload = {"prompt": shot_prompt(ep, k, fmt), "image_urls": [urls[w] for w in s.who], "duration": secs,
               "resolution": resolution(), "aspect_ratio": "9:16"}
    last = None
    for attempt in range(2):
        try:
            fal_video(VIDEO_MODEL, payload, out)
            _add_spend(secs)
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            if "no credit" in str(e):
                raise
            log(f"   ⚠️ Shot {k + 1} failed ({str(e)[:140]}); {'trying again' if attempt == 0 else 'giving up'}.")
    raise RuntimeError(f"Shot {k + 1} could not be made: {str(last)[:200]}")


def to_canvas(src, out, log=print):
    """``src`` at 1080x1920: Real-ESRGAN's video model, then a lanczos resize. TALKIES_UPSCALE=photo picks the photo
    model (made for real footage), but on this laptop's Intel GPU it wrote black frames on 3 of 4 lifelike videos
    (10-nov-2026, caught by upscale's dark-frame guard), while the video model has run reliably since 22-oct."""
    big = src
    mode = (os.environ.get("TALKIES_UPSCALE") or "video").strip().lower()
    if mode != "0" and resolution() != "1080p":
        try:
            import upscale
            if upscale.available():
                model = upscale.PHOTO_MODEL if mode == "photo" else upscale.VIDEO_MODEL
                scale = 4 if model == upscale.PHOTO_MODEL else max(2, min(4, round(kit.OUT_W / SIZE[resolution()][0])))
                t0 = time.time()
                big = upscale.video(src, src[:-4] + "_up.mp4", scale, model=model)
                log(f"   🔍 Sharpened with {model} in {time.time() - t0:.0f} s.")
        except Exception as e:  # noqa: BLE001 — resized instead
            log(f"   ⚠️ Sharpening skipped ({type(e).__name__}: {str(e)[:100]}).")
            big = src
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", big, "-vf",
                        f"scale={kit.OUT_W}:{kit.OUT_H}:flags=lanczos,setsar=1,fps={kit.FPS}", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", out],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"resizing failed: {r.stderr.strip()[-300:]}")
    return out


def make_video(client, fmt, ep, work, log=print, kept=None):
    """(canvas video, its sound as wav, [(start, end)] per shot, [shot wav]). ``kept``: part 1's pictures."""
    import toon_motion as tm
    planned = total_seconds(ep)
    cap = _int_env("TALKIES_SECONDS_PER_DAY", 60)
    if spent_today() + planned > cap:
        raise RuntimeError(f"Today's video budget is used ({spent_today():.0f} of {cap} s made today; this video "
                           f"needs {planned} s). The next one is made tomorrow.")
    seen = sorted({w for s in ep.shots for w in s.who})
    chars = {c.key: c for c in ep.characters}
    log(f"   🖼️ Reference pictures: {', '.join(chars[w].name for w in seen)}")
    urls = {w: fal_upload(ref_picture(client, fmt, chars[w], work, kept)) for w in seen}
    clips = []
    for k, s in enumerate(ep.shots):
        log(f"   🎬 Shot {k + 1}/{len(ep.shots)} ({seconds_of(s)} s, {', '.join(chars[w].name for w in s.who)})...")
        clips.append(make_shot(ep, k, fmt, urls, os.path.join(work, f"shot{k + 1}.mp4"), log))
    joined = os.path.join(work, "joined.mp4")
    times = tm.join(clips, joined, SIZE[resolution()])
    canvas = to_canvas(joined, os.path.join(work, "canvas.mp4"), log)
    sound = tm.wav_of(joined, os.path.join(work, "sound.wav"))
    shot_wavs = [tm.wav_of(joined, os.path.join(work, f"shot{k + 1}.wav"), a, b) for k, (a, b) in enumerate(times)]
    return canvas, sound, times, shot_wavs


# ------------------------------------------------------------------ on screen

def text_events(ep, times, body_end):
    """The hook caption (sound-off viewers), each speaker's name the first time they talk, and a part-2 promise."""
    W = kit.OUT_W
    ev = []
    hook = re.sub(r"[{}\\]", "", ep.hook_caption or "").strip()[:48].upper()
    if hook:
        # 135% of the cartoon channel's hook size: at 72 px it read small on the first samples (10-nov-2026).
        ev.append(kit.dialogue(5, 0.0, min(body_end, 2.6), "TnHook",
                               rf"{{\an5\pos({W // 2},360)\fscx120\fscy120\t(0,180,\fscx135\fscy135)\fad(0,200)}}{hook}"))
    if ep.ending == "part2" and times:
        ev.append(kit.dialogue(7, max(0.0, body_end - 2.2), body_end, "TnHook",
                               rf"{{\an5\pos({W // 2},330)\1c&H3FD2FF&\fscx60\fscy60\t(0,200,\fscx100\fscy100)"
                               rf"\fad(120,0)}}PART 2 KAL!"))
    colours = {c.key: PALETTE[i % len(PALETTE)] for i, c in enumerate(ep.characters)}
    names = {c.key: c.name for c in ep.characters}
    seen = set()
    for s, (a, b) in zip(ep.shots, times):
        span = (b - a) / max(1, len(s.lines))
        for i, l in enumerate(s.lines):
            if l.speaker in seen or l.speaker not in names:
                continue
            seen.add(l.speaker)
            t0 = a + 0.3 + i * span
            ev.append(kit.dialogue(6, t0, min(b, t0 + 1.8), "TnName",
                                   rf"{{\an5\pos({W // 2},{ts.NAME_Y})\3c{ts._ass(colours[l.speaker])}"
                                   rf"\fscx70\fscy70\t(0,140,\fscx100\fscy100)\fad(60,160)}}{names[l.speaker].upper()}"))
    return ev


def captions(ep, times, shot_wavs):
    rows = []
    for s, (a, b), wav in zip(ep.shots, times, shot_wavs):
        text = " ".join(l.text for l in s.lines)
        if text:
            rows.append((text, a + 0.15, max(a + 0.5, b - 0.1), wav))
    return kit.timed_transcript(rows)


# ------------------------------------------------------------------ the channel's daily job

SEO_CONTEXT = ("IMPORTANT: this Short is an ORIGINAL story from our own series of AI-made {label} (episode {n}), not "
               "a clip from a show and not a kids' video. The characters are fictional: {cast}. The story: {premise} "
               "The twist: {twist}. Write the title about the situation and its turn (what happened, who got caught), "
               "Roman Urdu; never call it a kids' cartoon or a moral story.")
NOTE = ("Original stories with AI-made talking characters. All characters are fictional; the video and voices are "
        "made with AI.")


def _history_file():
    return os.path.join(STATE_DIR, "episodes.json")


def history():
    try:
        with open(_history_file(), encoding="utf-8") as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def record(ep, fmt, n, follows=None):
    rows = history()
    for r in rows:
        if follows is not None and r.get("n") == follows:
            r["part2_done"] = True
    rows.append({"n": n, "format": fmt, "date": time.strftime("%Y-%m-%d"), "title": ep.title, "premise": ep.premise,
                 "ending": ep.ending, "ending_note": ep.ending_note, "follows": follows, "script": ep.model_dump()})
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _history_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows[-200:], f, indent=1, ensure_ascii=False)
    os.replace(tmp, _history_file())


def open_part2(rows):
    """The latest episode whose "part 2" promise is not kept yet (within a week), or None."""
    for r in reversed(rows[-7:]):
        if r.get("ending") == "part2" and not r.get("part2_done"):
            return r
    return None


def next_format(rows):
    """The format used least recently, from TALKIES_FORMATS (owner, 10-nov-2026: baby, organ and food are good, the
    pet one "isn't that good", so pet is off unless named there)."""
    allowed = [f.strip() for f in (os.environ.get("TALKIES_FORMATS") or "baby,organ,food").split(",")
               if f.strip() in FORMATS] or list(FORMATS)
    last = {r.get("format"): i for i, r in enumerate(rows)}
    return min(allowed, key=lambda f: (last.get(f, -1), allowed.index(f)))


def keep_refs(work, n):
    """This episode's one-off character pictures, kept for a part 2."""
    dst = os.path.join(cast_dir(), f"ep{n}")
    for f in os.listdir(work):
        if f.startswith("ref_") and f.endswith(".png"):
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(os.path.join(work, f), os.path.join(dst, f[4:]))


def run(output_dir, pipeline):
    """One episode for the channel (toon_shorts.run hands over here): written, filmed, captioned, queued."""
    import credits
    import framed_layout as fl
    os.environ["STOCK_FOOTAGE"] = "0"
    cfg = fl.settings()
    client = kit.gemini()
    rows = history()
    prev_row = open_part2(rows)
    fmt = prev_row["format"] if prev_row else next_format(rows)
    prev = Talkie(**prev_row["script"]) if prev_row else None
    premise = "" if prev else re.sub(r"\s+", " ", os.environ.get("TOON_PREMISE") or "").strip()[:240]
    n = (max(r.get("n", 0) for r in rows) + 1) if rows else 1
    print(f"🎭 Episode {n}: {FORMATS[fmt]['label']}" + (f" (part 2 of {prev_row['n']})" if prev else ""))
    ep, sc = write(client, fmt, premise, [r.get("premise", "") for r in rows if r.get("format") == fmt],
                   follow=prev)
    print(f"   ✅ {ep.title} | {len(ep.shots)} shots, ~{total_seconds(ep)} s | {total_score(sc)}/70")
    stem = kit.neutral_stem("Talk")
    work = os.path.join(output_dir, f".{stem}_shots")
    os.makedirs(work, exist_ok=True)
    kept = os.path.join(cast_dir(), f"ep{prev_row['n']}") if prev_row else None
    canvas, sound, times, shot_wavs = make_video(client, fmt, ep, work, kept=kept)
    keep_refs(work, n)
    body_end = times[-1][1]
    card_ev, card_sfx = kit.end_card(body_end, kit.outro_seconds(cfg))
    total = body_end + (kit.outro_seconds(cfg) if card_ev else 0.0)
    if total > body_end:
        held = os.path.join(work, "canvas_held.mp4")       # the end card sits on the last frame held still
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", canvas, "-vf",
                        f"tpad=stop_mode=clone:stop_duration={total - body_end + 0.2:.3f}", "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", held], check=True,
                       capture_output=True, timeout=900)
        canvas = held
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    transcript = captions(ep, times, shot_wavs)
    kit.render(final, total, [cfg["bg"], cfg["bg"]], text_events(ep, times, body_end) + card_ev, ts.STYLES,
               voices=[(sound, 0.0)], sfx=card_sfx, bg_video=canvas, fast=True)
    lines = [l for s in ep.shots for l in s.lines]
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": ep.title, "viral_hook_text": lines[0].text if lines else ep.hook_caption,
            "why": f"{FORMATS[fmt]['label']} episode {n}: {ep.premise}", "predicted_score": 90,
            "captions": transcript, "genre": "toons", "ai_voice": "AI voice", "comment_question": ep.question,
            "talkie": {"format": fmt, **ep.model_dump()}, "episode": n, "background_music": None}
    kit.seo_or_fail([clip], transcript, source_title=ep.title, text_limit=3000, context=SEO_CONTEXT.format(
        label=FORMATS[fmt]["label"], n=n, cast=", ".join(f"{c.name} ({c.what})" for c in ep.characters),
        premise=ep.premise, twist=ep.twist))
    for field in ("seo_description", "video_description_for_instagram"):
        if clip.get(field):
            clip[field] = credits.insert(clip[field], NOTE)
    kit.finish(output_dir, stem, [clip], transcript, pipeline, extra={"genre": "toons"})
    record(ep, fmt, n, follows=prev_row["n"] if prev_row else None)
    if os.environ.get("TOON_KEEP_ART", "0") != "1":
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ a sample (nothing uploaded)

def save_script(ep, sc, fmt, out_dir, stem, extra=""):
    """``<stem>_script.txt`` (to read) and ``<stem>_script.json`` (to film later) in ``out_dir``."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{stem}_script.txt"), "w", encoding="utf-8") as f:
        f.write(script_text(ep) + "\n\nSCORES: " + ", ".join(f"{k} {getattr(sc, k)}" for k in SCORE_KEYS)
                + f" = {total_score(sc)}/70\nWEAKEST: {sc.weakest}\n" + extra)
    with open(os.path.join(out_dir, f"{stem}_script.json"), "w", encoding="utf-8") as f:
        json.dump({"format": fmt, "script": ep.model_dump(), "scores": sc.model_dump()}, f, indent=1,
                  ensure_ascii=False)
    return os.path.join(out_dir, f"{stem}_script.json")


def sample(fmt, premise="", out_dir=None, log=print, script_json=None):
    """One finished video of ``fmt`` in output/samples/talkies (script beside it). Nothing is uploaded.
    ``script_json``: film an already-written script (``python talkies.py script``) instead of writing one."""
    out_dir = out_dir or os.path.join(ROOT, "output", "samples", "talkies")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%m%d_%H%M%S")
    client = kit.gemini()
    if script_json:
        with open(script_json, encoding="utf-8") as f:
            saved = json.load(f)
        fmt, ep, sc = saved["format"], Talkie(**saved["script"]), Scores(**saved["scores"])
    else:
        log(f"✍️ Writing a {FORMATS[fmt]['label']} script...")
        ep, sc = write(client, fmt, premise, log=log)
    stem = f"{fmt}_{stamp}"
    save_script(ep, sc, fmt, out_dir, stem)
    log(f"   ✅ {ep.title} | {len(ep.shots)} shots, ~{total_seconds(ep)} s | {total_score(sc)}/70")
    work = os.path.join(out_dir, f".{stem}_work")
    os.makedirs(work, exist_ok=True)
    log(f"🎞️ Filming {len(ep.shots)} shots with {VIDEO_MODEL} at {resolution()} "
        f"(~${total_seconds(ep) * PRICE[resolution()]:.2f})...")
    canvas, sound, times, shot_wavs = make_video(client, fmt, ep, work, log)
    return _sample_render(ep, canvas, sound, times, shot_wavs, os.path.join(out_dir, f"{stem}.mp4"), log)


def remake(script_json, log=print):
    """A sample rebuilt from its already-filmed shots (``<stem>_script.json`` beside ``.<stem>_work``): no new
    video is paid for."""
    import toon_motion as tm
    with open(script_json, encoding="utf-8") as f:
        ep = Talkie(**json.load(f)["script"])
    stem = os.path.basename(script_json)[:-len("_script.json")]
    out_dir = os.path.dirname(os.path.abspath(script_json))
    work = os.path.join(out_dir, f".{stem}_work")
    clips = [os.path.join(work, f"shot{k + 1}.mp4") for k in range(len(ep.shots))]
    missing = [c for c in clips if not os.path.isfile(c)]
    if missing:
        raise RuntimeError(f"These shots are not there: {missing}")
    joined = os.path.join(work, "joined.mp4")
    times = tm.join(clips, joined, SIZE[resolution()])
    canvas = to_canvas(joined, os.path.join(work, "canvas.mp4"), log)
    sound = tm.wav_of(joined, os.path.join(work, "sound.wav"))
    shot_wavs = [tm.wav_of(joined, os.path.join(work, f"shot{k + 1}.wav"), a, b) for k, (a, b) in enumerate(times)]
    return _sample_render(ep, canvas, sound, times, shot_wavs, os.path.join(out_dir, f"{stem}.mp4"), log)


def _sample_render(ep, canvas, sound, times, shot_wavs, final, log=print):
    import framed_layout as fl
    import main as pipeline
    body_end = times[-1][1]
    cfg = fl.settings()
    kit.render(final, body_end, [cfg["bg"], cfg["bg"]], text_events(ep, times, body_end), ts.STYLES,
               voices=[(sound, 0.0)], bg_video=canvas, fast=True)
    transcript = captions(ep, times, shot_wavs)
    os.environ.setdefault("CAPTION_EMPHASIS", "1")
    served = pipeline.auto_caption_clip(final, transcript, 0.0, body_end, margin_v=kit.caption_margin()) or final
    if served != final:
        os.replace(served, final)
    log(f"🎉 Sample ready: {final}")
    return final


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    if len(sys.argv) >= 3 and sys.argv[1] == "sample" and sys.argv[2] in FORMATS:
        sample(sys.argv[2], " ".join(sys.argv[3:]))
    elif len(sys.argv) == 3 and sys.argv[1] == "remake":
        remake(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "script" and sys.argv[2] in FORMATS:
        import ai_fallback
        since = time.strftime("%Y-%m-%dT%H:%M:%S")
        ep, sc = write(kit.gemini(), sys.argv[2], " ".join(sys.argv[3:]))
        out = os.path.join(ROOT, "output", "samples", "talkies", "scripts")
        cost = ai_fallback.usage_cost(since, pid=os.getpid())
        path = save_script(ep, sc, sys.argv[2], out, f"{sys.argv[2]}_{time.strftime('%m%d_%H%M%S')}",
                           extra=f"WRITING COST: {cost}\n")
        print(f"📝 {path} | {ep.shape} | {total_score(sc)}/70 | writing: {cost['calls']} calls, ${cost['usd']}")
    elif len(sys.argv) == 3 and sys.argv[1] == "film":
        sample("", script_json=sys.argv[2])
    else:
        print(f"usage: python talkies.py sample <{'|'.join(FORMATS)}> [premise]\n"
              f"       python talkies.py script <{'|'.join(FORMATS)}> [premise]   (the script only, no video)\n"
              "       python talkies.py film <..._script.json>     (film a written script)\n"
              "       python talkies.py remake <..._script.json>   (rebuild from filmed shots, nothing paid)")
        sys.exit(2)
