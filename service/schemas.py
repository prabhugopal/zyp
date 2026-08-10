"""Marshmallow schemas — validation at the boundary and response serialization in one declaration,
same role as sLink's Bean Validation + DTO records."""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class CreateLinkRequest(Schema):
    originalUrl = fields.Str(required=True, validate=validate.Length(min=1))
    customAlias = fields.Str(required=False, allow_none=True, load_default=None,
                              validate=validate.Length(min=4, max=20))
    expiresAt = fields.Float(required=False, allow_none=True, load_default=None,
                              metadata={"description": "Unix timestamp (seconds)"})


class UpdateLinkRequest(Schema):
    expiresAt = fields.Float(required=False, allow_none=True, load_default=None)
    active = fields.Bool(required=False, allow_none=True, load_default=None)


class LinkResponse(Schema):
    code = fields.Str()
    originalUrl = fields.Str()
    shortUrl = fields.Str()
    active = fields.Bool()
    createdAt = fields.Float()
    expiresAt = fields.Float(allow_none=True)


class LinkPageResponse(Schema):
    links = fields.List(fields.Nested(LinkResponse))
    page = fields.Int()
    size = fields.Int()
    totalElements = fields.Int()


class ClickRecordResponse(Schema):
    clickedAt = fields.Float()
    referrer = fields.Str()
    userAgent = fields.Str()


class AnalyticsResponse(Schema):
    totalClicks = fields.Int()
    clicksByDay = fields.Dict(keys=fields.Str(), values=fields.Int())
    topReferrers = fields.List(fields.List(fields.Raw()))
    topUserAgents = fields.List(fields.List(fields.Raw()))
    recentClicks = fields.List(fields.Nested(ClickRecordResponse))
