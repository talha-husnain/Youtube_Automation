"""Credit lines for Creative Commons sources, in the copy only, never on screen.

YouTube's CC BY licence lets anyone reuse a video on one condition: credit the
creator (title, author, source link, licence; support.google.com/youtube/
answer/2797468). seo_copy keeps the creator's name out of every field (owner's
rule), so without this a Short cut from a CC video broke the one term that
made the reuse allowed. The owner agreed on 12-oct-2026 to credit in the
description, not in the video.

Only sources whose licence YouTube reports as Creative Commons get a line:
a standard-licence source is not reusable whatever the description says, and
naming its creator would only break the owner's rule. ``CREDIT_CC=0`` turns
it off.
"""
import os
import re

_TRAILING_TAGS = re.compile(r"(\n\n(?:#\S+\s*)+)$")


def _on():
    return os.environ.get("CREDIT_CC", "1").strip() != "0"


def sources(urls):
    """[{title, channel, url}] for the Creative Commons videos among these links."""
    import channel_tools
    import used_moments
    out, seen = [], set()
    for url in urls or []:
        vid = used_moments.video_id(url or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        try:
            info = channel_tools.licence(url)
        except Exception:  # noqa: BLE001 — a failed check never fails the job
            continue
        if info.get("licence") == "creative_commons":
            out.append({"title": (info.get("title") or "").strip(), "channel": (info.get("channel") or "").strip(),
                        "url": f"https://www.youtube.com/watch?v={vid}"})
    return out


def block(found):
    """The description's credit block, or "" when nothing needs one."""
    if not found:
        return ""
    lines = []
    for s in found:
        who = f" by {s['channel']}" if s["channel"] else ""
        what = f"\"{s['title']}\"" if s["title"] else "Original video"
        lines.append(f"{what}{who}: {s['url']}")
    head = "Credit (original video, licensed under CC BY):" if len(lines) == 1 else \
        "Credit (original videos, licensed under CC BY):"
    return head + "\n" + "\n".join(lines)


def short_line(found):
    """One line for captions with little room (TikTok)."""
    names = [s["channel"] or s["title"] for s in found if s["channel"] or s["title"]]
    return f"Credit: {', '.join(dict.fromkeys(names))} (CC BY)" if names else ""


def insert(text, credit):
    """Put the credit before a trailing hashtag line, or at the end."""
    if not credit or not text or credit in text:
        return text
    m = _TRAILING_TAGS.search(text)
    if m:
        return text[:m.start()] + "\n\n" + credit + m.group(1)
    return text.rstrip() + "\n\n" + credit


def apply(clips, urls):
    """Add the credit to every clip's copy in place. Returns the sources credited."""
    if not _on() or not clips:
        return []
    found = sources(urls)
    if not found:
        return []
    full, short = block(found), short_line(found)
    for c in clips:
        c["credit"] = full
        for field in ("seo_description", "video_description_for_instagram"):
            if c.get(field):
                c[field] = insert(c[field], full)
        if c.get("video_description_for_tiktok") and short:
            c["video_description_for_tiktok"] = insert(c["video_description_for_tiktok"], short)
    print(f"   Credit added for {len(found)} Creative Commons source(s) (description only).")
    return found
