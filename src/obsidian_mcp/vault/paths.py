"""Safe path resolution for Obsidian vault operations."""

from pathlib import Path

from obsidian_mcp.errors import VaultPathError


class VaultPathResolver:
    """Resolve user-provided vault-relative paths safely."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.resolve()

    def resolve_note_path(self, relative_path: str | Path) -> Path:
        """Resolve a vault-relative note path, adding `.md` when missing."""
        path_text = str(relative_path)
        if Path(path_text).suffix:
            return self.resolve_relative_path(path_text)
        return self.resolve_relative_path(f"{path_text}.md")

    def resolve_relative_path(self, relative_path: str | Path) -> Path:
        """Resolve a vault-relative path and reject paths outside the vault."""
        path = Path(relative_path)
        path_text = str(relative_path).strip()

        if not path_text:
            raise VaultPathError("Path must not be empty.")
        if path.is_absolute():
            raise VaultPathError("Path must be relative to the vault.")
        if any(part == ".." for part in path.parts):
            raise VaultPathError("Path must not contain parent traversal.")

        resolved_path = (self.vault_path / path).resolve()
        if not resolved_path.is_relative_to(self.vault_path):
            raise VaultPathError("Path resolves outside the vault.")
        return resolved_path

    def to_vault_relative(self, path: Path) -> str:
        """Return a normalized POSIX-style vault-relative path."""
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(self.vault_path):
            raise VaultPathError("Path resolves outside the vault.")
        return resolved_path.relative_to(self.vault_path).as_posix()
