# Running an instance

This section is for whoever installs Schematalog and keeps it running - on a laptop,
a container platform, or a box in a cupboard. It assumes nothing about how the
schemas in it will be used.

Read it roughly in order:

- **[Configuration](configuration.md)** is the whole surface: a handful of
  environment variables, of which one - the storage URL - does most of the work.
- **[Choosing a storage backend](storage.md)** is the decision that actually matters,
  and the one worth making before you have data. It is written by deployment shape
  ("one machine, one process", "more than one instance") rather than by backend, so
  you can find yourself in it.
- **[Writing a storage backend](writing-a-backend.md)** is for when none of the
  built-in ones fit. It is a real extension point, not a hook: a backend is five
  methods and needs nothing from the application.

An instance has **no authentication**. Anyone who can reach it may read and publish,
so the network boundary is the only boundary - put it somewhere that reflects that.
