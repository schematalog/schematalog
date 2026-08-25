# Decisions

Product and architectural decisions, with the reasoning and the options that were
rejected. Newest first.

This file exists because the rejected option is the part that gets lost. Someone
meeting this codebase for the first time - including us, in a year - will look at the
absent authentication, the flat schema namespace, or the free-form version strings and
reasonably assume an oversight. An entry here answers that before it is asked.

How this differs from its neighbours:

- **`CLAUDE.md`** describes how the codebase works *now* - conventions, architecture,
  rules to follow while writing code.
- **`ROADMAP.md`** describes what is next, and what is still open.
- **This file** describes what was chosen, when, and what was turned down. Entries are
  not revised when the world changes; a reversal gets a new entry that supersedes the
  old one, so the trail stays readable.

Not every choice needs an entry. A decision belongs here when a reasonable person might
later propose the opposite, and the reasons are not obvious from the code.

**Everything here is a recommendation until it is implemented.** These entries record
what was chosen and why at the time of choosing; they are not commitments. Any of them
may be reversed if it proves inadequate in contact with the code - by a new entry that
supersedes the old one, so the reasoning stays legible either way.

---

## 2026-08-25: The CLI becomes an extension point; where it lives stays open

**Open, with a leaning.** `schematalog` is today a two-command argparse CLI (`serve`,
`info`) shipped by `schematalog-app` as a console script. The expectation is that it
grows into the entry point for the other tools too - the SDK first - which turns it from
an application detail into an extension point. The leaning is that the dispatcher ends up
in `schematalog-core`. Nothing is decided here, and nothing needs to be until there is a
second consumer.

**First, a correction to the obvious framing.** "Move it to the root `schematalog`
package" describes something that does not exist: the meta-package ships no modules at
all (`bypass-selection = true` - the wheel is metadata and one dependency), and the
namespace level deliberately has no `__init__.py`. The candidates are core, a new
distribution, or giving the meta-package a body.

**The constraint that decides the shape** is not layout, it is the command name. More
than one distribution may declare `[project.scripts] schematalog = ...`, and whichever
installs last silently overwrites the shim. So the name needs exactly one owner, and
everything else registers into it.

**The mechanism is already in the house.** A `schematalog.commands` entry-point group,
name to subcommand, is the direct analogue of `schematalog.storage`. Both of that seam's
safety rules carry over unchanged: a plugin may not shadow a built-in command, and a
plugin that fails to load is logged and skipped, so one broken package cannot stop
`serve` from working. The underscore trap does *not* carry over - that was RFC 3986 on
URL schemes, and a command name is under no such restriction.

**The three homes, and the objection to each:**

- **`schematalog-core`.** The dispatcher is argparse, so stdlib, so it costs core's
  deliberately small footprint nothing. The objection: a backend author who installs only
  core to implement five methods gets a `schematalog` command with nothing in it. That is
  answerable - with no commands registered it can say so, which is honest rather than
  broken - and it is the reason for the leaning rather than a decision.
- **The meta-package.** Giving it a body changes what it is, and anyone installing
  `schematalog-app` alone would *lose* the command. A regression on today.
- **A new `schematalog-cli`.** Cleanest ownership, and a whole distribution whose entire
  content is an argparse loop.

Under any of them the application keeps `serve`: it owns the uvicorn dependency, and that
must not leak downward into core.

**Why not now.** There is exactly one consumer. A seam designed against a single example
is precisely the mistake the implementer's guide exists to document - every seam built so
far has had something wrong with it that only appeared on contact. Waiting until the SDK
is real means one move informed by two consumers instead of two moves. The move is also a
public-surface change twice over: `schematalog.app.cli:main` is a declared console-script
target, and the command name changes owning distribution.

**Two questions to settle at the move, not before:**

- **Lazy dispatch.** If the parser is built by importing every registered command, then
  `schematalog info` pays the SDK's import cost and the application's uvicorn import.
  Register a loader per command and import only the one invoked. Cheap to design in,
  expensive to retrofit once third parties have registered against it.
- **What `--version` reports.** It is the application's today, whose minor tracks the
  roadmap phase. With several distributions in play a single number misleads; the natural
  answer is what `info` already does and reports each installed component. So the move is
  an `info` change too.

**Free thing that preserves the option**: shape the storage connectivity check as a
subcommand rather than more flags piled onto `info`, so the eventual split is mechanical.

---

## 2026-08-23: Tags name the distribution; the meta-package has no tag of its own

**Decided.** A release tag is `<distribution-name>/v<version>` -
`schematalog-core/v0.1.0`, `schematalog-app/v0.1.0`, `schematalog-s3/v0.1.0` - with a
GitHub release per tag. The application's release is marked *Latest*, because that is
what the repository sidebar links to and the registry is what a visitor arrived for.

**Why the full distribution name** rather than a short `core/` or `app/`. The tag then
matches the PyPI name exactly, so nothing has to be mentally mapped and a check can
compare the tag against that package's `name` and version constant mechanically. A short
prefix reads better and invents a second vocabulary for the same three things.

**Consequences worth knowing**, all of them mild and all of them permanent:

- `git describe --tags` becomes meaningless across mixed prefixes; it needs
  `--match 'schematalog-app/v*'`. Relevant if `buildinfo.py` ever grows a `git describe`.
- Auto-generated release notes compare against whatever tag GitHub considers previous,
  which across interleaved prefixes is usually another package's. `--notes-start-tag`
  fixes it, and has to be passed every time.
