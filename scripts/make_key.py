"""Admin CLI nástroj — generuje licenční klíče.

Použití:
    python scripts/make_key.py                        # 1 klíč
    python scripts/make_key.py --count 10             # 10 klíčů
    python scripts/make_key.py --customer "Jana N."   # s poznámkou do logu

Klíče se LOGUJÍ do souboru `keys_log.txt` v aktuálním adresáři (gitignored).
Tento log si dobře hlídej — kdo měl jaký klíč, kdy a za jakou cenu.

POZN: Klíče vygenerované tímto nástrojem jsou validní pro aktuální verzi
aplikace (HMAC secret v app/licensing/_secret.py). Pokud změníš secret,
všechny dříve vydané klíče přestanou fungovat.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Přidat root do PYTHONPATH aby fungoval `from app.licensing import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.licensing import generate_key, validate_key  # noqa: E402

LOG_FILE = Path(__file__).resolve().parent.parent / "keys_log.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generátor licenčních klíčů (admin)")
    parser.add_argument("--count", type=int, default=1, help="Kolik klíčů vygenerovat (default 1)")
    parser.add_argument("--customer", type=str, default="", help="Poznámka o zákazníkovi (jen do logu, ne do klíče)")
    parser.add_argument("--no-log", action="store_true", help="Nezapisovat do keys_log.txt")
    args = parser.parse_args()

    if args.count < 1 or args.count > 1000:
        print(f"Count musí být 1-1000, ne {args.count}", file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    keys: list[str] = []
    for _ in range(args.count):
        k = generate_key()
        assert validate_key(k), f"INTERNAL BUG: just-generated key failed validation: {k}"
        keys.append(k)

    print()
    print("=" * 60)
    print(f"  Vygenerováno {len(keys)} klíčů")
    print("=" * 60)
    print()
    for k in keys:
        print(f"  {k}")
    print()

    if not args.no_log:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            for k in keys:
                customer = args.customer if args.customer else "-"
                f.write(f"{timestamp}\t{k}\t{customer}\n")
        print(f"  -> Uloženo do {LOG_FILE.name}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
