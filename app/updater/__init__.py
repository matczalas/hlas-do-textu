"""Auto-updater přes GitHub Releases.

Flow:
1) check_for_update() -> volá GitHub API, vrátí UpdateInfo pokud je novější verze
2) download_installer(info, progress_cb) -> stáhne .exe asset s progress
3) apply_update(path) -> spustí installer s /SILENT a ukončí aplikaci

Konfigurace v config.py: GITHUB_OWNER, GITHUB_REPO.
"""
from app.updater.client import (
    UpdateInfo,
    apply_update,
    check_for_update,
    download_installer,
)

__all__ = ["UpdateInfo", "check_for_update", "download_installer", "apply_update"]
