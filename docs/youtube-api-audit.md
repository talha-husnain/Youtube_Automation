# YouTube API audit: how to get uploads out of "private"

YouTube keeps every video uploaded through your own Google project private
until that project passes YouTube's API audit. Shortkaar's upload and
schedule buttons work before that, but the videos stay private. This guide
gets the audit done in one sitting.

What you need first:

- The Google project from the My channel setup steps, with its **project
  number** (Google Cloud console, project dashboard, "Project number").
- A small public website with https. A free Google Sites page is enough:
  one page that says what Shortkaar is, plus a Privacy Policy page and a
  Terms page (drafts below).
- Your legal name and address.
- 4 screenshots: the website home page showing the Privacy Policy link,
  the privacy policy page, Google's sign-in screen when you press Connect in
  My channel, and the upload panel under a Short in Shortkaar.

Form: https://support.google.com/youtube/contact/yt_api_form

## Answers to paste

| Field | Answer |
|---|---|
| Select the reason for your request | Compliance audit (first audit) |
| Are you applying | As an individual |
| Your Organization's Legal Name | self |
| Your Organization's Primary Website | your Google Sites address (https://...) |
| Category | Media |
| Organization Size / Type | Individual / sole creator |
| Who is your target audience? | Internal (only me) |
| How does your API Client monetize? | Free (it is not sold) |
| Google or YouTube Partner Manager | No |
| API Client Name | Shortkaar (must not contain the word "YouTube") |
| Primary Access URL | your Google Sites address |
| Privacy Policy URL | your Google Sites privacy page |
| Is your API Client publicly accessible? | No |
| Use Case Category | Internal Tools, Video Uploading, Analytics |
| Requires users to sign in with Google (OAuth 2.0)? | Yes |
| Expected API Usage Volume | Less than 1,000 requests per day |
| Endpoints | videos.insert, videos.list, channels.list, playlistItems.list, comments.insert, youtubeAnalytics reports.query |
| Total quota requested | Default (10,000 units per day) |

**Describe your organization's work as it relates to YouTube** (paste and
adjust):

> I run the YouTube channel Punchline Bazaar (@PunchlineBazaar), which posts
> short comedy clips with Roman Urdu titles and cricket facts. Shortkaar is
> a tool I built for my own channel only. It runs on my own computer, signs
> in to my own channel with OAuth, and uses the YouTube Data API to upload
> and schedule the Shorts I have made and reviewed, read my channel's videos
> and analytics to see which Shorts perform best, and reply to comments on my
> own videos. No other user can sign in, nothing is sold, and no YouTube
> data leaves my computer.

**Detailed justification for videos.insert** (if asked):

> Up to 10 Shorts a day on my own channel, uploaded as scheduled videos at
> my posting times. Every video is made and checked by me before upload.

## Draft privacy policy (for the website)

> **Shortkaar privacy policy**
>
> Shortkaar is a personal tool used only by its owner to manage the YouTube
> channel Punchline Bazaar. It uses YouTube API Services. By using it you
> agree to the YouTube Terms of Service (https://www.youtube.com/t/terms)
> and Google's Privacy Policy (https://policies.google.com/privacy).
>
> What it accesses: the owner's own YouTube channel details, videos,
> comments and analytics, through Google sign-in (OAuth), only to upload and
> schedule the owner's videos, show which videos perform best, and reply to
> comments on the owner's videos.
>
> Where data is kept: only on the owner's computer. The sign-in token is
> stored locally and never shared, sold or sent to anyone except Google.
> No data from other people is collected, except the public comments on the
> owner's own videos, which are read to draft replies and are not stored
> beyond the owner's computer.
>
> How to revoke access: Google account, Security, Third-party apps, remove
> Shortkaar, or press Disconnect in Shortkaar. Stored data is deleted with
> the local files.
>
> Contact: your email address.

## Draft terms (for the website)

> **Shortkaar terms**
>
> Shortkaar is a private tool used only by its owner. It is not offered,
> sold or licensed to anyone else. Use of YouTube features through it is
> subject to the YouTube Terms of Service (https://www.youtube.com/t/terms).

## After you submit

Google replies by email, often within a few weeks, sometimes with
questions. Until it is approved, keep posting from YouTube Studio or the
app with the copy from Ready to post. Once approved, the "schedule on
YouTube" button and Autopilot's auto upload publish for real.
