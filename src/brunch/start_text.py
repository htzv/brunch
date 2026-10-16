"""One line saying where a new branch started and whether the remote was fetched."""

from __future__ import annotations

FETCH_CREATED_THE_BRANCH = (
    "fetched {remote!r}; the fetch itself created the branch locally, so it is checked out as it is"
)


def describe_start(
    *,
    remote: str | None,
    start_point: str,
    fetched: bool,
    tracks: str | None,
    dry_run: bool,
) -> str:
    """Phrase the outcome of the fetch and start-point decision for a person."""

    if remote is None:
        return f"no remote used, so it starts from the local {start_point!r}"
    if not fetched:
        return f"not fetched (--no-fetch), so it starts from the local {start_point!r}"
    fetch = "would fetch" if dry_run else "fetched"
    if tracks is not None:
        return (
            f"{fetch} {remote!r}; the branch is on the remote, so it starts from "
            f"{tracks!r} and tracks it"
        )
    return f"{fetch} {remote!r}; starts from {start_point!r}"
