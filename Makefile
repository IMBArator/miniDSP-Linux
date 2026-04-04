VENV := .venv
PYTHON := $(VENV)/bin/python
CAPTURES := analysis/usb_captures

.PHONY: install test analyze analyze-raw analyze-no-poll analyze-all check-all list-captures capture-enable capture-disable

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -v

# Analyze a single capture (usage: make analyze FILE="path/to/capture.txt")
analyze:
	$(PYTHON) -m dspanalyze analyze "$(FILE)" --format claude --decode

# Analyze in raw hex format
analyze-raw:
	$(PYTHON) -m dspanalyze analyze "$(FILE)" --format raw

# Analyze excluding poll/level noise (useful for command discovery)
analyze-no-poll:
	$(PYTHON) -m dspanalyze analyze "$(FILE)" --format claude --decode --exclude 0x40

# Analyze with human-readable table output
analyze-human:
	$(PYTHON) -m dspanalyze analyze "$(FILE)" --format human --decode

# Summary only
analyze-summary:
	$(PYTHON) -m dspanalyze analyze "$(FILE)" --format claude --decode --summary

# Analyze all captures (summaries only to avoid flooding)
analyze-all:
	@for f in $(CAPTURES)/*.txt $(CAPTURES)/*.pcapng; do \
		[ -f "$$f" ] || continue; \
		echo ""; \
		$(PYTHON) -m dspanalyze analyze "$$f" --format claude --summary --decode; \
		echo ""; \
	done

# Run protocol assertions against all captures
check-all:
	@for f in $(CAPTURES)/*.txt $(CAPTURES)/*.pcapng; do \
		[ -f "$$f" ] || continue; \
		$(PYTHON) -m dspanalyze check "$$f" --assertion all 2>/dev/null || true; \
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
