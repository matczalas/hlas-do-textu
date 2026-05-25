"""Stabilní machine fingerprint — pro evidenci aktivací.

Spojuje několik zdrojů, hashuje SHA-256, vrací prvních 16 hex znaků.
Stejný PC = stejný fingerprint. Reinstall Windows = jiný fingerprint
(MachineGuid je per-OS-install).

Použití:
    get_machine_fingerprint() -> "a1b2c3d4e5f60718"
"""
from __future__ import annotations

import hashlib
import platform
import sys
import uuid
from functools import lru_cache


def _get_windows_machine_guid() -> str | None:
    """Windows MachineGuid z registry — stabilní per OS install."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except Exception:  # noqa: BLE001
        return None


def _get_macos_hardware_uuid() -> str | None:
    """macOS IOPlatformUUID — stabilní per hardware."""
    if sys.platform != "darwin":
        return None
    try:
        import subprocess

        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                # Line format:  "IOPlatformUUID" = "ABCDEF12-3456-..."
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[3].strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def _get_linux_machine_id() -> str | None:
    """Linux /etc/machine-id (systemd)."""
    if sys.platform.startswith("linux"):
        try:
            from pathlib import Path

            p = Path("/etc/machine-id")
            if p.is_file():
                return p.read_text().strip()
        except OSError:
            return None
    return None


@lru_cache(maxsize=1)
def get_machine_fingerprint() -> str:
    """Vrátí 16-hex-znaků fingerprint aktuálního zařízení.

    Pořadí zdrojů:
    1) Native machine GUID (Windows registry / macOS IOPlatform / Linux machine-id)
    2) Fallback: uuid.getnode() + platform.node() (méně stabilní)

    Vrací konzistentní výsledek během běhu (lru_cache).
    """
    sources: list[str] = []

    native = (
        _get_windows_machine_guid()
        or _get_macos_hardware_uuid()
        or _get_linux_machine_id()
    )
    if native:
        sources.append(f"native:{native}")
    else:
        # Fallback
        sources.append(f"mac:{uuid.getnode()}")
        sources.append(f"node:{platform.node()}")

    sources.append(f"platform:{sys.platform}")

    combined = "|".join(sources)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return digest[:16]


def get_machine_display_name() -> str:
    """Lidsky čitelný název zařízení pro UI: 'tvuj-pc (Windows)'."""
    return f"{platform.node()} ({platform.system()})"
