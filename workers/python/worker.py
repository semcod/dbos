"""
worker-python
=============
Executes commands routed from the command-bus.

Supported commands:
  * create_device      -> inserts into entities + content_json
  * change_device_status -> updates device status in content_json
  * render_article     -> calls gen-jinja HTTP API, returns result
"""
import os
import json
import hashlib
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATABASE_URL   = os.environ["DATABASE_URL"]
GEN_JINJA_URL  = os.environ.get("GEN_JINJA_URL", "http://gen-jinja:6001")

app = FastAPI(title="worker-python")


class ExecuteRequest(BaseModel):
    command_id: str | None = None
    command_name: str
    payload: dict[str, Any]


def db():
    return psycopg.connect(DATABASE_URL)


@app.get("/health")
def health():
    return {"ok": True, "service": "worker-python"}


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
def handle_create_device(payload: dict) -> dict:
    required = {"name", "device_type"}
    missing = required - payload.keys()
    if missing:
        raise HTTPException(400, f"missing fields: {sorted(missing)}")

    data = {
        "name":         payload["name"],
        "device_type":  payload["device_type"],
        "status":       payload.get("status", "inactive"),
        "customer_id":  payload.get("customer_id"),
        "serial_number":payload.get("serial_number"),
        "firmware":     payload.get("firmware"),
        "tags":         payload.get("tags", []),
    }
    external_id = payload.get("external_id") or f"device-{hashlib.md5(data['name'].encode()).hexdigest()[:8]}"
    checksum    = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    with db() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entities (external_id, entity_type, schema_id, primary_mime)
            VALUES (%s, 'device', 'device_v1', 'application/json')
            RETURNING id
            """,
            (external_id,),
        )
        entity_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO content_json (entity_id, data, checksum, source)
            VALUES (%s, %s::jsonb, %s, 'command')
            """,
            (entity_id, json.dumps(data), checksum),
        )

        cur.execute(
            """
            INSERT INTO events (event_name, aggregate_type, aggregate_id, payload, version)
            VALUES ('DeviceCreated', 'device', %s, %s::jsonb, 1)
            """,
            (entity_id, json.dumps({"entity_id": str(entity_id), "name": data["name"]})),
        )
        c.commit()

    return {
        "entity_id": str(entity_id),
        "external_id": external_id,
        "event": "DeviceCreated",
    }


def handle_change_device_status(payload: dict) -> dict:
    device_id  = payload.get("device_id")
    new_status = payload.get("new_status")
    if not device_id or not new_status:
        raise HTTPException(400, "device_id and new_status are required")

    with db() as c, c.cursor() as cur:
        # Lookup by UUID or external_id
        cur.execute(
            """
            SELECT e.id, cj.data, cj.version
              FROM entities e
              JOIN content_json cj ON cj.entity_id = e.id
             WHERE e.id::text = %s OR e.external_id = %s
             LIMIT 1
            """,
            (device_id, device_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"device {device_id} not found")
        entity_id, data, version = row

        old_status = data.get("status")
        data["status"] = new_status
        checksum = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

        cur.execute(
            "UPDATE content_json SET data=%s::jsonb, checksum=%s, source='command' WHERE entity_id=%s",
            (json.dumps(data), checksum, entity_id),
        )

        cur.execute(
            """
            INSERT INTO events (event_name, aggregate_type, aggregate_id, payload, version)
            VALUES ('DeviceStatusChanged', 'device', %s, %s::jsonb, %s)
            """,
            (entity_id,
             json.dumps({"device_id": str(entity_id),
                         "from_status": old_status,
                         "to_status": new_status,
                         "reason": payload.get("reason")}),
             version + 1),
        )
        c.commit()
    return {"entity_id": str(entity_id),
            "from_status": old_status, "to_status": new_status}


def handle_render_article(payload: dict) -> dict:
    external_id = payload.get("external_id") or payload.get("article_id")
    if not external_id:
        raise HTTPException(400, "external_id required")
    r = httpx.post(f"{GEN_JINJA_URL}/render/{external_id}", timeout=10)
    return {"status_code": r.status_code, "result": r.json()}


HANDLERS = {
    "create_device":         handle_create_device,
    "change_device_status":  handle_change_device_status,
    "render_article":        handle_render_article,
}


@app.post("/execute")
def execute(req: ExecuteRequest):
    handler = HANDLERS.get(req.command_name)
    if not handler:
        raise HTTPException(400, f"unknown command: {req.command_name}")
    return handler(req.payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
