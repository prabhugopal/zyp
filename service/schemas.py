"""Pydantic models — validation at the boundary and response serialization from one declaration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateLinkRequest(BaseModel):
    originalUrl: str = Field(min_length=1)
    customAlias: str | None = Field(default=None, min_length=4, max_length=20)
    expiresAt: float | None = Field(default=None, description="Unix timestamp (seconds)")


class UpdateLinkRequest(BaseModel):
    expiresAt: float | None = None
    active: bool | None = None


class LinkResponse(BaseModel):
    code: str
    originalUrl: str
    shortUrl: str
    active: bool
    createdAt: float
    expiresAt: float | None = None


class LinkPageResponse(BaseModel):
    links: list[LinkResponse]
    page: int
    size: int
    totalElements: int


class ClickRecordResponse(BaseModel):
    clickedAt: float
    referrer: str
    userAgent: str


class AnalyticsResponse(BaseModel):
    totalClicks: int
    clicksByDay: dict[str, int]
    topReferrers: list[tuple[str, int]]
    topUserAgents: list[tuple[str, int]]
    recentClicks: list[ClickRecordResponse]
