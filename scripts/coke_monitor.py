#!/usr/bin/env python3
"""Monitor miCoca-Cola public pages/catalog results and email when products change."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import smtplib
import ssl
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_TARGET_URL = (
    "https://andina.micoca-cola.cl/"
    "laminas-coleccionables-mundial-fifa-2026"
)

DEFAULT_SEARCH_TERMS = [
    "sobres mundial",
    "láminas mundial",
    "laminas mundial",
    "sobres coca cola",
    "láminas coca cola",
    "set laminas",
    "mundial fifa 2026",
]

DEFAULT_PAGE_URLS = [
    DEFAULT_TARGET_URL,
    "https://andina.micoca-cola.cl/mundial-2026",
    "https://andina.micoca-cola.cl/mundial-fifa-2026",
    "https://andina.micoca-cola.cl/sobres%20mundial?map=ft&_q=sobres%20mundial",
    "https://andina.micoca-cola.cl/l%C3%A1minas%20mundial?map=ft&_q=l%C3%A1minas%20mundial",
]

DEFAULT_KEYWORDS = [
    "lamina",
    "lámina",
    "laminas",
    "láminas",
    "sobre",
    "sobres",
    "album",
    "álbum",
    "mundial",
    "fifa",
    "figurita",
    "figuritas",
    "sticker",
    "stickers",
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


@dataclass(frozen=True)
class ProductSnapshot:
    key: str
    name: str
    sku: str
    product_id: str
    url: str
    available: bool
    quantity: int | None
    price: float | None
    source_terms: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "sku": self.sku,
            "product_id": self.product_id,
            "url": self.url,
            "available": self.available,
            "quantity": self.quantity,
            "price": self.price,
            "source_terms": sorted(set(self.source_terms)),
        }


def getenv_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def fetch_bytes(url: str, timeout: int = 30) -> tuple[bytes, dict[str, str]]:
    req = Request(
        url,
        headers={
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 CocaColaStockMonitor/1.0 "
                "(GitHub Actions availability checker)"
            ),
        },
    )
    with urlopen(req, timeout=timeout) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        if headers.get("content-encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
        return body, headers


def fetch_text(url: str, timeout: int = 30) -> str:
    body, headers = fetch_bytes(url, timeout)
    content_type = headers.get("content-type", "")
    encoding = "utf-8"
    if "charset=" in content_type:
        encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    return body.decode(encoding or "utf-8", errors="replace")


def extract_text(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    return parser.parts


def interesting_lines(lines: list[str], keywords: list[str]) -> list[str]:
    selected: list[str] = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for line in lines:
        low = line.lower()
        if any(keyword in low for keyword in lowered_keywords) or "oops" in low:
            selected.append(line)
    return selected[:80]


def sha256_json(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def normalize_quantity(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_price(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def product_matches(product: dict[str, Any], keywords: list[str]) -> bool:
    text_parts: list[str] = [
        str(product.get("productName", "")),
        str(product.get("productTitle", "")),
        str(product.get("metaTagDescription", "")),
        str(product.get("description", "")),
    ]
    for item in product.get("items", []) or []:
        text_parts.append(str(item.get("nameComplete", "")))
        text_parts.append(str(item.get("complementName", "")))
    haystack = " ".join(text_parts).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def catalog_search_url(term: str) -> str:
    return (
        "https://andina.micoca-cola.cl/api/catalog_system/pub/products/search"
        f"?ft={quote(term)}&_from=0&_to=49"
    )


def collect_products(search_terms: list[str], keywords: list[str]) -> tuple[dict[str, ProductSnapshot], list[str]]:
    products: dict[str, ProductSnapshot] = {}
    errors: list[str] = []

    for term in search_terms:
        url = catalog_search_url(term)
        try:
            payload = json.loads(fetch_text(url))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{term}: {exc}")
            continue

        if not isinstance(payload, list):
            errors.append(f"{term}: unexpected API payload")
            continue

        for product in payload:
            if not isinstance(product, dict) or not product_matches(product, keywords):
                continue

            product_id = str(product.get("productId", ""))
            product_name = str(product.get("productName", "Producto sin nombre"))
            product_url = str(product.get("link", ""))
            for item in product.get("items", []) or []:
                sku = str(item.get("itemId", ""))
                if not sku:
                    continue

                best_offer: dict[str, Any] = {}
                for seller in item.get("sellers", []) or []:
                    offer = seller.get("commertialOffer", {}) or {}
                    if not best_offer or offer.get("IsAvailable"):
                        best_offer = offer

                quantity = normalize_quantity(best_offer.get("AvailableQuantity"))
                available = bool(best_offer.get("IsAvailable")) or bool(quantity and quantity > 0)
                price = normalize_price(best_offer.get("Price"))
                key = f"{product_id}:{sku}"
                existing = products.get(key)
                source_terms = list(existing.source_terms) if existing else []
                source_terms.append(term)
                products[key] = ProductSnapshot(
                    key=key,
                    name=str(item.get("nameComplete") or product_name),
                    sku=sku,
                    product_id=product_id,
                    url=product_url,
                    available=available,
                    quantity=quantity,
                    price=price,
                    source_terms=source_terms,
                )

    return products, errors


def collect_pages(page_urls: list[str], keywords: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    pages: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for url in page_urls:
        try:
            html = fetch_text(url)
            lines = extract_text(html)
            selected = interesting_lines(lines, keywords)
            pages[url] = {
                "digest": sha256_json(selected),
                "interesting_lines": selected,
            }
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")

    return pages, errors


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    tmp.replace(path)


def format_price(value: float | None) -> str:
    if value is None:
        return "sin precio"
    return f"${value:,.0f}".replace(",", ".")


def build_alert(
    new_products: list[dict[str, Any]],
    availability_changes: list[tuple[dict[str, Any], dict[str, Any]]],
    page_changes: list[tuple[str, dict[str, Any]]],
    errors: list[str],
) -> str:
    lines: list[str] = [
        "Detecté movimiento en miCoca-Cola para la búsqueda de láminas/sobres del Mundial.",
        "",
    ]

    if new_products:
        lines.append("Productos nuevos vistos:")
        for product in new_products:
            lines.append(
                f"- {product['name']} | SKU {product['sku']} | "
                f"{'disponible' if product['available'] else 'no disponible'} | "
                f"{format_price(product['price'])} | {product['url']}"
            )
        lines.append("")

    if availability_changes:
        lines.append("Productos que pasaron a disponibles:")
        for _previous, current in availability_changes:
            lines.append(
                f"- {current['name']} | SKU {current['sku']} | "
                f"{format_price(current['price'])} | {current['url']}"
            )
        lines.append("")

    if page_changes:
        lines.append("Páginas con cambio relevante en texto público:")
        for url, page in page_changes:
            lines.append(f"- {url}")
            preview = page.get("interesting_lines", [])[:8]
            if preview:
                lines.append("  Texto detectado:")
                for item in preview:
                    lines.append(f"  • {item}")
        lines.append("")

    if errors:
        lines.append("Advertencias de la corrida:")
        for error in errors[:10]:
            lines.append(f"- {error}")
        lines.append("")

    lines.append(f"Revisión UTC: {datetime.now(timezone.utc).isoformat()}")
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    to_email = os.getenv("ALERT_EMAIL_TO", "").strip()
    from_email = os.getenv("ALERT_EMAIL_FROM", "").strip() or os.getenv("SMTP_USERNAME", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "465"))

    missing = [
        name
        for name, value in {
            "ALERT_EMAIL_TO": to_email,
            "ALERT_EMAIL_FROM or SMTP_USERNAME": from_email,
            "SMTP_USERNAME": username,
            "SMTP_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "No pude enviar email porque faltan secrets/env vars: " + ", ".join(missing)
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> int:
    state_path = Path(os.getenv("STATE_FILE", ".monitor/state.json"))
    keywords = getenv_list("KEYWORDS", DEFAULT_KEYWORDS)
    search_terms = getenv_list("SEARCH_TERMS", DEFAULT_SEARCH_TERMS)
    page_urls = getenv_list("PAGE_URLS", DEFAULT_PAGE_URLS)
    target_url = os.getenv("TARGET_URL", DEFAULT_TARGET_URL).strip()
    if target_url and target_url not in page_urls:
        page_urls.insert(0, target_url)

    state = load_state(state_path)
    previous_products = state.get("products", {})
    previous_pages = state.get("pages", {})
    first_run = not bool(state)

    products, product_errors = collect_products(search_terms, keywords)
    pages, page_errors = collect_pages(page_urls, keywords)
    errors = product_errors + page_errors

    current_products = {key: product.as_dict() for key, product in sorted(products.items())}

    new_products = [
        product for key, product in current_products.items() if key not in previous_products
    ]
    availability_changes = []
    for key, current in current_products.items():
        previous = previous_products.get(key)
        if previous and not previous.get("available") and current.get("available"):
            availability_changes.append((previous, current))

    page_changes = []
    for url, current in pages.items():
        previous = previous_pages.get(url)
        if previous and previous.get("digest") != current.get("digest"):
            page_changes.append((url, current))

    should_alert = bool(new_products or availability_changes or page_changes)
    if first_run and os.getenv("ALERT_ON_FIRST_RUN", "").lower() not in {"1", "true", "yes"}:
        should_alert = False

    state = {
        "last_checked_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": target_url,
        "search_terms": search_terms,
        "page_urls": page_urls,
        "keywords": keywords,
        "products": current_products,
        "pages": pages,
        "errors": errors[-20:],
    }
    save_state(state_path, state)

    summary = {
        "first_run": first_run,
        "products_seen": len(current_products),
        "new_products": len(new_products),
        "availability_changes": len(availability_changes),
        "page_changes": len(page_changes),
        "errors": len(errors),
        "state_file": str(state_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if should_alert:
        body = build_alert(new_products, availability_changes, page_changes, errors)
        subject = os.getenv("EMAIL_SUBJECT", "Alerta miCoca-Cola: cambio en láminas/sobres Mundial")
        print("\n--- ALERT BODY ---\n" + body)
        send_email(subject, body)
        print("Email enviado.")
    elif first_run:
        print("Primera corrida: línea base guardada, sin email.")
    else:
        print("Sin cambios relevantes.")

    if errors and not current_products and not pages:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(textwrap.dedent(f"""
        Error ejecutando monitor:
        {exc}
        """).strip(), file=sys.stderr)
        time.sleep(1)
        raise