- The releases page interleaves all packages in one chronological list. Nobody has solved
  that well; at three packages it does not matter.

The upside is what makes it worth the cost: a publishing workflow can key on
`tags: ['schematalog-app/v*']` and release exactly one package, which is the whole point
of versioning them independently.

**Resolves** the "still open: how to tag" note left by the 2026-08-22 versioning entry.

---

## 2026-08-23: The meta-package's version always equals the application's

**Decided.** `schematalog` - the meta-package that ships no modules - carries the same
version as `schematalog-app`, always, and is republished on every application release
even when nothing about it has changed. It gets no tag and no release of its own; the
application's covers both. Its dependency on `schematalog-app` stays **unpinned**.

**Why lockstep.** The alternative was to let it version on its own changes, which are
rare - its metadata and nothing else. That is defensible until the numbers separate, and
then `schematalog 0.1.0` installs `schematalog-app 0.4.0` and the number on the front
door means nothing. A version is only worth printing if a reader can act on it. The cost
is republishing an unchanged three-file package occasionally, which is nothing.

**Why the dependency stays unpinned**, even though lockstep invites `==` and the
no-upper-bound rule explicitly exempts packages released in step by one maintainer. The
failure modes are not symmetric. Pinned, forgetting to republish the meta means everyone
typing `pip install schematalog` silently receives the previous application release - a
stale install, no error, nothing to notice. Unpinned, the same slip leaves the meta's
number a release behind while users still get the current application: visible to us,
harmless to them. The pin buys a stricter promise about a number and pays for it in the
one currency that matters.

**Why the equality check is a publish gate, not part of `just check`.** Both numbers only
ever change at release time, so a gate fires exactly when drift can occur and cannot be
skipped the way a local run can. Running it on every check would mostly re-compare two
numbers nobody had touched. It lands with the publishing workflow; until that exists,
this entry is the only thing holding the rule.

**Rejected: deriving the meta's version from the application's file** via
`[tool.hatch.version]`. The path climbs out of the meta-package's own directory, so it
resolves inside the workspace and breaks when the sdist is built in isolation - passing
locally and failing in CI is the worst available outcome.

---

## 2026-08-22: Versions restart at 0.1.0, and the app's minor tracks the phase

**Decided.** Every package starts at **0.1.0** and versions independently. For
`schematalog-app` - the one a user sees - the **minor version tracks the roadmap phase**:
`0.1.x` is the phase-1 teardown, `0.2.x` will be phase 2, and so on. `schematalog-core`
and `schematalog-s3` move on their own changes instead, because the contract and a
backend have no reason to march in step with a UI release.

**Why restart at all.** The application was at `1.7`, and that number belonged to the
single all-in-one distribution built for a hosted service. Carrying it forward would
assert a continuity these packages do not have: the thing that was 1.7 had
authentication, tenancy, subdomain routing and a different storage story, and almost none
of its code survives unchanged. Starting again says plainly that this is a different
product, and it costs nothing while there are no users.

**Why the minor tracks the phase.** A version is only worth reading if it means
something. Tying it to the roadmap makes "0.2.3" answer the question people actually have
- how far along is this - rather than counting releases. It also gives the 1.0 question an
answer shaped by the work rather than by ceremony: 1.0 is when the phases that define the
product are done, not when someone feels ready.

**Supersedes** the two-part scheme recorded in `CLAUDE.md` (major = product era, minor =
feature increment), which described one distribution and has no meaning across three.

**Still open: how to tag.** `v<version>` was unambiguous for a single distribution and is
not for three that share a repository and now all read `0.1.0`. Something like
`app/v0.2.0` is the obvious shape, but nothing is decided, and it needs deciding before
anything is released rather than after.

## 2026-08-22: Packaging comes before phase 2

**Decided.** Making the packages genuinely installable - published, claimable, runnable
from a `pip install` - is finished *before* phase 2's features begin, rather than being
left to phase 5 with the rest of the open-source work.

**Why.** Three packages that cannot be installed are three directories. Everything the
split was for - a backend author depending on the contract alone, an operator installing
the registry, the S3 backend proving the seam - is asserted rather than true until a
wheel exists and someone can install it. The longer that stays theoretical, the more of
phase 2 gets built on assumptions nobody has tested.

The container build already showed what that costs: `aiosqlite` was missing from the
application's dependencies even though SQLite is the default backend, so a real install
failed on its first query, and every check passed because the development environment
happened to carry the driver. That is precisely the class of error only a real install
finds, and there will be more.

**What it includes.** A console entry point, so `pip install` is followed by a command
rather than a `uvicorn` invocation. Wheels that carry what they need, including the built
frontend assets. The `schematalog` name claimed on PyPI before the repository is public,
since the import namespace is `schematalog` and an unclaimed distribution name is a hole
rather than an untidiness. And a tagging scheme, per the entry above.

## 2026-08-22: Where the API stops and the SDK starts

**Decided.** The API is for **cataloguing**: publishing a version, fetching one, listing
what exists, and changing the metadata the registry owns. Anything that can be built by
calling those and looping belongs to the **SDK** instead. A soft rule - a good enough
reason overrides it - but the default runs that way.

**The refinement that makes it usable.** Taken literally the rule proves too much, because
*everything* is expressible as a loop if the client will download the whole catalog first:
search becomes "fetch every schema and filter locally". So the test is not whether a loop
can express it, but what the loop costs. The workable form:

> **The API owns what needs the store. The SDK owns what needs only the API.**

