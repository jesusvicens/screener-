# Screener

Screener de las cotizadas de EE. UU. con datos públicos y gratuitos:

- **Cuentas:** SEC (XBRL, «frames»): ventas, beneficio, BPA, flujo de caja, balance… de unas 5.000 empresas.
- **Precios y sectores:** screener público de Nasdaq.

Filtra por crecimiento, márgenes, rentabilidad, deuda y valoración, y descarga el resultado en CSV.

## Cómo funciona

- `actualizar.py` descarga los datos y los deja en `out/`.
- GitHub Actions lo ejecuta cada noche y publica el resultado en la rama `datos`.
- `app.py` (Streamlit) lee esa rama y muestra la tabla.

## Usarlo

```bash
pip install -r requirements.txt
python actualizar.py      # opcional: genera los datos en local (unos minutos)
streamlit run app.py
```

Para desplegarlo en Streamlit Community Cloud basta con apuntar a `app.py`. Si haces un fork, cambia
la variable de entorno `SCREENER_REPO` (por defecto `jesusvicens/screener-`) para que lea tu rama `datos`.

La SEC pide identificarse: define `SEC_USER_AGENT` («Nombre email») si lo ejecutas a menudo.
