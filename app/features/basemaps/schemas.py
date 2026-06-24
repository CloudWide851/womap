from typing import Literal

from pydantic import BaseModel, Field


class BasemapProvider(BaseModel):
    id: str
    type: Literal["xyz", "wms"] = "xyz"
    name: str
    url_template: str
    api_key: str = ""
    subdomains: list[str] = Field(default_factory=list)
    enabled: bool = True
    api_key_configured: bool = False
