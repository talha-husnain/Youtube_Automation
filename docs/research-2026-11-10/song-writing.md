# What makes a song's "hot part" work, and how to write original songs that have one (research, 10-nov-2026)

Why: the owner noticed that every hit song has a "hot part" (the stretch people replay and use in Shorts) and
wants our AI songs (English and Urdu; romantic, sad, workout, gym, chill, party) to be more engaging.

How:
- YouTube's own "Most replayed" graph for 42 well-known songs (yt-dlp, metadata only, one request at a time with
  pauses, nothing downloaded, no captions fetched). Raw data: `song_research_heatmap.json`, summary:
  `song_research_heat_summary.json` (both in the session scratchpad).
- YouTube search sorted by view count for song Shorts: 57 searches, about 1,100 results
  (`song_research_shorts.json`, `song_research_shorts_hashtag.json`).
- Web research on songwriting craft and on Urdu/Pakistani song conventions (sources at the end).
- **No lyrics were collected or are quoted here.** Song sections are described in our own words. We copy patterns
  (where the hook sits, how long it is, how it is built), never words or melodies.

---

## Short version (for the owner)

1. **The hot part is a chorus, a drop or a big "climax" moment, never the instrumental intro.** In 19 of the 41 songs
   that had a clear hot spot it was the *first* chorus (or first drop); in the rest it was a later chorus, the
   moment a second singer comes in, or the loud climax near the end.
2. **It is short: about 18 seconds** (median; the "warm" zone around it is about 25 s). That is one 4-line chorus.
3. **Where it sits:** English hits about 0:47 in (25% of the song); Pakistani and Hindi hits later, about 1:57
   (50%), because the replayed moment is often the *second voice* or the *final, bigger chorus*. Gym phonk: the drop,
   first drop at about 0:16.
4. **The first seconds always get the most eyeballs** (everyone sees 0:00; a quarter of streaming listeners skip in
   the first 5 seconds). So our Shorts should **open on the hook**, not lead up to it.
5. **Song Shorts come in two sizes.** "Status" clips of 14-60 s (median 28 s; Urdu 25 s, Hindi 29 s, English 35 s)
   and 1.5-3 min full-song uploads (median 2:23: "slowed + reverb", "lofi", "female version", "reply version" of a
   known hit). The short ones have the higher median views (3.6M against 2.0M).
6. **Titles that win are pipe-separated keyword chains** (74% use "|"), about 14 words, with emoji (32%), the
   mood word ("sad", "love", "status", "heart touching") and the format ("WhatsApp status", "slowed + reverb",
   "female version"). Song names themselves are short: 15 of the 20 South Asian hits have a 1 or 2 word title
   (Jhol, Pasoori, Pal Pal, Iraaday, Sajni, Barbaad...).
7. **"AI" in the title does not sell.** Only 5% of top song-Short titles mention AI, and those are covers of famous
   singers (we must not do that), parodies of real people (no), or "a joke song in an old style". We found no
   original AI love or sad song with big views.

---

## 1. Where the hot part sits (YouTube "Most replayed")

### How to read the graph

YouTube's "Most replayed" graph mixes two things: how many people are still watching (it always starts high at 0:00
and slopes down to the end) and how many people jumped back or replayed a stretch (a bump on top of the slope).
A raw "highest point" is therefore always 0:00 and is useless. We measured the **bumps above the slope**: the
biggest bump is the hot part; its width at half its height is the "hot stretch". (The brief asked for "seconds
above 70% of the peak": on the raw graph that gives 1 to 3 minutes for most songs because of the slope, so we used
the bump-height method instead and also give a wider "warm zone" = the stretch that keeps 70% of the bump.)

"What it is" comes from the shape of the graph (which bump of how many, evenly spaced bumps = repeating choruses)
plus the known structure of the song. Items marked *(likely)* are our best reading, not checked against audio.

### The 42 songs