If a client can do it in calls proportional to what it asked for, it is SDK work. If doing
it client-side would mean fetching the whole registry - because the answer depends on an
index, or on data the client has no reason to hold - it is API work.

**Why draw the line here at all.** Two reasons, and the second matters more. The obvious
one is that a small API is easier to keep complete, stable and worth depending on. The
better one is that the things which loop are exactly the things that fail halfway: an
import of two hundred schemas, a catalog being emptied, a lineage walk across registries.
Retrying, resuming, reporting what happened and deciding what to skip are all *client*
concerns with client-side state, and putting them in the registry means a stateful,
partially-failing operation inside an otherwise simple resource API.

**What this settles, applying it:**

- **SDK**: import in all its forms, emptying a catalog, walking successor and predecessor
  chains, cycle detection over a lineage, generating classes from stored schemas.
- **API**: search (it needs an index no client should rebuild), catalogs (stored state a
  client loop cannot persist), publication ordering and the *latest* rule (facts only the
  registry can know).
- **Reference resolution, split by the same test** - previously left open. Parsing the
  `$ref`s of one document and **bundling** it are proportional to that document, so they
  are SDK-shaped. The **reverse dependency graph** ("what depends on this?") is not:
  answering it client-side means reading every schema in the registry, so it needs the
  store and belongs to the API.

**The exception clause is real, not politeness.** A loop that is technically proportional
can still be wrong to push onto every client - if it would be identical in every SDK, in
every language, and easy to get subtly wrong, that is a reason to do it once in the API.
Nothing has met that bar yet.

## 2026-08-22: The storage contract - five methods, one URL, an inherited suite

**Decided.** The four open questions inside the storage plan, settled before anything is
built against the seam (it is a public interface, so its shape has to be right first).

**A backend implements five methods.** `add`, `get`, `set_metadata`, `list_versions(name)`
and a new `list_names()` - every schema name in ascending order. Three more come from a
base class and may be overridden where a backend can do better:

- `get_latest(name)` - the first `is_current` version in `list_versions`, else the first.
- `list_latest()` - `list_names()`, then `get_latest` for each.
- `list_predecessors(url)` - a scan, filtered by the successor predicate.

**Why derive those three.** They are the ones an outside author gets subtly wrong. Two of
them encode the "latest" rule - newest current, falling back to newest outright - which is
policy rather than storage, and duplicating policy across every backend is how backends
come to disagree. Inheriting it means a new backend is correct about `latest` before its
author has read what `latest` means. The SQL backend overrides all three, because it has
real queries for them; that is the point of the override, not an exception to it.

**Why `list_names()` is worth adding.** It is the enumerate primitive the derivations need
and the protocol lacked: `iterdir` on a filesystem, a delimited prefix listing on an object
store, dictionary keys in memory. Cheap everywhere, and it turns "list everything" from a
thing each backend invents into a thing each backend answers.

**Rejected: keeping all seven required**, with the conformance suite catching divergence
rather than inheritance preventing it. A suite finds a wrong answer after it is written;
a base class means the wrong answer cannot be written. Rejected too: **deriving
`set_metadata`** from get-plus-overwrite, which would leave four - a real backend wants
that write to be atomic, and forcing a read-modify-write on it to save one method is a bad
trade.

**`_reset` leaves the contract.** It exists only so tests can empty a repository, yet sits
in the protocol every plugin author must satisfy - a method the running application never
calls. The conformance suite instead asks for a *fixture* that yields a clean repository;
truncating, dropping or handing back a fresh temporary directory are all the author's
business.

**Configuration is the URL and nothing else.** Options travel as query parameters
(`postgresql://host/db?pool_recycle=1800`), and each backend validates its own with its own
model. This **simplifies the earlier decision**, which kept the nested `SCHEMATALOG_STORAGE__*`
models as an advanced form beside the URL: two spellings for one setting is a worse
interface than either alone, and it would oblige every plugin author to support both.

**The conformance suite ships as an importable base class**, which an author subclasses,
supplying one fixture. No pytest-plugin machinery, it works with plain pytest, and
inheritance makes it obvious which tests apply. The alternative - a plugin exposing
fixtures - buys indirection and a packaging dependency for no gain at this size.

## 2026-08-22: The filesystem backend is supported, not merely exemplary

**Decided.** The filesystem backend is a first-class supported option, not a worked example
that happens to run. The supported set is therefore **SQLite** (the default, no external
service), **PostgreSQL** (when it needs to scale), and the **filesystem** - three
deployments over two implementations.

**Why.** For a *schema* registry, "my schemas are plain files in a directory I can read,
grep, diff and commit" is a genuine product feature rather than a consolation. It fits a
real deployment - a single machine serving a modest catalog - and it is the only backend
that can sit inside a git working tree, which makes the repository the history and the
registry the server over it. No other option offers that, and a database cannot.

**Supersedes** the demotion in "SQLite by default, Postgres to scale, everything else a
plugin" (2026-08-22, earlier the same day), which kept the filesystem backend only as the
example a plugin author copies. It remains the best example - it is the only backend
readable in one sitting - but that is now a side benefit rather than its reason to exist.

**What being supported obliges.** It has to be *correct*, not merely illustrative: the same
conformance suite, the same ordering guarantees, and an honest statement of its limits. Two
in particular need documenting rather than discovering - it assumes a single writer (there
is no locking, so two processes writing concurrently is not a supported configuration), and
it holds the whole of a schema's version history as files under one directory, which is
fine for a modest catalog and not for a large one.

