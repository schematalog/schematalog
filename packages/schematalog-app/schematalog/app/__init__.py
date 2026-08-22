"""The Schematalog registry application: API, web UI, services and storage wiring.

`__version__` is this distribution's own, and `pyproject.toml` sources it from here so
the number lives in one place. Versions restart at 0.1.0 for every package: the 1.x
series belonged to the single all-in-one application built for a hosted service, and
carrying it forward would imply a continuity these packages do not have.

There is deliberately no `schematalog/__init__.py` above this one: `schematalog` is a
PEP 420 namespace shared by several distributions (`schematalog-core`, this package,
`schematalog-s3`), and an `__init__.py` at that level would make one of them own the
namespace and shadow the others.
"""

__version__ = "0.1.0"
