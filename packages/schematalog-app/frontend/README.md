# Frontend

The TypeScript + CSS build for Schematalog's server-rendered UI. The app stays
**server-rendered** (Jinja owns the HTML); this directory builds the **styling**
(Tailwind v4 + DaisyUI) and the **islands** of interactivity (TypeScript), which Vite
compiles into hashed assets that the FastAPI app serves. There is no SPA here.

**Scope, as of 2026-08-15:** this UI is an *interim demonstration* of what the API can
do, not the product's frontend - that lands later as a separate repo talking to the API
directly (see `../ROADMAP.md`). Keep it working and keep it clean, but don't invest
product-grade design effort in it; visual identity and theming belong to the separate
frontend.

This README is the counterpart to the Python conventions in `../CLAUDE.md`: if you know
the Python side but not the JS/TS ecosystem, start here.

## The toolchain, by analogy to the Python side

| Job | Python | Frontend | What runs |
| --- | --- | --- | --- |
| Package manager / env | `uv` | **pnpm** | `pnpm install` |
| Format + lint | `ruff` | **Biome** | `biome check` |
| Type check | `pyrefly` | **TypeScript** | `tsc --noEmit` |
| Build / dev server | (none) | **Vite** | `vite build` / `vite` |
| Unit tests | `pytest` | **Vitest** (jsdom) | `vitest run` |
| E2E tests | (none) | **Playwright** | *(not wired yet)* |

The big conceptual difference from Python: **there is a build step.** Nothing in here
runs in the browser directly - TypeScript is type-checked and bundled into plain JS,
and the Tailwind CSS is compiled, into `../schematalog/presentation/webapp/static/dist/`
(gitignored, rebuilt on demand and baked into the Docker image at deploy).

## Commands (all via `just`, from the repo root)

You rarely call pnpm directly - the `just` recipes wrap it, and the frontend is folded
into the same top-level recipes as Python so `just ready` covers everything.

| Recipe | Does | Python analogue |
| --- | --- | --- |
| `just install-fe` | install deps (run once after checkout) | `uv sync` |
| `just build-fe` | compile CSS + bundle islands -> `static/dist/` | (build) |
| `just watch-fe` | rebuild on change (run alongside `just serve`) | `--reload` |
| `just format-fe` | auto-format sources in place | `just reformat` |
| `just lint` | Python lint **+** `lint-fe` (Biome) | `just lint` |
| `just type` | pyrefly **+** `type-fe` (tsc) | `just type` |
| `just test` | pytest **+** `test-fe` (Vitest) | `just test` |
| `just ready` | everything, incl. the frontend | `just ready` |

Island unit tests are `*.test.ts` next to the code (jsdom environment, configured in
`vitest.config.ts`). `just test` runs them after the Python suite.

`just serve` builds the frontend once before starting uvicorn. While actively editing
the UI, run `just watch-fe` in a second terminal for fast rebuilds. (For true HMR you
can run `pnpm dev` and set `SCHEMATALOG_VITE_DEV_SERVER=http://localhost:5173`; not
needed for CSS-only work.)

### One-time setup: pnpm

We use **pnpm**, pinned via the `packageManager` field. The supported way to get it is
Corepack (ships with Node >= 16):

```
corepack enable pnpm     # may need sudo if Node lives in a root-owned dir
```

If `corepack enable` needs root and you can't run it, install pnpm standalone instead
(`curl -fsSL https://get.pnpm.io/install.sh | sh -`). Either way, `pnpm --version`
should work before you run the recipes.

## Conventions & rules

These are the TS-side equivalents of the rules in `../CLAUDE.md`, plus a few the Python
codebase doesn't need. **Don't hand-apply formatting** - `just format-fe` is the
arbiter, exactly like `ruff format`.

- **TypeScript only, never plain JS.** `strict: true` is on (the `pyrefly`-grade
  discipline we want). Treat `tsc` errors like type errors in Python: fix them, don't
  suppress.
- **No `any`.** Use `unknown` plus narrowing, or a real type. `any` defeats the entire
  reason we chose TS. (Biome's `noExplicitAny` enforces this.)
- **ESM modules only** - `import` / `export`, never `require`. `verbatimModuleSyntax`
  is on, so import *types* with `import type { Foo }` (keeps type-only imports out of
  the emitted JS).
- **ASCII only in source**, same as the Python rule: `-` not en/em dashes, `...` not
  the ellipsis char, straight quotes. Keeps diffs and grep clean.
- **Formatting** is Biome's: 2-space indent, 96-col lines (matching ruff), double
  quotes, semicolons. Configured in `biome.json`; non-negotiable, auto-applied.
- **Linting** is Biome's `recommended` preset. Prefer a **config-level** exception
  (`biome.json`) over an inline one when it's a project policy - mirrors how the Python
  side prefers a ruff setting over scattered `# noqa` (see `allowed-markup-calls`).
  When you do need a one-off, it's `// biome-ignore lint/<rule>: <reason>` (the `noqa`
  analogue) - always with a reason.
- **Naming:** island entry files are `kebab-case.ts` (e.g. `schema-editor.ts`); inside
  the code, `camelCase` for values/functions, `PascalCase` for types/classes. (Note
  this differs from Python's `snake_case` modules - it's the JS-ecosystem norm.)
- **Dependencies:** keep the runtime bundle lean - justify any new *runtime* dep (it
  ships to the browser). Dev-only tooling deps are cheaper. New deps need their build
  scripts approved in `pnpm-workspace.yaml` (`allowBuilds`) - pnpm blocks install
  scripts by default as a supply-chain guard.

### Islands: how interactivity is structured

The UI is server-rendered HTML with small **islands** of TS for the genuinely
interactive bits (the schema editor, etc.) - not a client-side app. Rules:

- Each island is **one entry** in `vite.config.ts` (`build.rollupOptions.input`) and
  **one file** under `src/islands/`.
- An island is **progressive enhancement**: the server-rendered page must be usable
  without it. The island finds its mount point via a `data-*` attribute and enhances
  it - it does not own or render the page.
- Keep islands small. Reach for Alpine (declarative sprinkles in the markup) before
  writing an island; write an island when the logic is real (e.g. CodeMirror).
- **Never hardcode an asset URL in a template.** Filenames are content-hashed for
  cache-busting. Templates resolve assets through the `vite_asset("<manifest key>")`
  Jinja helper, which reads Vite's `manifest.json`. To add an island: add its entry to
  the Vite config, then `{{ vite_asset("src/islands/<name>.ts") }}` in the template's
  `foot_extras` block. (The helper + the dev/prod switch live in
  `../schematalog/presentation/helpers/assets.py`.)

## Layout

```
frontend/
├── package.json          # deps + scripts; pins pnpm via packageManager
├── pnpm-workspace.yaml    # build-script approvals (allowBuilds)
├── vite.config.ts         # build config: entries, output dir, base URL
├── tsconfig.json          # strict TS
├── biome.json             # format + lint config
└── src/
    ├── styles/app.css      # Tailwind v4 + DaisyUI entry (@source scans the templates)
    └── islands/            # TS islands (one file = one Vite entry) + co-located *.test.ts
```

Build output lands in `../schematalog/presentation/webapp/static/dist/` (a `manifest.json`
plus hashed `assets/*`), served by the app under `/static/dist/`.