**Open: what "git-backed" actually means.** The simple version is that an operator points
the backend at a git working tree and commits when they choose, by hand or on a timer -
that needs nothing from us but documentation. Committing on publish, pulling before reads,
or treating the repository as the source of truth are all larger features with their own
questions (who authors the commit, what happens on conflict, which side wins), and none of
them is being committed to here.

## 2026-08-22: The interim UI keeps calling the services directly; a BFF comes later

**Decided.** The server-rendered UI continues to call the application services in
process, and the API is designed **without reference to it**. When the UI is replaced,
the replacement talks to a separate backend-for-frontend - a second, frontend-shaped API
that is itself a consumer of the pure one - rather than to the pure API directly.

A backend-for-frontend is an API written for exactly one client: it aggregates, reshapes
and trims the underlying API's responses into what one particular interface needs, and is
free to change whenever that interface does.

**Why not have the UI consume the pure API** (the option this supersedes). It sounds like
the principled choice, and it is how the API-is-the-product principle was originally going
to be enforced. But it makes one contract serve two masters with different shapes. A
resource API answers "give me this schema"; a page wants "give me everything this screen
renders", and the pressure to merge those lands on the public contract - the thing that
actually *is* the product. Worse, it shapes that contract around a surface explicitly
described as provisional and destined for replacement. Designing the product's contract
around the demo is backwards.

**Why a BFF rather than direct consumption, later.** It keeps the enforcement without the
distortion. A BFF is a real HTTP consumer of the pure API, so the API must still be
complete enough to build a whole interface on - the property that mattered. What changes
is where the reshaping happens: in a layer that exists to be reshaped, and that can churn
with the frontend without touching a contract other people depend on.

**Why option 1 in the meantime.** The interim UI is being thrown away. Routing it over
HTTP now buys enforcement for a surface that is leaving, and the coupling it would remove
is coupling that leaves with it. The work belongs to the replacement, not to the thing
being replaced.

**Accepted cost, and it is a real one.** Until the BFF exists, the API-is-the-product
principle has *no* enforcement mechanism at all - nothing proves the API can do what the
UI does, and the UI can quietly grow a capability the API lacks. Two things stand in for
enforcement until then:

- **A rule, stated because nothing checks it:** the UI may not gain a capability the API
  cannot express. If a page needs something the API cannot do, the API gains it first.
- **A cheap check worth adding when the API settles:** a test asserting that every public
  application-service use case is reachable through an API route. That encodes the
  principle directly rather than inferring it from a consumer, and it survives the UI
  being replaced.

**Supersedes** the closing clause of "The API is the product" (2026-08-15), which said
routing the UI through the API was part of the interim-UI work. The principle it states
is unchanged; only the mechanism for enforcing it moves.

## 2026-08-22: Alembic goes now, and returns when something needs migrating

**Decided.** The migration tool is removed in phase 1 rather than carried through the
teardown, and reintroduced only when a schema change has to preserve data that matters.
This settles the timing question left open by the database-reset entry below; it does not
disturb the storage entry's conclusion that Alembic is the right tool for the two
supported backends when it does return.

**Why now rather than at the end.** The database is being rebuilt from a fresh baseline
anyway, so there is no history to preserve. Through the teardown the shape changes
constantly - tenant and token tables go, visibility goes, `publication_id` arrives - and
every one of those changes is a rebuild rather than an alteration, which `create_all`
already handles. Keeping the tool means authoring revisions for a shape deliberately in
flux, over a database with no data and no users. That is ceremony, and it is ceremony that
has to be re-done the moment the shape settles differently than expected.

**When it returns.** At the first change that must preserve real data - in practice, before
the first release anyone could upgrade across. The cost of return is a single baseline
revision generated from the settled metadata; the async `env.py` and the custom column
types stay recoverable from git, so nothing is being thrown away that would have to be
rewritten from scratch.

**Accepted cost.** `auto_create_tables` stops being a development convenience and becomes
the only mechanism, so it defaults on everywhere including the hosted instance. Since
`create_all` cannot `ALTER`, any table-altering change before Alembic returns means
recreating the database. That is already the local workflow, and the hosted instance is a
demo carrying sample data that is reset by design, so the cost lands where it does no
damage. It would be an unacceptable cost for an instance holding data someone cares about,
which is precisely the condition that brings the tool back.

**Incidental benefit.** The removal takes with it a deploy-time dependency, the release
command, two Dockerfile copies, the migration-only second database in the compose stack,
the integration test that exercises the revisions, and the three separate tool exclusions
(`ruff`, `pyrefly`, `deptry`) that exist solely because autogenerated migration code should
not be linted as if it were ours.

## 2026-08-22: Versions stay free-form; the registry orders by publication

**Decided.** The version string keeps its current shape - the same permissive pattern as
a name, an alphanumeric followed by alphanumerics, dashes, dots and underscores - and the
registry never interprets it. Ordering is not derived from the string at all. Instead
every version carries an immutable **`publication_id`** - a UUIDv7, minted when the
version is published - and *that* is the order: `get_latest`, `list_latest` and
`list_versions` all derive from it. Lexicographic version comparison leaves the system
entirely.

**Two names, one stored.** `publication_id` is the stored field, and it is an
*identifier* - deliberately not named for time, because it is not a timestamp. It merely
encodes one. `published_on` is a genuine ISO-8601 timestamp derived from it and served on
the wire; nothing stores it. Keeping the distinction in the names is the point: a field
called `published_at` holding a UUID would mislead every reader of the schema, the
database and the API in the same way.

