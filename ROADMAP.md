# Roadmap

Forward-looking plan for Schematalog. This file is the human source of truth for
"what's next"; architecture and conventions live in `CLAUDE.md`, frontend conventions
in `frontend/README.md`, and the record of what was chosen and what was rejected in
`DECISIONS.md`. Update it as work lands.

**Direction reset, 2026-08-15.** The multi-tenant SaaS arc is abandoned. What follows
replaces it wholesale; the previous roadmap is recoverable from git history if the
reasoning is ever needed. See "What was abandoned, and why" at the end.

## What Schematalog is

A registry and catalog for JSON Schema specifications: it stores versioned schema
documents and serves them back for validation, `$ref` resolution, and format
conversion.

Five decisions define the current direction:

1. **The API is the product.** Everything else is a consumer of it.
2. **No authentication, and no tenancy as a security boundary.** The API is fully
   public. The target is an instance an organisation installs internally and runs for
   itself - and installing it should be quick and unceremonious (see phase 5).
3. **Catalogs replace workspaces, as soft grouping.** A schema belongs to nothing by
   default and lives in one flat namespace; a catalog is a separate named thing that
   *references* schemas, and any schema may be in many catalogs or none. See
   `DECISIONS.md` for why grouping was kept out of a schema's identity.
4. **A separate frontend repo is the long-term UI.** The current server-rendered UI
   stays in the meantime as a working demonstration of what the API can do.
5. **Everything is open source.** All repos public, under a permissive licence.

### The one principle that constrains everything else

**The API is the complete contract.** Every capability must be expressible through it;
no other surface may have powers the API lacks. This was previously an aspiration
carried by the UI work. It is now the whole thesis, and it is not currently true: the
server-rendered UI calls the application services directly rather than going over
HTTP, so it neither proves nor depends on API completeness. Closing that gap is part
of the interim-UI work below.

## Phase 1: teardown

Removing what the reset makes obsolete. Destructive and wide, so it goes first and in
its own sequence - the codebase does not need to stay deployable at every step, but it
does need to stay green.

**Done (2026-08-22), in four commits rather than the six bullets below.** The order was
Alembic, then visibility, then authentication, then tenancy - each removal made the next
smaller, because the thing it was entangled with was already gone. Two bullets merged into
one commit: subdomain routing could not outlive tenancy, since with no tenants every
request is a bare-domain request and the middleware would have redirected the whole UI to
the homepage. Orphan pruning happened inline rather than as a final sweep; it also took
the operator CLI (nothing left to provision), the Pico CSS base template and stylesheets
(the landing page was their last user), and the wildcard-DNS and local-TLS dev setup.

- **Remove authentication entirely.** The identity provider, the browser login and
  session flow, API tokens, the `Principal` model, and every authorization predicate.
  The identity vendor is confined to a single adapter module, so the vendor removal
  itself is small; the surrounding flows (login, callback, workspace onboarding, token
  management) are the bulk of the work.
- **Remove subdomain routing.** Schemas move to a plain `/schemas/...` path with nothing
  scoping them. The bare-domain middleware, the subdomain helpers, and the wildcard DNS
  and certificate requirements all go with it, which also removes the most awkward part
  of local development.
- **Take the scope out of schema identity.** A schema is identified by `(name, version)`
  alone, in one flat namespace per instance. This removes the tenant identifier from the
  primary key and from every repository method signature - wide but mechanical, and the
  teardown is touching those signatures anyway. What is left of the old tenant concept is
  rebuilt as catalogs in phase 2; it is not a rename of the existing code so much as a
  replacement of it.
- **Reset the database and drop the migrations - including Alembic itself.** With no
  users and no data worth keeping, a single fresh baseline beats a chain of
  drop-migrations; six of the ten existing revisions exist only to add tenancy and auth.
  Decided (see `DECISIONS.md`): the tool goes now rather than being carried through a
  teardown that rebuilds the shape repeatedly, and returns at the first change that must
  preserve data anyone cares about. Removal touches the dependency, `alembic.ini` and
  `alembic/`, the Fly release command, two Dockerfile copies, the migration-only second
  database in the compose stack, `tests/integration/test_migrations.py`, and the ruff,
  pyrefly and deptry exclusions that existed only for it. `auto_create_tables` becomes
  the only mechanism and so defaults on everywhere.
