# Coca-Cola Stock Monitor instructions

- Keep monitoring passive: request public pages and catalog data only. Do not bypass access controls, place orders, or introduce high-frequency retry loops.
- Keep mail addresses, SMTP credentials, tokens, and app passwords in GitHub Actions secrets or local environment variables only. Never log them or add them to state files.
- Preserve the baseline-first behavior and avoid sending duplicate notifications. Tests must not send email or make live network requests.
- Use the Python standard library unless a dependency provides a clear reliability or security benefit.
