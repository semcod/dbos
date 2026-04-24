---
title: Platform OS architecture in 60 seconds
author: Admin
tags: [intro, architecture]
slug: platform-os-architecture
published: true
---

# Platform OS — what this is

A **schema-driven runtime** for applications, not an application.

## The layers

**Data** — PostgreSQL, with one table per MIME type. `content_json`, `content_yaml`, `content_xml`, `content_html`, `content_markdown`, `content_binary`. Each is exportable on its own.

**Sync** — a filesystem watcher. Drop a `.md` file into `data/articles/`, it lands in `content_markdown`. Drop a `.yaml` file into `data/scenarios/`, it lands in `content_yaml` with the original text preserved.

**Contracts** — `schemas` and `mime_types` tables. Every service reads them at startup to know what to validate against and where payloads live.

**Execution** — a command bus that routes to workers by language (`worker-python`, `worker-php`). Which worker runs a command is decided by `schemas.target_runtime` — data-driven, not hard-coded.

**Rendering** — three website generators, one per language. `gen-jinja` (Python), `gen-twig` (PHP), `gen-handlebars` (Node). Each advertises in `schemas.renderers[]`. Swap one for another — no upstream change.

**Delivery** — nginx in front, caching previews and forwarding everything else.

## What makes it reusable

Services never hardcode "table X is where my data is." They ask `mime_types` at boot. Schemas travel as data. You can take any service + its schema into a new project, and it works.
