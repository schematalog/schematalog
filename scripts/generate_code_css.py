"""Regenerate the Pygments token styles in `frontend/src/styles/code.css`.

The schema detail page highlights its code blocks server-side (see
`presentation/helpers/format.highlight`), which needs a stylesheet for the token
classes Pygments emits. Those rules are generated rather than hand-written, so a
change of style is a one-line edit here instead of 70 lines of hex.

Run via `just regen-code-css`, which reformats the result afterwards - Biome owns
the frontend's formatting, and this script does not try to match it.
"""

from pathlib import Path

from pygments.formatters import HtmlFormatter

STYLE = "friendly"
"""A light Pygments style; the app pins `data-theme="light"` (see the file header)."""

TARGET = Path(__file__).parent.parent / "frontend" / "src" / "styles" / "code.css"

HEADER = """/* Syntax highlighting for server-rendered code blocks (the schema detail page).
   Pygments emits the markup; this file styles it.

   The token rules below are GENERATED - regenerate with `just regen-code-css`
   (scripts/generate_code_css.py). Light theme only for now: the app pins
   `data-theme="light"`, so a dark palette would be untestable dead CSS. */

.hl {
  counter-reset: hl-line;
  background: transparent;
}

.hl pre {
  margin: 0;
  background: transparent;
}

/* Line numbers are CSS, not markup, so they stay out of the DOM text - which keeps the
   copy button (and a manual selection) copying code only. */
.hl pre > span[id] {
  counter-increment: hl-line;
}

.hl pre > span[id]::before {
  content: counter(hl-line);
  display: inline-block;
  width: 2.5em;
  padding-right: 1em;
  text-align: right;
  color: color-mix(in oklch, currentColor 40%, transparent);
  user-select: none;
  -webkit-user-select: none;
}

/* Generated token styles */
"""


def token_rules() -> list[str]:
    """The `.hl`-scoped token rules, minus the ones that would fight the page.

    Dropped: the bare `pre` rule (it would leak into every code block on the site),
    the `linenos` rules (a formatter mode we do not use - line numbers are CSS
    counters here), and Pygments' own `.hl` background, which would override the
    panel colour the block inherits from DaisyUI.

    Returns:
        One CSS rule per line, in Pygments' order.
    """
    defs = HtmlFormatter(style=STYLE).get_style_defs(".hl")
    return [
        line
        for line in defs.splitlines()
        if line.startswith(".hl") and "linenos" not in line and not line.startswith(".hl {")
    ]


def main() -> None:
    rules = token_rules()
    TARGET.write_text(HEADER + "\n".join(rules) + "\n")
    print(f"wrote {len(rules)} token rules to {TARGET}")


if __name__ == "__main__":
    main()
