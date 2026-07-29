"""Migração manual do banco legado para o esquema canônico v2."""

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
        description="Migra o banco do Espetão para o schema v2."
    )
    parser.add_argument(
        "banco",
        nargs="?",
        default=str(database.caminho_banco()),
        help="Caminho do banco SQLite (padrão: banco da aplicação).",
    )
    args = parser.parse_args()
    resultado = database.migrar_banco_legado(args.banco)
    print(f"Banco pronto: {Path(args.banco).resolve()}")
    if resultado != Path(args.banco).resolve():
        print(f"Backup recuperável: {resultado}")


if __name__ == "__main__":
    main()
