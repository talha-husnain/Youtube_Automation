# Talking babies, organs and food: what the big Shorts do (research, 10-nov-2026)

Why: the owner liked the first baby, organ and food samples but said the scripting still needs work, and asked for
research on public videos in these trends (stories, scripting, tools) before improving the writer (talkies.py).

How: YouTube searches sorted by view count (yt-dlp, one query at a time, metadata and YouTube's own captions only,
no video downloaded) plus a web research pass (news, official policy pages, tool vendors' guides). Vendor pages sell
tools, so their numbers are claims, not facts.

## 1. Talking babies

| Video | Views | Length | What it is |
|---|---|---|---|
| Baby in the Flood / Cute Baby Funny Talks With Reporter (Scarlet Doll, 47.8K subs) | 6.8M | 62 s | ~10 rapid Q&A jokes |
| Cute Baby Vs Reporter, AI Funny Interviews of Baby (Scarlet Doll) | 3.2M | 67 s | same format |
| Cute Baby's Funniest Ice Cream Joke, Urdu Comedy (Tiny Baby, 1.2K subs) | 2.3M | 10 s | 3 lines, one joke |
| Part 2 - Funny Talking Babies Compilation (Viral Kids Ai Videos) | 1.1M | 126 s | compilation |
| Baby vs Doctor Funny Chat, Urdu AI (Renderloop AI) | 376K | 8 s | one joke |
| Many "Funny Urdu AI Baby in Hospital" 9-second clips (Ai Baby Tales) | 200-1,300 each | 9 s | same joke template again and again |

What the winners do (from their captions):
- An adult asks something ordinary, the baby answers with a grown-up worry or an innocent literal logic.
  "Aapne Pampers ki keemat dekhi? Ab sirf rone se ghar nahi chalta." / "Internet slow tha, isliye late download hua
  hoon." / "Uncle, ice cream itni thandi kyun hoti hai? ... Phir isse bhi sardi lagti hogi."
- Joke density: about one laugh every 6 seconds; one joke can carry a whole 10-second Short.
- The cheap copies that repeat one template (the hospital clips) get a few hundred views: variety matters.
- Globally the "baby podcast" (babies with podcast mics on adult topics) spread fast (an account gained 220K+
  followers in 13 days, per Pedaily, May 2025), but most of those reuse real podcast audio: YouTube's reused-content
  rule forbids that, so our dialogue stays original.

## 2. Talking organs

| Video | Views | Length |
|---|---|---|
| Your Organs When You Eat Too Much Sugar (CasiCreativo, 756K subs) | 5.4M | 147 s |
| Your Organs When You Do Intermittent Fasting / Go For A Run (CasiCreativo) | 5.0M each | 2.5-3 min |
| What if your ORGANS had Feelings? (Human Buddy) | 965K | 116 s |
| Your Organs React to Late Night Snacks (Organismo) | 841K | 171 s |
| Body Parts Talking Funny, Hindi (AI video only) | 168K | 10 s |

What the winners do: an office or workplace comedy inside the body (the brain is the boss, the stomach complains
about a "graveyard shift" and threatens "a complaint to the Guts Guild"), one habit drives the episode, real facts
ride inside the banter. Hindi/Urdu has almost no strong organ channel: an open gap. Vendors suggest a "what happens
if you do X for a day / a week / a month" timeline and a direct "you" voice; YouTube removes health content that
contradicts health authorities, so facts stay mainstream.

## 3. Talking food

| Video | Views | Length |
|---|---|---|
| Kadhi Ka Dil Kachori Par Aaya! Chawal Reh Gaya Akela, Part 1 (AI Wali, 22.5K subs) | 3.2M | 43 s |
| Tomatar aur bhindi ki ladai (Hanuman Toons) | 2.1M | 24 s |
| Aalu Ki TikTok, Sabzi Ki Funny Love Story (Dream Forge tech) | 516K | 10 s |
| Aalu bhindi ka affair, Part 3 (AI Love Toon Stories) | 390K | 38 s |
| Fruit Love Island (@ai.cinema021, TikTok/Instagram, news reports) | 300M+ in total, 22 episodes | 2-4 min |

What the winners do: filmi soap tropes among foods (secrets, lies, rivalry, a court case, and above all love
triangles), puns built on what each food really is ("Bhindi slim kyun? Yoga aur kaddu se doori"; "pressure cooker
mein sabse pehle tum hi jaate ho"), regional food jokes (Kachori = Rajasthan), Part 1/2/3 series that end on an
unanswered question ("Don't make me wait for the next part!"). Indian food microdramas named in the press: samosa
and jalebi facing family disapproval, aloo the serial flirt, chole bhature on trial, chai leaving biscuit for rusk
(Storyboard18, Curly Tales).

## 4. Tools the creators use

- Hindi tutorials (1.7M, 409K, 251K views): ChatGPT writes an image prompt and a video prompt; Gemini makes the
  picture; Google Flow "Frames to Video" (Veo) animates it with the dialogue; CapCut edits.
- A baby-dialogue tutorial (347K views) uses Higgsfield; Kling, Hedra and ElevenLabs appear in other workflows.
- Our chain is the same kind (GPT-5 writes, OpenAI pictures, Gemini Omni video on fal, our own captions), so the
  difference is the writing, not the tools.

## 5. Platform risks

- YouTube "inauthentic content" (July 2025): mass-produced, templated stories with little variation lose
  monetisation; every episode needs a new situation. AI disclosure is required for realistic scenes and does not cut
  earnings; our uploads already set containsSyntheticMedia.
- Made-for-kids risk: cute babies and organs need grown-up framing; uploads already set selfDeclaredMadeForKids
  false.
- Instagram recommends originals without visible watermarks; API video from fal has none.
- TikTok removed Fruit Love Island videos and ITV threatened action over the "Love Island" brand: never use a real
  show's name.

## 6. What changed in the writer (talkies.py)

- Each series has its own SHAPES: baby joke (1 shot, 6-12 s), Guddu ka interview (3 Q&A), Guddu Podcast, mini
  story; organ office, timeline (aaj / ek hafta / ek mahina), live commentary; food soap (part 2 cliffhanger),
  banter (puns), kitchen court.
- A LAUGHS section: a laugh every 5-6 seconds and the joke mechanisms above.
- Fixed series casts with personalities and signature looks (Guddu, Ammi, Abbu, Dadi, Sana the reporter, Pinky;
  Dimagh, Dil, Liver, Maida, Tum; Shaan Samosa, Aloo, Karela, Pyaaz, Jali Jalebi).
- A dialogue-polish pass, a higher bar (every score 8+), pet off by default.
- Rishta and shaadi comedy is allowed; love affairs stay out unless the owner turns on TALKIES_FOOD_ROMANCE=1.

## Sources

YouTube (views on 10-nov-2026): G_RadlUic3I, yXuGz1AetA8, cYVQkbRGGfs, WVbvCs28rA0, nYhW26hPEQs, BfzMi1EOe4I,
2L-W1We41Bo, fMsx_HEorHw, oBsXwgvzGEE, WiFhGlMqtec, LRZDOYMvhbA, yaSiiT7l95Q, w5oKapf2Piw, rokLNFsaPDs,
AEiFVJIiPpU, 7QWoElzc6i8, xurqkjPGhjY (https://www.youtube.com/watch?v=<id>).

Web: c21media.net (Fruit Love Island), thetriangle.org, dailydot.com (cheating fruit), storyboard18.com and
curlytales.com (Indian food microdramas), news.pedaily.cn and earlygame.com (baby podcasts),
kapwing.com and the-decoder.com (AI Shorts study), support.google.com/youtube answers 1311392, 14328491, 13813322,
9528076, 9527654; creators.instagram.com (originality).
