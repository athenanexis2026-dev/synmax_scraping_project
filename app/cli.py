"""Public CLI entrypoint for the SynMax backend package."""

from __future__ import annotations

from app.services import cli_commands as _commands
from app.services.cli_commands import (
    FirecrawlBrowserClient,
    FirecrawlBrowserError,
    FirecrawlBrowserSessionWellDetailsClient,
    FirecrawlWellDetailsClient,
    ProtectedPageError,
    ScrapeConfig,
    build_parser as _build_parser,
    check_session_command as _check_session_command,
    close_session_command as _close_session_command,
    load_database_command as _load_database_command,
    load_env_file,
    open_session_command as _open_session_command,
    parse_well_details_html,
    scrape_wells,
    scrape_wells_command as _scrape_wells_command,
)


# ============================================================================
# COMPATIBILITY
# ============================================================================
_COMPAT_DEPENDENCIES = (
    "FirecrawlBrowserClient",
    "FirecrawlBrowserSessionWellDetailsClient",
    "FirecrawlWellDetailsClient",
    "parse_well_details_html",
    "scrape_wells",
)


def _sync_compat_dependencies() -> None:
    """Keep monkeypatched app.cli dependencies visible to the implementation module."""

    for name in _COMPAT_DEPENDENCIES:
        setattr(_commands, name, globals()[name])


def __getattr__(name: str):
    return getattr(_commands, name)


# ============================================================================
# CLI ENTRYPOINT
# ============================================================================
def main() -> None:
    _sync_compat_dependencies()
    _commands.main()


def build_parser():
    _sync_compat_dependencies()
    return _build_parser()


def scrape_wells_command(args):
    _sync_compat_dependencies()
    return _scrape_wells_command(args)


def check_session_command(args):
    _sync_compat_dependencies()
    return _check_session_command(args)


def open_session_command(args):
    _sync_compat_dependencies()
    return _open_session_command(args)


def close_session_command(args):
    _sync_compat_dependencies()
    return _close_session_command(args)


def load_database_command(args):
    _sync_compat_dependencies()
    return _load_database_command(args)


__all__ = [
    "FirecrawlBrowserClient",
    "FirecrawlBrowserError",
    "FirecrawlBrowserSessionWellDetailsClient",
    "FirecrawlWellDetailsClient",
    "ProtectedPageError",
    "ScrapeConfig",
    "build_parser",
    "check_session_command",
    "close_session_command",
    "load_database_command",
    "load_env_file",
    "main",
    "open_session_command",
    "parse_well_details_html",
    "scrape_wells",
    "scrape_wells_command",
]


if __name__ == "__main__":
    main()
