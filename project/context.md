# System Architecture Analysis

## Overview

- **Project**: /home/tom/github/semcod/dbos
- **Primary Language**: md
- **Languages**: md: 18, yaml: 15, json: 5, txt: 5, shell: 4
- **Analysis Mode**: static
- **Total Functions**: 175
- **Total Classes**: 6
- **Modules**: 70
- **Entry Points**: 162

## Architecture by Module

### api-gateway.src
- **Functions**: 52
- **File**: `index.js`

### sync-engine.src
- **Functions**: 28
- **File**: `index.js`

### vfs-webdav.app
- **Functions**: 25
- **Classes**: 4
- **File**: `app.py`

### vfs-fuse.fuse_fs
- **Functions**: 18
- **Classes**: 1
- **File**: `fuse_fs.py`

### SUMD
- **Functions**: 16
- **File**: `SUMD.md`

### project.map.toon
- **Functions**: 16
- **File**: `map.toon.yaml`

### command-bus.src
- **Functions**: 9
- **File**: `index.js`

### generators.gen-handlebars.src
- **Functions**: 8
- **File**: `index.js`

### workers.python.worker
- **Functions**: 6
- **Classes**: 1
- **File**: `worker.py`

### generators.gen-jinja.app
- **Functions**: 5
- **File**: `app.py`

### workers.php.worker
- **Functions**: 4
- **File**: `worker.php`

### vfs-webdav.project.map.toon
- **Functions**: 3
- **File**: `map.toon.yaml`

### vfs-webdav.SUMD
- **Functions**: 3
- **File**: `SUMD.md`

### generators.gen-twig.index
- **Functions**: 2
- **File**: `index.php`

### vfs-fuse.project.map.toon
- **Functions**: 2
- **File**: `map.toon.yaml`

### vfs-fuse.SUMD
- **Functions**: 2
- **File**: `SUMD.md`

### README
- **Functions**: 1
- **File**: `README.md`

## Key Entry Points

Main execution flows into the system:

### sync-engine.src.body
- **Calls**: sync-engine.src.test, sync-engine.src.toString, sync-engine.src.matter, sync-engine.src.split, sync-engine.src.filter, sync-engine.src.connect, sync-engine.src.query, sync-engine.src.exists

### generators.gen-jinja.app.render
> Look up a markdown entity, convert its body to HTML via Jinja2,
and persist the rendered HTML into content_html.
- **Calls**: app.post, generators.gen-jinja.app.db, c.cursor, cur.execute, cur.fetchone, md_lib.markdown, cur.execute, cur.fetchone

### workers.python.worker.handle_create_device
- **Calls**: None.hexdigest, payload.keys, HTTPException, payload.get, payload.get, payload.get, payload.get, payload.get

### vfs-fuse.fuse_fs.PlatformFS._persist
- **Calls**: self._split, self.layout, None.hexdigest, FuseOSError, vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.execute

### vfs-webdav.app.EntityFile._persist
- **Calls**: None.hexdigest, vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.execute, c.commit, hashlib.sha256, cur.fetchone

### workers.python.worker.handle_change_device_status
- **Calls**: payload.get, payload.get, HTTPException, workers.python.worker.db, c.cursor, cur.execute, cur.fetchone, data.get

### sync-engine.src.client
- **Calls**: sync-engine.src.query, sync-engine.src.exists, sync-engine.src.entities, sync-engine.src.VALUES, sync-engine.src.CONFLICT, sync-engine.src.stringify, sync-engine.src.toString, sync-engine.src.sha256

### api-gateway.src.client
- **Calls**: api-gateway.src.query, api-gateway.src.entities, api-gateway.src.VALUES, api-gateway.src.createHash, api-gateway.src.update, api-gateway.src.stringify, api-gateway.src.digest, api-gateway.src.content_json

### generators.gen-handlebars.src.client
- **Calls**: generators.gen-handlebars.src.query, generators.gen-handlebars.src.status, generators.gen-handlebars.src.json, generators.gen-handlebars.src.compile, generators.gen-handlebars.src.template, generators.gen-handlebars.src.Date, generators.gen-handlebars.src.toISOString, generators.gen-handlebars.src.createHash

