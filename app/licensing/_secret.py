"""Interní HMAC secret — NEMĚŇ tuto hodnotu po prvním releasu!

Pokud změníš secret, všechny dříve vydané klíče přestanou být platné.
Tato hodnota je zabudovaná v aplikaci a používá se pro HMAC-SHA256 čeksum
licenčních klíčů.

POZN: Tento secret bude součástí binárky a kdokoliv s reverse-engineering
úsilím ho najde. To je inherentní limit offline aktivace. Pro skutečnou
ochranu by bylo třeba online activation server.
"""

# Vygenerováno secrets.token_urlsafe(32) — 25. května 2026
HMAC_SECRET: bytes = b"I7wymbVv4L9_okA_kdaA70GE_XVE9YWOnkcsMRg_S2o"

# Prefix klíčů — 'S4F1' = Safe4Future v1. Při změně secretu zvýšit na 'S4F2'.
KEY_PREFIX: str = "S4F1"
