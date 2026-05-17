UV      := uv
CAPTURES := analysis/usb_captures

.DEFAULT_GOAL := build

.PHONY: sync install test analyze analyze-raw analyze-no-poll analyze-human \
        analyze-summary analyze-all diff-config check-all \
        capture-enable capture-disable build version publish help \
        docs docs-serve docs-clean

help:
	@echo "Usage: make [target] [VAR=value]"
	@echo ""
	@echo "Build"
	@echo "  build                   Build sdist and wheel (default)"
	@echo "  version VERSION=X.Y.Z   Bump version, generate changelog, tag"
	@echo "  publish [VERSION=X.Y.Z] Create GitHub Release + deploy docs (prompts if VERSION omitted)"
	@echo ""
	@echo "Development"
	@echo "  sync                    Install all dependencies (incl. dev extras)"
	@echo "  install                 Alias for sync"
	@echo "  test                    Run test suite with pytest"
	@echo ""
	@echo "Analysis  (FILE=path/to/capture)"
	@echo "  analyze                 Decode capture (claude format)"
	@echo "  analyze-raw             Raw hex dump of capture"
	@echo "  analyze-no-poll         Decode, excluding 0x40 poll/level noise"
	@echo "  analyze-human           Decode with human-readable table output"
	@echo "  analyze-summary         Summary only (no per-frame detail)"
	@echo "  analyze-all             Summarise all captures in $(CAPTURES)"
	@echo "  diff-config             Compare config reads within a capture"
	@echo "  check-all               Run protocol assertions against all captures"
	@echo ""
	@echo "USB Capture"
	@echo "  capture-enable          Load usbmon and grant non-root capture access"
	@echo "  capture-disable         Revoke capture access and unload usbmon"
	@echo ""
	@echo "Documentation"
	@echo "  docs                    Build HTML docs into site/ (MkDocs Material)"
	@echo "  docs-serve              Live-reload docs preview at http://127.0.0.1:8000"
	@echo "  docs-clean              Remove generated site/ directory"

sync:
	$(UV) sync --extra dev

install: sync

test:
	$(UV) run pytest -v

build:
	$(UV) build

# Create a release (usage: make version VERSION=X.Y.Z)
version:
	@bash scripts/version.sh $(VERSION)

# Publish an already-tagged version to GitHub Releases + Pages
# (usage: make publish               -> prompts for version
#         make publish VERSION=X.Y.Z -> non-interactive)
# Requires GITHUB_TOKEN env var with `repo` scope.
publish:
	@bash scripts/publish.sh $(VERSION)

# Analyze a single capture (usage: make analyze FILE="path/to/capture.txt")
analyze:
	$(UV) run dspanalyze analyze "$(FILE)" --format claude --decode

# Analyze in raw hex format
analyze-raw:
	$(UV) run dspanalyze analyze "$(FILE)" --format raw

# Analyze excluding poll/level noise (useful for command discovery)
analyze-no-poll:
	$(UV) run dspanalyze analyze "$(FILE)" --format claude --decode --exclude 0x40

# Analyze with human-readable table output
analyze-human:
	$(UV) run dspanalyze analyze "$(FILE)" --format human --decode

# Summary only
analyze-summary:
	$(UV) run dspanalyze analyze "$(FILE)" --format claude --decode --summary

# Compare config reads within a capture to find changed bytes
diff-config:
	$(UV) run dspanalyze diff-config "$(FILE)"

# Analyze all captures (summaries only to avoid flooding)
analyze-all:
	@for f in $(CAPTURES)/*.txt $(CAPTURES)/*.pcapng; do \
		[ -f "$$f" ] || continue; \
		echo ""; \
		$(UV) run dspanalyze analyze "$$f" --format claude --summary --decode; \
		echo ""; \
	done

# Run protocol assertions against all captures
check-all:
	@for f in $(CAPTURES)/*.txt $(CAPTURES)/*.pcapng; do \
		[ -f "$$f" ] || continue; \
		$(UV) run dspanalyze check "$$f" --assertion all 2>/dev/null || true; \
	done

# Load usbmon, grant access, and enable dumpcap capabilities for non-root USB capture
capture-enable:
	sudo modprobe usbmon
	sudo chgrp $(shell id -gn) /dev/usbmon*
	sudo chmod g+r /dev/usbmon*
	sudo setcap cap_net_raw,cap_net_admin=eip /usr/sbin/dumpcap
	@echo "USB capture enabled (usbmon loaded, devices accessible, dumpcap caps set)"

# Remove dumpcap capabilities and unload usbmon
capture-disable:
	sudo setcap -r /usr/sbin/dumpcap
	sudo modprobe -r usbmon
	@echo "USB capture disabled (dumpcap caps removed, usbmon unloaded)"

# Build HTML documentation (MkDocs Material) into site/
# Note: not --strict because README is transcluded with cross-context relative
# links (e.g. analysis/protocol.md → /protocol/) that show as warnings only.
docs:
	$(UV) sync --extra docs --inexact
	$(UV) run mkdocs build

# Live-reload docs preview (http://127.0.0.1:8000)
docs-serve:
	$(UV) sync --extra docs --inexact
	$(UV) run mkdocs serve

# Remove generated docs output
docs-clean:
	rm -rf site