- **Remove visibility (public/private).** It is access control, and there is no longer
  anything to control access against. Everything in an instance is readable, until
  further notice - if basic API authentication ever returns (see Open questions), this
  is the natural thing to reconsider alongside it.
- **Prune what the removals orphan**: the operator CLI's token commands, the auth
  templates, the deploy-time secrets, and the now-unreferenced configuration.

Deferred deliberately: deciding what the *lifecycle* metadata (deprecated, successor)
looks like once visibility is gone. It is independent of all of the above and should
not be disturbed by the teardown.

## A repeatable reset for the demo

The demo at schematalog.com is the one instance affected by shipping no migrations before
1.0 (see `DECISIONS.md`), so it is recreated rather than upgraded, and that needs to be
one unceremonious command rather than a remembered sequence.

Wanted for a second reason too: once anyone reaching the demo can publish to it, it needs
restoring to known sample data periodically, so a visitor meets the registry as intended
rather than as whatever the last passer-by left.

Note what it cannot be built from today: there is **no delete** anywhere - not on the API,
not on the repository protocol - so a reset is currently an infrastructure operation
(drop the store, `just seed`) rather than something expressible through the product. That
is worth deciding deliberately rather than by default, because "empty this catalog" was
explicitly ruled out of the storage contract and assigned to a future SDK as orchestration
over the API - which presumes an API that can delete.

## Phase 2: the API

The product. Roughly in dependency order.

**Designed in its own right, with no UI constraint** (decided 2026-08-22): the interim UI
does not consume it, and the eventual frontend reaches it through a backend-for-frontend
rather than directly. So this is a resource API answering for itself, not one shaped by
what a page happens to render.

**Order revised 2026-08-29** (see `DECISIONS.md`): versioning, then storage - both
done - then **search**, then **labels**, then **catalogs only if still wanted**, then
reference resolution, then import last if at all. Search moved ahead of grouping because
finding things in a large registry is what grouping is *for*, and because a catalog is a
second aggregate that would either double what the storage guide asks of a backend author
or fracture the contract into which-backend-supports-what. Labels avoid that entirely:
they are mutable per-schema metadata, the family `set_metadata` already carries.
- **Order versions by publication, not by string.** Decided (see `DECISIONS.md`):
  versions stay free-form and the registry never interprets them, so ordering becomes a
  registry fact. Each version gains an immutable `publication_id` - a UUIDv7, required
  to be one and documented as such - minted once above the repository layer, from which
  `get_latest`, `list_latest` and `list_versions` all derive; the wire keeps a real
  timestamp as `published_on`, derived from that identifier rather than stored, replacing
  `created_on`. Lexicographic version
  comparison leaves the system, along with the `10.0`-before-`9.0` defect and the
  disagreement between `get_latest` and `list_versions`. `deprecated` and `successor`
  become filters on what may be latest, not an ordering.
- **Rework storage configuration and open the extension point.** Fully decided (see
  `DECISIONS.md`); the versioning change it waited on has landed. In order:
  1. **Shrink the protocol to five required methods** - `add`, `get`, `set_metadata`,
     `list_versions`, and a new `list_names()` - with `get_latest`, `list_latest` and
     `list_predecessors` derived in a base class and overridden by the SQL backend.
     `_reset` leaves the contract entirely.
  2. **Replace the config union with one `SCHEMATALOG_STORAGE_URL`**, options as query
     parameters, the scheme selecting the backend.
  3. **Add entry-point discovery** (plus a dotted-path escape hatch) so a third party can
     register a scheme without editing this repository.
  4. ~~Publish the conformance suite~~ - done: `schematalog.testing.SchemaRepositoryConformance`,
     signed by every in-tree backend, by Postgres in the integration lane, and by an
     out-of-tree probe backend.
  5. **Operator guidance on choosing a backend** - which one suits which deployment,
     and each one's honest limits. SQLite is the default; Postgres is for scale and for
     more than one instance; the filesystem backend is supported in its own right,
     including inside a git working tree.
  6. ~~Revive S3 through the seam~~ - done: `packages/schematalog-s3` is a separate
     distribution registering the `s3` scheme by entry point, and it passes the whole
     conformance suite. Barely a revival - the pruned code was synchronous, used the old
     method names, raced on check-then-put, and picked latest by string comparison.
  7. **The implementer's guide** - the repository contract, the conformance suite,
     entry-point registration, and a worked example. Deliberately *after* S3 rather than
     before: S3 is the first real walk of that path, and every seam built so far has had
     something wrong with it that only appeared on contact (underscores in URL schemes,
     `max(uuid)` on PostgreSQL, `UUID.time` under asyncpg). The guide should document a
     route that has been travelled, including whatever turned out to be awkward, which is
     the part a third party most needs warning about. Moved here from phase 5's
     documentation bullet: an extension point nobody has instructions for is not finished.
