from __future__ import annotations

from unittest import TestCase

from app.core.update_checker import _pick_checksum_asset, _pick_installer_asset


class UpdateCheckerTests(TestCase):
    def test_picks_installer_and_matching_checksum_assets(self) -> None:
        assets = [
            {"name": "NovaNotetakerSetup_1.2.3.exe", "browser_download_url": "https://github.com/Hallister2/Nova-Notetaker/releases/download/v1/NovaNotetakerSetup_1.2.3.exe"},
            {"name": "NovaNotetakerSetup_1.2.3.exe.sha256", "browser_download_url": "https://github.com/Hallister2/Nova-Notetaker/releases/download/v1/NovaNotetakerSetup_1.2.3.exe.sha256"},
        ]

        download_url, asset_name = _pick_installer_asset(assets)
        checksum_url, checksum_name = _pick_checksum_asset(assets, asset_name)

        self.assertTrue(download_url.endswith(".exe"))
        self.assertEqual(asset_name, "NovaNotetakerSetup_1.2.3.exe")
        self.assertTrue(checksum_url.endswith(".sha256"))
        self.assertEqual(checksum_name, "NovaNotetakerSetup_1.2.3.exe.sha256")

    def test_rejects_non_github_asset_urls(self) -> None:
        assets = [
            {"name": "NovaNotetakerSetup_1.2.3.exe", "browser_download_url": "https://example.com/NovaNotetakerSetup_1.2.3.exe"},
        ]

        self.assertEqual(_pick_installer_asset(assets), ("", ""))
