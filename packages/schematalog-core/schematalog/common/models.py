from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base class for immutable, frozen Pydantic models.

    Layer-neutral implementation base. Domain layers wrap this with semantic
    aliases (e.g. `ValueObject` in `domain/schema.py`); presentation DTOs can
    inherit directly. Mirrors gapmap's `common.models.FrozenModel`.
    """

    model_config = ConfigDict(frozen=True)