**Why free-form.** Semantic versioning describes *code* compatibility, where the producer
knows who breaks. Schema compatibility is directional: adding a required field breaks
writers and is harmless to readers, making a field optional is the reverse. One number
cannot carry that, so a scheme imposed by the registry would be imposing the wrong thing.
SnowPlow's SchemaVer (`MODEL-REVISION-ADDITION`) is a genuine improvement because it is
explicitly about a *data* contract rather than a code one, but it still presumes a single
scheme for everybody. Whoever owns the schema owns its versioning.

**The consequence that forces the rest.** A registry that refuses to interpret the version
string cannot order by it. The only orderings available are ones the registry itself
creates - so the ordering must be a registry fact, and the honest registry fact is
publication order.

**The defect this fixes.** Two orderings already existed and disagreed. `list_versions`
ordered by `created_on` descending in all three backends, while `get_latest` and
`list_latest` took the lexicographic maximum of the version string. Publish `1.0` and
then `0.9`, and the version list shows `0.9` first while `get_latest` returns `1.0`.
The lexicographic half is also the reason `10.0` sorted before `9.0`, and the reason
`IdentifierColumn` had to pin `COLLATE "C"` on Postgres so that "latest" would not
resolve differently depending on where the instance was deployed.

**Why UUIDv7 specifically.** It is in the 3.14 standard library (`uuid.uuid7()`). Its
48-bit millisecond timestamp occupies the high bits, so the value sorts lexicographically
in creation order on any backend that can compare strings - including one whose only
index is an object-key prefix. CPython documents monotonicity within a millisecond, and
200,000 generated values spanning roughly 240 millisecond buckets came out strictly
increasing, so a bulk import or a seed run orders in true sequence rather than by
coin-flip. Above all it needs **no coordination**: it is generated in-process, with no
round trip and no contention.

**Rejected: a per-name integer sequence** (version 1, 2, 3 of this schema). More readable,
obviously total, and it makes "the fourth version" a thing one can say. It loses on
coordination - it needs a read-modify-write or a database sequence at publish time, which
is fine on Postgres and awkward-to-hostile on a backend with no transactions. Since
pluggable storage is now a goal, coordination-free wins.

**Rejected: making it the primary key.** Not for the obvious reason - `add` takes its
fail-on-conflict semantics from the composite primary key raising an integrity error, and
under a surrogate key a `UNIQUE(name, version)` constraint restores exactly that in one
line. The reasons that hold are different. First, it would introduce a second identity
into a design that rests on `(name, version)` being *the* identity: the canonical `$id` is
built from it, `SchemaIdentity` is a value object around it, and every lookup addresses by
it. Nothing in the domain would ever retrieve a schema by the surrogate, and a primary key
no caller addresses by is a storage detail wearing identity's clothes. Second, it would
wreck the layout of precisely the backends kept for their layout: the filesystem backend's
remaining justification is that schemas are plain files one can grep and commit, and an
object-store backend's natural key is the same `{name}/{version}` path. A UUID key turns
both into opaque blob stores needing a secondary index to answer "what versions exist".

So it is a unique, immutable, non-identifying field. It is nonetheless **exposed in the
API**, because a stable sortable opaque token is the right cursor for keyset pagination;
exposure does not require primacy. If something later genuinely needs to address a version
by opaque handle - an events table, an audit trail - promoting it is a small change.

**UUIDv7 is a contract, not an implementation detail.** `publication_id` must be a
version 7 UUID, and this has to be documented as a requirement rather than left as the
happenstance of how the reference implementation mints it. Three things depend on the
layout specifically, and all three fail quietly rather than loudly if some other version
is substituted:

- **Ordering.** The whole scheme rests on the value sorting in creation order. That is
  true of v7 because its high 48 bits are a big-endian millisecond timestamp; a v4 is
  uniformly random and would randomise the order of every listing while remaining a
  perfectly valid UUID.
- **The derived timestamp.** `published_on` is read straight out of those same high bits,
  so a non-v7 value yields a nonsense date rather than an error.
- **Storage form.** A backend must persist it so that its natural ordering is preserved -
  a native `uuid` column, fixed-width lowercase hex, or 16 big-endian bytes in an object
  key. Anything that reorders the bytes, or any variable-width text form, breaks ordering
  without breaking storage.

So the domain validates the version on the way in rather than accepting any UUID, the
repository conformance suite covers ordering across a boundary that spans more than one
millisecond, and the plugin author documentation states the requirement outright. The
generation itself stays trivial: `uuid.uuid7()` from the 3.14 standard library.

**One stored field, two facts served.** `published_on` is *derived* from
`publication_id` (`UUID.time`, or a shift of the high bits) rather than stored beside it.
That removes a column from every backend, and it makes drift between the two impossible by
construction rather than by diligence - a backend cannot store a timestamp that disagrees
with the identifier next to it, because there is no such timestamp to store. It is computed
on the domain entity rather than at the presentation boundary, so the API, the UI, the CLI
and the SDK all read the same value, and the repository contract carries one clause fewer.
The timestamp still appears on the wire - requiring a JSON consumer to bit-shift a UUID to
learn when something was published would violate the API-is-the-product principle. Since
there are no users, the existing `created_on` is renamed to `published_on` at the same
time, which is what it has always meant.

**Accepted cost: millisecond resolution.** UUIDv7 carries 48 bits of epoch milliseconds,
where the `created_on` column it replaces was microsecond-resolution on Postgres. Nothing
about a schema registry cares, but it is the one observable change on the wire and is
recorded here so it is stated rather than discovered.