| # | Song (artist) | Channel | Views | Length | Hot part peaks at | Hot stretch | What it is |
|---|---|---|---|---|---|---|---|
| | **English pop, 2024-2025** | | | | | | |
| 1 | Espresso (Sabrina Carpenter) | Sabrina Carpenter | 708M | 3:21 | 0:25 (12%) | 0:20-0:34, 14 s | 1st chorus; the final chorus (2:20) is almost as hot; 3 even bumps = 3 choruses |
| 2 | APT. (ROSE & Bruno Mars) | ROSE | 2,752M | 2:53 | 0:32 (19%) | 0:28-0:42, 14 s | 1st chorus, weak bump: the chant hook is already at 0:00, the whole song is replayed evenly |
| 3 | Die With A Smile (Lady Gaga, Bruno Mars) | Lady Gaga | 1,924M | 4:12 | 0:42 (17%) | 0:33-0:51, 18 s | 1st chorus |
| 4 | BIRDS OF A FEATHER (Billie Eilish) | Billie Eilish | 1,005M | 3:51 | 2:34 (66%) | 2:23-2:51, 28 s | last chorus section; the 1st chorus (about 1:10) is a flatter plateau |
| 5 | Beautiful Things (Benson Boone) | Benson Boone | 1,143M | 3:13 | 1:22 (42%) | 1:09-1:35, 25 s | the loud "explosion" after the quiet first half (only bump) |
| 6 | Good Luck, Babe! (Chappell Roan), lyric video | Chappell Roan | 164M | 3:38 | 0:38 (18%) | 0:31-0:48, 18 s | 1st chorus; the late high-note section (2:19) nearly as hot |
| 7 | Ordinary (Alex Warren) | Alex Warren | 494M | 3:07 | 0:51 (28%) | 0:45-0:56, 11 s | 1st chorus |
| 8 | Golden (HUNTR/X, KPop Demon Hunters), lyric video | Sony Pictures Animation | 1,832M | 3:19 | 2:12 (66%) | 2:01-2:19, 18 s | late climax / big final chorus *(likely)*; the 1st chorus (0:21) is a small bump |
| 9 | Lose Control (Teddy Swims), Village Sessions | Teddy Swims | 533M | 3:29 | none | - | no hot spot: smooth slope (a live version) |
| 10 | The Fate of Ophelia (Taylor Swift) | Taylor Swift | 573M | 3:58 | 1:15 (32%) | 1:07-1:21, 14 s | 1st chorus *(likely)*; bumps at 1:15, 2:15, 3:22 |
| | **English sad / romantic (viral)** | | | | | | |
| 11 | Until I Found You (Stephen Sanchez) | Stephen Sanchez | 659M | 2:56 | 0:38 (22%) | 0:30-0:46, 16 s | 1st chorus |
| 12 | Someone You Loved (Lewis Capaldi) | Lewis Capaldi | 1,399M | 3:05 | 0:42 (23%) | 0:35-0:48, 13 s | 1st chorus (weak bump, even replay) |
| 13 | Another Love (Tom Odell) | Tom Odell | 1,216M | 4:08 | 2:00 (48%) | 1:49-2:21, 32 s | the loud climax in the second half (the part used in viral edits) |
| 14 | lovely (Billie Eilish, Khalid) | Billie Eilish | 2,524M | 3:21 | 1:13 (37%) | 1:06-1:18, 12 s | chorus (2nd of 3 bumps) |
| 15 | Perfect (Ed Sheeran) | Ed Sheeran | 4,259M | 4:42 | 0:27 (10%) | 0:20-0:34, 14 s | the opening sung lines, before the 1st chorus *(likely)* |
| 16 | The Night We Met (Lord Huron), audio | Lord Huron | 513M | 3:28 | 1:31 (44%) | 1:22-1:40, 19 s | first full chorus after a long quiet build (only bump) |
| 17 | blue (yung kai) | yung kai | 324M | 3:41 | 0:43 (20%) | 0:29-0:56, 27 s | 1st chorus (only bump) |
| | **Pakistani (Coke Studio, pop, OST)** | | | | | | |
| 18 | Pasoori (Ali Sethi x Shae Gill) | Coke Studio Pakistan | 1,025M | 4:36 | 0:57 (21%) | 0:50-1:20, 30 s | 1st chorus (the Punjabi refrain) |
| 19 | Kana Yaari (Kaifi Khalil x Eva B x Abdul Wahab Bugti) | Coke Studio Pakistan | 127M | 3:59 | 2:08 (54%) | 2:00-2:22, 22 s | a guest singer's section mid-song *(likely)*; the end (3:13) also hot |
| 20 | Tu Jhoom (Naseebo Lal x Abida Parveen) | Coke Studio Pakistan | 144M | 6:40 | 3:23 (51%) | 3:08-3:41, 32 s | the middle, where the second voice takes over *(likely)* |
| 21 | Afreen Afreen (Rahat Fateh Ali Khan & Momina Mustehsan) | Coke Studio Pakistan | 700M | 6:45 | 2:48 (42%) | 2:34-3:18, 45 s | the second singer's solo *(likely)*; the biggest single bump among the ballads |
| 22 | Kahani Suno 2.0 (Kaifi Khalil) | Kaifi Khalil | 765M | 2:54 | 1:33 (54%) | 1:29-1:44, 16 s | the hook coming back after verse 2 |
| 23 | Jhol (Maanu x Annural Khalid) | Coke Studio Pakistan | 657M | 4:39 | 2:49 (60%) | 2:39-2:59, 20 s | later section (2nd of 3 bumps), second voice / hook return *(likely)* |
| 24 | Tu Hai Kahan (AUR) | AUR | 493M | 4:23 | 0:54 (21%) | 0:42-1:01, 18 s | 1st chorus (weak bump, even replay) |
| 25 | Wishes (Hasan Raheem ft. Talwiinder), lyric video | Hasan Raheem | 157M | 3:38 | 1:57 (54%) | 1:50-2:09, 20 s | the featured artist's section *(likely)*; sharpest spike of all non-phonk songs |
| 26 | Pal Pal (Afusic) | AFUSIC | 739M | 2:27 | 0:23 (16%) | 0:21-0:25, 4 s | the hook near the start; otherwise even replay |
| 27 | Meray Paas Tum Ho OST (Rahat Fateh Ali Khan) | ARY Digital HD | 223M | 5:01 | 2:33 (51%) | 2:25-2:37, 12 s | the refrain returning mid-song *(likely)* |
| 28 | Iraaday (Abdul Hannan & Rovalio) | Abdul Hannan | 137M | 2:13 | 0:41 (31%) | 0:35-0:48, 13 s | 1st chorus |
| 29 | Chal Diye Tum Kahan (Kabhi Main Kabhi Tum OST), lyrical | ARY Digital HD | 48M | 4:44 | 0:53 (19%) | 0:46-1:08, 23 s | 1st chorus; 2:52 also hot |
| | **Hindi / Bollywood, 2024-2025** | | | | | | |
| 30 | Saiyaara (title song) | YRF | 785M | 4:08 | 2:10 (52%) | 2:04-2:16, 12 s | a later chorus (3rd of 4 bumps) |
| 31 | Barbaad (Saiyaara) | YRF | 279M | 3:45 | 2:50 (76%) | 2:38-3:07, 29 s | final climax |
| 32 | Jo Tum Mere Ho (Anuv Jain) | Anuv Jain | 479M | 4:18 | 2:39 (62%) | 2:19-2:55, 36 s | late climax (only bump) |
| 33 | Sajni (Arijit Singh, Laapataa Ladies) | T-Series | 226M | 2:26 | 0:30 (20%) | 0:22-0:38, 16 s | 1st chorus / mukhda (only bump) |
| 34 | Raanjhan (Do Patti) | T-Series | 558M | 4:13 | 2:00 (48%) | 1:46-2:12, 25 s | 2nd chorus |
| 35 | Finding Her (Kushagra, Bharath) | UR DEBUT | 240M | 3:33 | 0:39 (18%) | 0:26-0:49, 23 s | 1st chorus; 2:09 also hot |
| 36 | Tauba Tauba (Karan Aujla, Bad Newz) | Saregama Music | 612M | 3:42 | 1:57 (52%) | 1:47-2:07, 20 s | 2nd chorus (the dance-step hook) |
| 37 | Aaj Ki Raat (Stree 2) | Saregama Music | 1,088M | 3:02 | 0:32 (18%) | 0:16-0:44, 27 s | 1st chorus |
| | **Gym phonk** | | | | | | |
| 38 | Murder In My Mind (Kordhell) | KORDHELL | 240M | 2:25 | 0:50 (34%) | 0:44-0:57, 13 s | the main (2nd) drop; 1st drop at 0:17 |
| 39 | Metamorphosis (INTERWORLD) | PHONK DOMAIN | 118M | 2:23 | 1:05 (46%) | 0:54-1:12, 17 s | a drop; the 0:31 drop is almost as hot |
| 40 | Sahara (Hensonn) | Hensonn | 118M | 2:51 | 0:35 (21%) | 0:28-0:43, 15 s | 1st drop |
| 41 | Close Eyes (DVRST), slowed + reverb | Chill Nation | 189M | 2:24 | 0:22 (16%) | 0:16-0:29, 13 s | 1st drop |
| 42 | Neon Blade (MoonDeity) | The Vibe Guide | 102M | 4:26 | 1:35 (36%) | 1:25-1:44, 19 s | the main (2nd) drop; 3:48 also hot |

