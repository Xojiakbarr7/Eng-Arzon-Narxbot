"""Ruxsatli kataloglar uchun adapter kontrakti. Yashirin scraping ishlatilmaydi."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class NormalizedOffer:
    product_id: int
    store_id: int
    price: int
    currency: str
    in_stock: bool
    url: str
    observed_at: datetime
    source_reference: str


class StoreAdapter(Protocol):
    async def fetch(self) -> list[NormalizedOffer]: ...


class DisconnectedAdapter:
    status = "disconnected"
    async def fetch(self) -> list[NormalizedOffer]:
        raise RuntimeError("Ruxsatli API ulanmagan. CSV import yoki hamkor API shartnomasi kerak.")


class UzumAdapter(DisconnectedAdapter): pass
class AsaxiyAdapter(DisconnectedAdapter): pass
class OlchaAdapter(DisconnectedAdapter): pass
class TexnomartAdapter(DisconnectedAdapter): pass
class MediaParkAdapter(DisconnectedAdapter): pass
class PartnerApiAdapter(DisconnectedAdapter): pass


class CsvCatalogAdapter:
    status = "csv"
    def __init__(self, validated_rows: list[NormalizedOffer]):
        self.rows = validated_rows
    async def fetch(self):
        return self.rows
