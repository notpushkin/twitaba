import asyncio
import requests

from ttp import ttp


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Ubuntu Chromium/71.0.3578.98 Chrome/71.0.3578.98 Safari/537.36"
)


def get_guest_token():
    r = requests.get(
        "https://mobile.twitter.com/jack", headers={"user-agent": USER_AGENT}
    )
    try:
        return r.text.rsplit('("gt=', 1)[1].split(";")[0]
    except:
        print(r.text)


def get_home_thread_ids(session):
    r = session.get(
        "https://api.twitter.com/1.1/statuses/home_timeline.json",
        params={"count": 40, "trim_user": True, "include_entities": False},
    )
    r.raise_for_status()

    thread_ids = []

    for thread in r.json():
        if "retweeted_status" in thread:
            thread_id = thread["retweeted_status"]["id"]
        else:
            thread_id = thread["conversation_id"]

        if thread_id not in thread_ids:
            thread_ids.append(thread_id)

    return thread_ids


async def fetch_home_threads(session):
    thread_ids = get_home_thread_ids(session)

    guest_token = get_guest_token()

    def except_pass(f, *a, **kw):
        try:
            return f(*a, **kw)
        except Exception as e:
            print(repr(e), a, kw)
            pass

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(None, except_pass, fetch_thread, thread_id, guest_token)
        for thread_id in thread_ids
    ]

    return [x for x in await asyncio.gather(*futures) if x is not None]

def fetch_thread(thread_id, guest_token=None):
    r = requests.get(
        "https://api.twitter.com/2/timeline/conversation/%i.json" % thread_id,
        headers={
            "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "x-guest-token": guest_token or get_guest_token(),
        },
        params={
            "include_profile_interstitial_type": 1,
            "include_blocking": 1,
            "include_blocked_by": 1,
            "include_followed_by": 1,
            "include_want_retweets": 1,
            "include_mute_edge": 1,
            "include_can_dm": 1,
            "include_can_media_tag": 1,
            "skip_status": 1,
            "cards_platform": "Web-12",
            "include_cards": 1,
            "include_composer_source": "true",
            "include_ext_alt_text": "true",
            "include_reply_count": 1,
            "tweet_mode": "extended",
            "include_entities": "true",
            "include_user_entities": "true",
            "include_ext_media_color": "true",
            "include_ext_media_availability": "true",
            "send_error_codes": "true",
            "count": 200000,
            "ext": "mediaStats,highlightedLabel,cameraMoment",
        },
    )

    r.raise_for_status()
    global_objects = r.json()["globalObjects"]
    tweets = global_objects["tweets"].values()

    return [
        prepare_post(post, global_objects) for post in sorted(tweets, key=lambda tweet: tweet["id_str"])
    ]


def prepare_post(t, global_objects):
    if "full_text" not in t:
        print("tweet:", t)
        raise ValueError("Non-extended tweet was passed to filter")

    start, end = t["display_text_range"]
    text = t["full_text"][start:end]

    files = []
    if t["id_str"] == "1089875279839866880":
        print(t)
        print(global_objects["media"])
    if "extended_entities" in t:
        for medium in t["extended_entities"]["media"]:
            text = text.replace(" " + medium["url"], "")

            if medium["type"] == "photo":
                files.append(
                    {
                        "name": medium["media_url_https"].rsplit("/", 1)[-1],
                        "type": "photo",
                        "src": medium["media_url_https"],
                        "href": medium["media_url_https"] + ":orig",
                    }
                )
            elif medium["type"] in ["animated_gif", "video"]:
                # `video_info.variants` look like either:
                # - {"bitrate": N, "content_type": "video/mp4", "url": ...}
                # - {"content_type": "application/x-mpegURL", "url": ...}
                #
                # We're only interested in video/mp4 with highest bitrate, so:

                best = max(
                    medium["video_info"]["variants"], key=lambda v: v.get("bitrate", -1)
                )

                files.append(
                    {
                        "name": best["url"].rsplit("/", 1)[-1].rsplit("?", 1)[0],
                        "type": medium["type"],
                        "src": medium["media_url_https"],
                        "href": best["url"],
                    }
                )

    for link in t["entities"].get("urls", []):
        text = text.replace(link["url"], link["expanded_url"])

    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = "<br>".join(
        [
            f'<span class="unkfunc">{l}</span>' if l.startswith("&gt;") else l
            for l in text.split("\n")
        ]
    )
    text = TweetEntityParser().parse(text).html

    user = global_objects["users"][t["user_id_str"]]

    return {
        "id": t["id_str"],
        "short_id": shortid(t["id_str"]),
        "created_at": t["created_at"],
        "source": t["source"],
        "user_name": user["name"],
        "screen_name": user["screen_name"],
        "text": text,
        "files": files,
        "thread_op": t["conversation_id_str"],
        "reply_to": t.get("in_reply_to_status_id_str"),
        "short_reply_to": shortid(t.get("in_reply_to_status_id_str")),
    }


class TweetEntityParser(ttp.Parser):
    def format_tag(self, tag, text):
        """Return formatted HTML for a hashtag."""
        return '<a href="https://twitter.com/search?q=%s" target="_blank">%s%s</a>' % (
            ttp.quote(("#" + text).encode("utf-8")),
            tag,
            text,
        )

    def format_username(self, at_char, user):
        """Return formatted HTML for a username."""
        return '<a href="https://twitter.com/%s" target="_blank">%s%s</a>' % (
            user,
            at_char,
            user,
        )

    def format_list(self, at_char, user, list_name):
        """Return formatted HTML for a list."""
        return '<a href="https://twitter.com/%s/%s" target="_blank">%s%s/%s</a>' % (
            user,
            list_name,
            at_char,
            user,
            list_name,
        )

    def format_url(self, url, text):
        """Return formatted HTML for a url."""
        return '<a href="%s" target="_blank">%s</a>' % (
            ttp.escape(url),
            ttp.escape(url),
        )


def shortid(s):
    if s is None: return None
    s = str(s)
    return s[:3] + s[-5:]
