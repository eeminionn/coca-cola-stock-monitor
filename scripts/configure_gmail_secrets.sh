#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-eeminionn/coca-cola-stock-monitor}"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) no está instalado." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh no está autenticado. Ejecuta: gh auth login" >&2
  exit 1
fi

read -r -p "Gmail remitente (SMTP_USERNAME / ALERT_EMAIL_FROM): " gmail_from
read -r -p "Email destinatario de alertas (ALERT_EMAIL_TO): " alert_to
read -r -s -p "App Password de Gmail (no tu clave normal): " gmail_app_password
echo
gmail_app_password="${gmail_app_password//[[:space:]]/}"

if [[ -z "$gmail_from" || -z "$alert_to" || -z "$gmail_app_password" ]]; then
  echo "Error: todos los campos son obligatorios." >&2
  exit 1
fi

gh secret set ALERT_EMAIL_FROM --repo "$REPO" --body "$gmail_from"
gh secret set ALERT_EMAIL_TO --repo "$REPO" --body "$alert_to"
gh secret set SMTP_USERNAME --repo "$REPO" --body "$gmail_from"
gh secret set SMTP_PASSWORD --repo "$REPO" --body "$gmail_app_password"

echo "Secrets configurados en $REPO."
echo "Puedes probar con:"
echo "  gh workflow run \"Coca-Cola stock monitor\" --repo \"$REPO\""