- **Search.** The most-missed capability: today a catalog with hundreds of schemas
  offers one alphabetical list and nothing else. A capability with a default
  implementation rather than a sixth required repository method - the base class scans, a
  backend overrides when its store can answer better - so it works everywhere from the
  first release. Defined by its guarantee (case-insensitive substring matching,
  name-ascending) rather than by its mechanism, so a better engine may only be faster and
  never different, and the conformance suite says so. Filtered, never ranked. Query
  parameters on `/api/schemas`, not a new resource.

  **Name and description are done (2026-08-31)**: one `q` parameter, every word of a
  query required in one field or the other, no syntax of any kind (see `DECISIONS.md` for
  why that rule is what keeps a query language from growing). Two pieces remain.
  **Searching the document itself** - property names above all - which the decision says
  should be its own parameter rather than folded into `q`, since an unranked union would
  swamp the other two. And **pagination**, still to be settled with search, since search
  is what makes large results likely.

  Also left open by the ASCII-only alphabet: matching a non-ASCII query needs backends to
  match against an application-written folded column rather than folding as they query,
  because no two stores lower-case alike. Worth doing when someone needs it.
- **Labels or annotations on a schema.** Free-form tags, a fixed category hierarchy,
  or arbitrary annotations - scope still open, including whether free-form labels need
  any constraint to stop them drifting (`payments`, `payment`, `Payments`). Cheap by
  construction: mutable per-schema metadata in the same family as `deprecated` and
  `successor`, so it extends one existing method rather than adding an aggregate.
- **Catalogs, only if labels and search leave something missing.** Deferred 2026-08-29
  rather than dropped; `DECISIONS.md` keeps both the design (soft grouping, referencing
  rather than containing) and the reason for holding off. The test for whether one is
  ever needed: a grouping that must be **described, linked to and owned** - "the payments
  team's schema set", with a URL and a paragraph saying what it means. Labels can be
  searched, filtered and combined, but cannot carry that prose, cannot be renamed without
  rewriting every member, and can only be discovered by scanning rather than listed
  authoritatively. If nobody asks for the describable thing, an aggregate and a contract
  expansion are saved.
- **Reference resolution, bundling, and the dependency graph.** Three faces of one
  mechanism - reading the `$ref`s inside a stored document. Today the registry stamps
  each schema with a resolvable address so references *can* be followed, but it will not
  follow them itself, will not return a schema bundled together with everything it
  depends on, and cannot answer "what depends on this one". The dependency graph between
  schemas is therefore invisible, which is a strange gap for a catalog. `CLAUDE.md`
  already anticipates this, noting that `$ref` resolution belongs on `JsonSchemaDocument`.
  Distinct from the successor and predecessor chain, which is lifecycle rather than
  structure.

  **Full resolution is the goal, arrived at gradually.** Each step is useful on its own
  and none of them commits the next, so this does not need to land as one piece:

  1. **Parse and expose** the references a document declares. No fetching, no rewriting -
     just the forward edges, made visible.
  2. **Invert them** into "what depends on this", which falls out of step 1 for free
     within a single instance.
  3. **Resolve references to this registry's own schemas**, one hop and then
     transitively. Cycle handling starts to matter here.
  4. **Bundle** - return one self-contained document with local references inlined or
     gathered into `$defs`, which is what a consumer validating offline actually wants.
  5. **External references**, pointing at other registries or arbitrary URLs.

  **Which of these are even ours** is now answered by the API/SDK boundary rule (see
  `DECISIONS.md`): steps 1, 3, 4 and 5 are all proportional to the document being asked
  about, so they are SDK-shaped. **Step 2 - the reverse dependency graph - is the API's**,
  because answering "what depends on this?" client-side means reading every schema in the
  registry. Build that here; leave the rest to the SDK unless a reason appears.

  **The remaining boundary worth deciding in advance** is between steps 4 and 5. Everything
  up to bundling is internal and safe; following an external reference makes whoever does
  it a client of the open internet, with the fetching, caching, trust and availability
  questions that brings - which is a further argument for it being the SDK's.

  **A subtlety that shapes step 4.** A reference to a version-pinned address resolves to
  something immutable, so a bundle built from it is reproducible forever. A reference to
  an unversioned address resolves to *latest*, which moves - so the same bundle request
  can return different content over time. Either restrict bundling to pinned references,
  or record in the bundle what each reference resolved to; deciding late means deciding
  after someone has depended on the answer.

  **A concrete payoff along the way:** the in-house Avro converter currently refuses any
  schema containing a `$ref`, so bundling would make the Avro and Python renderings work
  for documents that today produce only an apology.