**Time-range queries survive the missing column.** The obvious objection to storing no
timestamp is that "everything published since Tuesday" no longer has a column to filter on.
It does not need one: because time occupies the high bits, a range over `publication_id` is
a time range. Construct the boundary identifier from the timestamp and compare - an
ordinary indexed range scan, and one that works on any backend able to compare the stored
form, including an object store filtering on key prefixes. Written down because it is not
obvious, and because the alternative is someone reinstating the column to get it back.

**`deprecated` and `successor` filter, they do not order.** Both are optional and mutable,
so the graph they form is sparse - most versions will declare neither - and "latest" would
be undefined for nearly every schema if it depended on them. The successor reference is
also a URI that may point at a differently-named schema, and the acyclicity rule
deliberately lives in the SDK rather than the domain, so nothing guarantees it is even a
DAG. As filters on *what may be latest*, however, they are exactly right:

**Latest is the most recently published version that is neither deprecated nor
superseded**, falling back to the most recently published overall if that excludes
everything.

This answers the objection that publication order mishandles backports. Publish `1.0`,
then `2.0`, then backport `1.1`: naively the backport hijacks the head. The publisher sets
`1.1`'s successor to `2.0` and the head is `2.0` again - declarative, using fields that
already exist, and asking effort only of the person who created the ambiguity. Returning a
deprecated version as "latest" is separately just wrong: it answers "use this" for
something marked "do not use this".

**Minted above the repository.** `created_on` is currently stamped inside each
repository's `add`, so `datetime.now(tz=UTC)` appears three times in infrastructure for
what is a domain fact. The publication identifier must not inherit that placement: if each
backend mints its own, every third-party backend author must remember to do it correctly
or their backend silently orders wrong. It is minted once, above the repository, and the
repository stores what it is handed. One less clause in the conformance contract.

**Consequence for `COLLATE "C"`.** It stops being load-bearing for correctness - which
version is latest no longer depends on how the database collates strings. It remains
relevant to name-ordered listings being byte-identical across backends, so it is not
automatically removable.

**Deferred, with its vocabulary reserved: drafts, and a separate creation timestamp.**
Creation and publication are currently the same instant only because nothing allows them
to differ. Separating them is wanted later - see `ROADMAP.md` - and the strongest argument
is not workflow convenience but that a draft phase is the only legitimate place for editing
a schema document to exist, giving the immutability invariant a pressure-release valve
without weakening it. The reason to name the field for *publication* now, while the two
coincide, is that doing so makes drafts purely additive later: a status field and a filter,
with no stored value quietly changing meaning and no need to reopen this decision. Naming
it for creation would guarantee revisiting this conversation with data in the ground.

The same reservation disposes of the one case where a stored timestamp column would have
earned its keep - importing schemas from another registry with their original dates. If
the stored fact is *when this was published into this registry*, an imported schema's
original date is provenance, a different field that can be added when import exists.

## 2026-08-22: One storage URL, and a real extension point for other backends

**Decided.** Storage is selected and configured by a **single URL** whose scheme names
the backend, and backends beyond the in-tree set are supplied by third parties rather
than by us:

```
SCHEMATALOG_STORAGE_URL=sqlite:///./data/schematalog.db     # the default; set nothing
SCHEMATALOG_STORAGE_URL=postgresql://user:pw@host/db
SCHEMATALOG_STORAGE_URL=s3://bucket/prefix                  # a plugin, same variable
```

The scheme is simultaneously the configuration, the backend selector, and the plugin
registry key. The nested typed models survive as an advanced form for knobs that do not
fit a URL (`pool_recycle` and friends), but the zero-configuration path is one variable
with a working default, so `docker run schematalog` needs nothing set.

**Why.** Two questions ("which backend" and "how is it configured") collapse into one
answer, and it is the form every comparable application uses, so it needs no
explanation. It also replaces the closed discriminated union on `Settings.STORAGE`,
which is the actual barrier to third-party backends: no outside package can add a member
to `MemoryStorageConfig | FilesystemStorageConfig | SQLAlchemyStorageConfig` without
editing our source.

**Discovery** is by Python entry point (`[project.entry-points."schematalog.storage"]`),
with a dotted-path escape hatch (`mypkg.storage:build`) for people who would rather not
package anything. An operator's derived image is `FROM schematalog` plus an install; the
URL scheme then finds it.

**Accepted cost.** `StorageConfig` stops being a closed discriminated union - the scheme
is parsed first, then the remainder is handed to the plugin's own Pydantic model for
validation. That is a real loss of single-model settings parsing, and it is worth it.

**The part that actually makes third-party backends work** is not discovery. It is two
other things, both mostly built already:

- **A small required surface.** The repository contract currently demands seven public
  methods. `get_latest` and `list_predecessors` are the ones an outside author will get
  subtly wrong - the first encodes the version-ordering rule, the second is a scan with
  a stable sort. Require the irreducible core and ship a base class deriving the rest
  generically, which a backend may override where it can push the work down. A first
  working backend should be an afternoon.
- **A published conformance suite.** The unit tests already run one test function across
  three backends, which is most of a reusable suite; exporting it (`schematalog.testing`)
  turns "implement the protocol" from an inference off docstrings into an inherited
  specification. This is the cheapest high-value item in the whole plan.

