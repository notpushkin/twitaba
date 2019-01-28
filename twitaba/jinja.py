import jinja2
from sanic import response

from .util import get_banner
from .twitter import prepare_post


j2 = jinja2.Environment(
    loader=jinja2.PackageLoader(__name__, "templates"),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)

j2.globals.update({"len": len, "get_banner": get_banner})


def renderpost_filter(t, show_thread_link=False):
    return jinja2.Markup(
        j2.get_template("post.html").render(
            show_thread_link=show_thread_link, **t
        )
    )


j2.filters.update({"renderpost": renderpost_filter})


def render_template(name, **kwargs):
    return response.html(j2.get_template(name).render(**kwargs))
