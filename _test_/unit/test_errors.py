from obsidian_mcp.errors import ApplicationError, ConfigurationError, ErrorCode


def test_application_error_exposes_safe_payload() -> None:
    error = ApplicationError(
        code=ErrorCode.CONFIGURATION_INVALID,
        message="Configuration is invalid.",
        internal_detail="secret path detail",
    )

    assert error.to_public_dict() == {
        "code": "configuration_invalid",
        "message": "Configuration is invalid.",
    }


def test_configuration_error_has_stable_code() -> None:
    error = ConfigurationError("Missing vault path.")

    assert error.code is ErrorCode.CONFIGURATION_INVALID
    assert str(error) == "Missing vault path."
