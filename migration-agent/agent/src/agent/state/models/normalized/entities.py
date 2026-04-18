from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NormalizedUser(BaseModel):
    source_id: str
    upn: str
    display_name: str
    email: str
    timezone: str
    license_skus: list[str] = Field(default_factory=list)
    is_service_account: bool = False
    is_contractor: bool = False
    manager_upn: str | None = None
    department: str | None = None


class NormalizedGroup(BaseModel):
    source_id: str
    name: str
    group_type: str  # security, distribution, m365
    members: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)


class NormalizedMailbox(BaseModel):
    source_id: str
    upn: str
    mailbox_type: str  # user, shared, room, equipment
    size_bytes: int = 0
    item_count: int = 0
    delegates: list[str] = Field(default_factory=list)
    rules_count: int = 0
    retention_policy: str | None = None


class NormalizedSharePointSite(BaseModel):
    source_id: str
    url: str
    title: str
    storage_bytes: int = 0
    file_count: int = 0
    permissions: list[dict[str, object]] = Field(default_factory=list)
    is_external_shared: bool = False


class NormalizedDocumentLibrary(BaseModel):
    source_id: str
    site_id: str
    name: str
    content_types: list[str] = Field(default_factory=list)
    version_history_enabled: bool = False
    item_count: int = 0


class NormalizedCalendar(BaseModel):
    source_id: str
    owner_upn: str
    calendar_type: str  # personal, shared, resource
    sharing_acl: list[dict[str, object]] = Field(default_factory=list)
    working_hours: dict[str, object] = Field(default_factory=dict)
    timezone: str = ""


class NormalizedCalendarEvent(BaseModel):
    source_id: str
    organizer_upn: str
    attendees: list[str] = Field(default_factory=list)
    start: datetime
    end: datetime
    is_recurring: bool = False
    has_online_meeting: bool = False
    online_meeting_provider: str | None = None


class NormalizedTeamsChannel(BaseModel):
    source_id: str
    team_id: str
    name: str
    visibility: str  # standard, private
    member_count: int = 0
    message_count: int = 0


class NormalizedTeamsMessage(BaseModel):
    source_id: str
    channel_id: str
    author_upn: str
    timestamp: datetime
    content_type: str  # text, html, adaptive_card
    reply_to_id: str | None = None
    reaction_count: int = 0


class NormalizedLicense(BaseModel):
    source_id: str
    sku: str
    assigned_upn: str
    assigned_at: datetime | None = None


class NormalizedDelegation(BaseModel):
    source_id: str
    mailbox_upn: str
    delegate_upn: str
    permissions: list[str] = Field(default_factory=list)
    can_send_on_behalf: bool = False


class NormalizedRetentionLabel(BaseModel):
    source_id: str
    name: str
    retention_days: int | None = None
    disposition_action: str  # delete, review, relabel
    applied_to_entity: str | None = None