- **An import path - last, if at all, and probably not here.** Four things wear this one
  name, and they deserve separate verdicts: bulk publish, a directory-of-files import,
  synchronisation from a git repository, and migration from a competing registry.

  **The leaning (2026-08-22) is that this belongs to the SDK rather than the API.** Every
  one of the four is client-side orchestration over a per-version endpoint the API already
  has - read a directory, translate a foreign model, decide what to skip, retry the
  failures, report what happened. None of it needs to run inside the registry, and putting
  it there would add a stateful, partially-failing operation to an otherwise simple
  resource API. It is the same argument as the shell loop below, one level up: if a loop is
  most of the feature, the place for the loop is a library. Revisit under phase 4.

  Further notes from the same discussion, to be gone into properly if and when this is
  reached:
  - **The case for it is adoption, not evaluation.** Someone *trying* Schematalog needs
    three schemas, which the seed script and the demo instance already cover. Someone with
    two hundred schemas in a git repository has already decided to adopt. So it serves
    users who do not exist yet - the same reasoning that removed authentication.
  - **Bulk publish is mostly a documentation problem.** For a JSON API the user's
    alternative is a five-line shell loop over `POST /api/schemas`, and the things a loop
    cannot do turn out to be things we do not want: atomicity is wrong at this granularity
    (conflicts are per-version), dependency ordering does not matter because `$ref`s are
    not resolved at publish time, and throughput is irrelevant at these volumes. A
    documented recipe is most of the feature.
  - **Git sync and competitor migration are separate products.** Git sync raises which
    side is the source of truth, push versus pull, conflict handling, and whether it
    belongs in CI tooling rather than in the registry. Confluent migration means modelling
    subjects and compatibility policies. Judge each on its own, against a real request.
  - **The one part that constrains earlier work: provenance.** Under publication ordering
    an imported version gets today's `publication_id`, so `published_on` says today and
    version order becomes *import* order rather than the original chronology - import five
    years of history and the registry claims it all happened in one afternoon. Defensible,
    since it genuinely was published *here* today, but "when was v1 created" becomes
    unanswerable, which is a real loss for a product built on version history. So: does a
    version need a provenance field (original date, source registry) distinct from its
    publication into this instance? Cheap to decide, impossible to backfill - dates not
    captured at import are gone. And "additive later" is no longer free, because with no
    migration tool a new column means recreating the database. Fine while there are no
    users, which is exactly the window this is being decided in.

## Phase 3: interim UI

The current server-rendered UI stays, on the frameworks it already uses (Jinja,
Tailwind v4, DaisyUI, TypeScript islands, Vite). It is a demonstration of the API's
capabilities, not a product surface, and should not attract product-grade investment.

- **Shrink it to what survives the teardown** - *done in phase 1*: the login, callback,
  workspace-onboarding and token pages are gone, and so is the old CSS base (the landing
  page was its last user, and went with the tenancy removal). What remains is the schema
  list, the detail page with its format tabs, and publishing.
- **Keep basic create/update/delete**, deliberately - a demo that can only read is a
  poor demo. This is provisional; it can be reduced later if the maintenance cost shows
  up.
- **It keeps calling the application services directly** (decided 2026-08-22, see
  `DECISIONS.md`). It is not routed through the HTTP API, and the API is designed without
  reference to it. The replacement UI will talk to a separate backend-for-frontend, which
  is itself a consumer of the pure API - so completeness stays enforced, but at a seam
  where the reshaping does not distort the public contract. Until that exists, nothing
  enforces the principle, so the standing rule is that the UI may not gain a capability
  the API cannot express.
