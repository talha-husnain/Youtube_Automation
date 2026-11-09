# Remix a viral video into our own video: research notes (22-oct-2026)

Web research only. No yt-dlp, no YouTube scraping. Not legal advice.
Where a point rests on secondary/trade press only, it says so.

---

## 1. Copyright: is a video's spoken script protected?

**Yes, the wording is.** A YouTube video is fixed, so its spoken script is protected expression
(literary/dramatic work inside an audiovisual work). A transcript is a copy of that expression.
What is NOT protected is the idea, the topic, the facts, the method, titles and short phrases.

Sources and the exact line each draws:
- YouTube's own copyright page: "Intangible things like ideas, facts, and processes aren't subject
  to copyright" and a work must be "creative and fixed in a physical medium".
  https://support.google.com/youtube/answer/2797466
- US 17 U.S.C. 102(b) (no protection for "any idea, procedure, process, system, method of
  operation, concept, principle, or discovery") and Copyright Office Circular 33 (ideas, methods,
  names, titles, short phrases not protected). https://www.copyright.gov/circs/circ33.pdf ,
  https://copyright.gov/help/faq/faq-protect.html
- Feist v. Rural (US Supreme Court 1991): facts are free; a factual work only gets "thin"
  protection for its creative **selection and arrangement**. A later author may copy the facts as
  long as it does not reproduce the same selection and arrangement.
  https://www.law.cornell.edu/supremecourt/text/499/340 ,
  https://en.wikipedia.org/wiki/Feist_Publications,_Inc._v._Rural_Telephone_Service_Co.
  -> Practical meaning for us: same facts = fine; same handful of facts picked in the same order
  with the same framing = the risky part.
- Close paraphrase can infringe: Salinger v. Random House (2d Cir. 1987) treated close
  paraphrases of letters as taking protected expression (fair-use context).
  https://en.wikipedia.org/wiki/Salinger_v._Random_House,_Inc.
  Non-literal copying is judged by "comprehensive nonliteral similarity" / the abstractions test
  (Nichols v. Universal): the more concrete the shared element (sentences > scene order > theme),
  the more it counts.
- **India** (audience + precedent Pakistan courts tend to follow): R.G. Anand v. Delux Films,
  Supreme Court of India 1978. "copyright cannot subsist in an idea, subject-matter, themes, plots
  or historical or legendary facts"; violation is "confined to the form, manner and arrangement and
  expression of the idea". Test: whether a viewer who has seen both gets "an unmistakable
  impression that the subsequent work appears to be a copy". "A literal imitation of the
  copyrighted work with some variations here and there" still infringes.
  https://en.wikipedia.org/wiki/R._G._Anand_v._Deluxe_Films ,
  https://api.sci.gov.in/jonew/judis/5032.pdf
- **Pakistan**: Copyright Ordinance 1962 (amended 2000), s.10 literary works, s.57 fair dealing
  for criticism, review, reporting current events.
  https://en.wikipedia.org/wiki/Copyright_law_of_Pakistan
  I found no Pakistani ruling stating the idea/expression rule in so many words (unverified; common
  law systems generally follow it).

### Safe vs not safe (synthesis of the above)

| Keep from source (safe) | Risky / not safe |
|---|---|
| Topic, news event, question asked | Sentences, even with words swapped ("literal imitation with variations") |
| Facts (verified independently) | Same selection of facts in the same order + same framing (Feist "selection and arrangement") |
| Genre/angle category ("X vs Y", "top 3", "myth busted") | Distinctive jokes, metaphors, catchphrases, original analogies |
| Hook TYPE (question, shock stat, contradiction) | The hook's actual line, or a close paraphrase of it |
| Length band, beat count, pacing | Beat-by-beat mirror of the same scenes/examples/conclusion |
| Title pattern | Same title, thumbnail text, thumbnail image |

### Claims/strikes seen for "rewritten script" channels

- **Nothing documented found** of a YouTube copyright strike or Content ID claim against a channel
  for a *rewritten* script. Content ID matches audio/video fingerprints, not text, so a new voice
  reading new words does not trip it; a strike needs the owner to file a manual takedown, which a
  close paraphrase could justify.
  https://en.wikipedia.org/wiki/YouTube_copyright_strike
