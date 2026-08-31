"""Application-layer (service) errors.

Service-level outcomes that presentation maps to its transport (HTTP status, CLI
exit). The application services catch domain errors (repository/entity invariants)
and the common validation error, then re-raise these - so presentation depends only
on the application's contract, never on domain internals.
"""


class ApplicationError(Exception):
    """Base for service-level errors that presentation is expected to handle."""


class SchemaNotFoundError(ApplicationError):
    """The requested schema (name, or specific version) does not exist (-> 404)."""


class DuplicateSchemaError(ApplicationError):
    """A schema version with this identity already exists (-> 409)."""


class InvalidSchemaError(ApplicationError):
    """The submitted document conforms to no supported metaschema (-> 422)."""

    def __init__(self, message="Schema does not conform to any supported metaschema."):
        super().__init__(message)


class InvalidSearchQueryError(ApplicationError):
    """The search query holds something no schema could match (-> 422).

    Answering it with an empty result would look like "nothing found" for what is
    really "that cannot be searched for", leaving the caller to guess which.
    """


class InvalidSuccessorError(ApplicationError):
    """The requested successor reference is not acceptable (-> 422).

    An internal successor must point at a schema that exists, and a schema cannot
    supersede itself. External references are taken on faith (not existence-checked).
    """
