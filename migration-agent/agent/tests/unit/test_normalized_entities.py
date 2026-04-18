"""Unit tests for normalized entity models."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.state.models.normalized.entities import (
    NormalizedCalendarEvent,
    NormalizedGroup,
    NormalizedMailbox,
    NormalizedRetentionLabel,
    NormalizedTeamsMessage,
    NormalizedUser,
)

_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)


def test_normalized_user_defaults() -> None:
    u = NormalizedUser(
        source_id="u1",
        upn="alice@contoso.com",
        display_name="Alice",
        email="alice@contoso.com",
        timezone="America/New_York",
    )
    assert u.is_service_account is False
    assert u.is_contractor is False
    assert u.license_skus == []


def test_normalized_mailbox_defaults() -> None:
    m = NormalizedMailbox(source_id="m1", upn="alice@contoso.com", mailbox_type="user")
    assert m.size_bytes == 0
    assert m.delegates == []
    assert m.rules_count == 0


def test_normalized_calendar_event() -> None:
    ev = NormalizedCalendarEvent(
        source_id="ev1",
        organizer_upn="alice@contoso.com",
        start=_NOW,
        end=_NOW,
        has_online_meeting=True,
        online_meeting_provider="teams",
    )
    assert ev.is_recurring is False
    assert ev.online_meeting_provider == "teams"


def test_normalized_teams_message() -> None:
    msg = NormalizedTeamsMessage(
        source_id="msg1",
        channel_id="ch1",
        author_upn="bob@contoso.com",
        timestamp=_NOW,
        content_type="text",
    )
    assert msg.reply_to_id is None
    assert msg.reaction_count == 0


def test_normalized_retention_label() -> None:
    label = NormalizedRetentionLabel(
        source_id="l1",
        name="7yr-delete",
        retention_days=2555,
        disposition_action="delete",
    )
    assert label.retention_days == 2555
    assert label.applied_to_entity is None


def test_normalized_group_members() -> None:
    g = NormalizedGroup(
        source_id="g1",
        name="Engineering",
        group_type="m365",
        members=["alice@c.com", "bob@c.com"],
    )
    assert len(g.members) == 2
