from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app import __version__

GITHUB_REPOSITORY = "Hallister2/Nova-Notetaker"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"
RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"

_VERSION_RE = re.compile(r"\bv?(\d+(?:\.\d+){1,3}(?:[-.][A-Za-z0-9]+)?)\b")


class UpdateCheckError(Exception):
    def __init__(self, message: str, no_release: bool = False) -> None:
        super().__init__(message)
        self.no_release = no_release


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    release_name: str
    release_url: str
    is_update_available: bool
    release_found: bool
    is_prerelease: bool
    download_url: str = ""
    asset_name: str = ""


def _parse_version(text: str) -> list[int]:
    match = _VERSION_RE.search(text)
    if not match:
        return [0]
    numeric = re.split(r"[-.][A-Za-z]", match.group(1))[0]
    try:
        return [int(x) for x in numeric.split(".")]
    except ValueError:
        return [0]


def _is_newer(candidate: str, current: str) -> bool:
    c_parts = _parse_version(candidate)
    k_parts = _parse_version(current)
    length = max(len(c_parts), len(k_parts))
    c_parts += [0] * (length - len(c_parts))
    k_parts += [0] * (length - len(k_parts))
    return c_parts > k_parts


def _pick_installer_asset(assets: list[dict]) -> tuple[str, str]:
    candidates = [a for a in assets if a.get("name", "").lower().endswith((".exe", ".msi"))]
    if not candidates:
        return "", ""
    _VALID_PREFIXES = ("https://github.com/", "https://objects.githubusercontent.com/")
    for keyword in ("setup", "installer", "install"):
        for asset in candidates:
            if keyword in asset["name"].lower():
                url = asset.get("browser_download_url", "")
                if url.startswith(_VALID_PREFIXES):
                    return url, asset["name"]
    url = candidates[0].get("browser_download_url", "")
    if url.startswith(_VALID_PREFIXES):
        return url, candidates[0]["name"]
    return "", ""


def check_for_updates(timeout: int = 5) -> UpdateCheckResult:
    current = __version__
    req = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Nova-Notetaker"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            releases = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateCheckError("No releases found.", no_release=True) from exc
        raise UpdateCheckError(f"GitHub returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise UpdateCheckError("Failed to parse GitHub response.") from exc

    if not isinstance(releases, list) or not releases:
        return UpdateCheckResult(
            current_version=current,
            latest_version=current,
            release_name="",
            release_url=RELEASES_URL,
            is_update_available=False,
            release_found=False,
            is_prerelease=False,
        )

    best: dict | None = None
    for release in releases:
        if release.get("draft"):
            continue
        tag = release.get("tag_name", "")
        if not tag:
            continue
        if best is None or _is_newer(tag, best["tag_name"]):
            best = release

    if best is None:
        return UpdateCheckResult(
            current_version=current,
            latest_version=current,
            release_name="",
            release_url=RELEASES_URL,
            is_update_available=False,
            release_found=False,
            is_prerelease=False,
        )

    latest_tag = best.get("tag_name", "")
    release_name = best.get("name") or latest_tag
    release_url = best.get("html_url") or RELEASES_URL
    is_prerelease = bool(best.get("prerelease"))
    download_url, asset_name = _pick_installer_asset(best.get("assets", []))

    return UpdateCheckResult(
        current_version=current,
        latest_version=latest_tag,
        release_name=release_name,
        release_url=release_url,
        is_update_available=_is_newer(latest_tag, current),
        release_found=True,
        is_prerelease=is_prerelease,
        download_url=download_url,
        asset_name=asset_name,
    )
