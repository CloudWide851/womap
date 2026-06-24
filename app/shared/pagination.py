from pydantic import BaseModel, Field


class CursorPageMeta(BaseModel):
    limit: int
    next_cursor: str | None = None
    returned: int = 0
    truncated: bool = False
    warning: str | None = None


class BBoxQuery(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @classmethod
    def from_csv(cls, value: str) -> "BBoxQuery":
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must contain min_x,min_y,max_x,max_y")
        min_x, min_y, max_x, max_y = (float(part) for part in parts)
        if min_x >= max_x or min_y >= max_y:
            raise ValueError("bbox min values must be lower than max values")
        return cls(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)


class FeatureQueryMeta(CursorPageMeta):
    bbox: tuple[float, float, float, float] | None = None
    simplify: float | None = None
    cache_hit: bool = False
    strategy: str = Field(default="bbox-window")
