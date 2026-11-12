"""Descarga los datos (SEC y Nasdaq) y los deja en ./out. Lo ejecuta GitHub Actions cada noche."""
from __future__ import annotations

from pathlib import Path

from screener import datos


def main():
    out = Path("out")
    out.mkdir(exist_ok=True)
    mk = datos.build_market()
    mk.to_parquet(out / "mercado.parquet")
    print(f"Precios: {len(mk)} acciones")
    base = datos.build_base()
    if len(base) < 3000:  # la SEC no ha respondido bien: mejor fallar que publicar una tabla vacía
        raise SystemExit(f"La SEC solo ha devuelto {len(base)} empresas")
    base.to_parquet(out / "base.parquet")
    print(f"Fundamentales: {len(base)} empresas")


if __name__ == "__main__":
    main()