- Route-naming constraint worth preserving: schema pages live under a user-chosen
  namespace, so the publish page is `/publish` rather than `/schemas/new` - the latter
  would permanently shadow a schema named "new". The same reasoning applies to any
  future action route.

Design and visual identity - palette, typography, logo, spacing, a component
inventory, an accessibility baseline, responsive targets, and light/dark theming -
were owed to the old UI and are **not** owed to this one. They belong to the separate
frontend repo below. Dark mode is currently inert (the page template hardcodes the
light theme); leave it that way rather than half-fixing it.

## Phase 4: the SDK

A separate library, in its own repo, that retrieves schemas through the API and turns
them into usable classes. This is the piece the deliberately thin domain layer has
always been kept thin *for*. It owns what the API does not:

- Walking the successor and predecessor chain across registries, where the API answers
  only a single hop within one instance.
- Cycle detection over a whole lineage, where the API guards only the trivial
  self-reference.
- **Bulk operations over the catalog**, which keep turning out to belong here rather
  than in the registry: importing a directory or another registry's contents (see the
  import item in phase 2), and emptying a catalog - a real thing to want, and the reason
  the storage contract does *not* carry a reset method. Each is orchestration over
  per-version endpoints the API already has: read, translate, decide what to skip, retry
  the failures, report what happened. None of it needs to run inside the registry.
- **Moving a registry from one backend to another** - "search is constant now and the
  catalogue has outgrown PostgreSQL; move it to Elastic". Far future, and listed because
  it is the use case that makes the bulk operations above worth building rather than a
  curiosity. The tractable version is backend-to-backend *within one instance*: the
  address stays the same, so every `$id` keeps resolving, and the work is read
  everything through the API, repoint `SCHEMATALOG_STORAGE_URL`, write it all back.
  **The obstacle is `publication_id`.** It is minted above the repository layer,
  immutable, and validated as a UUIDv7; it is also the ordering of every version and the
  source of `published_on`. Republishing through the API mints a fresh one, so a naive
  copy would stamp the entire catalogue as published on migration day and could reorder
  it. Preserving it needs an affordance the publish endpoint deliberately does not have -
  which is the same question the import item in phase 2 has to answer, and a good reason
  to answer it there rather than twice.

Open: whether to build on momoa (already open source, parked for exactly this) or
start fresh.

Packaging: this is the moment to make `schematalog` a namespace package, moving
today's application under `schematalog.app` and shipping the SDK as
`schematalog.sdk`, each independently versioned. A namespace of one is premature, so
this happens when the SDK starts and not before. It is a mechanical but wide rename,
best landed as one isolated commit with no behaviour change.

## Phase 5: open source and easy self-hosting

- ~~A console entry point~~ - done: `pip install schematalog-app` then `schematalog serve`,
  with `schematalog info` to check how configuration resolved.
- **A very simple way to get a running instance, quickly.** This is a goal of the whole
  direction rather than a nicety - an internally-installed registry that is awkward to
  install is a contradiction. Someone evaluating Schematalog should get from "I found
  this" to "it is running and I have published a schema" in minutes, without reading the
  documentation first.

  **What that mechanism actually is stays open** - the space runs from a single container
  command, through a compose file, to a one-click template on a hosting provider, and
  more than one of those may be worth having. Decide later.

  The decision leans heavily on the **storage backend** question in phase 2: a default
  backend that needs no external service turns the whole thing into one command, whereas
  a database-first default means anyone trying it must provision one before they begin.
  That is the difference between an evaluation that takes two minutes and one that takes
  an afternoon, so the two decisions are worth taking together.
- **Decide whether our own deployment config belongs in this repository at all.**
  `fly.toml` and `compose.yaml` are excluded from the sdist - they name a provider and an
  app that are ours, and configure nothing a user owns - but they still sit inside
  `packages/schematalog-app/`, where they read as part of the package rather than as how
  *we* happen to run the demo instance. A `deploy/` directory at the root, or dropping
  `fly.toml` entirely if the hosting moves, would say that more honestly. Raised
  2026-08-22.