### vfs-fuse.fuse_fs.PlatformFS.getattr
- **Calls**: time.time, dict, self._split, self.layout, FuseOSError, self._load_payload, os.getuid, os.getgid

### generators.gen-jinja.app.preview
> Render but don't persist — useful for quick dev checks.
- **Calls**: app.get, md_lib.markdown, env.from_string, tpl.render, generators.gen-jinja.app.db, c.cursor, cur.execute, cur.fetchone

### sync-engine.src.handleFile
- **Calls**: sync-engine.src.relative, sync-engine.src.split, sync-engine.src.warn, sync-engine.src.extname, sync-engine.src.toLowerCase, sync-engine.src.path, sync-engine.src.substring, sync-engine.src.readFile

### sync-engine.src.entityId
- **Calls**: sync-engine.src.query, sync-engine.src.content_json, sync-engine.src.VALUES, sync-engine.src.CONFLICT, sync-engine.src.content_yaml, sync-engine.src.content_xml, sync-engine.src.allowed, sync-engine.src.content_html

### sync-engine.src.checksumBase
- **Calls**: sync-engine.src.query, sync-engine.src.content_json, sync-engine.src.VALUES, sync-engine.src.CONFLICT, sync-engine.src.content_yaml, sync-engine.src.content_xml, sync-engine.src.allowed, sync-engine.src.content_html

### sync-engine.src.checksum
- **Calls**: sync-engine.src.query, sync-engine.src.content_json, sync-engine.src.VALUES, sync-engine.src.CONFLICT, sync-engine.src.content_yaml, sync-engine.src.content_xml, sync-engine.src.allowed, sync-engine.src.content_html

### vfs-fuse.fuse_fs.main
- **Calls**: range, os.makedirs, print, FUSE, PlatformFS, vfs-fuse.fuse_fs.db, c.cursor, cur.execute

### workers.php.worker.handle_render_page
- **Calls**: workers.php.worker.RuntimeException, workers.php.worker.sprintf, workers.php.worker.rawurlencode, workers.php.worker.curl_init, workers.php.worker.curl_setopt_array, workers.php.worker.json_encode, workers.php.worker.curl_exec, workers.php.worker.curl_getinfo

### vfs-fuse.fuse_fs.PlatformFS.write
- **Calls**: self._open.get, len, FuseOSError, len, buf.extend, len, len, len

### vfs-fuse.fuse_fs.PlatformFS.layout
- **Calls**: vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.fetchall, time.time, time.time, tpl.split, tpl.rsplit

### vfs-fuse.fuse_fs.PlatformFS._load_payload
- **Calls**: vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.fetchone, None.encode, None.encode, json.dumps, bytes

### vfs-webdav.app.EntityFile._load
- **Calls**: vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.fetchone, None.encode, None.encode, json.dumps, bytes

### api-gateway.src.checksum
- **Calls**: api-gateway.src.content_json, api-gateway.src.VALUES, api-gateway.src.content_yaml, api-gateway.src.content_xml, api-gateway.src.content_html, api-gateway.src.content_markdown, api-gateway.src.content_binary, api-gateway.src.from

### api-gateway.src.entityId
- **Calls**: api-gateway.src.content_json, api-gateway.src.VALUES, api-gateway.src.content_yaml, api-gateway.src.content_xml, api-gateway.src.content_html, api-gateway.src.content_markdown, api-gateway.src.content_binary, api-gateway.src.from

### vfs-fuse.fuse_fs.PlatformFS.readdir
- **Calls**: self._list_dir, None.split, FuseOSError, list, None.keys, path.strip, self.layout

### vfs-fuse.fuse_fs.PlatformFS.unlink
- **Calls**: self._split, self.layout, FuseOSError, vfs-fuse.fuse_fs.db, c.cursor, cur.execute, c.commit

### vfs-webdav.app.PlatformProvider.get_resource_inst
- **Calls**: RootCollection, root.get_member, folder.get_member, len, RootCollection, path.split, len

### workers.php.worker.handle_render_report
- **Calls**: workers.php.worker.db, workers.php.worker.prepare, workers.php.worker.execute, workers.php.worker.fetchColumn, workers.php.worker.RuntimeException, workers.php.worker.strlen

