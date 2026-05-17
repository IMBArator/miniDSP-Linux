"""Load the bundled factory-default parameter values.

The TOML file shipped at ``minidsp/factory_defaults.toml`` is generated from
the F00 preset-load USB capture by ``dspanalyze extract-defaults``. It is the
source of truth for "what does the device look like immediately after loading
the factory preset" and is intended for UIs (e.g. a Qt control tool) that need
a starting state without having to talk to a device first.

Values are in the raw protocol form (matches ``parse_preset_params`` output).
Use the converters in :mod:`minidsp.protocol` (``raw_to_db``, ``freq_raw_to_hz``,
``peq_raw_to_q``, etc.) to derive human-friendly numbers.
"""

from __future__ import annotations

import importlib.resources
import tomllib

_RESOURCE_NAME = "factory_defaults.toml"


def load_factory_defaults() -> dict:
    """Return the parsed contents of ``minidsp/factory_defaults.toml``.

    Returns:
        Dict with top-level keys ``schema_version``, ``preset``,
        ``preset_name``, ``source_capture``, ``encoding``,
        ``channels`` (8-element list), and ``params`` (matches
        :func:`~minidsp.protocol.parse_preset_params` output plus
        ``test_tone_mode``, ``test_tone_freq``, ``delay_unit``).

    Raises:
        FileNotFoundError: If the bundled TOML resource is missing — this
            indicates a packaging bug (the data file was not included in the
            build). Regenerate with ``dspanalyze extract-defaults <f00-capture>``.
    """
    resource = importlib.resources.files("minidsp").joinpath(_RESOURCE_NAME)
    with importlib.resources.as_file(resource) as path:
        if not path.exists():
            raise FileNotFoundError(
                f"Bundled resource missing: minidsp/{_RESOURCE_NAME}. "
                "Regenerate with: dspanalyze extract-defaults <f00-capture>"
            )
        with open(path, "rb") as f:
            return tomllib.load(f)