- **Licence.** This repo already carries MIT (2022). Confirm it is still the intended
  choice now that the server is opening too, not only a client library, and apply the
  same choice consistently across repos.
- **Claim `schematalog` on PyPI before the repository is public.** The distributions are
  `schematalog-core`, `schematalog-app`, `schematalog-s3` and later `schematalog-sdk`,
  which leaves the bare name unclaimed - and the import namespace *is* `schematalog`, so
  a package published under that name could install files straight into it. PyPI reserves
  no prefixes, so publishing is the protection, and the risk rises the moment the project
  becomes visible.

  The recommendation is a **meta-package rather than a placeholder**: `schematalog`
  depending on `schematalog-app`, so `pip install schematalog` installs the registry -
  which is what someone typing that name intends - while claiming the name. It ships no
  files of its own, so it cannot conflict with the namespace. The alternative is to name
  the application distribution `schematalog` outright (it would still provide
  `schematalog.app`); that is one fewer artefact but breaks the symmetry of the other
  names. Raised 2026-08-22.
- **Publish from CI rather than by hand**, using PyPI trusted publishing: the workflow
  authenticates by OIDC, so there is no long-lived API token to store or leak. Worth doing
  once releases stop being rare, and it pairs with the tagging decision below - a tag
  becomes the thing that triggers a release. The first upload is manual regardless, since
  trusted publishing has to be configured against a project that already exists.
- **Decide how to tag releases across three packages.** `v<version>` was unambiguous for
  one distribution and is not for three, and all three now start at 0.1.0 independently.
- ~~Make the repos public, starting the history clean~~ - done at 0.1.0. The published
  history begins at the first release: three months of building a multi-tenant SaaS and
  then dismantling it is noise to a newcomer, and `DECISIONS.md` already carries forward
  the only part that was load-bearing, which is the reasoning. The earlier history is kept
  privately rather than published. It was checked and carries no committed secrets - no
  environment files, certificates or provider URLs.
- **The contributor-facing basics** - README and `CONTRIBUTING.md` written at 0.1.0; an
  issue tracker and a first pass over the docs for a stranger's eyes remain.
- **Operator documentation, which now matters more than it did.** For a hosted service
  the operator was us, and anything undocumented could be answered by reading the code
  we had just written. For software someone installs and runs themselves, the
  documentation *is* the product surface for every decision they have to make. The set
  that has to exist:
  - **Deploying an instance** - the two-minute path, and the real one. Whatever the
    quick-deploy mechanism turns out to be, it needs a page rather than a paragraph.
  - **Choosing and configuring a storage backend**, and **writing your own** - both
    written during the storage work in phase 2 (steps 5 and 7), so this is a review pass
    for a stranger's eyes rather than a first draft.
  - **Adding authentication**, when that seam lands - the same shape as the storage
    page, since the plan is one mechanism for both.
  - **Upgrading**, which for now means "there is no migration tool, so a change to an
    existing table means recreating the database" - an unusual constraint that must be
    stated rather than discovered.
  - **Backup and restore**, which today is "whatever your storage backend does" and
    should say so plainly rather than being silently absent.

  Also part of this: the *existing* eight guides were written for a hosted multi-tenant
  service. Authentication, workspaces, tokens and visibility are the subject of several
  of them, so the teardown deletes or rewrites more of the documentation than it leaves
  standing. Treat the surviving set as a first draft aimed at the wrong reader.
- **Publish the documentation site.** It builds today (eight narrative guides) but is
  hosted nowhere. Two candidates were weighed on 2026-06-19: **plus.hr**, the existing
  Croatian host where the domains already live (lowest friction - sovereign, no new
  account, one DNS record; build in CI and upload the static site), or **Northflank**,
  as a low-stakes trial of the European hosting migration parked below - the docs are a
  harmless place to learn a provider's custom-domain, TLS and CI story. More setup, but
  it doubles as evaluation. (A separate static app on the current host was considered and
  set aside as heavier than either.) The build step is identical either way; only
  publishing differs. The `docs` subdomain is already reserved, and hosting it externally
  means DNS never reaches the application, so there is no routing collision.

## The live instance

schematalog.com becomes a **public demo** carrying a small set of sample data. With
authentication gone it is world-writable by definition; that is acceptable at current
traffic. If it is ever abused or simply fills up, the answer is a scheduled reset
rather than reintroducing accounts.

