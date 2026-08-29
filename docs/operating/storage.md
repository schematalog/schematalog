# Choosing a storage backend

Schematalog stores schemas in one of several backends, chosen by the scheme of
`SCHEMATALOG_STORAGE_URL` (see [Configuration](configuration.md) for the
syntax). This page is about *which* to choose.

**If you do not want to think about it, do not.** The default is SQLite in the working
directory, it needs no external service, and it is a perfectly good answer for a catalog
one team publishes to. You will know when it stops being enough, and moving is a matter
of changing one variable and republishing.

## What the data is actually like

The choice is wider than it would be for most applications, because the data is unusually
undemanding. A published version never changes. Documents are small - kilobytes. Reads
vastly outnumber writes, and writes are rare enough to be measured in "per week" for most
catalogs. Nothing needs a transaction spanning several rows.

So performance is rarely the reason to change backend. **The reasons that do come up are
operational**: how many instances run, whether the disk survives a restart, and what your
organisation already runs and would rather not add to.

## By deployment

### One machine, one process

**SQLite** (`sqlite:///./schematalog.db`) is the default and the right answer. One file,
no service to run, atomic writes, and a straightforward backup story: copy the file.

**The filesystem backend** (`file:///data/schemas`) is the alternative worth knowing
about. It stores each version as a JSON file under a directory named for the schema, so
the store is legible: you can `grep` it, `diff` two versions, read one in an editor, and
put the whole thing in version control. For a *schema* registry that is a real feature
rather than a curiosity - the data is text that people write and review.

Choose it over SQLite when you want the store inspectable or under git; choose SQLite
when you would rather not think about the files at all.

### A container platform, with ephemeral disk

This is where the default needs attention. SQLite is a file, and a platform that gives
each deployment a fresh filesystem will discard it. Two ways out:

- **Mount a volume** and point the URL at it (`sqlite:////data/schematalog.db` - note the
  four slashes for an absolute path). Cheapest, and keeps a single-container deployment.
- **Use PostgreSQL** (`postgresql://user:pw@host/db`) if the platform offers one. More
  moving parts, but nothing to remember about disks.

The same applies to the filesystem backend, which is equally a directory that can vanish.

### More than one instance

**PostgreSQL, necessarily.** SQLite and the filesystem backend both assume a single
writer: SQLite serialises writers with file locks, which works across processes on one
machine but not across machines, and is actively hazardous on network filesystems where
locking is unreliable. The filesystem backend does not lock at all.

If you are running two instances behind a load balancer, or a rolling deploy that briefly
runs two, PostgreSQL is the only supported answer.

### Backed by git

Point the filesystem backend at a git working tree and the repository becomes the history:
every version is a file, `git log` is an audit trail, and a push is an off-site backup.

What it does **not** do is commit for you. Schematalog writes files; committing is
yours - by hand, or on a timer. Pulling changes made elsewhere is likewise outside its
knowledge, and two writers are no safer here than anywhere else on this backend. A
tighter integration, where the registry authors commits and tags, is [on the
roadmap](https://github.com/berislavlopac/schematalog) but does not exist.

### Object storage

**S3** (`s3://bucket/prefix`) comes from a separate package, `schematalog-s3` - install
it and the scheme works. It suits an instance that should hold no disk of its own: object
storage survives the container, costs almost nothing at this volume, and is often already
part of the estate.

It is a reasonable choice for several instances too. A published version is written once
and never changed, and creation uses a conditional write, so two instances publishing the
same version cannot both win. What it is *not* is fast at listing: naming every schema
costs a request per thousand, and reading every version of one schema costs a request per
object. For a catalog of hundreds that is unnoticeable; for one of hundreds of thousands
it is the wrong shape.

Credentials come from the ordinary AWS chain, not the URL.

### Tests and throwaway demos

**`memory://`** keeps everything in the process and loses it on exit. Useful for tests and
for showing someone the interface; never for anything you would miss.

## At a glance

| Backend | External service | Survives a restart | More than one instance | Readable on disk |
| --- | --- | --- | --- | --- |
| `sqlite` | none | yes, if the file persists | no | no (one binary file) |
| `file` | none | yes, if the directory persists | no | yes (JSON per version) |
| `postgresql` | a database | yes | yes | no |
| `s3` | an object store | yes | yes | yes (JSON per object) |
| `memory` | none | no | no | no |

## When to build your own

Because the data is small, immutable and read-mostly, an unusual range of stores can hold
it - an object store, a document database, a key-value store, something in-house. It is
worth building one when:

- **You already run something suitable** and would rather not add a database to your
  estate for a service this small.
- **Policy decides where data lives** - a particular region, a particular system, a
  particular retention regime - and the store is how you satisfy it.
- **You want the registry inside something else**, such as an existing document pipeline.

It is *not* worth building one for performance. If SQLite is slow for your catalog,
something else is wrong.

A backend implements five methods; three more are derived for you, including the rule for
which version counts as "latest", so you inherit that rather than reimplementing it.
`schematalog.testing.SchemaRepositoryConformance` is the contract as a test suite - you
subclass it, supply one fixture, and it tells you whether your backend is correct.
Registration is an entry point, so nothing in this repository needs changing.

[Writing a storage backend](writing-a-backend.md) is the guide to doing it, including
the parts that turned out to be awkward. There are also three worked examples to read:
the filesystem backend inside the registry, which is small enough to take in at a
sitting; `schematalog-s3`, a real backend living entirely outside it - the same shape
yours would take; and a probe backend that implements the five methods and nothing else.