- The well-known script-copying cases were reputational, not YouTube enforcement: hbomberguy's
  "Plagiarism and You(Tube)" (Dec 2023) on James Somerton (scripts that "added or changed words in
  other writers' sentences") and Internet Historian; Somerton left the internet, channel stayed up.
  https://fanlore.org/wiki/Plagiarism_and_You(Tube) ,
  https://www.thepinknews.com/2023/12/06/james-somerton-hbomberguy-plagiarism-claims
- The AI-channel terminations that did happen were for **spam / misleading metadata**, not
  copyright: Screen Culture and KH Studio (fake AI trailers), Dec 2025.
  https://letsdatascience.com/news/youtube-removes-popular-ai-slop-channels-6d157385
- So the bigger practical risk for a remix feature is **YPP policy (section 2)**, not copyright.

---

## 2. YouTube policy 2025-2026

### Inauthentic content (renamed 15-jul-2025) - YPP channel monetization policies
https://support.google.com/youtube/answer/1311392 (fetched 22-oct-2026). Exact wording:
- Notice: "We're making a minor update to our "repetitious content" policy to better clarify this
  includes content that is repetitive or mass-produced." ... "We are also renaming this policy from
  "repetitious content" to "inauthentic content."" ... "There is no change to our reused content
  policy".
- Not allowed: "Similar or repetitive content with low educational value, commentary, narratives,
  or minimal variation across videos"; "Videos where characters are put in the same situation over
  and over again with the same outcome"; "Image slideshows, templated storylines, or scrolling text
  with minimal or no narrative, commentary, or educational value"; **"AI-generated content made
  with generic or unoriginal templates giving the impression of mass production"**.
- Allowed: "Same intro and outro for your videos, but the bulk of your content is different";
  "Similar content, like a series ... but in which each video has a distinct storyline, focus, or
  concept".
- Scope: "applies to your channel as a whole"; "monetization may be removed from your entire
  channel."

### Reused content (unchanged in 2025), same page
- **"If you borrow content from someone else, you need to change it significantly to make it your
  own."**
- Not allowed includes: "Content downloaded or copied from another online source without any
  substantive modifications"; "Content uploaded many times by other creators"; **"Content that
  exclusively features readings of other materials you did not originally create"** (a TTS reading
  of a lightly rewritten transcript sits right next to this one).
- Allowed includes: "A scene from a movie where you've rewritten the dialog and changed the
  voiceover"; "Replays of a sports tournament where you explain the moves"; "Edited footage from
  other creators where you add a storyline and commentary".

### Originality push for Shorts (announced 1-oct-2026)
Rene Ritchie (Creator Insider): recommendations will "further prioritise original Shorts and reduce
the reach of channels that mainly aggregate or re-upload other creators' clips without significant
changes". Remixers must add value, "not just VO descriptions of what's happening on screen, minor
technical edits, or template-based bulk changes". Reach, not monetization; no start date, no
indicator. (Secondary sources quoting the video; original not checked.)
https://www.searchenginejournal.com/youtube-original-shorts-reposted-clips-reach/591774/ ,
https://ppc.land/re-uploaded-shorts-lose-reach-as-youtube-favours-original-clips/ ,
https://www.socialmediatoday.com/news/youtube-updates-shorts-algorithm-to-put-more-focus-on-original-content/

### AI channels and demonetisation (2025-26)
- Rene Ritchie (Jul 2025): channels using AI remain eligible; the target is mass-produced /
  repetitive. https://www.searchenginejournal.com/youtube-monetization-update-spam-not-reaction-channels/550755/
- Neal Mohan's Jan 2026 letter: building on spam/clickbait systems to reduce low-quality AI
  content. Kapwing: ~1 in 5 Shorts shown to new users is low-quality AI. Tubefilter counts ~18
  slop channels deleted or hidden.
  https://tubefilter.com/2026/01/29/youtube-ai-slop-channel-crackdown-bans/ ,
  https://www.searchenginejournal.com/youtubes-ai-slop-problem-and-how-marketers-can-compete/
- Reported demonetisations ("inauthentic and mass-produced content") are judged on the **pattern
  across the channel**: same structure, same voice style, same visuals across hundreds of videos.
  Anecdotal, vendor blog: https://fliki.ai/blog/youtube-ai-demonetization

### Disclosure of synthetic content
https://support.google.com/youtube/answer/14328491
- Must disclose realistic content that "Makes a real person appear to say or do something they
  didn't do", "Alters footage of a real event or place", "Generates a realistic scene that didn't
  actually occur", or "Creates music that's the main focus of the video".
- No disclosure for "Production assistance, like using generative AI tools to create or improve a
  video outline, script", "Idea generation", unrealistic content.
