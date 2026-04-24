"""
gen-jinja  —  Renders markdown articles as HTML using Jinja2 templates.

Data flow:
  content_markdown (body + front_matter)  →  Jinja2 template  →  content_html

This service is project-agnostic:
  - It looks up which schemas list 'gen-jinja' in their renderers[]
  - It reads only from content_markdown (doesn't care about other MIME tables)
  - It writes back to content_html with rendered_from pointing at the source entity

Drop this container into any project that has the same content_markdown and
content_html tables and it will work.
"""
import os
import hashlib
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, BaseLoader, select_autoescape
import markdown as md_lib

DATABASE_URL  = os.environ["DATABASE_URL"]
RENDERER_NAME = os.environ.get("RENDERER_NAME", "gen-jinja")

app = FastAPI(title="gen-jinja", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True, lstrip_blocks=True,
)

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ lang|default('en') }}">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <meta name="generator" content="{{ renderer }}">
  <meta name="rendered-at" content="{{ rendered_at }}">
</head>
<body>
  <article>
    <header>
      <h1>{{ title }}</h1>
      {% if author %}<p class="byline">by {{ author }}</p>{% endif %}
      {% if tags %}<ul class="tags">{% for t in tags %}<li>{{ t }}</li>{% endfor %}</ul>{% endif %}
    </header>
    <section>{{ body_html|safe }}</section>
    <footer><small>Rendered by {{ renderer }} at {{ rendered_at }}</small></footer>
  </article>
</body>
</html>"""


def db():
    return psycopg.connect(DATABASE_URL)


@app.get("/health")
def health():
    return {"ok": True, "service": RENDERER_NAME}


@app.get("/capabilities")
def capabilities():
    """
    Which schemas this renderer advertises support for.
    Other services discover this by querying schemas.renderers.
    """
    with db() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id FROM schemas WHERE %s = ANY(renderers) ORDER BY id",
            (RENDERER_NAME,),
        )
        ids = [r[0] for r in cur.fetchall()]
    return {"renderer": RENDERER_NAME, "supports_schemas": ids}


@app.post("/render/{external_id}")
def render(external_id: str):
    """
    Look up a markdown entity, convert its body to HTML via Jinja2,
    and persist the rendered HTML into content_html.
    """
    with db() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT e.id, cm.body, cm.front_matter
              FROM entities e
              JOIN content_markdown cm ON cm.entity_id = e.id
             WHERE e.external_id = %s
            """,
            (external_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"no markdown content for '{external_id}'")
        entity_id, md_body, fm = row
        fm = fm or {}

        # Markdown -> HTML fragment
        body_html = md_lib.markdown(
            md_body, extensions=["fenced_code", "tables", "toc"]
        )

        # Optional custom template (lookup by external_id 'template-jinja-default')
        cur.execute(
            """
            SELECT body FROM content_html ch
              JOIN entities e ON e.id = ch.entity_id
             WHERE e.external_id = %s AND ch.is_template = TRUE
             ORDER BY ch.updated_at DESC LIMIT 1
            """,
            ("template-jinja-default",),
        )
        t_row = cur.fetchone()
        template_src = t_row[0] if t_row else DEFAULT_TEMPLATE

        tpl = env.from_string(template_src)
        rendered = tpl.render(
            title    = fm.get("title", external_id),
            author   = fm.get("author"),
            tags     = fm.get("tags", []),
            lang     = fm.get("lang", "en"),
            body_html= body_html,
            renderer = RENDERER_NAME,
            rendered_at = datetime.now(timezone.utc).isoformat(),
        )

        checksum = hashlib.sha256(rendered.encode("utf-8")).hexdigest()

        # Persist as a new content_html row linked back to the source entity
        cur.execute(
            """
            INSERT INTO content_html
              (entity_id, body, is_template, rendered_from, checksum, source)
            VALUES (%s, %s, FALSE, %s, %s, 'generator')
            RETURNING id
            """,
            (entity_id, rendered, entity_id, checksum),
        )
        html_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO audit_log
              (content_table, entity_id, content_id, source, action, after_state)
            VALUES ('content_html', %s, %s, 'generator', 'render',
                    jsonb_build_object('renderer', %s::text, 'bytes', %s::int))
            """,
            (entity_id, html_id, RENDERER_NAME, len(rendered)),
        )
        c.commit()

    return {
        "renderer": RENDERER_NAME,
        "entity_id": str(entity_id),
        "content_html_id": str(html_id),
        "bytes": len(rendered),
    }


@app.get("/preview/{external_id}", response_model=None)
def preview(external_id: str):
    """Render but don't persist — useful for quick dev checks."""
    with db() as c, c.cursor() as cur:
        cur.execute(
            """SELECT cm.body, cm.front_matter
                 FROM entities e JOIN content_markdown cm ON cm.entity_id = e.id
                WHERE e.external_id = %s""",
            (external_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        body, fm = row
    html = md_lib.markdown(body, extensions=["fenced_code", "tables"])
    tpl  = env.from_string(DEFAULT_TEMPLATE)
    return tpl.render(
        title=(fm or {}).get("title", external_id),
        body_html=html,
        renderer=RENDERER_NAME,
        rendered_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6001)
