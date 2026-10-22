# Craft research: Shorts + long video scripts (22-oct-2026)

Legend: [E] = evidence (platform doc, measured data, or a named creator's own stated practice);
[R] = reported second-hand (vendor blog / AI summary of an interview; plausible, not verified);
[O] = opinion / rule of thumb.

## 0. What YouTube itself says (primary sources)

- Shorts views since 31-mar-2025: a view counts every time a Short starts or REPLAYS, no minimum
  watch time; the old count is "engaged views" (Advanced mode, used for YPP). [E]
  https://www.digitalmusicnews.com/2025/03/27/how-does-youtube-shorts-count-views-2025/
  https://tech.yahoo.com/general/articles/youtube-changing-view-means-youtube-162942286.html
  -> A Short that loops cleanly earns extra views directly.
- Shorts analytics: "viewed vs swiped away" (Studio label "how many chose to view"). YouTube publishes
  no benchmark. Community ranges: 70-79% working, 80%+ strong; APV can pass 100% when viewers loop. [R]
  https://1of10.com/blog/youtube-shorts-analytics/
  Study cited in vendor blogs (attributed to a 3.3B-view analysis): best Shorts 70-90% viewed, under 60%
  distribution collapses. Primary not found. [R]
  https://photutorial.com/youtube-shorts-statistics
- Todd Sherman (Shorts product lead, Aug 2023): "The audience is the algorithm"; a view should "encode
  for your intent of watching"; no ideal length, focus on story; hashtags optional; better content beats
  more uploads; early views are exploratory. [E]
  https://www.searchenginejournal.com/youtube-explains-how-shorts-algorithm-works/494953/
- Rene Ritchie (Creator Liaison, Aug 2024): "The algorithm follows the audience, so please the audience";
  file name does not matter, title does. [E]
  https://www.tubefilter.com/2024/08/26/rene-ritchie-shorts-creator-faqs/
  https://www.socialmediatoday.com/news/youtube-launches-new-q-and-a-shorts-series-for-creator-questions/725188/
- Hashtags help page: up to 3 hashtags "considered most engaging" show by the title; more than 60
  hashtags -> all ignored. (The 15 limit our code uses is not on this page today; keep 3-5 anyway.) [E]
  https://support.google.com/youtube/answer/6390658?hl=en
- Long video "Key moments for audience retention": "Intro tells you what percentage of your audience
  still watched your video after the first 30 seconds"; fix by matching title/thumbnail and "Modify the
  first 30 seconds"; "Top moments" late in a video -> move compelling content earlier. [E]
  https://support.google.com/youtube/answer/9314415?hl=en
  Vendors report 50%+ at 30 s as "above typical" (not official). [R]
- YouTube editor Julia Lee Harter: the opening seconds of a long video linked from a Short should
  "confirm they made the right choice". [E]
  https://www.socialmediatoday.com/news/youtube-offers-tips-on-working-with-shorts-videos/

## 1. Retention benchmarks (third-party data)

- quso.ai (≈508k posts, 1,900 creators, 12 months, updated jun-2026): median Short ~45% average
  view-through, top 10% ~91%; "Most retention loss happens in the first three seconds"; 11-20 s band
  had the highest median views; recommended 11-30 s unless content needs more. [R, large sample]
  https://quso.ai/research/video-retention-benchmarks
- Our numbers: 7-19 s median watch on 30-35 s Shorts = roughly 20-55% APV, i.e. at or below median.
- Jenny Hoyos: typical Short ~34 s; a 1-second trim changed performance; keep reading level at or
  below 5th grade (her analysis of thousands of Shorts). [R: AI summary of her interview]
  https://videohighlight.com/v/As7abwNhG7Y
- MrBeast onboarding doc (leaked sep-2024, authenticity unconfirmed): CTR, AVD, AVP are the three
  metrics; first minute must prove the thumbnail promise; minutes 3-6 hold the most exciting simple
  content; a "wow factor" early (crane brings the house ~30 s in); title/thumbnail set expectations and
  a mismatch kills AVD. [R/E]
  https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/
  https://www.creatorhandbook.net/leaked-document-allegedly-reveals-mrbeasts-secrets-to-youtube-success-the-key-takeaways/

## 2. Hooks (first 1-3 s)

Evidence and reports:
- Jenny Hoyos: hook ~3 s, must work ON MUTE ("so good that you can be watching the video on mute and still
  know what it's about"); three tactics: foreshadow the ending, proven openers ("Did you know about this...?"),
  open on an emotional reaction. [R] https://vidiq.com/blog/post/how-jenny-hoyos-gets-10m-views-per-youtube-short/
- Jenny Hoyos TED: open with a surprising question; "constant progression"; conflict ("if everything is smooth
  sailing, then nobody cares"); answer fast once asked. [R]
  https://www.contentgrip.com/how-to-tell-a-great-story-in-60-seconds/
- Jenny teardown (21M-view Short): "Get right into it", no preamble, explain as you go; set stakes/conflict
  early; recap the premise (viewers land mid-feed); CTA mid-video at peak action, not at the end; end
  abruptly on a high note, lingering reduces re-watches. [R]
  https://www.demandcurve.com/newsletters/growth-newsletter-187
- Jenny writes 10+ hooks per idea and picks with data. [R] (several summaries; no primary transcript found)
- vidIQ list of 18 hook formulas with real view counts (Did you know + concrete object, X vs Y, "I never do
  THIS and here's why", "They don't want you to know"); suggests visual hook + 3-7 word text hook + 5-10 word
  spoken hook all saying ONE thing; claims viewers decide in ~1 s. [R]
  https://vidiq.com/blog/post/viral-video-hooks-youtube-shorts
- Bytecap taxonomy (no data, honest about it): result-first, precise question, problem-solution, story teaser,
  surprising claim, visual reveal, direct promise; "Start where the value starts. Remove greetings and setup";
  a high chose-to-view + weak retention = broken promise. [O]
  https://www.bytecap.io/research/best-hooks-for-youtube-shorts
- Kallaway's 3-step spoken hook: context lean-in (topic in plain words) -> scroll-stop interjection
  ("but/however") -> contrarian snapback (the twist). [R] https://postiz.com/blog/how-to-write-viral-hooks-social-media-psychology
- quso: "Most retention loss happens in the first three seconds". [R]
- Curiosity = an information gap the viewer feels they can close (Loewenstein 1994, Psychological Bulletin,
  "The Psychology of Curiosity"). The hook must say precisely WHAT is unknown; a vague mystery is no gap. [E, academic]

What kills retention (consistent across sources): greetings, channel name, "in this video / aaj hum
baat karenge", context before the subject, a promise bigger than the clip, a first frame that needs context. [R]
Our own data point: a match Short opened "Namaste dosto ... swagat hai" (CLAUDE.md, 22-oct-2026).

Hook formulas for our niches (my synthesis, [O]):
- Number shock: "Sirf 19 saal ki umar mein, 7 wicket. Pakistan ka record aaj tak koi nahi tod saka."
- Contradiction: "Sab kehte hain Babar slow hai. Last 10 innings ka strike rate kuch aur kehta hai."
- Result first: "India 2 run se haari. Aur galti last ball pe nahi, 17th over mein hui thi."
- Precise question: "Kis mulk ke jhande pe AK-47 bani hui hai?" (quiz: the question IS the hook)
- Stakes/consequence (history): "1979 ka ek din. Aaj bhi har Pakistani scientist us din ko yaad karta hai."
- Controversy: name + action + open question: "X pe ilzaam laga, phir usne Y kiya. Sach kya hai?"

## 3. Shorts structure (30-45 s)

- Story spine: set up conflict -> resolve -> new conflict, joined by "but" and "so" (Jenny, via vidIQ) [R];
  same as Parker & Stone's "but/therefore" screenwriting rule [O for Shorts].
- Pacing curve (Jenny, vidIQ): hook fast, middle medium, peak fast and sharp, resolution medium, ending fast;
  peak-end effect: people remember the best moment and the end. [R]
- Restate the premise just before the payoff; make the answer feel uncertain before revealing it. [R]
- Reading level at or below 5th grade (Jenny's analysis of thousands of Shorts). [R] https://videohighlight.com/v/As7abwNhG7Y
- Narration speed: vendor guides put Shorts narration at 150-180 wpm (2.5-3 words/s), fatigue above ~180;
  pauses 200-400 ms. No study ties wpm to retention. [R] https://syllaby.io/blog/voiceover-pacing-silence-trimming-retention-editing/
  -> a 30 s Short is ~75-90 spoken words; 35 s ~90-105.
- Re-hook cadence: no evidence for "every 3 s". Long-form sources say 60-90 s; one short-form glossary says
  10-15 s. [R] My rule for 30 s: a new fact/number/turn every 5-7 s (one per sentence pair). [O]
- Length: quso's dataset: 11-20 s band has the highest median views; recommends 11-30 s unless content needs
  more. [R] Jenny's typical Short ~34 s. [R]
- Loop: YouTube's 2021 Shorts report advised "planning the ending so it flows into the beginning"; Jake
  Fellman's loop Shorts went from 96.8% to 187.1% average percentage viewed. Since 31-mar-2025 every replay
  is a view. [E/R] https://vidiq.com/blog/post/double-youtube-watch-time-looping-shorts
  -> write the LAST line first and make it lead into line 1 (last line "...aur isi wajah se", first line
  "Pakistan ne 1992 ka World Cup jeeta"). [O]
- End abruptly right after the payoff: MrBeast doc "satisfying payoff at the end of the video with an abrupt
  ending"; Jenny "end abruptly on a high note". [R] https://larryjordan.com/articles/social-media-production-tips-from-mrbeast/
- CTAs: mid-video at peak, not at the end (Jenny teardown). [R] Comment prompts: YouTube's own editor pushes
  polls/quiz/Q&A stickers for responses. [E] https://www.socialmediatoday.com/news/youtube-offers-tips-on-working-with-shorts-videos/
- Comment bait that is not cringe [O]: a question with a one-word answer the viewer already has an opinion
  on ("Babar ya Kohli? Ek naam."), or the quiz answer before the reveal ("Pause karo, jawab likho").
  Never "aapki kya raay hai, comment mein zaroor batayein". Never "comment YES if..." (engagement bait).

## 4. Long video (8-14 min documentaries / explainers)

- YouTube: Intro = % still watching at 30 s; fix by matching title/thumbnail and changing the first 30 s;
  "top moments" late in a video = move compelling material earlier. [E] https://support.google.com/youtube/answer/9314415?hl=en
  Vendors call 50%+ at 30 s "above typical" (not on the help page). [R]
- MrBeast doc [R, authenticity unconfirmed]: most loss is in minute 1; minute 1 proves the thumbnail promise;
  minutes 1-3 "transition from hype to execution... Stop telling people what they will be watching and start
  showing them"; a "3 minute re-engagement" ("content that is highly interested that fits the story and makes
  people genuinely impressed"), another around minute 6; "no dull moments"; minutes 3-6 hold the most exciting
  simple content; abrupt ending after the payoff; wow moment early (house by crane ~30 s in).
- YouTube editor: the opening seconds of a long video reached from a Short must "confirm they made the right
  choice". [E]
- Structure I recommend [O, built from the above]:
  0-15 s cold open: the most dramatic true moment, mid-action, no title card, no greeting.
  15-30 s stakes + promise: why it matters to the viewer today + the question the video answers (without
  "is video mein"). One concrete number.
  30-60 s first payoff: answer a small part early to prove the video delivers.
  Each chapter opens with a question and ends on an unresolved turn the next chapter answers
  ("lekin asal kahani yahan se shuru hoti hai"). A re-engagement beat every ~3 min.
  Best material in minutes 3-6, not saved for the end.
  End: payoff, one line of meaning, stop. No recap, no long outro.
- Our test: six 8-10 min history videos got 0 views (CLAUDE.md 21-oct-2026): packaging (topic/title) is the
  first problem, not the script. MrBeast doc: CTR decides topics; "the more extreme, the better", but the video
  must match it or AVD falls. [R]

## 5. Titles and hashtags

- Shorts ranking follows viewers' choices ("The audience is the algorithm", Sherman 2023; "The algorithm
  follows the audience", Ritchie 2024). File name does not matter, title does (Ritchie Q&A); hashtags optional. [E]
- Shorts title max 100 characters (help page). [E] https://support.google.com/youtube/answer/10059070?hl=en
- Hashtags: up to 3 shown by the title; more than 60 = all ignored. [E] https://support.google.com/youtube/answer/6390658?hl=en
- Content buckets: repeatable formats with similar titles so YouTube links them (Jenny, via vidIQ). [R]
- Long titles: Test & Compare tests up to 3 titles and picks by WATCH TIME, not CTR (2025). [E via SEJ/Tubefilter]
  https://www.searchenginejournal.com/youtube-title-a-b-testing-rolls-out-globally-to-creators/562571/
  -> a title that over-promises loses on the metric YouTube uses.
- YouTube "Get feedback" (sep-2026, US only) grades hook, pacing and visuals before publish: these are what
  YouTube itself checks. [E] https://www.searchenginejournal.com/youtube-gives-you-feedback-on-shorts-before-publishing/589088/
- Title rules [O]: Shorts: subject + twist, under ~45 characters, words a viewer would search (player, team,
  country), not a summary. Long: specific promise + concrete noun/number, payoff in the first 50 characters,
  title and thumbnail text never repeat each other.

## 6. Prompt engineering for human-sounding scripts

- Self-Refine (Madaan et al., NeurIPS 2023): generate -> self-feedback -> refine with the same model, ~20%
  absolute average gain over one-shot generation across 7 tasks incl. dialogue. [E] https://arxiv.org/abs/2303.17651
- Meincke, Mollick, Terwiesch 2024: plain prompts give low idea diversity; step-by-step prompting gave the most
  diverse/unique ideas, close to human groups -> brainstorm many hooks in a reasoning step. [E]
  https://papers.ssrn.com/abstract=4708466
- LLM-as-judge has position and verbosity bias (Zheng et al. 2023, "Judging LLM-as-a-Judge with MT-Bench",
  arXiv 2306.05685): shuffle candidate order, fixed rubric. [E]
- Anthropic docs: "Tell Claude what to do instead of what not to do"; give the reason behind a rule;
  3-5 diverse examples, because models pick up unintended patterns from examples. [E]
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Google Gemini 3 guide: blanket negative instructions get over-applied; state the positive behaviour; keep
  temperature at 1.0. [E via search summary of the official page]
  Phil Schmid (Google DeepMind DevRel) template: "Does this sound like a human or a template? If it sounds
  robotic, rewrite it." [R] https://www.philschmid.de/gemini-3-prompt-practices
- Antislop (Paech et al., ICLR 2026): some slop patterns appear >1,000x more often in LLM output than in
  human text; they suppress them at sampling time / by fine-tuning, not with prompt ban lists. [E]
  https://arxiv.org/abs/2510.15061
  -> enforce banned phrases in CODE (regex after generation, one rewrite naming only the hits); keep the
  generation prompt positive ("start on the fact", "talk like a friend at a dhaba"). [O]
- No controlled study found that "do not say X" raises X in text LLMs (white-bear effect shown for image
  models only). [E: absence] https://arxiv.org/html/2404.15154v2
- Wikipedia "Signs of AI writing" (WikiProject AI Cleanup; descriptive, not proof): significance inflation
  ("stands as a testament", "pivotal role", "evolving landscape", "indelible mark", "deeply rooted"), trailing
  "-ing" analysis ("highlighting...", "underscoring..."), promotional ("vibrant", "rich", "profound", "nestled",
  "in the heart of", "groundbreaking", "renowned"), vague attribution ("experts argue", "observers have cited"),
  negative parallelism ("not only... but also", "It's not X, it's Y", "no X, no Y, just Z"), rule of three,
  em dashes, "Despite its... faces several challenges"; overused words: additionally, boasts, bolstered,
  crucial, delve, enduring, enhance, fostering, garner, interplay, intricate, landscape, meticulously, pivotal,
  robust, showcase, tapestry, testament, underscore, valuable, vibrant; newer: leverage, multifaceted, quietly,
  steady, matters. [E] https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- YouTube "inauthentic content" (renamed 15-jul-2025): mass-produced/repetitive content is not monetisable;
  examples: "narrated stories with only superficial differences", "slideshows with identical narration across
  multiple videos". AI itself is allowed. [E]
  https://www.netinfluencer.com/youtube-clarifies-july-15-policy-update-repetitious-content-rebranded-as-inauthentic-content/
  -> rotate hook types and structures per video; never reuse template sentences across videos.
- Kapwing AI-slop report (oct-2025): Pakistan has 20 AI-slop channels in its top-100 trending (most of any
  country), 5.34B views, 2nd after South Korea. The Pakistani feed is saturated with AI narration. [E]
  https://www.kapwing.com/blog/ai-slop-report-the-global-rise-of-low-quality-ai-videos/

Pipeline recipe [O, built on the above]:
1. Fact pack first (verified facts, each with a number/name/date). The script may only use the pack.
2. Hook step: 12 hooks across 6 formulas (number shock, contradiction, result-first, precise question, stakes,
   versus); judge with a rubric (clear on mute? number or proper noun in first 6 words? a promise the clip
   keeps? no greeting/channel/"is video mein"? under 12 words?), shuffled order; keep the top one.
3. Write the last line first so it flows into line 1.
4. Draft at ~2.7 words/s, sentences of 10 words or fewer, one fact per sentence, "lekin/isliye" turns.
5. Critique pass against the rubric + regex hits from the banned list -> rewrite once.
6. Code check: banned phrases, word count vs target seconds, first sentence has a number or proper noun.

## 7. Banned phrases

Paste-ready, English [E: Wikipedia AI-signs list; O: YouTube clichés]:
delve, tapestry, testament, pivotal, crucial, vibrant, rich history, nestled, in the heart of, groundbreaking,
renowned, intricate, meticulously, underscore, showcase, foster, enhance, leverage, multifaceted, robust,
evolving landscape, indelible mark, deeply rooted, stands as / serves as, plays a pivotal role, not only... but
also, it's not X, it's Y, experts say, in today's fast-paced world, imagine a world, picture this, let's dive in,
buckle up, here's the kicker, without further ado, in this video, welcome back, stay tuned, you won't believe,
mind-blowing, the answer may surprise you, little did they know, fast forward to, the rest is history,
let that sink in, smash the like button.

Paste-ready, Hinglish / Roman Urdu [O]:
namaste dosto / assalam-o-alaikum dosto, doston (as filler), swagat hai aapka (hamare channel par), aaj hum
baat karenge, aaj ki video mein, toh chaliye shuru karte hain, bina waqt zaya kiye, video ko end tak zaroor
dekhein, like share aur subscribe, bell icon dabayein, milte hain agli video mein, aaiye jaante hain /
aaiye samajhte hain, kya aap jaante hain (unless the fact is in the same sentence), yeh jaankar aap hairan reh
jayenge, rongte khade ho jayenge, hosh uda dene wala, ek aisa raaz jo koi nahi batata, itihaas ke panno mein,
aaj ke is daur mein (= "in today's fast-paced world"), na sirf... balki (= "not only... but also"), aham kirdar
ada kiya / mahatvapurn bhoomika (= "pivotal role"), gehri chhaap chhodi (= "indelible mark"), ek naya adhyay
(= "a new chapter"), behad dilchasp / bahut hi rochak (adjective instead of the fact), muaziz nazreen,
aapki kya raay hai comment mein zaroor batayein, toh dosto yeh thi...

English: Wikipedia list above [E]; YouTube clichés ("in this video", "welcome back", "smash the like button",
"without further ado", "let's dive in") [O, consistent with every source's "cut the preamble" rule].
Hinglish / Roman Urdu: NO source found that documents specific Hindi/Urdu phrases as mocked or stale (searched in
English, Hinglish and Devanagari). The list is judgement from (a) the greeting/preamble evidence and (b) literal
calques of the English AI phrases. Treat as [O].
"Kya aap jaante hain": "Did you know + concrete object" works in vidIQ's examples (Nas Daily, "Did you know this
book is poisonous?", 31M). The stale form is the vague standalone opener ("Kya aap jaante hain ek aisi jagah ke
baare mein..."). Allow only when the same sentence carries the specific fact; better to drop it and say the fact.

## 8. Pakistani / Indian audience

- India vs Pakistan, Champions Trophy 2025: 60.2-61.1 crore JioHotstar views, 20.6 crore TV viewers. [E]
  https://www.exchange4media.com/digital-news/icc-champions-trophy-indo-pak-match-records-over-60-crore-views-141157.html
- Google Year in Search Pakistan 2025: cricket tops again (PSL, Asia Cup, Champions Trophy); most searched people
  were cricketers Abhishek Sharma, Hassan Nawaz, Irfan Khan Niazi (new names = search demand); dramas next. [E]
  https://dailytimes.com.pk/1414617/what-did-pakistanis-google-the-most-this-year-search-records-reveal-all/
- YouTube India 2025: 76% of surveyed Gen Z go to YouTube "to find out more when something is happening";
  77% watched translated content; 68% use slang from videos/memes; IPL and Asia Cup were the shared moments. [E]
  https://blog.google/intl/en-in/products/platforms/2025s-biggest-trends-on-youtube-that-gave-india-a-new-shared-vernacular/
- Hindi "fact channels" grew on boisterous news-anchor voice-overs (4 of the 10 fastest-growing channels,
  Jan 2023) but many were terminated for reused content. [E] https://restofworld.org/2023/indian-teenagers-youtube-shorts/
- Hindi GK quiz channels are big but low-engagement (GK Drishti ~337M views, 1.83% engagement per vidIQ). [R]
- Asia Cup 2025 no-handshake row dominated; a fabricated Ricky Ponting quote went viral and was denied. [E]
  https://english.factcrescendo.com/2025/09/22/ricky-ponting-has-not-criticised-india-on-the-handshake-controversy-with-pakistan-in-asia-cup-2025/amp
  -> never use a quote the fact pack cannot source.
- Rules [O unless marked]: rivalry framing (Pak vs Ind numbers side by side); numbers viewers can argue about;
  underdog and injustice stories; nostalgia (1992, 2007, 2017); new young players (search demand [E]); quiz as
  a challenge with a timer, never a made-up "only 5% get this right"; binary formats (Sach ya Jhoot, Kaun behtar)
  because a one-word comment is easy; same-day stories first ([E] 76%); everyday Roman Urdu/Hinglish words, not
  bookish Urdu or shuddh Hindi.