The previously-planned move to `schematalog.dev` is dropped along with the marketing
site it was waiting on.

## Open questions

- **Authentication, later, and pluggable.** Something to let an operator make an
  instance non-public if they want that. The leaning (2026-08-22) is *not* to pick one
  mechanism but to expose a seam and let whoever runs the instance choose - bearer
  token, OAuth, SSO, whatever their organisation already uses. That fits an
  internally-installed product far better than a built-in scheme, since the answer is
  usually "whatever we already log into everything else with", and it is the same shape
  as the storage extension point: a seam, a small default set, and someone else's
  package for the rest. Worth building both seams with one mechanism rather than two.
  Still explicitly not now, and still not user accounts owned by this application - the
  previous attempt cost a great deal for very little.
- **Drafts, visibility and authentication are one cluster.** A draft is only *unlisted*
  while there is nobody to hide it from, so "created but not yet visible" is a weaker
  promise than it sounds (see the drafts item under Parked/future). If genuine privacy
  is ever wanted, these three want deciding together rather than in sequence: what a
  draft promises depends on whether anything authenticates, and visibility is the flag
  that would express it.
- **How a catalog's membership is addressed.** Schemas keep their own short path, so
  what needs settling is the shape of the catalog side: listing members, and adding or
  removing one. Worth a moment's thought before it is a public contract.
- ~~**What 2.0 means now.**~~ Answered: it is **1.0**, not 2.0. "2.0" was vocabulary
  from before the restart, when the application was at 1.7 and the next era would have
  been 2.0; after restarting at 0.1.0 it pointed at nothing, since the phase scheme runs
  0.1 through 0.5 and has no route to a 2. The milestone itself is unchanged - the API
  is stable and the project starts making promises - and it now coincides with what
  leaving ZeroVer already means. Half of its old definition, the repositories being
  public, has happened.

## Parked / future

- **Drafts, and with them a real creation timestamp.** A version that exists in the
  registry but is not yet published: unlisted, not resolvable, and - uniquely - still
  editable. The strongest argument is not workflow convenience but that this is the only
  legitimate place for editing a schema document to exist, which gives the immutability
  invariant a pressure-release valve without weakening it. Coordinated releases
  ("version 2 of these five schemas, together") and simply wanting review before
  consumers can `$ref` something are the everyday cases. It brings back a genuine
  `created_on` alongside `published_on`, the two having been the same instant only
  because nothing allowed them to differ. Deliberately additive: the ordering decision
  already names its field for publication, so this lands as a status field and a filter
  on the read paths without reopening anything. Two things to settle when it does -
  that with no authentication a draft is *unlisted* rather than private, which is a
  weaker promise than the word suggests (though exactly how `deprecated` already
  behaves); and that it is new product surface, so it waits until the teardown is done.
- Notifications and integrations - webhooks or events when a schema one depends on is
  published, deprecated or superseded, and integration with source control and CI
  systems. Those are the paths by which schemas actually reach production in most
  organisations, and a registry nothing notifies is a registry people forget to consult.
- Validation as a service - sending data and asking whether it matches a stored schema.
  The product's own description says schemas are served back "for validation", but that
  validation is something the consumer does after fetching. Offering it directly is a
  different product surface, and possibly a better fit for the SDK than the API.
- Bulk export, the counterpart of the import path above. Less urgent, but "can I get my
  schemas back out" is a fair question to be able to answer for a self-hosted product.
- **Elasticsearch or OpenSearch as a backend.** The obvious next out-of-tree backend
  once search exists, and the strongest test the extension point has had: it would be
  the first store that can push a query down *richly* rather than merely efficiently,
  which is exactly the case the "a backend may override when it can answer better" seam
  was built for. Two things to settle before it is more than an idea. **Near-real-time
  indexing**: a get by document id is immediate, but anything search-backed - which for
  this backend would include `list_names` and `list_versions` - lags by the refresh
  interval, so publishing and immediately listing may not see the new version. The
  conformance suite does exactly that, so it would fail, which is the suite doing its
  job rather than an obstacle. And **whether a search index is an acceptable system of
  record** for a registry whose whole promise is that a `$id` resolves forever; the
  honest answer may be that it belongs as a secondary index beside a durable store
  rather than as primary storage, which is a different shape from the seam we have.

