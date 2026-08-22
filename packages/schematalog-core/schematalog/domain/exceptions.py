class SchemaConflictError(Exception):
    """Signifies that the schema version being stored already exists."""

    def __init__(self, schema):
        super().__init__(f"Conflict: Schema `{schema.name} v{schema.version}` already exists.")


class UnknownSchemaError(Exception):
    """Signifies that the schema version being requested does not exist."""

    def __init__(self, schema_name, version=""):
        version = f" v{version}" if version else ""
        super().__init__(f"Unknown schema: `{schema_name}{version}`.")