- Penalties for consistent non-disclosure: label applied, "removal of content or suspension from
  the YouTube Partner Program". "Disclosing AI content alone won't limit a video's audience or
  impact its eligibility to earn money."
- API: `status.containsSyntheticMedia` on videos.insert/update since 30-oct-2024
  (https://developers.google.com/youtube/v3/revision_history). The repo already sets it for songs.

---

## 3. How existing tools do it

### Open source
| Project | Licence | Does it start from someone else's video? | Notes |
|---|---|---|---|
| ShortGPT (RayVentura) https://github.com/RayVentura/ShortGPT | MIT (GitHub sidebar; a README mirror says Apache-2.0) | Only ContentTranslationEngine: transcribe -> translate -> re-voice -> captions. That is a dub, not a rewrite. | Engines: ContentShortEngine, ContentVideoEngine, EditingEngine (JSON "editing markup"). |
| MoneyPrinterTurbo https://github.com/harry0703/MoneyPrinterTurbo | MIT | No. Topic/keyword -> LLM script ("generate or rewrite") -> TTS -> stock -> subtitles -> music -> compose. | Already our reference for free footage/voices. |
| MoneyPrinterV2 (FujiwaraChoki) | AGPL-3.0 (mirror; unverified on GitHub) | No. Niche -> idea -> script -> image -> TTS -> upload. | AGPL: do not copy code. |
| ViralMint https://sourceforge.net/projects/viralmint/ | AGPL-3.0 | **Yes.** Scouts trending + "channel-outlier breakouts" (YouTube, TikTok, Reddit, Google Trends) -> Whisper transcript -> "AI extracts the hook and structure" -> writes script -> TTS (Gemini / Edge / cloned) -> captions + music. | No originality safeguard stated. AGPL: ideas only. |
| Hype Shorts Remix (agent skill) https://www.agensi.io/skills/hype-shorts-remix | MIT (bundled) | Yes: studies "the hook, pacing, and visual structure" -> "fresh script and shot plan" -> FFmpeg edit. | No copy rule stated. |
| youtube-video-analyst skill (shipshitdev/library) | not verified | Transcript -> 11-section breakdown (hooks, storytelling, CTAs). | Listing only. |

### Commercial
- Skripr ($19-99/mo): "reverse-engineers the hooks, structure, and retention patterns" of a video
  that performed, then writes a fresh script on your topic. https://alternativeto.net/software/skripr/about/
- TokScript ($10/mo): Viral Script Writer "uses the same structure and hooks that made the original
  go viral"; Virality Explainer analyses "the hook, pacing, structure, emotional triggers, and
  engagement patterns". https://tokscript.featurebase.app/help/articles/6856467-what-are-the-3-ai-agents-and-what-does-each
- vidIQ Outliers: score = a video's views vs the channel's own average (bands <2x ... >10x).
  https://support.vidiq.com/en/articles/9660010-outliers

### The common recipe (what they all do)
1. Find an outlier (views / channel median or average; per-subscriber variants).
2. Get the transcript.
3. Extract a blueprint, not text: hook type, opening promise, section order/beats, examples used,
   open loops, pattern interrupts, CTA placement, ending payoff, emotional trigger, length.
4. Change the angle, rebuild the outline, write a new title promise.
5. Write in our voice with **new examples/proof/facts**.
6. Polish retention (strong hook, open loops, bridges).
Warning in the best guide: "a rewrite that keeps the same hook, structure, examples, pacing, and
conclusion can still feel copied"; your version should be clearly better in at least one way
(newer, clearer, more specific). https://www.overseeros.com/blog/youtube-transcript-to-script

**Already in this repo:** `trend_explainer.py` does exactly the safe half of this for long videos:
rivals' top-3 captions -> one call that describes their angles in English -> the script writer
never sees their words -> `copied_runs` (8 words) forces a rewrite, then refuses. A Shorts remix is
mostly that pattern generalised to cricket/quiz/controversy/history Shorts.

---

## 4. Finding a niche's viral Shorts cheaply (no search.list)

| Source | Cost | Notes |
|---|---|---|
| **Playboard** https://playboard.co/en/chart/short/most-viewed-all-videos-in-pakistan-daily | free, no login to view | Most viewed Shorts, country = Pakistan/India, daily/weekly/monthly; rank, title, hashtags, upload date, views, channel, subs. No category filter visible. One page fetch a day, not a scrape. |
| **Rival channels' /shorts tab** (rivals.py already does it) | free | Sort by views; outlier = views / that channel's median. A few calls in a row, never fanned out (bot-check lesson of 22-oct-2026). |
| **Channel RSS** `youtube.com/feeds/videos.xml?channel_id=UC...` | free, no key | Last 15 uploads with `media:statistics views`. `?playlist_id=UUSH<rest of id>` is said to give Shorts only (UULF long, UULV live): **undocumented, not tested here**. |
| **Data API without search** | 1 unit per call | `playlistItems.list` on the uploads playlist (1 unit/50 items) + `videos.list` for stats (1 unit/50 ids) is ~100x cheaper than `search.list` (100 units). https://developers.google.com/youtube/v3/determine_quota_cost . `videos.list chart=mostPopular&regionCode=PK` is still documented; Shorts inclusion not confirmed. |
| **Google Trends daily RSS** `trends.google.com/trending/rss?geo=PK` | free | trends.py already uses it (same-day stories). Trends also has a YouTube Search property for keyword interest. |
| **YouTube search, "Popularity"** | free (yt-dlp, 1 call) | Since 8-jan-2026 "Sort by: View count" is "Prioritize: Popularity" (views + watch time, not pure count); "Last hour" and "Rating" removed; a Shorts type filter was added. https://9to5google.com/2026/01/08/youtube-search-filters/ |
| **YouTube Studio Research tab** | free, manual | Searches across YouTube (28 days) with "Content gap" labels, per geography/language. https://support.google.com/youtube/answer/11962757 . An outlier-multiplier version is a small test (Aug 2026), Inspiration tab being deprecated. https://www.tubefilter.com/2026/08/05/youtube-research-tab-outlier-multipliers-viewer-comparison-data/amp/ |
| **YouTube Trending page** | gone | Removed July 2025 (visits fell "significantly"); replaced by YouTube Charts (music, podcasts, trailers only) and Explore. https://9to5google.com/2025/07/10/youtube-trending-page-removal/ |
| vidIQ / Social Blade / OutlierKit | freemium | Outlier finders; not needed if we compute median ourselves. |

---

## 5. Safest design

### Keep from the source (ideas, not expression)
- Topic / event / question, and the **angle category** (versus, myth-bust, countdown, "kya aap
  jante hain", explainer).
- Hook **type** (shock number, question, contradiction, "nobody talks about"), not its words.
- Beat count and length band (e.g. 5 beats, 30-35 s), pacing (line every ~2.5 s).
- Retention device types: open loop, mid-video reveal, quiz pause, ending callback.
- Proof that it works: views, outlier multiple (feeds the planner's ranking only).

### Always make new
- Every sentence, the hook line, the title, description, thumbnail text.
- **Facts from our own grounded research** (3+ sources, claim labels); the source transcript's
  claims are leads to verify, never inputs to the writer. Drop any fact we cannot confirm.
- The selection and order of facts: add at least one fact/angle the source does not have, and
  change the order (Feist "selection and arrangement"; R.G. Anand viewer test).
- Visuals (our footage/photos/cards), voice, music, captions style. Never the source's clips,
  audio, thumbnail or title.

### Pipeline sketch (fits the existing code)
1. Find: Playboard PK/IN daily Shorts + rivals' /shorts outliers (>=3x channel median) + Trends RSS.
2. Fetch captions for the 1-3 picks (a few calls in a row; never a fan-out).
3. **Blueprint call** (English, abstract): topic, angle category, hook type, beat count, length,
   retention devices, what the comments ask for. Output has a word cap and is checked for
   8-word runs against the source, so no wording leaks through it.
4. Grounded research on the topic (existing planners' research step), facts labelled.
5. Writer gets blueprint + our facts + channel rules; never the transcript.
6. Gates: `copied_runs` (8 words) vs the source; a semantic check (one judge call: "would a viewer
   who saw both think this is a copy?" plus same-facts-in-same-order check); the existing fact /
   defamation checks. Fail -> one rewrite -> refuse.
7. Record `remix_of:<video id>` on `used` so one source makes at most one video; cap remixes per
   rival per week; rotate structures so the channel does not look templated.
8. Disclosure: set `containsSyntheticMedia` only when the 14328491 triggers apply (realistic
   scene of a real person/event, AI music as the focus); AI-written scripts do not need it.

### Open questions / unverified
- No case law or YouTube enforcement found specifically about AI rewrites of transcripts.
- UUSH playlist feed and chart=mostPopular Shorts coverage were not tested.
- Oct 2026 originality wording comes from trade press quoting a video.
