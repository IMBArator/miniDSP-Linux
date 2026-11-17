"""mkdocs hooks: post-process transcluded files' relative links.

Several pages (docs/index.md, docs/changelog.md, …) transclude source
files via mkdocs-include-markdown-plugin with rewrite_relative_urls=true.
The source files' GitHub-relative paths get rewritten to docs-tree paths,
but our docs tree doesn't mirror the source layout (analysis/ files are
surfaced at the site root, not under analysis/). Map those rewritten
paths to their rendered counterparts so MkDocs' link checker stops
warning.

The second hook drops api/SUMMARY.md from the build after
mkdocs-literate-nav has consumed it (otherwise it would render as an
orphan page and pollute the search index).
"""
from __future__ import annotations

import re

# Pages whose relative links point at source files outside docs/ and
# therefore need rewriting: pages that transclude an upstream Markdown
# file, and architecture.md and development.md, which link the sources
# directly so the links also work on GitHub. Any page not listed here is
# passed through unchanged.
_TRANSCLUDED_PAGES = {
    "index.md",
    "changelog.md",
    "contributing.md",
    "architecture.md",
    "development.md",
}

_LINK_MAP = {
    "../analysis/protocol.md": "protocol.md",
    "../analysis/feature-list.md": "feature-list.md",
    "../dspanalyze/USAGE.md": "dspanalyze-usage.md",
    "../LICENSE": "https://github.com/IMBArator/miniDSP-Linux/blob/main/LICENSE",
    "../CHANGELOG.md": "changelog.md",
    "../CONTRIBUTING.md": "contributing.md",
    "../README.md": "index.md",
}


def on_page_markdown(markdown: str, *, page, config, files) -> str:
    if page.file.src_uri not in _TRANSCLUDED_PAGES:
        return markdown
    for old, new in _LINK_MAP.items():
        markdown = re.sub(
            r"\]\(" + re.escape(old) + r"(#[^)]*)?\)",
            lambda m, new=new: f"]({new}{m.group(1) or ''})",
            markdown,
        )
    return markdown


def on_files(files, config):
    """Drop api/SUMMARY.md from the build after literate-nav has read it.

    literate-nav consumes the file during its own ``on_files`` to build the
    API reference nav tree. We then remove it so MkDocs doesn't render it as
    an orphan HTML page (also keeping it out of sitemap.xml and the search
    index). Hooks run after plugins, so the ordering is safe.
    """
    summary = files.get_file_from_path("api/SUMMARY.md")
    if summary is not None:
        files.remove(summary)
    return files
