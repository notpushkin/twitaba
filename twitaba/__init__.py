import json
import asyncio
import random
import pkg_resources

from sanic import Sanic
from sanic import response
import jinja2
from requests_oauthlib import OAuth1Session
from ttp import ttp


app = Sanic()
app.static('/static', pkg_resources.resource_filename(__name__, "static"))


j2 = jinja2.Environment(
    loader=jinja2.PackageLoader(__name__, "templates"),
    autoescape=jinja2.select_autoescape(["html", "xml"])
)

# key/secret are from the official apps
# needed to use the /1.1/conversation/show unofficial API
# (displays threads more fully)
#
# Twitter for Android:
# TWITTER_CONSUMER_KEY = "3nVuSoBZnx6U4vzUxf5w"
# TWITTER_CONSUMER_SECRET = "Bcs59EFbbsdF6Sl9Ng71smgStWEGwXXKSjYvPVt7qys"
# Twitter for iPhone:
TWITTER_CONSUMER_KEY = "IQKbtAYlXLripLGPWd0HUA"
TWITTER_CONSUMER_SECRET = "GgDYlkSvaPxGxC4X8liwpUoqKwwr3lCADbz8A7ADU"


def get_banner():
    return random.choice([
        "https://u.ale.sh/twi-bnr.png",
        "https://u.ale.sh/twi-bn2.png",
        "https://u.ale.sh/twi-bn3.png",
        "https://u.ale.sh/twi-bn4.png",
    ])


def shortid(s):
    s = str(s)
    return s[:3] + s[-5:]


j2.globals.update({
    "len": len,
    "get_banner": get_banner,
})


class EntityParser(ttp.Parser):
    def format_tag(self, tag, text):
        """Return formatted HTML for a hashtag."""
        return '<a href="https://twitter.com/search?q=%s" target="_blank">%s%s</a>' \
            % (ttp.quote(('#' + text).encode('utf-8')), tag, text)

    def format_username(self, at_char, user):
        """Return formatted HTML for a username."""
        return '<a href="https://twitter.com/%s" target="_blank">%s%s</a>' \
               % (user, at_char, user)

    def format_list(self, at_char, user, list_name):
        """Return formatted HTML for a list."""
        return '<a href="https://twitter.com/%s/%s" target="_blank">%s%s/%s</a>' \
               % (user, list_name, at_char, user, list_name)

    def format_url(self, url, text):
        """Return formatted HTML for a url."""
        return '<a href="%s" target="_blank">%s</a>' \
               % (ttp.escape(url), ttp.escape(url))


def renderpost_filter(t, show_thread_link=False):
    if "full_text" not in t:
        raise ValueError("Non-extended tweet was passed to filter")

    start, end = t["display_text_range"]
    text = t["full_text"][start:end]
    
    files = []
    if "extended_entities" in t:
        for medium in t["extended_entities"]["media"]:
            text = text.replace(" " + medium["url"], "")
            
            if medium["type"] == "photo":
                files.append({
                    "name": medium["media_url_https"].rsplit("/", 1)[-1],
                    "type": "photo",
                    "src": medium["media_url_https"],
                    "href": medium["media_url_https"] + ":orig",
                })
            elif medium["type"] in ["animated_gif", "video"]:
                # `video_info.variants` look like either:
                # - {"bitrate": N, "content_type": "video/mp4", "url": ...}
                # - {"content_type": "application/x-mpegURL", "url": ...}
                #
                # We're only interested in video/mp4 with highest bitrate, so:

                best = max(
                    medium["video_info"]["variants"],
                    key=lambda v: v.get("bitrate", -1)
                )

                files.append({
                    "name": best["url"].rsplit("/", 1)[-1].rsplit("?", 1)[0],
                    "type": medium["type"],
                    "src": medium["media_url_https"],
                    "href": best["url"],
                })
    
    for link in t["entities"].get("urls", []):
        text = text.replace(link["url"], link["expanded_url"])
    
    # ensure html escaped
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = "<br>".join([
        f'<span class="unkfunc">{l}</span>'
        if l.startswith("&gt;")
        else l
        for l in text.split("\n")
    ])
    text = EntityParser().parse(text).html
    text = jinja2.Markup(text)
            
    return jinja2.Markup(j2.get_template("post.html").render(
        # post=t,
        id=t["id_str"],
        short_id=shortid(t["id_str"]),
        created_at=t["created_at"],
        source=t["source"],
        user_name=t["user"]["name"],
        screen_name=t["user"]["screen_name"],
        text=text,
        files=files,
        show_thread_link=show_thread_link,
        thread_op=t["conversation_id_str"],
        reply_to=t["in_reply_to_status_id_str"],
        short_reply_to=shortid(t["in_reply_to_status_id_str"]),
    ))


