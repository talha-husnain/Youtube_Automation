# Scripting and video quality for Shortkaar Shorts

Research date: 11 November 2026, from web sources only. **[Vendor]** marks a number from a company that sells tools; nobody has audited it. **[Opinion]** marks my own recommendation, not a sourced fact.

## 0. Read the numbers first

A median of 1–12 views means YouTube is barely testing these Shorts. Since March 2025 every start or replay counts as a view. Money and YPP use **engaged views**, which count only viewers who stay past the opening seconds ([TechCrunch](https://techcrunch.com/2025/03/26/youtube-is-changing-how-youtube-shorts-views-are-counted)). Studio's "Stayed to watch" (also shown as "Viewed vs. swiped away") is the share who did not swipe away ([YouTube Help](https://support.google.com/youtube/answer/12220281)). In Paddy Galloway's study of 5,400 Shorts, those under 60% viewed did badly and those at 70–90% did very well ([Digital Information World](https://www.digitalinformationworld.com/2023/04/paddy-galloway-decoded-youtube-shorts.html)). YouTube's Shorts lead, Todd Sherman, says the goal is viewer satisfaction ([Search Engine Journal](https://www.searchenginejournal.com/youtube-explains-how-shorts-algorithm-works/494953/)).

[Opinion] Check "Shown in feed" and "Stayed to watch" for each channel's last 20 Shorts. Few impressions points to a channel-level quality problem (section 3). Under 60% stayed points to the hook (sections 1–2).

## 1. Scripting

**First line and first 2 seconds**
- Creator Jenny Hoyos, on YouTube's blog: "you have one second to hook someone". Her hooks go shock, then intrigue, then satisfaction ([YouTube Blog](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/)).
- TikTok's ad guide says over 63% of its top click-through videos state the key message within 3 s ([TikTok PDF](https://ads.tiktok.com/business/library/Auction_Ads_Creative_Tips.pdf)). This is ad data and shows correlation only.
- ClipFlip puts the keep-or-scroll decision at about 0.8 s ([ClipFlip](https://clipflip.io/resources/how-to-make-viral-clips)) [Vendor].
- [Opinion] Speech starts within 0.3 s. Sentence 1 has at most 8 words and names a person, a number or a conflict. No greeting and no "aaj hum baat karenge". For example, "1999 mein ek over ne Pakistan se World Cup cheen liya."

**Open loops.** [Opinion] Use this shape: hook (0–2 s), stakes (2–8 s), then 2–3 beats that each end on a new small question. The payoff comes in the last 5 s, and the final line leads back into the first. Every loop must close, because YouTube refuses to monetize content that "lacks a clear narrative arc" or uses "deceptive or misleading imagery or narratives" ([YouTube Help](https://support.google.com/youtube/answer/1311392)).

**Sentences and pace for TTS**
- edge-tts accepts no custom SSML, only rate, volume and pitch ([edge-tts](https://github.com/rany2/edge-tts)), so pauses must come from punctuation or from joining sentences synthesised one at a time.
- Syllaby suggests 160–175 words per minute for Shorts and 200–300 ms micro-pauses ([Syllaby](https://syllaby.io/blog/voiceover-pacing-silence-trimming-retention-editing/)) [Vendor, English]. I found no published Urdu or Hindi norm.
- [Opinion] Write 6–12 words per sentence with no nested clauses. Aim for 2.3–2.8 words/s, measured from edge-tts timings.

**Endings.**
- Replays add to public views, but engaged views leave them out (YouTube Help, above).
- YouTube suggests poll and quiz stickers, and replying to comments with a new Short ([YouTube Blog](https://blog.youtube/creator-and-artist-stories/grow-youtube-channel-interactive-shorts/)).
- [Opinion] End on the payoff and a two-option question ("Babar ya Kohli?"), never on "like and subscribe".

**Niche notes**

| Channel | Rules |
|---|---|
| Cricket | No broadcast footage. Content ID blocks claimed Shorts longer than 1 minute ([YouTube Help](https://support.google.com/youtube/answer/6013276)), and Cricket Australia's notice took down archivist Rob Moody's channel ([Wisden](https://www.wisden.com/cricket-news/cricket-fans-aghast-as-youtube-archivist-robelinda2-has-channel-removed-rob-moody-robelinda)). Realistic AI images of real players in a match must be disclosed ([YouTube Help](https://support.google.com/youtube/answer/14328491)). [Opinion] Hook with one name and one number. |
| Controversies | AI personas posing as experts on sensitive topics cannot be monetized (1311392), and Tubefilter lists politics as one such topic ([Tubefilter](https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/)). [Opinion] Give each side one line and show one checkable source. |
| Paisa Kahani | "AI-generated podcast hosts offering financial guidance, investment tips" cannot be monetized (1311392). [Opinion] Tell stories, not tips. |
| Night stories | YouTube refuses to monetize repeated "disturbing themes… without building a cohesive narrative" (1311392). [Opinion] Use a slower voice (2.0–2.4 words/s), but keep the hook. |
| Quran | No music or vocal effects behind recitation ([IslamQA](https://islamqa.info/en/answers/271405), [Dar al-Ifta](https://www.dar-alifta.org/en/article/details/498/dar-al-ifta-reciting-the-quran-accompanied-with-musical-instruments-is-prohibit)). Dar al-Ifta accepts AI recitation only if it follows tajweed and the authorities approve it ([Dar al-Ifta](https://www.dar-alifta.org/en/fatwa/details/24202/the-use-of-artificial-intelligence-in-the-creation-of-electronic-mushafs-and-ai-g)). Readings of material you did not create count as "reused content" (1311392). [Opinion] Use licensed human reciters and a named, published translation. Add 1–2 lines of your own context. |
| Songs | AI music that is the main focus of a video must be disclosed (14328491). Imagery focused on body parts can be age-restricted ([YouTube Help](https://support.google.com/youtube/answer/2802002)). [Opinion] Put the chorus in the first 3 s. |
| Punchline Bazaar | Clips "with little or no narrative" cannot be monetized; clips with "storyline and commentary" can (1311392). [Opinion] The host speaks at least one line every 15 s. |
| Talking babies | Characters in "the same situation over and over again with the same outcome" cannot be monetized (1311392). [Opinion] Keep the cast, change the situation. |

**Pakistani and Indian examples.** No source I found analyses these scripts. The notes below come from tracker pages and video titles.
- **Zem TV** (Pakistan, 6.1M subscribers): its top video is a "why" question with big stakes, "Why Is MBS's Biggest Mega Project Failing?" ([Vidanalyze](https://vidanalyze.com/channel/zemtv.official/shorts)).
- **Urdu Facts HD** (Pakistan, 510K) gets its top views from cricketers' personal stories, not statistics ([vidIQ](https://vidiq.com/youtube-stats/channel/UC0oJfvgU4c2aq4a56FzG7Mw)).
- **Scary Pumpkin** (India, 3.7M) makes animated horror about recurring folk legends in one visual style ([OutlierKit](https://outlierkit.com/channel/scarypumpkin)).
- **Bandar Apna Dost** (India) drew 2.07B views with a recurring AI monkey, but Kapwing classes it as slop ([Kapwing](https://www.kapwing.com/blog/ai-slop-report-the-global-rise-of-low-quality-ai-videos/)).
- About 60% of Pakistani YouTube watch time comes from abroad ([ProPakistani](https://propakistani.pk/2025/12/15/over-1000-pakistani-youtubers-reached-1-million-subscribers-in-2025/)). [Opinion] Write in plain Roman Urdu that Indian viewers also understand.

## 2. Video quality

**How often visuals change.** Vendors say top Shorts cut every 2–4 s ([Opus](https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention)) or 2–3 s (ClipFlip, above) [Vendor]. [Opinion] Change something every 2–3 s, and never hold a shot longer than 4 s.

**Ken Burns or real motion**
- ReelForge prices Ken Burns at about $0.08 per video against $0.50–0.58 for Stable Video Diffusion. It calls the visual gap "small" but did not test retention ([ReelForge](https://reelforgeai.io/blog/why-we-dropped-stable-video-diffusion-2026)) [Vendor].
- Free options: DepthFlow turns one image into a parallax clip (AGPL-3.0) ([GitHub](https://github.com/BrokenSource/DepthFlow)). Wan 2.2 TI2V-5B (Apache 2.0) renders 5 s of 720p in under 9 minutes on a 24 GB GPU ([GitHub](https://github.com/Wan-Video/Wan2.2)).
- FFmpeg's zoompan filter shakes ([ticket #4298](https://ffmpeg.org/pipermail/ffmpeg-trac/2025-March/072904.html)). The fix is to upscale 4–8× before zooming ([still-motion](https://pypi.org/project/still-motion/)).

**Consistency.** Recurring-character series are allowed (1311392). Viewers spot AI through plastic textures, garbled text and inconsistent lighting ([Artlist](https://artlist.io/blog/what-is-ai-slop-and-why-it-matters-for-video-creators/)). [Opinion] Give each channel a fixed style prompt and palette, and vary the composition.

**Captions**
- Google says to keep text out of the top 10%, bottom 25% and right 10% of the frame, which is 192, 480 and 108 px on a 1080×1920 video ([Google](https://business.google.com/us/ad-solutions/youtube-ads/shorts-ads/)).
- BlitzCut suggests 60–75 px text (never below 55 px), in a block at most 850 px wide, placed 700–1,000 px above the bottom ([BlitzCut](https://blitzcutai.com/blog/best-caption-size-youtube-shorts-2026)) [Vendor].
- A study reportedly found deaf and hard-of-hearing viewers disliked single-word caption lines ([NSF PAR](https://par.nsf.gov/servlets/purl/10253921)).
- Netflix's Hindi limit is 17 characters per second ([Netflix](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215600497-Hindi-Timed-Text-Style-Guide)).

**Audio**
- YouTube plays audio at about −14 LUFS. It turns loud uploads down but never turns quiet ones up. Keep true peak at −1 dB or lower ([Youlean](https://youlean.co/?p=30813), [Production Advice](https://productionadvice.co.uk/youtube-loudness/)).
- FFmpeg's `loudnorm` defaults to −24 LUFS ([FFmpeg docs](https://ffmpeg.org/ffmpeg-filters.html)). Left at the default, a Short plays about 10 dB quieter than its neighbours in the feed.
- WCAG asks for background sound at least 20 dB below speech ([W3C](https://www.w3.org/WAI/WCAG21/Understanding/low-or-no-background-audio.html)).
- YouTube's Audio Library includes sound effects ([YouTube Help](https://support.google.com/youtube/answer/3376882)).

**Colour, encoding and thumbnails**
- YouTube's SDR spec ([YouTube Help](https://support.google.com/youtube/answer/1722171)):
  - BT.709, 8-bit, 4:2:0;
  - H.264 High profile with 2 B-frames and a closed GOP of half the frame rate;
  - 8 Mbps at 1080p30 or 12 Mbps at 1080p60;
  - AAC-LC at 48 kHz and 384 kbps;
  - the file index at the front (faststart).
- HDR needs a Rec.2020 grade ([YouTube Help](https://support.google.com/youtube/answer/7126552)) and adds nothing to AI stills.
- Custom Shorts thumbnails began rolling out to all YPP creators on 24 July 2026 ([Tubefilter](https://www.tubefilter.com/2026/07/24/youtube-shorts-custom-thumbnails-neal-mohan-feature-update/)). Hoyos still gets 99.9% of her views from the feed (YouTube Blog, above). [Opinion] The first frame is the real thumbnail.

## 3. "AI slop" and how to avoid it

- **July 2025:** "inauthentic content" now covers "image slideshows, templated storylines… with minimal or no narrative" and "AI-generated content made with generic or unoriginal templates giving the impression of mass production" (1311392).
- **January 2026:** Neal Mohan promised to "reduce the spread of low quality AI content", and Kapwing counted at least 18 slop channels deleted or hidden ([Tubefilter](https://tubefilter.com/2026/01/29/youtube-ai-slop-channel-crackdown-bans/)).
- **July 2026:** YouTube's guidance now names three categories: repetitive content, unsatisfying content and AI personas on sensitive topics (Tubefilter, above). Penalties can reach "all of your existing channels" (1311392), so all eight Shortkaar channels share the risk.
- **Pakistan:** Pakistan had 20 of the top 100 trending slop channels, the most of any country, and 21% of a new account's first 500 Shorts were AI-generated (Kapwing, above).
- **Disclosure:** realistic AI can be flagged through the API field `status.containsSyntheticMedia` ([YouTube API](https://developers.google.com/youtube/v3/revision_history)). Disclosure alone does not cut reach (14328491).

[Opinion] What looks cheap: the same voice, captions and music on every channel; one image held 5–8 s; visuals that don't match the words; garbled text inside images. The fixes:
- Every script carries at least one sourced fact and one opinion line.
- Each channel has its own voice, palette and music.
- Each channel rotates at least 3 script structures.
- Post fewer Shorts. Sherman says there is no magic posting frequency.

## 4. Checks to run before every upload

| Check | Open-source tool | Fail rule [Opinion] |
|---|---|---|
| Black frames | FFmpeg `blackdetect` (its default 2.0 s minimum is too lax) | Any black of 0.1 s or more, or a black first frame |
| Frozen frames | FFmpeg `freezedetect` (default −60 dB, 2 s) | A freeze of 1.5 s or more |
| Static visuals | PySceneDetect `detect-content` ([docs](https://www.scenedetect.com/docs/latest/cli.html)); FFmpeg `siti` motion score ([FFmpeg](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2022-April/131624.html)) | Any shot longer than 4 s |
| Loudness | FFmpeg `ebur128=peak=true` | Outside −15 to −13 LUFS, or true peak above −1 dBTP |
| Dead air | FFmpeg `silencedetect` | Speech starts after 0.3 s, or a gap over 0.7 s |
| Hook | Script linter; [Whisper](https://github.com/openai/whisper) | Sentence 1 over 8 words, or no name, number or question |
| Caption overflow | The renderer's text boxes; [Tesseract](https://github.com/tesseract-ocr/tessdata) for garbled text in images | Any box outside the safe zone, or a line over 18 characters |
| Format | `ffprobe` | Not 1080×1920, yuv420p, BT.709 and faststart |
| Duplicates | PySceneDetect `detect-hash` (perceptual hashing) | More than 30% of frames match one of the last 50 Shorts |

## Top 10 changes, ranked by expected impact

The ranking and the thresholds are [Opinion], built on the sources above.

1. **Hook gate:** speech within 0.3 s; sentence 1 has at most 8 words and a name, number or conflict; the first frame is the strongest image plus 3–5 words of text; no fade-in or greeting.
2. **Originality gate:** at least 1 sourced fact and 1 opinion line per script; at least 3 structures per channel, never the same one twice in a row; own-voice context on Quran; a host line every 15 s or less on Punchline Bazaar.
3. **Visual change every 2–3 s:** fail any shot over 4 s; at least 1 shot in 3 gets real motion (DepthFlow or Wan 2.2); zoompan runs on 4–8× upscaled images.
4. **Loudness:** −14 LUFS ±1 and true peak at −1 dBTP or lower, with `loudnorm` set explicitly; music 18–22 dB under the voice; no music under Quran recitation.
5. **Captions:** 2–4 words and at most 18 characters per chunk; 65–75 px bold with an outline; 700–1,000 px above the bottom; nothing in the top 192 px or the right 108 px.
6. **TTS pacing:** 6–12-word sentences; 2.3–2.8 words/s (2.0–2.4 for night stories); synthesise sentence by sentence with 200–300 ms gaps.
7. **Feedback loop:** default length 25–45 s; retire any template under 60% stayed-to-watch after 48 h; allow 60 s only on channels above 70%.
8. **Policy flags:** set `containsSyntheticMedia=true` for realistic AI of real people or events; no investment advice; no broadcast cricket footage.
9. **QC gate blocks upload on any failure** in the section 4 checks.
10. **Encoding:** H.264 High, CRF 18 with maxrate 16 Mbps, source frame rate, closed GOP of half the frame rate, BT.709, AAC 48 kHz at 384 kbps, faststart, SDR only.
