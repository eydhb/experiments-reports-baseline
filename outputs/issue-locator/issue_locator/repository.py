"""Read-only, bounded repository tools. Repository code is never executed."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat


class Repository:
    """Inspect source text beneath one resolved local directory."""

    MAX_FILES = 20_000
    MAX_ENTRIES = 100_000
    MAX_FILE_BYTES = 1_048_576
    MAX_READ_LINES = 400
    MAX_MATCHES = 200
    MAX_QUERY_LENGTH = 256

    IGNORED_DIRS = frozenset({
        ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
        "target", "build", "dist", "out", "bin", "obj", ".idea", ".vscode",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".next", ".nuxt", ".cache", "cache", "coverage", ".gradle",
        ".aws", ".ssh", ".azure", ".terraform", "vendor",
    })
    EXTENSIONS = frozenset({
        ".java", ".kt", ".kts", ".scala", ".py", ".pyi", ".js", ".jsx",
        ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".c", ".h", ".cpp",
        ".hpp", ".cc", ".cs", ".fs", ".rb", ".php", ".swift", ".m",
        ".mm", ".vue", ".svelte", ".html", ".css", ".scss", ".less",
        ".sql", ".graphql", ".proto", ".xml", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".properties", ".gradle", ".md", ".rst",
        ".txt", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".r", ".dart",
        ".ex", ".exs", ".erl", ".hrl", ".clj", ".cljs",
    })
    FILE_NAMES = frozenset({
        "makefile", "dockerfile", "jenkinsfile", "gemfile", "rakefile",
        "procfile", "cmakelists.txt", ".gitignore", ".dockerignore",
    })
    SECRET_NAMES = frozenset({
        "credentials.json", "credentials", "secrets.json", "secrets.yaml",
        "secrets.yml", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
        ".npmrc", ".pypirc", ".netrc",
    })

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("repo_path must be an existing directory")
        self._files: tuple[str, ...] | None = None
        self._truncated = False

    @staticmethod
    def _is_link(path: Path) -> bool:
        """Reject symlinks and Windows junction/reparse points."""
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )

    @classmethod
    def _allowed(cls, relative: PurePosixPath) -> bool:
        parts = [part.casefold() for part in relative.parts]
        if not parts or any(part.startswith(".env") for part in parts):
            return False
        if any(part in cls.IGNORED_DIRS for part in parts[:-1]):
            return False
        name = parts[-1]
        if name in cls.SECRET_NAMES:
            return False
        if name.startswith(("service-account", "service_account")):
            return False
        return name in cls.FILE_NAMES or relative.suffix.casefold() in cls.EXTENSIONS

    def _safe_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or "\x00" in relative:
            raise ValueError("path must be a nonempty repository-relative path")
        # Normalize Windows separators on every platform, and disallow drive/ADS paths.
        normalized = relative.replace("\\", "/")
        parsed = PurePosixPath(normalized)
        if parsed.is_absolute() or ".." in parsed.parts or ":" in normalized:
            raise ValueError("path must stay inside the repository")
        if not self._allowed(parsed):
            raise ValueError("file is excluded from repository inspection")
        current = self.root
        for part in parsed.parts:
            current = current / part
            if self._is_link(current):
                raise ValueError("symlinks and junctions are not inspected")
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError("path must identify a regular file inside the repository")
        return resolved

    def _read_text(self, relative: str) -> tuple[str, str]:
        path = self._safe_path(relative)
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError("file exceeds the 1 MiB inspection limit")
        with path.open("rb") as handle:
            raw = handle.read(self.MAX_FILE_BYTES + 1)
        if len(raw) > self.MAX_FILE_BYTES:
            raise ValueError("file exceeds the 1 MiB inspection limit")
        if b"\x00" in raw:
            raise ValueError("binary files are not inspected")
        return raw.decode("utf-8-sig", errors="replace"), hashlib.sha256(raw).hexdigest()

    def list_files(self) -> dict:
        if self._files is not None:
            return {"files": list(self._files), "truncated": self._truncated}

        collected: list[str] = []
        entries = 0
        stopped = False

        def walk_error(_error: OSError) -> None:
            self._truncated = True

        for directory, directories, files in os.walk(
            self.root, topdown=True, followlinks=False, onerror=walk_error
        ):
            base = Path(directory)
            safe_directories: list[str] = []
            for name in sorted(directories, key=lambda value: (value.casefold(), value)):
                entries += 1
                if entries > self.MAX_ENTRIES:
                    stopped = True
                    break
                if name.casefold() in self.IGNORED_DIRS or name.casefold().startswith(".env"):
                    continue
                try:
                    path = base / name
                    if not self._is_link(path) and path.resolve().is_relative_to(self.root):
                        safe_directories.append(name)
                except OSError:
                    self._truncated = True
            directories[:] = safe_directories
            if stopped:
                break
            for name in sorted(files, key=lambda value: (value.casefold(), value)):
                entries += 1
                if entries > self.MAX_ENTRIES:
                    stopped = True
                    break
                path = base / name
                relative = path.relative_to(self.root).as_posix()
                if not self._allowed(PurePosixPath(relative)):
                    continue
                try:
                    if self._is_link(path) or not path.is_file():
                        continue
                    if path.stat().st_size > self.MAX_FILE_BYTES:
                        self._truncated = True
                        continue
                except OSError:
                    self._truncated = True
                    continue
                if len(collected) >= self.MAX_FILES:
                    stopped = True
                    break
                collected.append(relative)
            if stopped:
                break

        self._truncated = self._truncated or stopped
        self._files = tuple(sorted(collected, key=lambda value: (value.casefold(), value)))
        return {"files": list(self._files), "truncated": self._truncated}

    def search_code(self, query: str, limit: int = 30) -> dict:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty literal string")
        if len(query) > self.MAX_QUERY_LENGTH or "\n" in query or "\r" in query:
            raise ValueError("query must be one line of at most 256 characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_MATCHES:
            raise ValueError("limit must be an integer between 1 and 200")

        index = self.list_files()
        matches: list[dict] = []
        truncated = index["truncated"]
        needle = query.casefold()
        for relative in index["files"]:
            try:
                content, _digest = self._read_text(relative)
            except (OSError, ValueError):
                truncated = True
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if needle in line.casefold():
                    if len(matches) >= limit:
                        return {"query": query, "matches": matches, "truncated": True}
                    # Preserve the matching text even when a generated line is huge.
                    folded = line.casefold()
                    position = folded.find(needle)
                    left = max(0, position - 240)
                    right = min(len(line), max(left + 640, position + len(query) + 80))
                    snippet = line[left:right]
                    if left:
                        snippet = "…" + snippet
                    if right < len(line):
                        snippet += "…"
                    matches.append({"path": relative, "line": number, "snippet": snippet})
        return {"query": query, "matches": matches, "truncated": truncated}

    def read_file(self, path: str, start_line: int = 1, end_line: int = 160) -> dict:
        if (
            isinstance(start_line, bool)
            or isinstance(end_line, bool)
            or not isinstance(start_line, int)
            or not isinstance(end_line, int)
            or start_line < 1
            or end_line < start_line
            or end_line - start_line + 1 > self.MAX_READ_LINES
        ):
            raise ValueError("line range must be positive, ordered, and at most 400 lines")
        content, digest = self._read_text(path)
        all_lines = content.splitlines()
        if start_line > len(all_lines) and all_lines:
            raise ValueError("start_line is beyond the end of the file")
        selected = [
            {"line": index + 1, "text": all_lines[index]}
            for index in range(start_line - 1, min(end_line, len(all_lines)))
        ]
        return {
            "path": PurePosixPath(path.replace("\\", "/")).as_posix(),
            "start_line": start_line,
            "end_line": selected[-1]["line"] if selected else 0,
            "lines": selected,
            "content": "\n".join(item["text"] for item in selected),
            "sha256": digest,
        }
