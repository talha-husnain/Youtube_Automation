# One more channel, music-channel growth, more features (5-nov-2026)

Web research only (web search, page reads, and YouTube's public autocomplete endpoint for the
suggestion lists). No downloader, no GitHub API, no code edited. I grepped the repo only so this note
doesn't recommend things that are already built (listed at the end of Part 3).

How to read it:
- Every factual claim has a URL.
- **(inference)** marks my own reasoning, not a source.
- **(secondary)** marks figures from vendor/SEO blogs or third-party trackers (OutlierKit, vidIQ, Qoruz,
  SpeakRJ, Fluxnote). They model subscribers and revenue; they don't report them. Treat as order-of-magnitude.
- Pages were read on 5-nov-2026 unless a date is given.

---

## 0. The two rule changes that decide everything below

1. **July 2026 inauthentic-content clarification.** It rolled out 16 July 2026 to all YPP channels
   (TechCrunch, 20-jul-2026: https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/).
   Three kinds of channel can't monetize:
   - "generic, repetitive, or template-based" content with little variation between videos, including
     tutorials that only repeat what is already common on YouTube;
   - "off-putting or distressing" content made to manipulate emotions;
   - AI personas presented as human experts on health, legal, financial or political topics.

   The policy page itself (https://support.google.com/youtube/answer/1311392) still lists:
   - "templated storylines, or scrolling text with minimal or no narrative";
   - "AI-generated content made with generic or unoriginal templates giving the impression of mass production";
   - content that "repeatedly uses disturbing themes (such as violence or loss) without building a cohesive narrative";
   - under reused content, "Collections of songs from different artists" and "Songs modified to change the
     pitch or speed, but are otherwise identical".

   Enforcement is real. In January 2026, 16 of the 100 most-subscribed "AI slop" channels were deleted or
   emptied: 35.0M subscribers and 4.7B views between them
   (https://www.netinfluencer.com/youtube-removes-major-ai-slop-channels-with-combined-9-8m-in-estimated-annual-revenue/).
   Kapwing counted 20 AI-slop channels among Pakistan's top-100 trending channels, with 5.34B views
   combined (https://www.kapwing.com/blog/ai-slop-report-the-global-rise-of-low-quality-ai-videos/).
   So the audience watches AI content, and YouTube is removing the templated kind.

2. **YPP terms from 1 February 2027** (Google, 11-aug-2026:
   https://blog.google/intl/en-mena/product-updates/connect-communicate/new-opportunities-to-earn-and-changes-to-the-youtube-partner-program/):
   - **Existing members** keep Shorts ad and Premium revenue only with **10M qualified Shorts views in
     the last 90 days**. Long-form earnings are unchanged.
   - **New applicants** need **1,000 subscribers plus 8,000 watch hours in 12 months, or 20M Shorts
     views in 90 days**.
   - Current partners must accept three sets of terms in Studio **by 31 January 2027**. Channels that
     miss it stop earning from those features on 1 February until they accept
     (https://www.searchenginejournal.com/youtube-updates-partner-program-terms-shorts-payout-rules/585331/).

   **(inference)** A brand-new channel in 2027 almost has to qualify through long-form watch hours. The
   new channel should be a long-form niche that throws off Shorts, not a Shorts-only niche. Shorts pay
   little here anyway: India Shorts RPM is about ₹5-30 per 1,000 views against ₹25-150 for long-form
   (https://upgrowth.in/youtube-cpm-in-india-complete-guide/, **secondary**).

AI labels: YouTube auto-labels "significant photorealistic" AI content using C2PA metadata and SynthID.
On long videos the label sits directly under the player; on Shorts it is an overlay. YouTube says labelled
videos are not demoted and don't lose monetization (TNW, 27-may-2026:
https://thenextweb.com/news/youtube-will-now-automatically-label-ai-generated-videos-whether-creators-disclose-them-or-not).
Disclosure is required for realistic content and for AI music that is "the main focus" of a video. Fantasy
or non-realistic AI content, and AI help with scripts, titles or thumbnails, doesn't need it
(https://support.google.com/youtube/answer/14328491).

---

## 1. ONE MORE CHANNEL: ranked

| # | Niche | Why now (evidence) | Pipeline reuse | Policy risk |
|---|---|---|---|---|
| **1** | **Hindi/Urdu horror stories** (long 15-30 min + teaser Shorts) | Several 1-4M-sub faceless channels; "horror story hindi urdu" is a top YouTube suggestion in PK | History long pipeline almost as-is | Low-medium |
| 2 | Hindi/Urdu true-crime documentaries | One faceless channel averages 3.4M views a video | Controversies pipeline (sources, defamation check) | High |
| 3 | "Money in numbers" as a channel (Urdu/Hindi money and economy explainers) | Highest-RPM niche in India; gold rate is a top PK search | Already built as a kind | Medium |
| 4 | AI and tech explainers in Urdu/Hindi | Gemini was #2 overall search in India 2025 and #1 tech search in PK | Trend explainer + grounded search | Medium |
| 5 | Islamic stories (Qasas-ul-Anbiya, Sahaba) | Large Urdu channels | History + sacred guard | **High (Pakistan law)**: a playlist on the Quran channel, not a new channel |

### 1.1 Hindi/Urdu horror stories ("Khauf ki kahaniyan"): recommended

**Evidence of demand**

| Channel | Size | Format | Source |
|---|---|---|---|
| Scary Pumpkin | 3.7M subs, 931.7M views, 594 videos | Avg ~29.5 min, ~2.3 uploads/week, 84% of views from long-form. Top: "Chhalava Back to Back" 40M | https://outlierkit.com/channel/scarypumpkin (data 8-jul-2026, **secondary**) |
| Skull Tales | 637K subs, 130.1M views, 344 videos | Avg 18.5 min, 0% Shorts | https://outlierkit.com/channel/skulltalesofficial (17-jul-2026, **secondary**) |
| Koo Koo TV Hindi Horror | ~3.5M subs (Aug 2026) | | https://qoruz.com/Koo_Koo_TV_Hindi_Horror/youtube (**secondary**) |
| Horror Stories Hindi Urdu | 1.53M subs, 217.3M views | Only 77 videos | https://www.speakrj.com/audit/report/UCUQ3t3RWHCHMdcXpranvWww/youtube (27-jan-2026, **secondary**) |

- What drives Skull Tales's outliers: trapped-vehicle horror ("Haunted Train" 4.5M, "Haunted Bus"
  3.5M), curses and black magic ("Kaala Jaadu", "Pishachini"), multi-part series, and festival or
  trend-timed specials. Ad revenue is modelled at $4K-10K a month.
- YouTube's own suggestions for "horror story" in PK, fetched 5-nov-2026: "horror story in hindi",
  "horror story hindi urdu", "horror story in urdu", "horror story real", "horror story khooni monday"
  (https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=horror%20story&gl=PK).
  For "jinn": "jinn stories", "jinnat ki video".
- **(inference)** The channels above are Indian. Hindi and Urdu are one spoken language, so the same
  story in Urdu-leaning Hindustani with Roman/Devanagari/Nastaliq titles serves both countries.
  "horror story hindi urdu" being a top suggestion supports that.

**How the pipeline makes it (inference)**
- `history_videos.py` already does script -> chapters of scenes -> painted AI pictures + parallax ->
  OmniVoice/Gemini narration -> a music bed per chapter -> YouTube chapters -> thumbnail. Horror changes
  only the writer prompt (an original story with a twist, not facts), the bed moods (drones, low strings),
  and adds sound effects.
- Sound effects source: the Sonniss GDC bundles are "royalty-free for commercial use and no attribution
  is required", but may not be used for AI training
  (https://bedroomproducersblog.com/2020/09/22/sonniss-gdc-2020-bundle/,
  https://app.cinevva.com/guides/free-sound-effects-music; check sonniss.com/gdc-bundle-license before use).
- Shorts: a 45-60 s cliff-hanger cut from each long story, linked to it (see 3.8). Series ("Part 1/2")
  and "back to back" compilations of the channel's OWN stories are proven formats (Scary Pumpkin's top
  video is one).

**Ad rates**
- No reliable horror-specific RPM was found. Third-party revenue estimates for "Horror Stories Hindi
  Urdu" range from $596 to $289K a month, which shows how unreliable they are.
- **(inference)** Treat it like "entertainment" in upGrowth's India table: ₹40-80 RPM long-form
  (https://upgrowth.in/youtube-cpm-in-india-complete-guide/, **secondary**). Pakistan is a bit lower:
  one table gives an average CPM of $0.65 for Pakistan vs $0.77 for India
  (https://thesrzone.com/2025/07/youtube-cpm-cpc-rates-by-country.html, **secondary**).
- The lever is minutes per viewer from 20-30 min stories, not CPM.

**Policy risk: low-medium**
- **Ads:** scripted violence where "injuries are mostly indiscernible" keeps full ads. Severe or shocking
  injuries get limited ads. "Dramatized shocking elements presented with little context, solely with the
  intent to shock" gets no ads. Frightening material in family-styled content ("Characters aimed to scare
  kids, such as Momo or adult horror characters") gets limited or no ads
  (https://support.google.com/youtube/answer/6162278).
  **(inference)** Keep the painted, adult style the history channel already uses. No cartoon look that
  YouTube's classifier could read as made for kids.
- **Templated:** "characters put in the same situation over and over again with the same outcome" is
  named as inauthentic (1311392). The writer needs a rotating set of plot shapes (twist, haunting, curse,
  survival, possession) and the same per-channel sameness gate the 4-nov note proposed.
- **Distressing:** a cohesive narrative is the defence, and a story has one by construction.
- **Disclosure:** fiction in a painted style is non-realistic, so no disclosure is needed (14328491).
- **(inference)** Religion: jinn stories touch Islamic belief. Never quote Quran verses as "spells", never
  depict religious figures, and reuse the existing sacred rules.

### 1.2 Hindi/Urdu true-crime documentaries: strong demand, high risk

- **Wronged:** 1.9M subs, 488.7M views from 145 videos, an average of **3.4M views a video**, about one
  ~20-min upload a week. Top videos are Indian cases (Greeshma-Sharon Raj 13.0M, "Muskan Meerut Drum
  Case" 8.9M). Ad revenue is modelled at $5K-7K a month
  (https://outlierkit.com/channel/wrongedx, 23-sep-2026, **secondary**).
- **Pipeline:** `controversy_shorts.py` already requires 3+ reliable sources and runs a defamation check
  (seen in the code). A long true-crime video is that pipeline plus maps and timelines.
- **Ads:** "Documentaries about crime" get full ads. A recent homicide told with "descriptive language of
  the circumstances of death" gets limited ads (https://support.google.com/youtube/answer/6162278).
- **Pakistan law:** the January 2025 PECA amendment set penalties for spreading "fake news" of "up to
  three years in prison or a fine of Rs. 2 million"
  (https://propakistani.pk/2025/01/23/na-passes-controversial-peca-amendment-bill-to-tighten-social-media-rules/).
  In July 2025 a court ordered 27 YouTube channels blocked under PECA
  (https://rsf.org/en/pakistan-multiple-journalists-and-dozen-youtube-channels-targeted-under-peca-less-year).
- **(inference)** Real victims and families, realistic AI images of real people (which need disclosure and
  are ethically fraught), and overlap with "Controversies explained" put this second. If you do it: only
  closed cases with verdicts, no minors, no graphic detail, Indian and international cases rather than
  Pakistani ones, and no AI faces of real people.

### 1.3 "Money in numbers" as its own channel: cheapest to launch

- **Highest ad rate:** upGrowth's India long-form RPMs are finance/investment ₹100-150, technology
  ₹80-120, entertainment ₹40-80, comedy ₹30-60, music ₹25-50
  (https://upgrowth.in/youtube-cpm-in-india-complete-guide/, updated Sep 2026, **secondary**). Finance
  is roughly 2-3x the comedy channel (inference from that table).
- **Pakistani demand:** "gold prices" was a finance trend in Pakistan's Google Year in Search 2025
  (https://profit.pakistantoday.com.pk/2025/12/09/google-year-in-search-2025-cricket-leads-pakistans-online-trends-amid-rising-interest-in-dramas-floods-and-govt-schemes/).
  YouTube suggestions for "gold rate" in PK are all dated daily queries ("gold rate today in pakistan
  4 nov 2026"), fetched 5-nov-2026.
- **Pipeline:** the motion-graphics kind (bars, counters, timelines) exists.
- **Risk:**
  - The July 2026 rule bans **AI personas presented as financial experts**. No persona, no
    "advice": numbers and history ("Rs 1 lakh in gold in 2010 vs today").
  - A daily "gold rate today" Short on one template is the textbook templated case **(inference)**.
    Make it weekly explainers instead.
- No strong evidence was found of a large faceless Urdu finance channel. Vendor guides rank Hindi
  finance explainers as the top faceless niche in India
  (https://fluxnote.io/guides/highest-rpm-faceless-youtube-niches-2026, **secondary**).

### 1.4 AI and tech explainers in Urdu/Hindi

- **Search demand:** Google Gemini was India's #2 overall search of 2025, with Grok also in the top 10
  (https://www.businesstoday.in/technology/news/story/indias-search-habits-in-2025-reveal-a-year-driven-by-culture-curiosity-and-big-tech-shifts-504934-2025-12-04).
  In Pakistan, Gemini, Google AI Studio and Ghibli-style photo creation were top tech and how-to trends
  (profit.pakistantoday link above).
- **Ad rate:** tech is ₹80-120 RPM in India (upGrowth).
- **Weak spot:** no evidence of a big faceless Urdu tech channel. Trackers show small channels: Urdu_Ali
  23.9K, Burhan's TechLab 1.7K (https://socialcounts.org/youtube-live-subscriber-count/UCwrqvYpSGhLX1z78jM5lyfg,
  https://developereducators.com/channel/burhanstechlab/, **secondary**).
- **Policy:** Halprin named tutorials that "reproduce content already common on the platform" as
  inauthentic (TechCrunch link above). **(inference)** News value decays fast, and screen-recorded
  how-tos are not something this pipeline makes.

### 1.5 Islamic stories: only as a playlist on the existing Quran channel

- **Demand is real:** "Stories of the Prophets - Quran Stories" has about 914K subs (Jul 2026), up from
  about 810K in Dec 2024 (https://qoruz.com/urduislamickidsvideos/youtube,
  https://vidiq.com/youtube-stats/channel/UCIIWR4JQld9zLjnAWPNlYlQ, **secondary**). Urdu Center Plus has
  about 1.54M (https://vidiq.com/youtube-stats/channel/UCZZGhX3gGSX_GqR7oHhkatg, **secondary**).
- **Pakistan's regulator acted in 2026:** PEMRA suspended Geo News for 15 days over "religious
  visualization" in its Muharram-10 programme "Safar-e-Ishq" (notice 27 June 2026:
  https://www.arabnews.pk/node/2648852/pakistan).
  On 12 July it kept the order and added a Rs10M fine
  (https://www.journalismpakistan.com/as-geo-news-returns-pemra-s-signals-tougher-era-for-pakistan-s-broadcasters).
  Reports that the programme used AI images of Islamic figures are unconfirmed
  (https://www.theweek.in/news/world/2026/06/29/what-pakistans-geo-news-aired-on-muharram-before-15-day-suspension.html).
- **The Council of Islamic Ideology ruled** that visual portrayals of prophets and revered figures are
  impermissible and urged pre-publication screening (https://pakobserver.net/cii-declares-publication-of-visual-depictions-of-prophets-sacred-personalities-impermissible/, 1-jul-2026).
- `history_videos.py` already shows no people for sacred topics (seen in the code); this case confirms
  that rule is right.
- **(inference)** A separate channel would also look like the "Bible story" channels that blogs report
  were demonetized for mass production (single-source, unverified:
  https://www.webpronews.com/youtubes-war-on-ai-slop-collides-with-faceless-creators-who-built-the-platform-first/).
  As a calligraphy-and-landscape playlist on the Quran channel it adds watch time without a new channel to
  get monetized.

### 1.6 Considered and not recommended

- **Kids' rhymes:**
  - YouTube says it holds YouTube Kids to "elevated standards" and limits AI content there to a small
    set of selected channels. Over 200 experts asked Google to ban AI kids' videos
    (https://www.thestar.com.my/tech/tech-news/2026/03/11/how-ai-generated-videos-are-distorting-your-childs-youtube-feed,
    https://fairplayforkids.org/wp-content/uploads/2026/03/YouTube-Letter-AI-Slop.pdf).
  - Made-for-kids videos get no personalized ads and no comments
    (https://tubefilter.com/2020/01/07/youtube-disables-more-product-features-kid-oriented-content/),
    and can't use Test & Compare (https://support.google.com/youtube/answer/16391400).
- **Facts / did-you-know:**
  - Saturated. FactTechz has about 21M subs, but one tracker shows ~0 net gain in 30 days
    (https://vidiq.com/youtube-stats/channel/@facttechz/, **secondary**).
  - Shorts-only formats hit the 2027 10M/90-day Shorts bar.
- **Motivational / Islamic-reminder slideshows:** "image slideshows ... scrolling text with minimal or no
  narrative" is the policy's own example (1311392).
- **Country comparisons / geography:** the reuse is good (flag maps, bars), but the one faceless
  data-viz channel found is small: about 13.3K subs, 21.7M views
  (https://outlierkit.com/channel/datavisualization2, **secondary**). Better as a series inside Money
  in numbers **(inference)**.
- **Other sports / gaming:**
  - Pro Kabaddi League was a top-5 Indian search of 2025
    (https://www.deccanherald.com/technology/year-in-google-search-2025-operation-sindoor-waqf-bill-dharmendra-kantara-ipl-vaibhav-suryavamshi-gemini-ai-dominate-3819481).
  - Match footage is copyrighted, and gaming needs capture the pipeline doesn't do **(inference)**.

---

## 2. MUSIC CHANNEL GROWTH (AI songs in English, mood playlists)

### 2.1 Which moods people search for

YouTube's suggestions, fetched 5-nov-2026 from `suggestqueries.google.com` (`ds=yt`). They show what
people type, ranked by popularity, but not volume.

| Seed (region) | Top suggestions |
|---|---|
| "sad songs" (PK) | punjabi, lyrics, hindi, mashup, **english**, new, urdu, **playlist** |
| "english songs" (PK) | **with lyrics**, remix, **playlist**, 2026, mashup, dance, **sad**, trending |
| "phonk" (PK) | song, music, **slowed reverb**, 2026, **edit**, playlist, slowed |
| "gym music" (IN) | hindi, song, bollywood, english, **phonk**, 2026, punjabi, playlist |
| "lofi" (IN) | songs, hip hop, songs hindi, music, **sad songs**, beats, bhojpuri, **love song** |
| "study music" (IN) | lofi, for concentration, hindi, playlist, alpha waves, **1 hour**, motivation, rain, 40 hz |

What that suggests (inference):
- "english songs **with lyrics**" being the #2 suggestion in Pakistan supports the lyric-video format.
- "playlist", "1 hour" and "mashup" show people want long listening sessions, not single songs.
- "sad" crosses every seed. It was also the most-searched term on Uppbeat's music library in 2025, a
  platform signal rather than YouTube-wide (https://uppbeat.io/blog/music/biggest-music-trends-2025).
- Phonk is the Shorts soundtrack: Tubefilter (24-feb-2026) calls it the music of Gen-Alpha "brainrot"
  Shorts, and "Passo bem Solto" Shorts topped India's 2025 year-end rankings
  (https://www.tubefilter.com/2026/02/24/gen-alpha-brainrot-shorts-phonk-music-brazil/).

### 2.2 What each mood earns

OutlierKit's planning estimates, not survey data: sleep/relaxation $4-8 RPM, lofi/study $3-6, generic AI
playlists ~$1, type-beats/phonk ~$0.50. They list "AI phonk and TikTok loop channels" and "raw Suno/Udio
dumps" as niches to avoid (https://outlierkit.com/resources/ai-generated-music-youtube-monetization-2026/,
updated 19-jun-2026, **secondary**). India music RPM is ₹25-50 long-form (upGrowth).

**(inference) What to do with it:**
- **Shorts for reach:** gym phonk, sad and romantic Shorts bring discovery.
- **Long mixes for money:** lofi/chill, study/focus, sleep/rain and sad bring watch time and the better RPM.
- Two moods are missing from `music_moods.py` today:
  - **study/focus**: instrumental lofi, 70-85 BPM, no vocals;
  - **sleep/rain**: ambient, 60-70 BPM.
- Both are instrumental, so the free MIT ACE-Step 1.5 can make them instead of Lyria at $0.08 a song
  (https://9to5google.com/2026/03/25/gemini-lyria-3-pro/ for Lyria 3 Pro's 3-minute songs and Gemini
  app limits; the $0.08 API price is from secondary listings).

### 2.3 Long "mood mix" videos vs Shorts

- **OutlierKit's case** (https://outlierkit.com/resources/youtube-music-channel-growth-strategy/, 27-sep-2026, **secondary**):
  - "one well-positioned 3-hour mix can out-earn dozens of standard videos";
  - aim for 1-hour-plus for sleep and focus;
  - track "watch time per viewer" ahead of CTR;
  - order tracks so they flow;
  - name the mood in context ("lofi study music", "rain sounds for sleeping").
  - Benchmarks: Lofi Girl 15.8M subs, Soothing Relaxation 12.0M, Sleepless Historian 702K.
- **The catch:** a "1-hour lofi mix" that loops one short AI clip with small filter changes counts as
  reused content (OutlierKit AI-music page above).
- **(inference) Recipe for a weekly 30-60 min mix per mood:**
  - built from 12-20 of the channel's OWN full-length songs (Lyria 3 Pro makes up to 3 minutes);
  - a fresh set of songs each time, never the same songs reshuffled;
  - one chapter per song, using the existing `long_video.chapters`;
  - crossfades and one mastering target for the whole mix (2.5);
  - a different visual per song;
  - Shorts point to it as the related video (3.8).
  - Title pattern from the suggestions: "Sad English Songs Playlist 1 Hour (with Lyrics) | AI Music".
- **Don't** upload slowed or sped-up copies of the channel's own songs as separate videos. The policy
  names "Songs modified to change the pitch or speed, but are otherwise identical" (1311392). If
  "slowed + reverb" is wanted, generate a new arrangement (inference).
- **Shorts pay little and get harder from Feb 2027** (10M qualified Shorts views per 90 days), so long
  mixes are what earn **(inference)**.
- **24/7 "radio" live stream** (the Lofi Girl model): YouTube archives a stream automatically only if it
  is under 12 hours, so keep a local recording (https://support.google.com/youtube/answer/6247592).
  **(inference)** Only worth it once there are 50+ chill/study songs, and only on a stable connection.
  The laptop's power and internet are the limits. A 720p ffmpeg RTMP loop is about 2-3 Mbps.

### 2.4 YouTube's current policy on AI music

- **Disclosure:** AI music that is "the main focus of the video" must be disclosed (14328491). The code
  already sets `containsSyntheticMedia` on upload.
- **Automatic labels:** every Lyria 3 track carries SynthID (9to5google above), and YouTube auto-labels
  from SynthID/C2PA (TNW above). Expect the label on every song; YouTube says it doesn't hurt reach or money.
- **YouTube Music labels (14 Oct 2026):** a label on the player page for tracks with "significant" GenAI
  use, from partner declarations and YouTube's own detection, also coming to the main app
  (https://blog.youtube/news-and-events/youtube-music-ai-labels/). The post says nothing about reach.
- **Music partners declare** Fully / Partly / No GenAI per asset (https://support.google.com/youtube/answer/17124251).
- **Content ID:** don't plan on it. Fully AI tracks are "usually not eligible", and proof of rights and
  human contribution may be requested (https://lastplaydistro.com/blog/youtube-content-id-ai-generated-music-policy-2026-what-creators-must-know,
  **secondary**). **(inference)** That also means others can re-upload the songs with nothing to stop
  them except manual copyright takedowns.
- **Lyria commercial terms are unclear in public:** a 21-oct-2026 Google AI developer-forum question
  about distributing and monetizing Lyria 3.5 output got no official answer
  (https://discuss.ai.google.dev/t/can-music-generated-with-lyria-3-5-gemini-api-gemini-app-be-distributed-to-streaming-services-through-a-distributor-like-distrokid/191171).
  Google says Lyria 3 was trained on material YouTube and Google have rights to use, and that output
  filters check generations against existing content (9to5google above).
  **Owner action:** read the Gemini API / Vertex "Generative AI Additional Terms" for the access route
  actually used, and keep the prompt and lyrics for every song as proof of human contribution.

### 2.5 Free / open-source music tools worth adding (licence noted)

| Tool | Licence | Use here | Note |
|---|---|---|---|
| **ACE-Step 1.5** (already cloned, per the 4-nov note) | MIT; model card: "You can strictly use the generated music for commercial purposes" (https://huggingface.co/ACE-Step/Ace-Step1.5) | Instrumental study/sleep beds for long mixes; "Repaint" to make the end of one track lead into the next | Up to 10 min a track, <4 GB VRAM; CPU speed unverified |
| **Matchering 2.0** | GPL-3.0 (https://github.com/sergree/matchering) | Master every song in a mix against ONE reference track (RMS, EQ, peak, stereo width) so the hour sounds even, then the existing loudnorm -14 | Run it as a separate process (CLI or Docker), not imported into the app, to keep GPL away from the codebase **(inference)** |
| **Beat This!** | Code and weights MIT; some training audio was copyrighted (https://github.com/CPJKU/beat_this) | Downbeats (bar starts) for cuts on the "1"; `beats.py` has beats but no downbeats | Runs on CPU |
| **Chromaprint / fpcalc** | Own code MIT; as a whole LGPL-2.1 (includes FFmpeg parts) (https://raw.githubusercontent.com/acoustid/chromaprint/master/LICENSE.md) | Local fingerprint check before upload: block a song that is a near-copy of one already published (reused-content risk) | Do NOT use the AcoustID web service: commercial use is a paid plan (https://apis.io/providers/acoustid/, mirror, **unverified**) |
| ffmpeg `acrossfade`, `showcqt`, `avectorscope` | ffmpeg's licence (already in use) | Crossfades in mixes; a moving visualiser layer so each mix song looks different | |

The 4-nov note already covered MusicGen (non-commercial), Demucs weights (licence unclear) and
audio-separator (MIT).

---

## 3. MORE FEATURES (not in the 4-nov note, not already in the code)

Ranked by value per effort. Unit costs are from Google's docs.

### 3.1 Retention-curve drop-off finder (S-M)
- **What:** for each long video, pull the audience-retention report and find where viewers leave.
  Only one video per request (https://developers.google.com/youtube/analytics/channel_reports):
  - dimension `elapsedVideoTimeRatio` only;
  - metrics `audienceWatchRatio`, `relativeRetentionPerformance`;
  - filter `video==ID`.
- **Why:** the code only reads `averageViewPercentage` and `engagedViews` today. A curve says WHERE
  people leave. The history/horror pipelines know every scene's start time, so each dip maps to a named
  scene, and the writer gets "scene type X loses viewers at 30%" lessons **(inference)**.

### 3.2 Search-term and "suggested next to" harvest (S)
- **What:** the traffic-source detail report with `insightTrafficSourceType==YT_SEARCH` returns the
  search terms that found each video. With `RELATED_VIDEO` it returns the video IDs YouTube recommended
  you beside. `maxResults` must be 25 or less and `sort` (`-views`) is required
  (https://developers.google.com/youtube/analytics/dimensions, channel_reports above).
- **Why:**
  - Real search terms go into titles, tags and next topics (today SEO uses autocomplete, which is what
    people type, not what found you).
  - The RELATED_VIDEO IDs are your true rivals for every channel, not only comedy (`rivals.py` covers
    comedy Shorts only).
  - The Analytics API quota is separate from the Data API upload quota.

### 3.3 Thumbnail CTR loop from the Reporting API "reach" reports (M)
- **What:** since 15-jan-2026, channel owners get daily bulk reports `channel_reach_basic_a1` /
  `channel_reach_combined_a1` with `video_thumbnail_impressions` and `video_thumbnail_impressions_ctr`.
  Data arrives 48-72 h late (https://developers.google.com/youtube/reporting/revision_history).
- **Why:** this is the only API source of impressions and CTR. Score each thumbnail style per channel
  (text position, face or no face, colour) and let the thumbnail planner prefer winners. Nothing in the
  code uses the Reporting API yet.

### 3.4 Test & Compare helper (S)
- **What:** for every long video, make 3 titles and 3 thumbnails, then send a Telegram task with the
  files and the video link so the owner sets up the test.
- **Why:** YouTube tests up to 3 titles/thumbnails and keeps the one with the highest **watch time
  share** (https://support.google.com/youtube/answer/16391400). It only works on long-form videos (not
  Shorts, not made-for-kids), on desktop Studio, needs advanced features, and runs up to two weeks. The
  help page mentions no API.
  **(inference)** About 5 minutes of the owner's time per video for YouTube's own statistically tested winner.

### 3.5 YPP-2027 readiness tracker (S)
- **What:** per channel, track 90-day engaged Shorts views against **10M** (existing members), and for
  channels not yet in YPP, 12-month watch hours against **8,000** and 90-day Shorts views against
  **20M**. Send a weekly Telegram line.
- **Why:** these thresholds start 1-feb-2027 (Google blog, section 0). Partners must accept the new terms
  in Studio first, so that is an owner action now.
  **(inference)** "Qualified views" are closest to `engagedViews`, which the code already reads.

### 3.6 Long-form playlists as podcasts (S)
- **What:** set `status.podcastStatus = enabled` on History, horror and Quran series playlists. It needs
  a square playlist image uploaded first with `playlistImages.insert` (50 units, JPEG/PNG, 1:1)
  (https://developers.google.com/youtube/v3/docs/playlists, https://developers.google.com/youtube/v3/docs/playlistImages/insert).
- **Why:** YouTube has 1B+ monthly podcast viewers (https://blog.youtube/news-and-events/1-billion-monthly-podcast-users/).
  **(inference)** Recitation, documentaries and stories are listen-in-background content. Marking them as
  podcasts lists them where podcast listeners browse. No views lost; one API call per playlist.

### 3.7 English auto-dub of the Urdu long videos (owner switch + guard)
- **What:** YouTube's automatic dubbing supports **Urdu -> English** and Hindi -> English. It is on by
  default for eligible channels. Music-only videos, videos over 120 min and copyrighted content are
  excluded. Studio has a "Publish manually" option to review dubs first
  (https://support.google.com/youtube/answer/15569972). In December 2025, 6M+ viewers a day watched at
  least 10 minutes of auto-dubbed video
  (https://www.indiatvnews.com/technology/news/youtube-auto-dubbing-feature-expands-to-all-users-now-supports-27-languages-2026-02-05-1029070).
- **(inference)** History and horror documentaries reach English speakers, who are worth far more per view.
  **Guard:** set "Publish manually" or turn dubbing off for the **Quran** channel. A machine re-voicing
  of a translation of the Quran is a religious-accuracy risk.

### 3.8 Shorts -> long "related video" link (S)
- **What:** YouTube's "related video" puts a tappable link to another video on the same channel inside
  the Shorts player (https://support.google.com/youtube/answer/14075157). Tool vendors report the public
  API can't set it (https://help.opus.pro/docs/article/link-shorts-to-original-video).
- **Feature:** after upload, send a Telegram list of Short -> long pairs (teaser -> story, song -> mix,
  history teaser -> documentary) for the owner to set in Studio desktop. This is the main path from
  Shorts views into the long-form watch hours that 2027 needs **(inference)**.

### 3.9 Song fingerprint dedupe (S): see 2.5 (Chromaprint, local only)
**(inference)** The songs channel's sharpest policy risk is near-duplicates. A fingerprint gate before
upload is cheap insurance, and the same gate can catch a Punchline Bazaar clip that was already uploaded.

### 3.10 Horror sound-effects library (S): see 1.1 (Sonniss GDC bundles)
- Royalty-free, commercial use, no attribution; AI training forbidden.
- Index the files once by tag (door, wind, whisper, footsteps) so the writer's beat sheet can call for
  them **(inference)**.

### Already in the code (seen, so not repeated)
- title/description **localizations**;
- `containsSyntheticMedia` on upload;
- caption-track upload in several languages (400 units each);
- YouTube **chapters** for long videos;
- loudnorm at -14 LUFS;
- YouTube autocomplete (`trend_explainer.py`) and Google Trends RSS (`trends.py`);
- rivals for comedy (`rivals.py`);
- `averageViewPercentage` / `engagedViews` hook lessons;
- the sacred-figures no-people rule;
- 3-source + defamation gate for controversies;
- beat-synced cuts (`beats.py`);
- music-bed variety (against mass-production sameness);
- LLM spam/abuse skip in comment replies.

---

## Owner actions arising from this note

1. **Accept the new YPP terms** in Studio for every monetized channel by 31-jan-2027 (section 0).
2. Read the **Lyria terms** for the access route in use (2.4).
3. Check **auto-dubbing** per channel; set Quran to "Publish manually" or off (3.7).
4. Set up **Test & Compare** and **related video** links when Telegram asks (3.4, 3.8). Both are Studio-only.
5. Check sonniss.com/gdc-bundle-license before importing sound effects (1.1).
