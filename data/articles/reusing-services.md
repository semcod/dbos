---
title: Reusing services across projects
author: Architect
tags: [architecture, reuse, mime]
slug: reusing-services
published: true
---

# Reusing services across projects

The point of MIME-typed tables isn't performance — it's **portability**.

## The core move

Take `content_markdown` + `schemas` + `gen-jinja` to another Postgres database and everything works the same day. No code change, no config change, no migration.

## Why

Each service depends on:

1. A **schema** it understands (pulled from `schemas` row)
2. A **content table** it reads from (discovered through `mime_types`)
3. A **content table** it writes to (same mechanism)

That's the whole contract. Anything else is implementation detail the service can swap out.

## Example

The three renderers in this repo — `gen-jinja` (Python), `gen-twig` (PHP), `gen-handlebars` (Node) — all implement identical behaviour: read some content, render HTML, write to `content_html`. You pick which one runs by looking at `schemas.renderers[]`.

Replace any one of them with a new implementation next week? Drop in the new container, make sure it advertises in `/capabilities`, done.
