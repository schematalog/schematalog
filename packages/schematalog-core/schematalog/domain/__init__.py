"""The domain: what a schema is, and the contract a storage backend implements.

`__version__` is this distribution's own. It is deliberately separate from the
application's: the contract a backend codes against changes on its own schedule, and a
backend pinning it should not be dragged along by a UI release.
"""

__version__ = "0.1.1"
