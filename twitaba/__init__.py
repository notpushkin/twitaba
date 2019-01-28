import json
import asyncio
import pkg_resources

from sanic import Sanic
from sanic import response
from requests_oauthlib import OAuth1Session

from .jinja import render_template
from .twitter import fetch_home_threads, fetch_thread


app = Sanic()
app.static("/static", pkg_resources.resource_filename(__name__, "static"))

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

    ts = OAuth1Session(TWITTER_CONSUMER_KEY, client_secret=TWITTER_CONSUMER_SECRET)
    fetch_response = ts.fetch_request_token(
        "https://api.twitter.com/oauth/request_token?oauth_callback=oob"
    )

    return render_template(
        "login.html",
        resource_owner_key=fetch_response.get("oauth_token"),
        resource_owner_secret=fetch_response.get("oauth_token_secret"),
        auth_url=ts.authorization_url("https://api.twitter.com/oauth/authorize"),
        flash=flash,
    )


@app.route("/")
async def index(req):
    if "oauth_token" not in req.cookies:
        return response.redirect("/login")

    session = OAuth1Session(
        TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=req.cookies["oauth_token"],
        resource_owner_secret=req.cookies["oauth_token_secret"],
    )

    threads = await fetch_home_threads(session)
    return render_template("index.html", threads=threads, type="home")


@app.route("/res/<thread_id:int>")
def thread(req, thread_id):
    if "oauth_token" not in req.cookies:
        return response.redirect("/login")

    session = OAuth1Session(
        TWITTER_CONSUMER_KEY,
        client_secret=TWITTER_CONSUMER_SECRET,
        resource_owner_key=req.cookies["oauth_token"],
        resource_owner_secret=req.cookies["oauth_token_secret"],
    )

    return render_template(
        "index.html", threads=[fetch_thread(session, thread_id)], type="thread"
    )
