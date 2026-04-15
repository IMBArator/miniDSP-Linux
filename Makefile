UV      := uv
CAPTURES := analysis/usb_captures

.PHONY: sync install test analyze analyze-raw analyze-no-poll analyze-human \
        analyze-summary analyze-all diff-config check-all \
        capture-enable capture-disable build

sync:
	$(UV) sync --extra dev

install: sync   ## alias kept for muscle memory

test:
	$(UV) run pytest -v

# Build the package (sdist and wheel)
build:
	$(UV) build

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