### api-gateway.src.auth
- **Calls**: api-gateway.src.startsWith, api-gateway.src.status, api-gateway.src.json, api-gateway.src.verify, api-gateway.src.slice, api-gateway.src.next

### vfs-fuse.fuse_fs.PlatformFS._list_dir
- **Calls**: self.layout, vfs-fuse.fuse_fs.db, c.cursor, cur.execute, cur.fetchall

### workers.python.worker.handle_render_article
- **Calls**: httpx.post, payload.get, payload.get, HTTPException, r.json

## Process Flows

Key execution flows identified:

### Flow 1: body
```
body [sync-engine.src]
```

### Flow 2: render
```
render [generators.gen-jinja.app]
  └─> db
```

### Flow 3: handle_create_device
```
handle_create_device [workers.python.worker]
```

### Flow 4: _persist
```
_persist [vfs-fuse.fuse_fs.PlatformFS]
  └─ →> db
```

### Flow 5: handle_change_device_status
```
handle_change_device_status [workers.python.worker]
  └─> db
```

### Flow 6: client
```
client [sync-engine.src]
```

### Flow 7: getattr
```
getattr [vfs-fuse.fuse_fs.PlatformFS]
```

### Flow 8: preview
```
preview [generators.gen-jinja.app]
  └─> db
```

### Flow 9: handleFile
```
handleFile [sync-engine.src]
```

### Flow 10: entityId
```
entityId [sync-engine.src]
```

## Key Classes

### vfs-fuse.fuse_fs.PlatformFS
> Virtual filesystem where:
  /                                  root
  /{folder}/                    
- **Methods**: 16
- **Key Methods**: vfs-fuse.fuse_fs.PlatformFS.__init__, vfs-fuse.fuse_fs.PlatformFS.layout, vfs-fuse.fuse_fs.PlatformFS._split, vfs-fuse.fuse_fs.PlatformFS._load_payload, vfs-fuse.fuse_fs.PlatformFS._list_dir, vfs-fuse.fuse_fs.PlatformFS.getattr, vfs-fuse.fuse_fs.PlatformFS.readdir, vfs-fuse.fuse_fs.PlatformFS.open, vfs-fuse.fuse_fs.PlatformFS.create, vfs-fuse.fuse_fs.PlatformFS.read
- **Inherits**: LoggingMixIn, Operations

### vfs-webdav.app.EntityFile
> One row in a content_* table, exposed as a single file.
- **Methods**: 14
- **Key Methods**: vfs-webdav.app.EntityFile.__init__, vfs-webdav.app.EntityFile._load, vfs-webdav.app.EntityFile.get_content_length, vfs-webdav.app.EntityFile.get_content_type, vfs-webdav.app.EntityFile.get_display_name, vfs-webdav.app.EntityFile.get_etag, vfs-webdav.app.EntityFile.support_etag, vfs-webdav.app.EntityFile.get_last_modified, vfs-webdav.app.EntityFile.support_ranges, vfs-webdav.app.EntityFile.get_content
- **Inherits**: DAVNonCollection

### vfs-webdav.app.EntityFolder
> A directory that lists all entities of one entity_type as files.
- **Methods**: 4
- **Key Methods**: vfs-webdav.app.EntityFolder.__init__, vfs-webdav.app.EntityFolder.get_member_names, vfs-webdav.app.EntityFolder.get_member, vfs-webdav.app.EntityFolder.support_recursive_delete
- **Inherits**: DAVCollection

### vfs-webdav.app.RootCollection
> Top-level collection: one subfolder per schema_paths row.
- **Methods**: 3
- **Key Methods**: vfs-webdav.app.RootCollection.__init__, vfs-webdav.app.RootCollection.get_member_names, vfs-webdav.app.RootCollection.get_member
- **Inherits**: DAVCollection

### vfs-webdav.app.PlatformProvider
> wsgidav hook — all paths resolve through here.
- **Methods**: 1
- **Key Methods**: vfs-webdav.app.PlatformProvider.get_resource_inst
- **Inherits**: DAVProvider

### workers.python.worker.ExecuteRequest
- **Methods**: 0
- **Inherits**: BaseModel

## Data Transformation Functions

Key functions that process and transform data:

### api-gateway.src.decodeExternalId
- **Output to**: api-gateway.src.decodeURIComponent

