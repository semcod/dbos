# =============================================================================
# Platform OS — Makefile
# =============================================================================
# Common operations on the whole stack + runnable examples showing different
# combinations of protocols / connectors / storage backends.
#
#   make help         — list everything
#   make up           — core stack
#   make up-all       — core + protocols + connectors + mirrors
#   make examples     — run every example and print PASS/FAIL
#   make example-01   — a specific example
# =============================================================================

SHELL          := /bin/bash
COMPOSE        := docker compose
PROFILES_ALL   := --profile protocols --profile connectors --profile mirrors
API_URL        ?= http://localhost:3000
UI_URL         ?= http://localhost:5173
ADMIN_EMAIL    ?= admin@platform.local
ADMIN_PASSWORD ?= demo1234

# Colours
C_OK    := \033[32m
C_FAIL  := \033[31m
C_HEAD  := \033[36m
C_OFF   := \033[0m
empty :=
space := $(empty) $(empty)

# Discover all example dirs (directories only — skip _lib.sh etc.)
EXAMPLES := $(sort $(notdir $(patsubst %/,%,$(wildcard examples/*/))))
example_short = $(subst $(space),-,$(wordlist 2,99,$(subst -, ,$(1))))

.DEFAULT_GOAL := help

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
.PHONY: help
help:
	@echo -e "$(C_HEAD)Platform OS$(C_OFF) — available targets"
	@echo
	@echo "  Core stack"
	@echo "    make up              Start core services (postgres, api, bus, ui, sync, generators, webdav)"
	@echo "    make up-all          Start core + protocols + connectors + mirrors"
	@echo "    make db-upgrade-protocols Apply new registry/mail SQL to an existing Postgres volume"
	@echo "    make down            Stop everything"
	@echo "    make logs SVC=<name> Follow logs for one service"
	@echo "    make build           Build all images (includes profiles)"
	@echo "    make rebuild         Down + rebuild + up-all"
	@echo "    make clean           Stop + remove volumes (DESTRUCTIVE)"
	@echo "    make ps              Status"
	@echo
	@echo "  Testing"
	@echo "    make test-protocols  Smoke-test FTP/IMAP/POP3/SMTP"
	@echo "    make test-gui        Existing GUI smoke test"
	@echo "    make token           Print a fresh admin token"
	@echo
	@echo "  Examples (examples/*/run.sh)"
	@for d in $(EXAMPLES); do \
	   desc=$$(head -n 1 examples/$$d/README.md 2>/dev/null | sed 's/^# *//'); \
	   printf "    make example-%-30s %s\n" "$$d" "$$desc"; \
	   printf "    make example-%-30s %s\n" "$${d#??-}" "(short alias)"; \
	 done
	@echo "    make examples        Run every example in sequence"
	@echo

# -----------------------------------------------------------------------------
# Stack lifecycle
# -----------------------------------------------------------------------------
.PHONY: up up-all db-upgrade-protocols down ps logs build rebuild clean
up:
	$(COMPOSE) up -d
	bash scripts/db-upgrade-protocols.sh

up-all:
	$(COMPOSE) $(PROFILES_ALL) up -d
	bash scripts/db-upgrade-protocols.sh

db-upgrade-protocols:
	bash scripts/db-upgrade-protocols.sh

down:
	$(COMPOSE) $(PROFILES_ALL) down

ps:
	$(COMPOSE) $(PROFILES_ALL) ps

logs:
	@if [ -z "$(SVC)" ]; then echo "usage: make logs SVC=<service>"; exit 2; fi
	$(COMPOSE) logs -f $(SVC)

build:
	$(COMPOSE) $(PROFILES_ALL) build

rebuild: down build up-all

clean:
	$(COMPOSE) $(PROFILES_ALL) down -v
	@rm -rf postgres-data vfs-mount mirror-data

# -----------------------------------------------------------------------------
# Token helper — most examples need an admin JWT. Cached under .cache/.
# -----------------------------------------------------------------------------
.cache:
	@mkdir -p .cache

.PHONY: token
token: .cache
	@TOKEN=$$(curl -s -X POST "$(API_URL)/auth/login" \
	    -H 'content-type: application/json' \
	    -d '{"email":"$(ADMIN_EMAIL)","password":"$(ADMIN_PASSWORD)"}' \
	  | python3 -c 'import sys, json; print(json.load(sys.stdin).get("token",""))'); \
	 if [ -z "$$TOKEN" ]; then echo "FAIL: could not obtain token (is the API running?)"; exit 1; fi; \
	 echo "$$TOKEN" > .cache/admin.token; \
	 echo "$$TOKEN"

# -----------------------------------------------------------------------------
# Smoke tests
# -----------------------------------------------------------------------------
.PHONY: test-protocols test-gui
test-protocols:
	@bash scripts/test-protocols.sh

test-gui:
	@bash test-gui.sh

# -----------------------------------------------------------------------------
# Examples — each directory is self-contained with a run.sh returning 0/1.
# -----------------------------------------------------------------------------
.PHONY: examples
examples:
	@fail=0; \
	 for d in $(EXAMPLES); do \
	   echo -e "\n$(C_HEAD)━━ example: $$d ━━$(C_OFF)"; \
	   if bash examples/$$d/run.sh; then \
	     echo -e "$(C_OK)PASS$(C_OFF) $$d"; \
	   else \
	     echo -e "$(C_FAIL)FAIL$(C_OFF) $$d"; \
	     fail=1; \
	   fi; \
	 done; \
	 exit $$fail

# Provide both exact and short targets, e.g.:
#   make example-01-write-http-read-protocols
#   make example-write-http-read-protocols
define MAKE_EXAMPLE_RULE
.PHONY: example-$(1) example-$(call example_short,$(1))
example-$(1):
	@bash examples/$(1)/run.sh
example-$(call example_short,$(1)):
	@bash examples/$(1)/run.sh
endef

$(foreach e,$(EXAMPLES),$(eval $(call MAKE_EXAMPLE_RULE,$(e))))
