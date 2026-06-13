import pytest

from obsidian_mcp.errors import ErrorCode
from obsidian_mcp.permissions import (
    PermissionAction,
    PermissionDeniedError,
    PermissionProfile,
    PermissionService,
)


def test_read_only_allows_read_actions_and_blocks_writes() -> None:
    service = PermissionService(PermissionProfile.READ_ONLY)

    assert service.is_allowed(PermissionAction.READ_NOTE) is True
    assert service.is_allowed(PermissionAction.SEARCH_NOTES) is True
    assert service.is_allowed(PermissionAction.UPDATE_NOTE) is False

    with pytest.raises(PermissionDeniedError) as exc_info:
        service.require(PermissionAction.DELETE_NOTE)

    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_safe_write_allows_non_destructive_writes() -> None:
    service = PermissionService(PermissionProfile.SAFE_WRITE)

    assert service.is_allowed(PermissionAction.CREATE_NOTE) is True
    assert service.is_allowed(PermissionAction.UPDATE_NOTE) is True
    assert service.is_allowed(PermissionAction.CREATE_DATAVIEW_DASHBOARD) is True
    assert service.is_allowed(PermissionAction.DELETE_NOTE) is False
    assert service.is_allowed(PermissionAction.MOVE_NOTE) is False


def test_admin_allows_every_action() -> None:
    service = PermissionService(PermissionProfile.ADMIN)

    assert all(service.is_allowed(action) for action in PermissionAction)


def test_permission_summary_lists_allowed_and_blocked_actions() -> None:
    summary = PermissionService(PermissionProfile.READ_ONLY).summary()

    assert summary["profile"] == "read_only"
    assert "read_note" in summary["allowed_actions"]
    assert "delete_note" in summary["blocked_actions"]
