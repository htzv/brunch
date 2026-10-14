"""Addresses on brunch's published website.

Build every link to the site from `BRUNCH_WEBSITE_URL`, so rehoming the site
means changing one line here.
"""

from __future__ import annotations

BRUNCH_WEBSITE_URL = "https://htzv.github.io/brunch"
UPDATE_DOCS_URL = f"{BRUNCH_WEBSITE_URL}/update/"

# Anchors are the ids mkdocs generates for the headings of the design memo.
_DESIGN_MEMO_URL = f"{BRUNCH_WEBSITE_URL}/ref/initial-design/"
WORKSPACE_MANIFEST_DOCS_URL = f"{_DESIGN_MEMO_URL}#41-brunchtoml-workspace-manifest"
SET_MANIFEST_DOCS_URL = f"{_DESIGN_MEMO_URL}#42-brunch-settoml-set-manifest"
TOOL_CONFIG_DOCS_URL = f"{_DESIGN_MEMO_URL}#43-tool-config-configbrunchconfigtoml"
TEMPLATES_DOCS_URL = f"{_DESIGN_MEMO_URL}#5-templates"
