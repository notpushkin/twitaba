from os import environ as env
from . import app

app.run(
    host="0.0.0.0",
    port=int(env.get("PORT", 8000)),
    workers=int(env.get("WEB_CONCURRENCY", 1)),
    debug=bool(env.get("DEBUG", "")),
)
