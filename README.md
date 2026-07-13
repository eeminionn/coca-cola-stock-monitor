# Coca-Cola Stock Monitor

Monitor para revisar la página de láminas/sobres del Mundial 2026 en miCoca-Cola.cl y mandar un correo cuando aparezcan cambios relevantes o productos nuevos.

El proyecto está pensado para correr gratis en GitHub Actions cada 5 minutos. La primera ejecución guarda una línea base en `.monitor/state.json`; desde la segunda ejecución avisa si detecta productos nuevos, SKUs que pasen a disponibles o cambios relevantes en las páginas públicas revisadas. El workflow solo commitea estado cuando esa línea base cambia.

## Qué revisa

- `https://andina.micoca-cola.cl/laminas-coleccionables-mundial-fifa-2026`
- `https://andina.micoca-cola.cl/mundial-2026`
- `https://andina.micoca-cola.cl/mundial-fifa-2026`
- Búsquedas públicas como `sobres mundial`, `láminas mundial`, `set laminas` y `mundial fifa 2026`
- API pública de catálogo VTEX para detectar productos, SKU, precio y disponibilidad

## Configuración en GitHub

1. Crea un repo en GitHub y sube estos archivos.
2. En el repo, entra a `Settings` -> `Secrets and variables` -> `Actions`.
3. Agrega estos `Repository secrets`:

| Secret | Valor |
| --- | --- |
| `ALERT_EMAIL_TO` | Email donde quieres recibir alertas |
| `ALERT_EMAIL_FROM` | Email remitente, normalmente tu Gmail |
| `SMTP_USERNAME` | Tu Gmail completo |
| `SMTP_PASSWORD` | App password de Gmail, no tu password normal |
Para Gmail necesitas activar verificación en dos pasos y crear una "App password" en tu cuenta Google. Esa clave es la que va en `SMTP_PASSWORD`.

## Cómo probar

En GitHub puedes ir a `Actions` -> `Coca-Cola stock monitor` -> `Run workflow`.

También puedes probar localmente:

```bash
python scripts/coke_monitor.py
```

La primera ejecución no manda correo por defecto. Si quieres forzar alerta en la primera corrida:

```bash
ALERT_ON_FIRST_RUN=true python scripts/coke_monitor.py
```

## Notas

GitHub Actions no garantiza ejecución exacta al minuto, pero `*/5 * * * *` es la frecuencia mínima razonable para este caso. El monitor revisa rutas públicas y no intenta saltarse controles de compra, stock ni zona del sitio.