(Searches picked "Tere Bin OST" and "Bikhra" but YouTube returned the Meray Paas Tum Ho OST and Iraaday; both are
big Pakistani hits, so we kept them.)

### What the numbers say

| Group | Songs | Hot part peaks at (median) | Middle half of songs | Hot stretch (median) | First replay bump starts (median) |
|---|---|---|---|---|---|
| English pop + sad/romantic | 16 | 0:47, 25% of the song | 19% to 44% | 17 s | 0:32 |
| Pakistani | 12 | 1:45, 46% | 21% to 54% | 20 s | 0:50 |
| Hindi | 8 | 1:58, 50% | 20% to 62% | 24 s | 0:26 |
| Gym phonk | 5 | 0:50, 34% | 21% to 36% | 15 s | 0:16 |
| **All** | **41** | **1:05, 34%** | **20% to 51%** | **18 s (warm zone 25 s)** | **0:31** |

What the hot part *is* (41 songs with a hot spot):

| Type | Count | Examples |
|---|---|---|
| First chorus / first hook / first drop | 19 | Espresso, Die With A Smile, Until I Found You, Pasoori, Sajni, Aaj Ki Raat, Sahara |
| A later chorus (2nd or 3rd time round) | 6 | lovely, Kahani Suno 2.0, Raanjhan, Tauba Tauba, Saiyaara, Meray Paas Tum Ho |
| A second / featured voice coming in | 5 | Afreen Afreen, Tu Jhoom, Kana Yaari, Wishes, Jhol (all *likely*) |
| Final chorus / loud climax near the end | 5 | Another Love, Golden, BIRDS OF A FEATHER, Barbaad, Jo Tum Mere Ho |
| First big chorus after a long quiet build | 2 | Beautiful Things, The Night We Met |
| A later, bigger drop (phonk) | 3 | Murder In My Mind, Metamorphosis, Neon Blade |
| Opening sung lines | 1 | Perfect |
| Instrumental intro | **0** | - |

Other things the graphs show:
- **How sharp the spike is depends on the genre.** Phonk drops stand out 3 to 6 times more than pop choruses do
  (bump height 0.30-0.68 against 0.04-0.18 for English pop): people skip straight to the drop. In pop, people
  mostly listen through, and the chorus is a gentle bump. Pakistani duets sit in between (0.14-0.49).
- **Songs where the "hook" is in the first seconds (APT., Pal Pal, Tu Hai Kahan, Lose Control) have flat graphs:**
  the whole song is the hook, nobody needs to skip to it. That is the ideal shape for a Short.