### api-gateway.src.validate
- **Output to**: api-gateway.src.get, api-gateway.src.compile, api-gateway.src.check

### api-gateway.src.decodedId

### sync-engine.src.parse
- **Output to**: sync-engine.src.toString, sync-engine.src.load, sync-engine.src.XMLParser, sync-engine.src.keys, sync-engine.src.find

### sync-engine.src.parser
- **Output to**: sync-engine.src.XMLParser

### sync-engine.src.parsed

## Public API Surface

Functions exposed as public API (no underscore prefix):

- `sync-engine.src.parse` - 47 calls
- `sync-engine.src.body` - 43 calls
- `generators.gen-jinja.app.render` - 28 calls
- `workers.python.worker.handle_create_device` - 27 calls
- `workers.python.worker.handle_change_device_status` - 21 calls
- `sync-engine.src.upsertEntity` - 21 calls
- `sync-engine.src.client` - 20 calls
- `api-gateway.src.client` - 18 calls
- `generators.gen-handlebars.src.client` - 15 calls
- `vfs-fuse.fuse_fs.PlatformFS.getattr` - 12 calls
- `generators.gen-jinja.app.preview` - 12 calls
- `sync-engine.src.handleFile` - 12 calls
- `sync-engine.src.entityId` - 11 calls
- `sync-engine.src.checksumBase` - 11 calls
- `sync-engine.src.checksum` - 11 calls
- `vfs-fuse.fuse_fs.main` - 10 calls
- `workers.php.worker.handle_render_page` - 10 calls
- `vfs-fuse.fuse_fs.PlatformFS.write` - 9 calls
- `vfs-fuse.fuse_fs.PlatformFS.layout` - 8 calls
- `api-gateway.src.checksum` - 8 calls
- `api-gateway.src.entityId` - 8 calls
- `vfs-fuse.fuse_fs.PlatformFS.readdir` - 7 calls
- `vfs-fuse.fuse_fs.PlatformFS.unlink` - 7 calls
- `vfs-webdav.app.PlatformProvider.get_resource_inst` - 7 calls
- `sync-engine.src.main` - 7 calls
- `vfs-webdav.app.load_directory_layout` - 6 calls
- `workers.php.worker.handle_render_report` - 6 calls
- `api-gateway.src.auth` - 6 calls
- `workers.python.worker.handle_render_article` - 5 calls
- `generators.gen-jinja.app.capabilities` - 5 calls
- `sync-engine.src.pathWithoutExt` - 5 calls
- `sync-engine.src.external_id` - 5 calls
- `command-bus.src.commandId` - 4 calls
- `command-bus.src.targetUrl` - 4 calls
- `vfs-fuse.fuse_fs.PlatformFS.open` - 4 calls
- `vfs-webdav.app.EntityFile.delete` - 4 calls
- `vfs-webdav.app.EntityFolder.get_member_names` - 4 calls
- `vfs-webdav.app.EntityFolder.get_member` - 4 calls
- `workers.python.worker.execute` - 4 calls
- `api-gateway.src.loadEntity` - 4 calls

## System Interactions

How components interact:

```mermaid
graph TD
    body --> test
    body --> toString
    body --> matter
    body --> split
    body --> filter
    render --> post
    render --> db
    render --> cursor
    render --> execute
    render --> fetchone
    handle_create_device --> hexdigest
    handle_create_device --> keys
    handle_create_device --> HTTPException
    handle_create_device --> get
    _persist --> _split
    _persist --> layout
    _persist --> hexdigest
    _persist --> FuseOSError
    _persist --> db
    _persist --> cursor
    _persist --> execute
    handle_change_device --> get
    handle_change_device --> HTTPException
    handle_change_device --> db
    handle_change_device --> cursor
    client --> query
    client --> exists
    client --> entities
    client --> VALUES
    client --> CONFLICT
```

## Reverse Engineering Guidelines

1. **Entry Points**: Start analysis from the entry points listed above
2. **Core Logic**: Focus on classes with many methods
3. **Data Flow**: Follow data transformation functions
4. **Process Flows**: Use the flow diagrams for execution paths
5. **API Surface**: Public API functions reveal the interface

## Context for LLM

Maintain the identified architectural patterns and public API surface when suggesting changes.