"""Validated public/partner observations, separate from demo catalog data."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CollectedItem:
    source: str
    reference: str
    name: str
    price: int
    url: str
    category_slug: str
    observed_at: datetime
    condition: str = "new"
    in_stock: bool = True
    brand: str = ""
    model: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    barcode: str | None = None
    image_url: str | None = None
