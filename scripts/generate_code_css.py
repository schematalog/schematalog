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

LIGHT_STYLE = "friendly"
"""The Pygments style used when the resolved theme is light."""

DARK_STYLE = "github-dark"
"""The Pygments style used when the resolved theme is dark.

There has to be a second one: `friendly` is built for a white ground and its comment
and string colours fall to roughly 2:1 contrast on a dark one, which is unreadable
rather than merely unpleasant.
"""

DARK_SELECTOR = '[data-theme="dark"]'
"""What the dark rules hang off when the theme has been resolved.

With JavaScript the page always carries a concrete `data-theme` - "auto" is a stored
*preference*, not a third value of the attribute - so this selector covers every
resolved case, whether the reader chose dark or inherited it from the system.
"""

DARK_FALLBACK_SELECTOR = ":root:not([data-theme])"
"""What the dark rules hang off when nothing resolved the theme.

Without JavaScript no attribute is ever set, and the component library switches to its
dark palette on `prefers-color-scheme` alone. Matching that here is what stops a
no-script reader on a dark system getting dark chrome around a light code block. It
mirrors the selector the component library uses for the same case, deliberately.
"""

TARGET = (
    Path(__file__).parent.parent
    / "packages"
    / "schematalog-app"
    / "frontend"
    / "src"
    / "styles"
    / "code.css"
)
"""Where the generated stylesheet goes.

The frontend moved under `packages/schematalog-app/` with the split into
distributions and this path did not follow, so the recipe had been writing
nowhere - it raised rather than silently missing, which is why the stylesheet
was merely stale and not wrong.
"""

HEADER = """/* Syntax highlighting for server-rendered code blocks (the schema detail page).
   Pygments emits the markup; this file styles it.

   The token rules below are GENERATED - regenerate with `just regen-code-css`
   (scripts/generate_code_css.py). Two palettes: the light one applies by default and
   the dark one is scoped to the resolved `data-theme`. */

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


def token_rules(style: str, prefix: str = "") -> list[str]:
    """The token rules for one Pygments style, minus the ones that would fight the page.

    Dropped: the bare `pre` rule (it would leak into every code block on the site),
    the `linenos` rules (a formatter mode we do not use - line numbers are CSS
    counters here), and Pygments' own `.hl` background, which would override the
    panel colour the block inherits from DaisyUI.

    Args:
        style: the name of the Pygments style to render.
        prefix: an optional selector the rules are nested under, so one palette can
            be scoped to a theme without the other being scoped to anything.

    Returns:
        One CSS rule per line, in Pygments' order.
    """
    selector = f"{prefix} .hl" if prefix else ".hl"
    defs = HtmlFormatter(style=style).get_style_defs(selector)
    return [
        line
        for line in defs.splitlines()
        if line.startswith(selector)
        and "linenos" not in line
        and not line.startswith(f"{selector} {{")
    ]


def main() -> None:
    light = token_rules(LIGHT_STYLE)
    dark = token_rules(DARK_STYLE, DARK_SELECTOR)
    fallback = token_rules(DARK_STYLE, DARK_FALLBACK_SELECTOR)
    body = (
        f"/* Light palette ({LIGHT_STYLE}) */\n"
        + "\n".join(light)
        + f"\n\n/* Dark palette ({DARK_STYLE}), once the theme has been resolved */\n"
        + "\n".join(dark)
        + "\n\n/* The same palette for a reader with no JavaScript, where nothing\n"
        + "   resolves the theme and only the system setting is known. */\n"
        + "@media (prefers-color-scheme: dark) {\n"
        + "\n".join(fallback)
        + "\n}"
    )
    TARGET.write_text(HEADER + body + "\n")
    print(f"wrote {len(light)} light and {len(dark)} dark token rules to {TARGET}")


if __name__ == "__main__":
    main()