**Blocked on the versioning decision, deliberately.** Version ordering is currently
"free-form strings, lexicographic", which is what forced `COLLATE "C"` on Postgres so it
would agree with SQLite and with Python's `str`. That is a subtle obligation to push onto
every plugin author and precisely how backends diverge in silence. If the domain instead
computes an explicit sort key at publish time, a backend only needs "order by this
field". **Settle versioning before freezing the storage contract**, not after.

**Historical note.** A single storage variable is close to what existed before the SaaS
pivot, in a bespoke format (`filesystem|/path/to/dir`, `s3|username|password|prefix`).
The idea was right; the encoding was not, and a URL is the standard spelling of it.

## 2026-08-22: SQLite by default, Postgres to scale, everything else a plugin

**Decided.** One implementation, two supported deployments: the existing SQLAlchemy
backend, defaulting to **SQLite** and moving to **Postgres** under load. Same code path,
same tests, same migrations, one variable apart. This costs no new code - it is a change
of defaults and documentation.

**Why.** The two requirements pull in opposite directions: a two-minute evaluation needs
no external service, and a credible production story needs a real database. One backend
implementation satisfying both is strictly better than two, and both are already written
and tested.

**Resolves a clustered question.** Alembic survives, owning exactly these two; plugin
backends own their own migration story, or have none.

**The wrinkle.** SQLite is a file, and quick-deploy platforms often provide ephemeral
disk, so a template that fails to mount a volume loses data on redeploy. Whichever
quick-deploy artefact ships must either declare the volume or default to Postgres where
the platform supplies one. That is a property of the template, not of the backend choice.

**Memory stays** - it is the test backend, and it makes a genuinely useful ephemeral
demo mode.

**Filesystem is demoted rather than deleted.** For a *schema* registry, "my schemas are
plain files in a directory I can grep and commit" is a real feature and the argument to
keep it first-class is not silly. But it is a second backend to keep conformant, and
SQLite is also just a file. So it stays in tree, stays in the conformance run, and is
documented as **the worked example a plugin author copies** - it is the only backend
simple enough to read in one sitting, which is what a reference implementation has to be.

**S3 is revived, but not recommended.** It needs credentials and an external service, so
it can never be the two-minute path. Its value is as the first backend built *through*
the plugin seam rather than inside it, proving the seam holds. The historical objection
is gone: conditional `PUT` (`If-None-Match`) now gives `add` its fail-on-conflict
semantics natively.

**Rejected: a wide in-tree backend set**, as existed before May 2026. Pluggable storage
is often cargo-culted, but it earns its place here for specific reasons - a registry's
data is small, read-mostly and rarely written, so an unusual range of substrates are
genuinely viable, and an internally-installed product meets people who already run
something they would rather not add to. What that argues for is a credible extension
point with a *tiny* in-tree set. Carrying every backend ourselves is what was correctly
thrown away.

## 2026-08-15: Catalogs are soft grouping, not a hard scope

**Decided.** A schema lives in a single flat namespace at `/schemas/{name}` and belongs
to nothing by default. A *catalog* is a separate, named thing that references schemas; a
schema may be referenced by any number of catalogs, or none. Asking for a catalog lists
its members. Membership is mutable metadata, in the same family as the deprecation flag
and the successor reference.

**Why.** The decisive argument is the canonical `$id` - the permalink stamped into every
served schema, which must resolve forever and mean the same thing forever. Under any
hard-scope model the grouping is part of the address (a subdomain, as it was until now,
or a path segment). That makes regrouping a schema an `$id` change, so the grouping
decision would be either permanent and unrevisable, or a broken promise. Under soft
grouping the address is `/schemas/{name}/versions/{version}` regardless of which
catalogs point at it, so grouping stays freely revisable precisely because it was never
part of identity.

It also disposes of a question that had no good answer: whether deleting a catalog
deletes the schemas inside it. It cannot, because it never held them.

**Rejected: catalogs as a hard scope** - the catalog forming part of a schema's identity,
as the tenant did. This was the initial recommendation, on the grounds that the scoping
machinery was already built and enforced by the database, so keeping it was nearly free.
That argument stands on cost but loses on correctness: it puts the `$id` promise at risk
to protect a namespace, and the namespace is the cheaper thing.

**Accepted cost.** Schema names are globally unique per instance, so one `customer` per
registry. This is normal for a single-organisation internal registry and matches how
unscoped npm and PyPI behave. `NAME_PATTERN` already admits dots, so `billing.customer`
works as a *convention* for anyone who wants it - deliberately a convention rather than a
mechanism, since it costs nothing and forces nobody.

**Related, decided at the same time:** catalog membership references a **schema**, not a
specific version. Version-level membership would turn a catalog into a pinned manifest
("these schemas, at exactly these versions"), which is interesting and possibly worth
having later, but it is not the founding behaviour. Whether individual schemas also need
labels or annotations of their own is left open.

**Open, not decided here:** whether "catalog" remains the name.

## 2026-08-15: The API is the product

**Decided.** The JSON API is the primary product surface. Every capability must be
expressible through it, and no other surface may hold powers the API lacks.

**Why.** It is the surface a registry is actually consumed through - by build pipelines,
by the planned SDK, by other services. Treating anything else as primary produces an API
that lags its own user interface, which is a poor foundation for both an SDK and an
independently-built frontend.

**Consequence worth naming:** this is not currently true. The server-rendered UI calls
the application services directly rather than going over HTTP, so it neither proves nor
depends on API completeness. Routing it through the API is part of the interim-UI work.

## 2026-08-15: No authentication