j2.filters.update({
    "renderpost": renderpost_filter,
})


def render_template(name, **kwargs):
    return response.html(j2.get_template(name).render(**kwargs))


@app.route("/login", methods=["GET", "POST"])
def login(req):
    flash = None

    if req.method == "POST":
        oauth = OAuth1Session(
            TWITTER_CONSUMER_KEY,
            client_secret=TWITTER_CONSUMER_SECRET,
            resource_owner_key=req.form["resource_owner_key"][0],
            resource_owner_secret=req.form["resource_owner_secret"][0],
            verifier=req.form["verifier"][0],
        )

        try:
            tokens = oauth.fetch_access_token(
                "https://api.twitter.com/oauth/access_token"
            )
        except Exception as e:
            flash = str(e)
        else:
            res = response.redirect("/")
            res.cookies["oauth_token"] = tokens["oauth_token"]
            res.cookies["oauth_token_secret"] = tokens["oauth_token_secret"]
            return res

    ts = OAuth1Session(
        TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
    )
    fetch_response = ts.fetch_request_token(
        "https://api.twitter.com/oauth/request_token?oauth_callback=oob"
    )

    return render_template(
        "login.html",
        resource_owner_key=fetch_response.get('oauth_token'),
        resource_owner_secret=fetch_response.get('oauth_token_secret'),
        auth_url=ts.authorization_url("https://api.twitter.com/oauth/authorize"),
        flash=flash,
    )


@app.route("/")
async def index(req):
    if "oauth_token" not in req.cookies:
        return response.redirect("/login")

    ts = OAuth1Session(
        TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=req.cookies["oauth_token"],
        resource_owner_secret=req.cookies["oauth_token_secret"]
    )

    r = ts.get("https://api.twitter.com/1.1/statuses/home_timeline.json", params={
        "count": 40,
        "trim_user": True,
        "include_entities": False
    })
    r.raise_for_status()

    thread_ids = []

    for thread in r.json():
        if "retweeted_status" in thread:
            thread_id = thread["retweeted_status"]["id"]
        else:
            thread_id = thread["conversation_id"]

        if thread_id not in thread_ids:
            thread_ids.append(thread_id)

    async def _fetch_threads():
        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(
                None,
                ts.get,
                "https://api.twitter.com/1.1/conversation/show/%i.json?tweet_mode=extended"
                    % thread_id
            )
            for thread_id in thread_ids
        ]

        threads = [
            t
            for t in (r.json() for r in await asyncio.gather(*futures)
                      if r.status_code == 200)
            if len(t) > 0
        ]

        return threads

    threads = await _fetch_threads()
    
    # return response.json(threads)

    return render_template(
        "index.html",
        threads=threads,
        raw_resp=json.dumps({
            "feed": r.json(),
            "parsed_threads": threads,
        }, ensure_ascii=0, indent=2),
        type="home"
    )


@app.route("/res/<thread_id:int>")
def thread(req, thread_id):
    if "oauth_token" not in req.cookies:
        return response.redirect("/login")
    
    ts = OAuth1Session(
        TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=req.cookies["oauth_token"],
        resource_owner_secret=req.cookies["oauth_token_secret"]
    )

    r = ts.get("https://api.twitter.com/1.1/conversation/show/%i.json?tweet_mode=extended" %
               thread_id)
    r.raise_for_status()

    return render_template("index.html", threads=[r.json()], type="thread", raw_resp=json.dumps(r.json(), ensure_ascii=0, indent=2))