- **In 8 songs a second bump is nearly as hot as the first** (Espresso, APT., Good Luck Babe!, Someone You Loved,
  Kana Yaari, Chal Diye Tum Kahan, Finding Her, Metamorphosis): the same chorus, coming back, is replayed again.
- **South Asian songs save the hot part for later**, and in 5 of the 12 Pakistani songs (by our reading) the replay
  spike sits where a second singer (often a contrasting voice: female after male, a folk voice after a pop voice, a rapper)
  takes over. A "voice change" is itself a hook.

What this means for us: a Short should be **built around one 15 to 20 second hook**, start on it (or 1-2 s before
it), and the full song should **repeat that hook at least 3 times** with the **last time bigger** (higher note,
more instruments, or a second voice).

---

## 2. Song Shorts that win on YouTube search

YouTube's "sort by view count, under 4 minutes" search (the filter in the brief) returns mostly **full official
songs of 2 to 4 minutes**, not Shorts (only 21 of 714 results were 60 s or less). Adding "#shorts" to the query
surfaced the real Shorts (201 unique Shorts of up to 3 minutes). The type-filter for Shorts returned nothing through
yt-dlp. Kids' songs (ABC, potty training) took over "ai song", "party song" and "workout song", so we ignore those.

### Examples (titles with a lyric or poetry line in them are shown as a template, not copied)

