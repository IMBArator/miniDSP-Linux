"""mkdocs hooks: post-process the transcluded README's relative links.

The home page (docs/index.md) transcludes README.md via
mkdocs-include-markdown-plugin with rewrite_relative_urls=true. README's
GitHub-relative paths get rewritten to docs-tree paths, but our docs tree
doesn't mirror the source layout (analysis/ files are surfaced at the
site root, not under analysis/). Map those rewritten paths to their
rendered counterparts so MkDocs' link checker stops warning.
"""
from __future__ import annotations

import re

_LINK_MAP = {
    "../analysis/protocol.md": "protocol.md",
    "../analysis/feature-list.md": "feature-list.md",
    "../LICENSE": "https://github.com/IMBArator/miniDSP-Linux/blob/main/LICENSE",
}


def on_page_markdown(markdown: str, *, page, config, files) -> str:
    if page.file.src_uri != "index.md":
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
