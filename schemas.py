from pydantic import BaseModel, Field, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BasketItem(StrictModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=20)


class BasketRequest(StrictModel):
    items: list[BasketItem] = Field(min_length=1, max_length=8)
    region: str = "tashkent"


class AlertRequest(StrictModel):
    product_id: int = Field(gt=0)
    target_price: int = Field(gt=0, le=10**12)
    enabled: bool = True


class AlertUpdate(StrictModel):
    target_price: int | None = Field(default=None, gt=0, le=10**12)
    enabled: bool | None = None


class AssistantRequest(StrictModel):
    message: str = Field(min_length=2, max_length=1500)


class ProfileUpdate(StrictModel):
    language: str | None = Field(default=None, pattern="^(uz|ru)$")
    region: str | None = None
    notifications_enabled: bool | None = None


class NotificationAck(StrictModel):
    delivered: bool
    error: str | None = Field(default=None, max_length=300)


class CategoryRequest(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    emoji: str = Field(default="🛍", max_length=16)
    parent_id: int | None = Field(default=None, gt=0)
    sort_order: int = 0
    active: bool = True


class ProductRequest(StrictModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=200, pattern=r"^[a-z0-9-]+$")
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    category_id: int = Field(gt=0)
    description: str = Field(default="", max_length=3000)
    emoji: str = Field(default="📦", max_length=16)
    attributes: dict[str, str] = Field(default_factory=dict)
    barcode: str | None = Field(default=None, min_length=8, max_length=14)


class CsvImportRequest(StrictModel):
    csv_text: str = Field(min_length=10, max_length=2_000_000)
    commit: bool = False


class StoreUpdate(StrictModel):
    delivery_fee: int = Field(ge=0, le=10**9)
    free_delivery_threshold: int | None = Field(default=None, gt=0, le=10**12)
    adapter_status: str = Field(default="csv", pattern="^(disconnected|csv|partner|public)$")