- **A git repository as a storage backend**, distinct from pointing the filesystem
  backend at a working tree: here Schematalog authors the commits and tags itself, so the
  repository *is* the store rather than a directory that happens to be versioned. The fit
  is unusually good - a published version is immutable and so is a git object, a version
  string is a tag, and history, attribution and audit come free from something already
  built. Needs design first, and the questions are real: who authors a commit when there
  are no users, what a tag collision means against the immutability promise, whether reads
  go through the working tree or the object database, what happens when someone pushes to
  the repository behind the registry's back, and whether remotes are involved at all.
  Raised 2026-08-22.
- An MCP server as a further driving adapter, letting AI agents query and publish
  schemas.
- Compatibility checking between versions - comparing a new version against its
  predecessor to classify the change as compatible or breaking. Previously tied to the
  versioning-scheme question; still the largest functional gap against comparable
  registries. `jsonsubschema` remains the candidate mechanism.
- A visual schema builder as an alternative to hand-writing JSON, so the first step
  into the product is less steep. JSONJoy Builder was the candidate; licence and
  embedding approach unchecked.
- Moving off Fly.io to a European provider. Not committed, but **Northflank is the
  leading candidate**. The bar is keeping what makes Fly pleasant: deploy from a
  container image, provision only what is needed, stay stable; a free tier is a bonus
  rather than a requirement. Candidates as researched on **2026-06-19**, in rough order
  of fit - worth re-checking before acting, since free tiers and ownership move:
  - **Northflank** (UK) - *leading candidate*, best all-rounder. Any Docker/OCI image, an
    always-on free sandbox (2 services, 2 databases, 2 scheduled jobs), usage-based
    pricing above it, and managed Postgres - so it could replace both Fly *and* the
    current database host in one vendor.
  - **Koyeb** (FR) - the closest philosophical twin to Fly: serverless containers, edge
    presence, scale-to-zero, a free instance. Mistral-owned since February 2026. Caveat:
    scale-to-zero is forced on the free tier, so cold starts.
  - **Clever Cloud** (FR) - mature (operating since 2010), sovereignty-focused, Docker
    plus managed Postgres. No real free tier, but very stable.
  - **Sliplane** (DE) - flat per-server pricing (around EUR 9/month), unlimited
    containers, push-to-deploy. No free tier, and no usage surprises either.
  - **Scaleway** (FR) - a larger AWS-shaped cloud (serverless containers, managed
    Postgres, object storage). Heavier than Fly's ergonomics.

  Two notes that outlast the specific candidates. The **database is the deeper lever**:
  the current host is US-incorporated, so pairing the compute move with a European
  Postgres is what actually makes it an end-to-end story. And the **compute swap itself
  is cheap** - the application is an image plus environment variables plus a release
  command - which is why this can stay parked without the cost growing.

  **The reset lowered the stakes here considerably** (noted 2026-08-15). The hosted
  instance is now a demo carrying sample data, so there is no customer data to migrate,
  no uptime obligation, and a reset is acceptable by design - this went from a production
  migration to moving a toy. Two consequences: the sovereignty argument largely dissolves
  along with the customer data, leaving preference and principle as the reason, which is
  a fine reason but a different one; and Northflank's strongest specific advantage
  (replacing the database host too) may not be needed at all, since a storage backend
  with no database would collapse the requirement to "run one container".
- OpenTelemetry instrumentation, for log retention and richer per-request context. The
  structured JSON logs already feed it cleanly.
- A release-tracking wrapper that deploys and tags the commit with its deployed version.

## What was abandoned, and why

For anyone reading the git history and wondering what happened.

Between May and August 2026 the project built, shipped and deployed a full multi-tenant
SaaS foundation: per-tenant API tokens, public/private schema visibility with
enforcement, a hosted identity provider for human login, self-service signup with
server-side organisation provisioning, tenant-per-subdomain routing, workspace
onboarding flows, and a page-by-page UI rebuild to support them.

It worked. It was also a great deal of machinery in service of a commercial product
that did not exist - there was no billing, no metering, no administrative surface, and
no users - and it made the thing meaningfully harder to install, to reason about, and
to contribute to. The reset trades all of it for a registry that anyone can run
internally in a few minutes, and puts the remaining effort into the API, the SDK, and
the capabilities the catalog never had: finding things, and grouping them.
