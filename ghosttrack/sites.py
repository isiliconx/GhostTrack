"""Curated profile routes. A generated URL is never treated as a match.

API rules can confirm a handle; HTML markers offer weaker evidence. Other
platforms remain manual links, since login walls cannot prove existence.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    name: str
    url: str
    probe: str = ""
    detector: str = "manual"
    pattern: str = r"[A-Za-z0-9_.-]{1,64}"
    present: tuple = ()
    missing: tuple = ()


SITES = (
    Site(
        "GitHub",
        "https://github.com/{u}",
        "https://api.github.com/users/{u}",
        "github",
        r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}",
    ),
    Site("GitLab", "https://gitlab.com/{u}", "https://gitlab.com/api/v4/users?username={u}", "gitlab"),
    Site(
        "Reddit",
        "https://www.reddit.com/user/{u}/",
        "https://www.reddit.com/user/{u}/about.json",
        "reddit",
        r"[A-Za-z0-9_-]{3,20}",
    ),
    Site(
        "Telegram",
        "https://t.me/{u}",
        detector="html",
        pattern=r"[A-Za-z][A-Za-z0-9_]{4,31}",
        present=("tgme_page_title", "tgme_page_extra"),
        missing=("<title>Telegram Messenger</title>",),
    ),
    Site(
        "SoundCloud",
        "https://soundcloud.com/{u}",
        detector="html",
        present=('"hydratable":"user"',),
        missing=("We can’t find that user.",),
    ),
    Site("Instagram", "https://www.instagram.com/{u}/", pattern=r"[A-Za-z0-9_.]{1,30}"),
    Site("X", "https://x.com/{u}", pattern=r"[A-Za-z0-9_]{1,15}"),
    Site("TikTok", "https://www.tiktok.com/@{u}", pattern=r"[A-Za-z0-9_.]{2,24}"),
    Site("YouTube", "https://www.youtube.com/@{u}"),
    Site("LinkedIn", "https://www.linkedin.com/in/{u}/"),
    Site("Facebook", "https://www.facebook.com/{u}/"),
    Site("Pinterest", "https://www.pinterest.com/{u}/"),
    Site("Twitch", "https://www.twitch.tv/{u}", pattern=r"[A-Za-z0-9_]{4,25}"),
    Site("Medium", "https://medium.com/@{u}"),
    Site("Behance", "https://www.behance.net/{u}"),
    Site("Dribbble", "https://dribbble.com/{u}"),
    Site("Snapchat", "https://www.snapchat.com/add/{u}"),
    Site("Tumblr", "https://www.tumblr.com/{u}"),
    Site("DEV", "https://dev.to/{u}"),
    Site("HuggingFace", "https://huggingface.co/{u}"),
)


def select_sites(names=None):
    if not names:
        return SITES
    from .http import LookupFailure

    selected = {name.strip().casefold() for name in names}
    unknown = selected - {s.name.casefold() for s in SITES}
    if unknown:
        raise LookupFailure("Unknown sites: " + ", ".join(sorted(unknown)))
    return tuple(s for s in SITES if s.name.casefold() in selected)
