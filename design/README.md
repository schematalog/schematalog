# Brand assets

The mark, and the things cut from it. Kept here because it was very nearly lost: the
only vector lived on an unmerged WIP branch of a private repository, and the project
shipped for months with nothing but two PNG exports.

| File | What it is |
| --- | --- |
| `schematalog-mark.svg` | The master geometry, cropped to the mark. No colours - the surround is a filled shape and the three inner rules are stroked, and whatever uses it supplies the ink. |
| `schematalog-avatar.svg` | Square, dark ink on a white ground, for an avatar or a social card. Fixed colours, because the places these are shown composite them against their own chrome and offer no theme to ask about. |
| `schematalog-avatar.png` | The above at 1024x1024, which is what upload forms want. |

Two more are derived from the same geometry and live where they are used, rather than
here, so nothing has to copy a file at build time:

- `packages/schematalog-app/schematalog/app/presentation/webapp/static/schematalog-icon.svg` -
  the favicon. Carries its own colours plus a `prefers-color-scheme` rule, since a
  favicon inherits nothing and the browser's tab strip follows the operating system.
- `_icons.html.jinja`'s `mark()` macro - the header. Inlined with `currentColor`, because
  the header follows the theme the *reader* chose, which is a different question from
  what the operating system is set to. Those two disagree the moment someone on a light
  system picks the dark theme.

## Regenerating

There is no build step: a mark changes about once a decade, and a pipeline for it would
be read once and wrong by the time it mattered. To change the shape, edit
`schematalog-mark.svg`, then update the favicon, the macro and the avatar from it
together. The original Inkscape working file - an A4 page with the wordmark and earlier
variants - is on the `logo` branch of the private `schematalog-archive` repository.