**Decided.** Authentication is removed entirely - the hosted identity provider, browser
login and sessions, API tokens, the principal model, and every authorization check. The
API is fully public. The target is an instance an organisation installs and runs
internally for itself.

**Why.** The authentication and tenancy work cost a great deal and returned very little.
It was built for a commercial product that did not exist: there was no billing, no usage
metering, no administrative surface, and no users. What it did produce was a system that
was materially harder to install, to reason about, and to contribute to - which is the
opposite of what an open-source internal registry needs.

**Rejected: keeping a reduced version** - for instance a single shared token - on the
grounds that some access control is better than none. Turned down for now because a
half-measure carries most of the conceptual weight for a fraction of the benefit, and
nobody has asked for it. Revisit only on a real request; if it returns it should be a
single bearer token, not user accounts.

**Supersedes** the multi-tenant SaaS direction pursued between May and August 2026.

## 2026-08-15: No tenancy as a security boundary

**Decided.** Tenant-per-subdomain routing is removed, along with the wildcard DNS and
certificate requirements it imposed. What remains of the concept becomes catalogs, per
the entry above.

**Why.** Isolation between customers only means something when there are customers to
isolate. The subdomain routing in particular was the single most awkward part of local
development - it required a wildcard DNS helper, a locally-trusted certificate authority,
and a real domain, because the identity provider refused plain HTTP and browsers refuse
cookies across the `.localhost` space.

## 2026-08-15: Schema visibility is removed

**Decided.** The public/private flag and its enforcement are removed. Everything in an
instance is readable, until further notice.

**Why.** It is access control, and with authentication gone there is nothing to control
access against.

**Reversal condition.** If basic API authentication ever returns, this is the natural
thing to reconsider alongside it - not before.

## 2026-08-15: Reset the database; drop the migrations

**Decided.** Rather than migrating the existing database forward, start from a fresh
baseline and discard the migration history.

**Why.** There is no data worth preserving and no users to disrupt. Six of the ten
existing revisions exist solely to add tenancy and authentication, so a chain of
drop-migrations would be pure ceremony over a clean slate.

**Open consequence.** Whether the migration tool is retained at all through the teardown,
or reintroduced once the shape settles, depends partly on which storage backends are
chosen - some of the candidates have no schema to migrate.

## 2026-08-15: Keep an interim server-rendered UI, with write capability

**Decided.** The existing server-rendered UI stays, on the frameworks it already uses,
shrunk to what survives the teardown, and keeping basic create/update/delete. It is a
demonstration of the API, not a product surface. The real frontend lands later as a
separate repository consuming the API directly.

**Why.** An API with no visible surface is hard to evaluate, and hard to attract
contributors to. Keeping write capability is deliberate: a demo that can only read is a
poor demo.

**Rejected: deleting the UI outright** in favour of going straight to the separate
frontend. The pages entangled with the teardown - login, callback, workspace onboarding,
tokens - are exactly the ones being removed anyway, so what survives is the valuable and
least-coupled part. Deleting it would discard working software to save maintenance that
mostly is not there.

**Consequence.** No product-grade design investment goes into this UI. Visual identity,
theming, and the component inventory belong to the separate frontend. Dark mode stays
inert rather than half-fixed.

## 2026-08-15: Everything becomes open source

**Decided.** All repositories become public under a permissive licence. This repository
already carries MIT, from 2022.

**Why.** It follows from the product being an internally-installed registry rather than a
hosted service: the thing being given away is the thing people want to run themselves,
and the SDK is broadly useful and secret-free.

**Still to confirm:** that MIT remains the right choice now that the server is opening
too, rather than only a client library, and that the same licence applies across all
repositories. The git history has been checked and carries no committed secrets.

## 2026-08-11: FastAPI stays; Litestar declined

**Decided.** Not to replace FastAPI with Litestar. Considered and sized rather than
started, and the sizing is the useful part.

**The size, as measured at the time.** Framework imports appeared on 15 lines across 8
files, all confined to the presentation layer and the composition root - the domain,
application, infrastructure and common layers were clean. The work would have been 37
route handlers, around 26 dependency-injection sites, 2 HTTP middlewares, 2 exception
handlers, 8 form parameters, the static mount, and the bearer-token scheme. Tests were
cheap: the 78 HTTP-level test functions swap application state rather than framework
dependency overrides, and Litestar offers both an equivalent state object and an
httpx-based test client. The identity provider's FastAPI binding was the only genuinely
coupled dependency, and its adapter module already isolated it behind three methods that
exist on the framework-agnostic base package. Roughly a week of evenings.

**Declined because nothing forced it.** The earlier move off pyapi-server answered a real
break; there was no equivalent here. Litestar's throughput advantage is irrelevant to an
application bound by network waiting rather than computation, its data-transfer-object
layer overlaps awkwardly with the deliberate three-layer object model, and its one
genuine win - layered dependency injection, without framework defaults polluting handler
signatures - did not justify a week that other work wanted more.

**Two costs beyond the time.** The generated OpenAPI document changes shape, and that
document is a public contract for a product whose whole premise is being fussy about
schemas. And it would have foreclosed evaluating FastAPI's built-in frontend serving.

**Revisit only** on a concrete wall in FastAPI, or something specifically wanted from
Litestar 3.0 (unreleased as of 2026-08-11). The cost should not grow while the layering
holds.

*Recorded here 2026-08-15; the decision itself predates this file and was recovered from
an earlier `ROADMAP.md`, where it had been filed under "parked/future" - the wrong home
for a decision.*
