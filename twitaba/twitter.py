import asyncio

from ttp import ttp


async def fetch_home_threads(session):
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

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(None, fetch_thread, session, thread_id)
        for thread_id in thread_ids
    ]

    return await asyncio.gather(*futures)


def fetch_thread(session, thread_id):
    r = session.get(
        "https://api.twitter.com/1.1/conversation/show/%i.json?tweet_mode=extended"
        % thread_id
    )

    return [prepare_post(post) for post in r.json()]


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
    s = str(s)
    return s[:3] + s[-5:]


def prepare_post(t):
    if "full_text" not in t:
        raise ValueError("Non-extended tweet was passed to filter")

    start, end = t["display_text_range"]
    text = t["full_text"][start:end]

    files = []
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

    return {
        "id": t["id_str"],
        "short_id": shortid(t["id_str"]),
        "created_at": t["created_at"],
        "source": t["source"],
        "user_name": t["user"]["name"],
        "screen_name": t["user"]["screen_name"],
        "text": text,
        "files": files,
        "thread_op": t["conversation_id_str"],
        "reply_to": t["in_reply_to_status_id_str"],
        "short_reply_to": shortid(t["in_reply_to_status_id_str"]),
    }
