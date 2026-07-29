"""Migração manual do banco para o esquema canônico atual."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

import database


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Migra o banco do PDV Espetinho para o schema v{database.SCHEMA_VERSION}."
        )
    )
    parser.add_argument(
        "banco",
        nargs="?",
        default=str(database.caminho_banco()),
        help="Caminho do banco SQLite (padrão: banco da aplicação).",
    )
    args = parser.parse_args()
    database.inicializar_banco(args.banco)
    print(f"Banco pronto: {Path(args.banco).resolve()}")


if __name__ == "__main__":
    main()
