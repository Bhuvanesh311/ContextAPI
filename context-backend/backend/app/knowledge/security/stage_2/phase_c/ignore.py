"""
Archive members that are never worth ingesting.

Project archives (a zipped repo or workspace) carry version-control data,
dependency caches and build output next to the real files. Those members
are skipped during extraction instead of becoming child documents that
Stage 1 would only reject. Path-safety checks still run on every member
before this filter, so skipping never hides an unsafe entry.
"""

from pathlib import PurePosixPath


# Any path component with one of these names skips the whole subtree.
IGNORED_DIRECTORIES: frozenset[str] = frozenset({
    # Version control
    ".git", ".svn", ".hg", ".bzr",
    # IDE / OS metadata
    ".idea", ".vscode", ".vs", "__MACOSX",
    # Dependencies, virtual environments, caches
    "node_modules", "bower_components", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".gradle", ".mvn",
    ".next", ".nuxt", ".cache", ".terraform",
    # Build output
    "target", "build", "dist", "bin", "obj",
})

IGNORED_FILENAMES: frozenset[str] = frozenset({
    ".DS_Store", "Thumbs.db", "desktop.ini",
    ".gitignore", ".gitattributes", ".gitmodules", ".gitkeep",
    ".dockerignore", ".editorconfig", ".npmignore",
    # Build-tool wrapper scripts (boilerplate, not project content)
    "mvnw", "mvnw.cmd", "gradlew", "gradlew.bat",
})

# Compiled / binary build artefacts.
IGNORED_EXTENSIONS: frozenset[str] = frozenset({
    ".class", ".jar", ".war", ".ear", ".pyc", ".pyo",
    ".o", ".obj", ".a", ".so", ".dll", ".dylib", ".exe", ".pdb", ".lib",
})


def is_ignored_member(member_name: str) -> bool:
    """True when an archive member should be skipped, not extracted."""

    path = PurePosixPath(member_name.replace("\\", "/"))

    if any(part in IGNORED_DIRECTORIES for part in path.parts[:-1]):
        return True

    if path.name in IGNORED_FILENAMES:
        return True

    return path.suffix.lower() in IGNORED_EXTENSIONS
