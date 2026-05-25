"""License key validace.

Offline HMAC-SHA256 verifikace klíčů ve formátu S4F1-XXXX-XXXX-XXXX-XXXX.
Klíč obsahuje 8 znaků customer ID + 8 znaků HMAC checksum. Validace nepotřebuje
internet ani server — vše lokálně.

Pro reálnou ochranu (revoke, expirace) by bylo třeba online activation server.
Tento systém zajišťuje 'casual protection' — obyčejný uživatel klíč neobejde,
ale pokročilý reverse-engineer ano.
"""
from app.licensing.keys import (
    generate_key,
    is_valid_format,
    validate_key,
)
from app.licensing.store import (
    clear_stored_key,
    get_activation_info,
    get_stored_key,
    is_activated,
    store_key,
)

__all__ = [
    "generate_key",
    "validate_key",
    "is_valid_format",
    "is_activated",
    "store_key",
    "get_stored_key",
    "clear_stored_key",
    "get_activation_info",
]