| Views | Length | Title (or its pattern) | Type |
|---|---|---|---|
| 20.7M | 26 s | Very sad status for boys \|\| very heart touching status \|\| WhatsApp status 2019.. \| crying boy\|😭😭 | Hindi sad status |
| 14.7M | 29 s | 💔🥀Very Sad Song status 2024 😥 Broken Heart 💔 WhatsApp Status Video 😥 Breakup Song Hindi 💔😭 | Hindi sad status |
| 9.8M | 30 s | Bewafa Status💔\|Breakup Status😢\| Bewafa Song Status 😭\| Hurt Status \|💔 very sad Status 2022💔#sadstatus | sad status |
| 8.1M | 29 s | 💔New Sad 😭 Heart Touching WhatsApp Status 2019💔 Breakup Status😥 \|Unfaithful 😡\| True Love Special | sad status |
| 12.9M | 24 s | [song line] trending song status💞 love hindi song status💞 [devotional pair] whatsapp status💞#shorts | love status |
| 7.3M | 37 s | New Love Status Song😍Superhit Song🌹 Trending Status song🥰Love Fellings 💔WhatsApp status | love status |
| 5.6M | 30 s | Husband Wife Love 😍 Romantic Status 🔴 New WhatsApp Status Video 💖 Cute Love Story | love status |
| 9.3M | 33 s | "[short English line]".. Best Poetry Status 💔 Sad Status \|\| Alone Life, [poet] poetry in Hindi shayari | poetry status |
| 7.1M | 27 s | [Roman-Urdu line about loving someone] \| Sad Shero Shayari Status In Urdu \| Dukhiya Poetry Hindi | Urdu poetry status |
| 6.6M | 24 s | Alone sad poetry in Urdu \| Sad Urdu Poetry WhatsApp Status \| deep line Poetry | Urdu poetry status |
| 4.5M | 30 s | [Roman-Urdu line] 💔🥀 \|\| Sad Urdu Poetry Status \|\| Heart Touching Poetry Status | Urdu poetry status |
| 3.9M | 24 s | [Roman-Urdu line] 💔🥺 \| Urdu Poetry \| Viral Poetry ~ Black Screen Status | Urdu poetry status |
| 2.4M | 35 s | [Drama name] Ost Status \| Pakistani Drama Song Status \| Urdu Whatsapp \| [song phrase] | Pakistani OST status |
| 0.8M | 19 s | [LINE IN CAPITALS] 🥹♥️ \| black screen urdu lyrics \| slowed and reverb \| whatsapp status | Urdu lyric status |
| 0.35M | 17 s | Pakistani Sad Song 🥺💔 \| Urdu Lyrics Status Video \| Pakistani Ost Song Status | Pakistani song status |
| 18.9M | 2:54 | Kahani Suno 2.0 \|\| Reply Version \|\| Lyrics - [singer] | "reply" version of a hit |
| 4.7M | 2:14 | Majboor - Female Version \| [singer] \| Heart Touching Cover Song \| [channel] ❤️ | female version |
| 12.2M | 2:54 | Afusic - Pal Pal \| Lofi version \| Slowed Reverb \| New sad song | lofi / slowed version |
| 57.4M | 1:44 | FUNK SIGILO (SLOWED) | phonk |
| 2.3M | 1:11 | 🎧//YARA YARA FUNK (SLOWED + REVERB)// SIGMA GYM PHONK🥵🥶 | gym phonk |
| 1.9M | 1:47 | BAILA LENTO (ULTRA SLOWED + REVERB) 🔥 BASS BOOSTED [BRAZILIAN PHONK] 🇧🇷🎧 | gym phonk |
| 2.4M | 1:31 | KALIYUGA PHONK | desi-word phonk |
| 146M | 2:14 | I Turned My Voice Into a Full Band \| Pop Edition #2 | AI (Suno's own channel, a demo) |
| 13.2M | 3:43 | Pashto Songs 2026 [title] \| Pashto Music \| New Ai Songs \| Pashto Ai Songs 2026 | AI regional-language songs |
| 5.7M | 2:52 | [provocative phrase] (but it's 1982 soul) | AI "joke lyric in an old style" |
| 10.6M | 3:52 | [famous song] \| [famous singer] \| Ai Cover | AI cover of a real singer: **do not copy this** |

### Lengths

Non-kids song Shorts (149, up to 3 min) fall into two groups:

| Group | How many | Median length | Median views |
|---|---|---|---|
| Up to 60 s ("status" and poetry clips, hook only) | 47 | 28 s (Urdu 25 s, Hindi 29 s, English 35 s) | 3.6M |
| 61-90 s | 13 | - | - |
| Over 90 s (full song, slowed/lofi/cover versions) | 89 | 2:23 | 2.0M |

| Kind of Short (all results) | How many | Median length | Range |
|---|---|---|---|
| "status" clips (sad / love / song status) | 38 | 30 s | 14-69 s |
| Urdu/Hindi poetry ("shayari") clips | 15 | 24 s | 14-151 s |
| "slowed + reverb" uploads | 52 | 1:53 | 19 s-3:00 |
| "lofi" versions | 14 | 2:46 | 2:21-2:59 |
| gym phonk Shorts | 33 | 1:47 | middle half 1:24-2:11 |

### Title features (119 top non-kids song Shorts, top 10 per search)

Pipe "|" separator 74%, the word "song" 47%, emoji 32% (broken-heart or crying emoji 12%), "status" 26%, "sad"
23%, "new/trending/viral" 20%, "love/romantic/ishq/pyar/mohabbat" 19%, an ALL-CAPS word 18%, hashtags 15%,
"slowed/reverb/lofi" 15%, "lyrics" 12%, "poetry/shayari" 11%, a year 9%, "heart touching/emotional" 8%, a line in
quote marks 6%, "AI" 5%. Median 14 words. Urdu or Hindi script: 0% (Roman Urdu always). Question marks: 0%.

### What the titles are doing (the formulas)
1. **Mood + format stack:** "[mood] Song Status | [mood] Status | Heart Touching Status | WhatsApp Status [year]".
2. **The line itself first:** a short Roman-Urdu or English line (the most quotable line of the song or poem),
   then emoji, then "| Sad Urdu Poetry Status | Heart Touching ...".
3. **Known song + new version:** "[Song] | Female Version / Reply Version / Lofi version / Slowed + Reverb".
4. **Who it is for / about:** "for boys", "Husband Wife Love", "Best Friend", "Birthday Dua".
5. **Phonk:** ALL CAPS name + "(ULTRA SLOWED + REVERB)" + "BASS BOOSTED" + "[BRAZILIAN PHONK]" + 🔥/🇧🇷/🗿 +
   "SIGMA / GYM PHONK".
6. **Country/language tag for search:** "Pakistani Sad Song", "Urdu Lyrics Status", "Pakistani Ost Song Status".

---

## 3. Songwriting craft (what research and teachers say)

| Finding | Number / detail | Source |
|---|---|---|
| Hits start singing sooner | the average US top-10 hit started its vocals after about 23 s in 1986 and about 5 s in 2015 (Leveille Gauvin, Ohio State, Musicae Scientiae) | SCMP / AFP coverage [1] |
| First chorus timing today | about 40-45 s into a hit (Taylor Swift hits average 42 s; 2024 No.1s reportedly 45 s); intros about 12-14 s | Hit Songs Deconstructed [2][3] |
| Listeners skip fast | 24% of Spotify plays skipped in the first 5 s, 29% in 10 s, 35% in 30 s | Paul Lamere, "The Skip" [4] |
| Repetition sells | more repetitive lyrics are processed more easily and adopted faster; each extra chorus repeat raised the odds of a No.1 by about 14.5% in Billboard 1958-2012 | Nunes, Ordanini & Valsesia 2015, J. Consumer Psychology [5][6] |
| "You" sells | songs with more second-person words ("you", "your") ranked higher; strongest when "you" is the *object* of the action (something done *to/for* you), in lab tests too | Packard & Berger 2020, Psychological Science [7] |
| Lyrics are getting simpler and more emotional | 12,000 songs 1980-2020: fewer different words, more repetition, more negative and angry emotion words | Zangerle et al. 2024, Scientific Reports [8] |
| Title placement | most hits put the title at the start or end of the chorus, often both; the last chorus line is the "payoff" line | Taxi (John Braheny) / songwriting courses [9] |
| Chorus vs verse | choruses use shorter, repeated phrases and a simpler melody than verses; contrast tells the ear "this is the chorus" | Gary Ewer, Secrets of Songwriting [10] |
| Specific beats generic | "sense-bound" imagery (what you see, hear, touch) and showing a feeling through a concrete detail instead of naming it | Pat Pattison, Berklee, *Writing Better Lyrics* [11] |
| Shorts loops count | since 31 Mar 2025 every play *and replay* of a Short counts as a view; a Short that loops cleanly gets more views | TechCrunch [12]; vidIQ on looping [13] |
| Captions use lyrics | half of US adults have used song lyrics as a social-media caption, mostly pop, mostly on happy posts | Preply survey [14] |
| Mass-produced = risky | YouTube's July 2025 "inauthentic content" rule demonetises mass-produced / repetitive uploads; varied original songs matter | TechCrunch [15] |

Putting it together, a line is **"caption-worthy"** when it: stands alone without the song (no names, no "he said");
is 4 to 8 words; is in first or second person ("I", "you"); is present tense; holds one specific, relatable
situation or image (not a generic feeling word); and has a small twist or contrast in it. The Urdu "poetry status"
Shorts (14 to 45 s, millions of views) are exactly this: one strong line on a black screen.

**Loop endings:** end the Short on a line that leads back into the first line (the first line answers the last, or
the last line is the title, so the restart repeats it), keep tempo and key the same across the cut, and do not end
on a fade-out or a final chord with silence.

---

## 4. Urdu / Hindustani conventions for modern Pakistani pop and ballads

**Structure is already hook-first.** Hindustani film and pop songs use the *mukhda* (the refrain, which opens the song
and sets its subject and mood) and *antaras* (the verses); the mukhda comes back after every antara [16]. Starting
with the mukhda is the native form, not a trick.

**Titles are one evocative word or a short question.** 15 of our 20 South Asian hits have 1-2 word titles (Jhol,
Pasoori, Pal Pal, Iraaday, Wishes, Sajni, Barbaad, Raanjhan, Saiyaara...), and this year's most-viewed Pakistani
uploads in "urdu sad/romantic song" searches are the same (Aarzu, Alfaaz, Muntazir, Khasara, Zabt, Majboor). Repeated words are common (Pal Pal, Afreen
Afreen, Tauba Tauba). Two of the hot Pakistani songs are questions to an absent lover (Tu Hai Kahan, Chal Diye Tum
Kahan).

**What Pakistan streams:** Spotify Wrapped 2025 Pakistan: top song Jhol (Maanu & Annural Khalid), then Pal Pal
(Afusic) and Maand (Bayaan, Hasan Raheem, Rovalio); Talha Anjum top artist for the 2nd year (370M streams); Afusic
most-discovered; local streaming up 70% [17]. Gen-Z Pakistani hits mix Urdu with Punjabi or English hooks (Pasoori's
refrain is Punjabi, Wishes is titled in English). Drama OSTs are a genre of their own, released before the drama to
build hype, and newer OST voices are moving to softer, lo-fi, confessional, heartbreak-leaning sounds that spread on
reels [18][19]. Pasoori was the first Pakistani video past 1 billion YouTube views [20].

**Common vocabulary and imagery** (single words, safe to reuse; these are the building blocks, not lyrics):

| Theme | Words people love |
|---|---|
| Love (romantic) | dil, jaan, ishq, mohabbat, pyaar, sanam, humsafar, saath, nazar, aankhein, muskurahat, dhadkan, khwaab, dua |
| Longing / sad | yaad, intezaar, judai, dooriyan, faasle, tanhai, aansu, bewafa, wafa, khamoshi, adhoora, khasara, majboor |
| Nature / time | chaand, raat, sitaare, baarish / barsaat, hawa, shaam, subah, dhoop, saaya, mausam |
| Everyday modern details (fresh, under-used) | chai, chhat (rooftop), gali, khirki, purani tasveer, last seen, voice note, station, Eid ka chaand, mehndi |

**Romantic vs sad (how they differ):**
- *Romantic:* present tense, speaks to the lover directly, promises and wishes (always, together, a prayer for them),
  bright images (moon, rain as joy, eyes, a smile), soft "tum" address, major-key feel.
- *Sad:* past tense or "now that you are gone", memory and waiting, distance, an unanswered question ("where are
  you", "why"), images of the same places now empty, often "tu" address (more intimate and raw). Two sub-moods:
  *bewafa* (blame) and *dignified heartbreak* (no blame, self-respect). Modern hits lean to the second.

**Roman Urdu spelling seen in titles** (297 South Asian titles): mohabbat 7 vs muhabbat 3; ishq 24 (never "ishk");
dil 26; zindagi 13; pyaar 4 / pyar 3; judai 2; bewafa 4; barsaat 4; dua 4; sanam 3; jaan 3; hai 20 vs "hy" 1;
shayari 26 vs shayri 1; status 97; ost 40; lyrics 28 / lyrical 21. There is no standard spelling (researchers list
many variants of one word, e.g. zindagi) [21]; Pakistani uploaders sometimes write -y endings (hy, kary, chahy) but
the common, searchable forms are the ones above. Titles use Roman Urdu; Urdu script is rare (AUR adds it at the end).

**What Pakistani audiences search for** (title words): "urdu", "sad", "status", "poetry/shayari", "ost",
"pakistani", "heart touching", "lyrics", "female version", "slowed reverb", "new [year]", plus the song name.

**Avoid for a Pakistani audience:**
- Religious words or holy figures in a romantic, party or joking context, and comparing a lover to God; blasphemy
  cases carry extreme penalties (a 2014 TV wedding segment with a devotional song led to 26-year sentences) [22].
  Simple everyday words like "dua" are fine; worship words aimed at a lover are not.
- Sexual or "suggestive" lyrics and item-song style: Punjab banned 132 stage songs as "vulgar" in Jan 2026 [23];
  PEMRA has warned music channels over "vulgar" songs [24].
- Alcohol or drug glorification, India-Pakistan politics, army, Kashmir, sectarian or ethnic jokes.
- Hindu devotional pairings (common in Indian "love status" Shorts) in Urdu songs aimed at Pakistan.
- AI covers or clones of real singers, and parodies of real people (copyright, impersonation, and "inauthentic"
  content risk).

---

## 5. Rules for our song-writing prompt (testable)

Both languages:
1. Write the **hook (chorus / mukhda) first**; the song and every Short start on it. No instrumental intro over 2 s.
2. **Chorus = exactly 4 lines** (about 8 bars, 16-20 s at 90-120 BPM: the size of a replay hot stretch).
3. **Title = 1-3 words, taken from the hook,** and it appears in **chorus line 1 and line 4** (at least 2 times per
   chorus, at least 6 times per song).
4. Song plan for a 2-3 min track: chorus, verse 1 (4 lines), chorus, verse 2 (4 lines), **lift** (2-line bridge,
   new image or new voice), final chorus with **one changed last line**. Chorus appears 3+ times.
5. Chorus lines shorter than verse lines (see language rules below); chorus words simpler than verse words.
6. **"You" (tum/tu) in at least 3 of 4 chorus lines,** ideally as the one the action is for/about ("waiting for you").
7. **One concrete, sensory image per verse** (an object, a place, a time of day); at most one abstract emotion word
   per 4 lines; never use a banned cliche (keep a list: "broken pieces", "heart of gold", "fire inside",
   "lost in your eyes", "stars align", "shattered heart", "dil toota", "aansu behte", etc.).
8. Exactly **one caption line** per song: 4-8 words, stands alone, first/second person, present tense, a small
   twist; mark it so the video can show it on screen.
9. The **Short's last line must lead back into its first line** (title or answer to the opening) for a clean loop;
   no fade-out ending.
10. Short length target: **20-35 s** for romantic/sad/chill (status-clip range), up to 45 s if it holds two chorus
    passes; phonk/gym Shorts 30-60 s with the drop by 0:03 of the Short.
11. Workout / gym / phonk: **1-3 word chant hook repeated 4 times**, imperative verbs, 2-4 words per line, the drop
    by 0:15 of the full track, a bigger second drop around 0:45-1:00.
12. Party: call-and-response or a countable chant in the first 5 s; a dance-move or gesture word in the hook.
13. Sad songs: a **specific memory detail + present consequence** in every verse; at most one line of blame.
14. Give the final chorus a lift (higher, fuller, or a second voice): in our data the late, bigger chorus is
    replayed as much as or more than the first one.

English only:
15. Chorus lines 4-7 words (about 5-9 syllables); verse lines 7-10 words (about 8-12 syllables). Rhyme lines 2 and 4.
16. Conversational words a person would text; no archaic or "poetic" words (thee, thine, eternity of my soul).

Urdu only:
17. Start with the **mukhda**; repeat it after every antara. Mukhda lines 3-6 words, antara lines 5-8 words.
18. End mukhda lines on a **repeated end word** (*radif*) with a rhyme just before it (*qafiya*); this is the Urdu
    way to get repetition and is what sticks.
19. Keep **one form of address** per song: "tum" for tender romantic, "tu" for raw sad or intense. Never mix.
20. Everyday Urdu (about 90%) with at most **one poetic/Persian word per stanza** and at most **one English or
    Punjabi hook phrase** per song; write the lyrics and titles in common Roman Urdu spellings (Mohabbat, Ishq, Dil,
    Zindagi, Pyaar, Judai, Bewafa, Yaad, Dua, Barsaat, hai) and give the singer the Urdu-script version if the music
    model sings Urdu better from it.
21. Title: one evocative Urdu word (or a repeated word, or a 2-3 word question to the lover).
22. For a duet, give the **second voice its own entry moment** in the middle of the song (in our data that entry is
    often the most replayed part).

---

## 6. Title formulas for our Shorts (templates)

1. `[Hook line, Roman Urdu] 💔 | [Song Title] | Urdu Sad Song | [Our channel]`
2. `[Song Title] ([translation]) | Pakistani Romantic Song | Urdu Song Status`
3. `[Hook line in English] 🥀 | Sad Song Status | Heart Touching | [Song Title]`
4. `[Song Title] - Female Version | [Mood] Urdu Song` (and later `[Song Title] - Reply Version`, our own answer song)
5. `[Song Title] (Slowed + Reverb) | Lofi Urdu Song | Late Night Vibes`
6. `[TITLE IN CAPS] (ULTRA SLOWED) 🔥 | GYM PHONK | Workout Motivation`
7. `POV: [relatable situation] | [Song Title] | [mood] song`
8. `[Song Title] 🌙 | Chill Urdu Song for [time/place, e.g. Chai at Night]`
9. `[Who it is for: For Her / For Him / For My Best Friend] | [Song Title] | Romantic Song Status`

Keep the line in the title the same as the caption line in the video; put "AI" in the description and YouTube's
disclosure setting, not at the front of the title.

---

## 7. Limits, and what we could not get

- The "Most replayed" graph exists only for well-watched videos and is normalised (0 to 1); it shows *where* people
  replay, not *how many*. Music videos have non-music intros, so times are video times, not song times.
- Section labels without *(likely)* come from the graph's pattern plus well-known structure; we did not listen to
  audio or read lyrics, by design.
- The Shorts-only search filter returns nothing through yt-dlp, and the "under 4 minutes, sort by views" filter
  returns full music videos; adding "#shorts" fixed most of it, but the Shorts sample (201) is smaller than hoped and
  leans toward older viral "status" clips.
- Kids' songs dominate "ai song", "party song" and "workout song" searches; we found no original, AI-labelled love
  or sad song Short with big views, so there is no proven "AI love song" title formula to copy yet.
- YouTube did not refuse or rate-limit any of the about 140 requests.
- Craft sources: the Leveille Gauvin, Nunes and Packard papers were read through their abstracts and press coverage,
  not full text. Taxi and Sound On Sound blocked direct reading; their points come from search summaries.

---

## Sources

1. SCMP (AFP), streaming making pop songs run faster: https://www.scmp.com/culture/music/article/2085224/streaming-making-pop-songs-run-faster-peoples-attention-span-shrinks
2. Hit Songs Deconstructed, Taylor Swift structure report: https://hitsongsdeconstructed.com/wp-content/uploads/2024/04/The-Taylor-Swift-Evolution-Structure.pdf
3. Hit Songs Deconstructed, intro techniques / 2024 top-10 trend report: https://hitsongsdeconstructed.com/hsd_wire/timeless-multipart-intro-technique and https://www.hitsongsdeconstructed.com/hsd_wire/the-state-of-the-hot-100-top-10-2024-trend-report
4. Hypebot on Paul Lamere's "The Skip": https://www.hypebot.com/new-data-reveals-almost-25-of-people-skipping-song-within-5-seconds/
5. Nunes, Ordanini, Valsesia (2015), "The power of repetition": https://iris.unibocconi.it/handle/11565/3955321
6. Psychology Today, "Hit Me Baby One More Time": https://www.psychologytoday.com/us/articles/201507/hit-me-baby-one-more-time
7. Packard & Berger (2020), "Thinking of You", Psychological Science: https://journals.sagepub.com/doi/10.1177/0956797620902380 and https://mappingignorance.org/2020/03/16/you-are-the-success-of-this-song/
8. Phys.org on Zangerle et al. (2024), Scientific Reports: https://phys.org/news/2024-03-song-lyrics-simpler-repetitive.html
9. Taxi, chorus construction (John Braheny): https://www.taxi.com/music-business-faq/songwriting/songstructure/chorusconstruction
10. Gary Ewer, 8 ways of creating contrast between song sections: https://www.secretsofsongwriting.com/2013/06/17/8-ways-of-creating-contrast-between-song-sections/
11. Pat Pattison, Writing Better Lyrics (publisher page): https://www.penguinrandomhouse.com/books/631443/writing-better-lyrics-2nd-edition-by-pat-pattison/
12. TechCrunch, YouTube changes how Shorts views are counted: https://techcrunch.com/2025/03/26/youtube-is-changing-how-youtube-shorts-views-are-counted
13. vidIQ, looping Shorts: https://vidiq.com/blog/post/double-youtube-watch-time-looping-shorts/
14. Preply, songs on social media / lyric captions: https://preply.com/en/blog/lyrical-captions
15. TechCrunch, YouTube crackdown on mass-produced content: https://techcrunch.com/2025/07/09/youtube-prepares-crackdown-on-mass-produced-and-repetitive-videos-as-concern-over-ai-slop-grows
16. Songs of Yore, mukhda and antara: https://www.songsofyore.com/where-is-the-mukhada-gone-where-is-antara-gone/
17. ProPakistani / Express Tribune, Spotify Wrapped 2025 Pakistan: https://propakistani.pk/lens/afusic-breaks-through-as-spotify-pakistans-most-discovered-artist-of-2025/ and https://tribune.com.pk/story/2580514/pakistans-spotify-wrapped-2025-just-dropped-and-local-hip-hop-is-running-the-show
18. The Friday Times, Pakistani drama OSTs: https://www.thefridaytimes.com/04-Jan-2025/soundtrack-of-a-nation-tracing-the-journey-of-pakistani-drama-osts
19. Express Tribune, new voices in drama soundtracks (2026): https://tribune.com.pk/story/2625564/the-new-voices-reshaping-pakistans-drama-soundtracks
20. Arab News, Pasoori passes 1 billion views: https://www.arabnews.pk/pakistan/coke-studio-hit-pasoori-becomes-first-pakistan-made-music-video-to-cross-1-billion-youtube-views-3000503 and Deccan Herald: https://www.deccanherald.com/features/pasoori-everyone-loves-a-little-angst-1105045.html
21. Roman Urdu spelling variation (lexical normalisation paper): https://arxiv.org/pdf/2004.00088v1.pdf
22. Amnesty UK on the 2014 blasphemy sentences: https://www.amnesty.org.uk/press-releases/pakistan-26-year-blasphemy-sentences-contemptuous-wedding-programme-condemned and Dawn: https://www.dawn.com/news/1107292
23. DESIblitz, Punjab bans 132 songs (Jan 2026): https://www.desiblitz.com/content/punjab-government-bans-132-songs-in-pakistani-theatres
24. Journalism Pakistan, PEMRA warns music channel: https://www.journalismpakistan.com/pemra-warns-8xm-for-airing-vulgar-songs
25. Phonk structure (production guides): https://emastered.com/blog/what-is-drift-phonk and https://beatkey.pages.dev/how-to-make-phonk-music
