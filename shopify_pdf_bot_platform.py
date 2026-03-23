# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import csv
import difflib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from flask import Flask, Response, redirect, render_template_string, request, send_file, url_for
from pypdf import PdfReader
from playwright.async_api import async_playwright

CODE_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.environ.get("BOT_DATA_DIR", CODE_DIR)).resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

BOT_PROFILE_DIR = BASE_DIR / "shopify_bot_profile"
BOT_PROFILE_DIR.mkdir(exist_ok=True)

HOST = "127.0.0.1"
PORT = 5000

SEARCH_WAIT_MS = 2200
ACTION_WAIT_MS = 1600
MIN_AUTO_SCORE = 0.75
STORE_HANDLE_RE = re.compile(r"/store/([^/?#]+)(?:[/?#]|$)")

app = Flask(__name__)

STATE = {
    "rows": [],
    "csv_path": None,
    "pdf_path": None,
    "logs": [],
    "browser_status": "idle",
    "worker_thread": None,
    "start_event": None,
    "stop_event": None,
}
STATE_LOCK = threading.Lock()

HTML = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>BOT Suivi Shopify</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; background:#f7f7f8; color:#111; }
    .card { background:white; border-radius:16px; padding:20px; box-shadow:0 2px 10px rgba(0,0,0,.06); margin-bottom:18px; }
    h1 { margin-top:0; }
    .btn { display:inline-block; padding:10px 14px; border-radius:10px; border:none; background:#111827; color:white; text-decoration:none; cursor:pointer; margin-right:8px; margin-bottom:8px; }
    .btn.secondary { background:#374151; }
    .btn.light { background:#e5e7eb; color:#111; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th, td { border-bottom:1px solid #e5e7eb; padding:8px; text-align:left; }
    th { background:#f9fafb; }
    .ok { color:#166534; font-weight:bold; }
    .warn { color:#92400e; font-weight:bold; }
    .muted { color:#6b7280; }
    .logs { background:#0b1020; color:#d1d5db; padding:14px; border-radius:12px; height:260px; overflow:auto; white-space:pre-wrap; font-family: Consolas, monospace; font-size:13px; }
    .row { display:flex; gap:12px; flex-wrap:wrap; }
    .badge { display:inline-block; padding:4px 8px; border-radius:999px; background:#eef2ff; color:#3730a3; font-size:12px; }
    input[type=file] { margin:12px 0; }
  </style>
</head>
<body>
  <div class="card">
    <h1>BOT Suivi Shopify</h1>
    <div class="muted">Plateforme locale : dépôt du PDF, extraction des suivis, génération CSV, puis traitement Shopify.</div>
    <form method="post" action="/upload" enctype="multipart/form-data">
      <input type="file" name="pdf_file" accept=".pdf" required>
      <button class="btn" type="submit">Déposer le PDF et extraire</button>
    </form>
  </div>

  <div class="card">
    <div class="row">
      <div><strong>PDF :</strong> {{ pdf_name or "aucun" }}</div>
      <div><strong>CSV :</strong> {{ csv_name or "aucun" }}</div>
      <div><strong>Shopify :</strong> <span class="badge">{{ browser_status }}</span></div>
      <div><strong>Lignes OK :</strong> {{ ok_count }}</div>
    </div>
    <div style="margin-top:12px;">
      {% if csv_name %}
        <a class="btn secondary" href="/download-csv">Télécharger le CSV</a>
        <form method="post" action="/prepare-shopify" style="display:inline;">
          <button class="btn" type="submit">1. Ouvrir Shopify / préparer la session</button>
        </form>
        <form method="post" action="/run-shopify" style="display:inline;">
          <button class="btn secondary" type="submit">2. Démarrer le traitement Shopify</button>
        </form>
      {% endif %}
      <form method="post" action="/clear" style="display:inline;">
        <button class="btn light" type="submit">Vider l'état</button>
      </form>
    </div>
    <p class="muted" style="margin-top:12px;">
      Premier lancement : clique sur <strong>Ouvrir Shopify</strong>, connecte-toi si besoin, va sur la page <strong>Commandes</strong>,
      puis reviens ici et clique sur <strong>Démarrer le traitement Shopify</strong>.
      La session est gardée dans le dossier <code>shopify_bot_profile</code>.
    </p>
  </div>

  <div class="card">
    <h3>Extraction</h3>
    <table>
      <thead>
        <tr>
          <th>Page</th>
          <th>Nom</th>
          <th>Suivi</th>
          <th>Backup</th>
          <th>Statut</th>
          <th>Raison</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
          <tr>
            <td>{{ row.page }}</td>
            <td>{{ row.nom }}</td>
            <td>{{ row.tracking }}</td>
            <td>{{ row.tracking_backup }}</td>
            <td class="{{ 'ok' if row.statut == 'ok' else 'warn' }}">{{ row.statut }}</td>
            <td>{{ row.raison }}</td>
          </tr>
        {% endfor %}
        {% if not rows %}
          <tr><td colspan="6" class="muted">Aucune donnée extraite pour l’instant.</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3>Logs</h3>
    <div class="logs" id="logs">{{ logs }}</div>
  </div>

  <script>
    setInterval(async () => {
      const r = await fetch("/logs");
      const t = await r.text();
      const box = document.getElementById("logs");
      box.textContent = t;
      box.scrollTop = box.scrollHeight;
    }, 2000);
  </script>
</body>
</html>
"""

def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with STATE_LOCK:
        STATE["logs"].append(line)
        STATE["logs"] = STATE["logs"][-400:]


def set_status(status: str) -> None:
    with STATE_LOCK:
        STATE["browser_status"] = status


IGNORE_RELAIS = True
RE_TRACKING_6A = re.compile(r'\b(6A)\s*([0-9]{10})\s*([0-9A-Z])\b', re.IGNORECASE)
RE_TRACKING_116A = re.compile(r'\b(116A)\s*([0-9]{10}[0-9A-Z])\b', re.IGNORECASE)
RE_TRACKING_8J = re.compile(r'\b(8J)\s*([0-9]{10})\s*([0-9A-Z])\b', re.IGNORECASE)
RE_TRACKING_118J = re.compile(r'\b(118J)\s*([0-9]{10}[0-9A-Z])\b', re.IGNORECASE)
RE_TRACKING_INTL = re.compile(r'\b([A-Z]{2}[0-9]{9}[A-Z]{2})\b')
RE_TRACKING_NUMERIC_14 = re.compile(r'\b([0-9]{14})\b')
RE_RELAIS = re.compile(r'\b24R\b|LOCKER|MONDIAL|RELAIS', re.IGNORECASE)
RE_NAME_BLOCK = re.compile(r'CP71 France\s+(.*?)\s+Réf desti\s*:', re.IGNORECASE | re.DOTALL)

def clean_text(text: str) -> str:
    text = text.replace('\x00', ' ').replace('\uFFFE', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def normalize_name(name: str) -> str:
    name = clean_text(name).replace('\n', ' ').strip()
    return re.sub(r'\s+', ' ', name)

def smart_title(name: str) -> str:
    raw = normalize_name(name)
    return raw.title() if raw.isupper() else raw

def extract_name(page_text: str) -> Optional[str]:
    m = RE_NAME_BLOCK.search(page_text)
    if not m:
        return None
    block = m.group(1).strip()
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    name = re.sub(r'^(Destinataire / Recipient)\s*', '', lines[0], flags=re.I).strip()
    return smart_title(name) if name else None

def extract_tracking(page_text: str) -> Tuple[Optional[str], Optional[str], str]:
    m = RE_TRACKING_6A.search(page_text)
    if m:
        tracking = f"{m.group(1).upper()}{m.group(2)}{m.group(3).upper()}"
        backup = None
        m2 = RE_TRACKING_116A.search(page_text)
        if m2:
            backup = f"{m2.group(1).upper()}{m2.group(2).upper()}"
        return tracking, backup, "trouvé via motif 6A"
    m = RE_TRACKING_8J.search(page_text)
    if m:
        tracking = f"{m.group(1).upper()}{m.group(2)}{m.group(3).upper()}"
        backup = None
        m2 = RE_TRACKING_118J.search(page_text)
        if m2:
            backup = f"{m2.group(1).upper()}{m2.group(2).upper()}"
        return tracking, backup, "trouvé via motif 8J"
    m = RE_TRACKING_116A.search(page_text)
    if m:
        return f"{m.group(1).upper()}{m.group(2).upper()}", None, "trouvé via motif 116A (secours)"
    m = RE_TRACKING_118J.search(page_text)
    if m:
        return f"{m.group(1).upper()}{m.group(2).upper()}", None, "trouvé via motif 118J (secours)"
    m = RE_TRACKING_INTL.search(page_text)
    if m:
        return m.group(1).upper(), None, "trouvé via motif international"
    m = RE_TRACKING_NUMERIC_14.search(page_text)
    if m:
        return m.group(1), None, "trouvé via motif numérique 14"
    return None, None, "aucun suivi détecté"

def is_relais_page(page_text: str) -> bool:
    return bool(RE_RELAIS.search(page_text))

def extract_from_pdf(pdf_path: Path) -> List[Dict[str, str]]:
    reader = PdfReader(str(pdf_path))
    rows: List[Dict[str, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        if not text:
            rows.append({"page": str(idx), "nom": "", "tracking": "", "tracking_backup": "", "statut": "a_verifier", "raison": "page vide / non lisible"})
            continue
        if IGNORE_RELAIS and is_relais_page(text):
            rows.append({"page": str(idx), "nom": "", "tracking": "", "tracking_backup": "", "statut": "ignore", "raison": "page relais / 24R ignorée"})
            continue
        name = extract_name(text)
        tracking, backup, reason = extract_tracking(text)
        status = "ok" if (name and tracking) else "a_verifier"
        rows.append({
            "page": str(idx),
            "nom": name or "",
            "tracking": tracking or "",
            "tracking_backup": backup or "",
            "statut": status,
            "raison": reason + ("" if name else " ; nom non trouvé"),
        })
    return rows

def write_csv(rows: List[Dict[str, str]], output_csv: Path) -> None:
    fieldnames = ["page", "nom", "tracking", "tracking_backup", "statut", "raison"]
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

def load_rows_from_csv(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        return [dict(row) for row in reader]

def hydrate_state_from_latest_csv() -> bool:
    candidates = sorted(UPLOAD_DIR.glob("*_extraction_colissimo.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return False
    csv_path = candidates[0]
    try:
        rows = load_rows_from_csv(csv_path)
    except Exception as e:
        log(f"Impossible de relire le dernier CSV d'extraction : {e}")
        return False

    pdf_candidate = csv_path.with_name(csv_path.name.replace("_extraction_colissimo.csv", ".pdf"))
    with STATE_LOCK:
        STATE["rows"] = rows
        STATE["csv_path"] = str(csv_path)
        STATE["pdf_path"] = str(pdf_candidate) if pdf_candidate.exists() else None
    ok_count = sum(1 for r in rows if r.get("statut") == "ok")
    log(f"État restauré depuis le dernier CSV : {csv_path.name} ({ok_count} ligne(s) OK).")
    return True

def build_shopify_operation_url(store_handle: str, operation_hash: str, operation_name: str, variables: Dict) -> str:
    encoded_vars = quote(json.dumps(variables, separators=(",", ":"), ensure_ascii=False))
    return (
        f"https://admin.shopify.com/api/operations/{operation_hash}/{operation_name}/shopify/"
        f"{store_handle}?operationName={operation_name}&variables={encoded_vars}"
    )

def extract_store_handle(url: str) -> Optional[str]:
    m = STORE_HANDLE_RE.search(url or "")
    return m.group(1) if m else None

def tracking_url(tracking: str) -> str:
    return f"https://www.laposte.fr/outils/suivre-vos-envois?code={tracking}"

def normalize_text_for_match(text: str) -> str:
    text = text or ""
    text = text.strip().lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = text.replace("-", " ").replace("_", " ")
    return " ".join(text.split())

def tokenize_name(name: str) -> List[str]:
    return [w for w in normalize_text_for_match(name).split() if w]

def score_name_match(pdf_name: str, shopify_name: str) -> float:
    a = normalize_text_for_match(pdf_name)
    b = normalize_text_for_match(shopify_name)
    if not a or not b:
        return 0.0
    a_words = set(tokenize_name(a))
    b_words = set(tokenize_name(b))
    common = len(a_words & b_words)
    max_words = max(len(a_words), 1)
    word_score = common / max_words
    fuzzy_score = difflib.SequenceMatcher(None, a, b).ratio()
    return (word_score * 0.7) + (fuzzy_score * 0.3)

async def safe_click(page, selectors: List[str], timeout: int = 4000) -> bool:
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False

async def safe_fill(page, selectors: List[str], value: str, timeout: int = 4000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.click(timeout=timeout)
            try:
                await loc.fill("")
            except Exception:
                pass
            await loc.fill(value, timeout=timeout)
            return True
        except Exception:
            continue
    return False

async def open_shopify(context):
    page = await context.new_page()
    await page.goto("https://admin.shopify.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    return page

async def shopify_fetch_json(page, url: str, method: str = "GET", body: Optional[Dict] = None) -> Dict:
    result = await page.evaluate(
        """
        async ({url, method, body}) => {
          const node = document.querySelector('[data-serialized-id="server-data"]');
          const token = node ? JSON.parse(node.textContent).csrfToken : null;
          const headers = {accept: 'application/json'};
          if (method !== 'GET') {
            headers['content-type'] = 'application/json';
            if (token) headers['x-csrf-token'] = token;
          }
          const response = await fetch(url, {
            method,
            credentials: 'include',
            headers,
            body: body ? JSON.stringify(body) : undefined,
          });
          return {status: response.status, text: await response.text()};
        }
        """,
        {"url": url, "method": method, "body": body},
    )
    if result["status"] >= 400:
        raise RuntimeError(f"Erreur Shopify API ({result['status']}) : {result['text'][:400]}")
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Réponse Shopify non JSON : {result['text'][:400]}") from e

async def ensure_orders_page(page) -> str:
    store_handle = None
    for _ in range(12):
        store_handle = extract_store_handle(page.url)
        if store_handle:
            break
        try:
            hrefs = await page.locator('a[href*="/store/"]').evaluate_all(
                "els => els.map(el => el.getAttribute('href')).filter(Boolean)"
            )
        except Exception:
            hrefs = []
        for href in hrefs:
            store_handle = extract_store_handle(href)
            if store_handle:
                break
        if store_handle:
            break
        await page.wait_for_timeout(500)
    if not store_handle:
        raise RuntimeError(f"Impossible de déterminer la boutique Shopify depuis l'URL courante ({page.url}).")
    target_url = f"https://admin.shopify.com/store/{store_handle}/orders"
    if "/orders" not in page.url:
        await page.goto(target_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
    return store_handle

def order_display_name(order: Dict) -> str:
    shipping = order.get("shippingAddress") or {}
    customer = order.get("customer") or {}
    shipping_name = " ".join(filter(None, [shipping.get("firstName"), shipping.get("lastName")])).strip()
    customer_name = " ".join(filter(None, [customer.get("firstName"), customer.get("lastName")])).strip()
    return shipping_name or customer_name

def order_match_score(pdf_name: str, order: Dict) -> float:
    shipping = order.get("shippingAddress") or {}
    customer = order.get("customer") or {}
    candidates = [
        " ".join(filter(None, [shipping.get("firstName"), shipping.get("lastName")])).strip(),
        " ".join(filter(None, [customer.get("firstName"), customer.get("lastName")])).strip(),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return 0.0
    return max(score_name_match(pdf_name, candidate) for candidate in candidates)

async def fetch_orders_list(page, store_handle: str) -> List[Dict]:
    url = build_shopify_operation_url(
        store_handle,
        "48cc555e5f44fb1601c2eed6244ee16867d15938cac4df432d5bfd1645fe5cf5",
        "OrderListData",
        {
            "batchesFulfillmentEnabled": False,
            "ordersFirst": 50,
            "ordersLast": None,
            "before": None,
            "after": None,
            "sortKey": "PROCESSED_AT",
            "reverse": True,
            "skipPurchasingEntity": True,
            "skipBusinessEntity": True,
            "skipCustomer": False,
            "skipFulfillmentDetails": True,
            "skipShippingAddress": False,
            "skipAutoSelectUnfulfilledDetails": True,
        },
    )
    data = await shopify_fetch_json(page, url)
    edges = (((data.get("data") or {}).get("ordersList") or {}).get("edges") or [])
    return [edge.get("node") for edge in edges if edge.get("node")]

def best_order_candidate_from_api(pdf_name: str, orders: List[Dict]) -> Tuple[float, Optional[Dict]]:
    def filter_orders(colissimo_only: bool) -> List[Dict]:
        filtered = []
        for order in orders:
            shipping_title = ((order.get("shippingLine") or {}).get("title") or "")
            fulfillment_status = order.get("displayFulfillmentStatus")
            if fulfillment_status != "UNFULFILLED":
                continue
            if colissimo_only and "colissimo" not in normalize_text_for_match(shipping_title):
                continue
            filtered.append(order)
        return filtered

    for subset in (filter_orders(colissimo_only=True), filter_orders(colissimo_only=False)):
        scored = [(order_match_score(pdf_name, order), order) for order in subset]
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return scored[0]
    return 0.0, None

async def fetch_open_fulfillment_order(page, store_handle: str, order_id: str) -> Optional[Dict]:
    url = build_shopify_operation_url(
        store_handle,
        "37ee3d4335dae4c0b26b85b523957542b3205f6f6f83ee57fb9992ffcfa81d52",
        "OrderFulfillmentOrdersQuery",
        {
            "isBatchesFulfillmentFlowEnabled": False,
            "orderId": order_id,
            "first": 25,
        },
    )
    data = await shopify_fetch_json(page, url)
    edges = ((((data.get("data") or {}).get("order") or {}).get("fulfillmentOrders") or {}).get("edges") or [])
    for edge in edges:
        node = edge.get("node") or {}
        if node.get("status") != "OPEN":
            continue
        line_items = []
        li_edges = (((node.get("lineItems") or {}).get("edges")) or [])
        for li_edge in li_edges:
            li_node = li_edge.get("node") or {}
            qty = li_node.get("remainingQuantity") or 0
            if qty <= 0:
                continue
            line_items.append({"id": li_node.get("id"), "quantity": qty})
        if line_items:
            return {"id": node.get("id"), "line_items": line_items}
    return None

async def create_shopify_fulfillment(page, store_handle: str, fulfillment_order_id: str, line_items: List[Dict], tracking: str) -> Dict:
    mutation = """
    mutation CreateFulfillment($fulfillment: FulfillmentV2Input!, $message: String) {
      fulfillmentCreateV2(fulfillment: $fulfillment, message: $message) {
        fulfillment {
          id
          status
          trackingInfo(first: 5) {
            company
            number
            url
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    payload = {
        "operationName": "CreateFulfillment",
        "variables": {
            "fulfillment": {
                "notifyCustomer": True,
                "trackingInfo": {
                    "number": tracking,
                    "company": "Colissimo",
                    "url": tracking_url(tracking),
                },
                "lineItemsByFulfillmentOrder": [
                    {
                        "fulfillmentOrderId": fulfillment_order_id,
                        "fulfillmentOrderLineItems": line_items,
                    }
                ],
            },
            "message": None,
        },
        "query": mutation,
    }
    url = f"https://admin.shopify.com/api/shopify/{store_handle}?operation=CreateFulfillment&type=mutation"
    data = await shopify_fetch_json(page, url, method="POST", body=payload)
    result = (data.get("data") or {}).get("fulfillmentCreateV2") or {}
    errors = result.get("userErrors") or []
    if errors:
        joined = " | ".join(err.get("message", "erreur inconnue") for err in errors)
        raise RuntimeError(f"Erreur fulfillment Shopify : {joined}")
    fulfillment = result.get("fulfillment")
    if not fulfillment:
        raise RuntimeError(f"Réponse fulfillment vide : {data}")
    return fulfillment

async def search_client(page, client_name: str) -> None:
    selectors = ['input[placeholder*="Rechercher"]', 'input[aria-label*="Rechercher"]', 'input[type="search"]']
    filled = await safe_fill(page, selectors, client_name, timeout=5000)
    if not filled:
        raise RuntimeError("Impossible de trouver la barre de recherche Shopify.")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(SEARCH_WAIT_MS)

async def extract_visible_client_candidates(page) -> List[str]:
    candidates, seen = [], set()
    selectors = ['span.Polaris-Text--root.Polaris-Text--bodySm', 'span.Polaris-Text--bodySm', 'td span', 'a span']
    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = await loc.count()
            for i in range(count):
                try:
                    txt = (await loc.nth(i).inner_text()).strip()
                    norm = normalize_text_for_match(txt)
                    if not txt or not norm or norm in seen:
                        continue
                    seen.add(norm)
                    candidates.append(txt)
                except Exception:
                    continue
        except Exception:
            continue
    return candidates

def best_candidate(pdf_name: str, candidates: List[str]) -> Tuple[float, str]:
    scored = [(score_name_match(pdf_name, c), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0] if scored else (0.0, "")

async def click_best_order_row(page, best_name: str) -> bool:
    selectors = [f'text="{best_name}"', f'a:has-text("{best_name}")', f'span:has-text("{best_name}")']
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=5000)
            return True
        except Exception:
            continue
    return False

async def click_mark_as_fulfilled(page) -> bool:
    return await safe_click(page, ['button:has-text("Marquer comme traité")', 'text="Marquer comme traité"', 'span:has-text("Marquer comme traité")'], timeout=7000)

async def fill_tracking_number(page, tracking: str) -> bool:
    return await safe_fill(page, ['input[autocomplete="off"]', 'input[type="text"]'], tracking, timeout=7000)

async def check_notify_customer(page) -> bool:
    for sel in ['input[type="checkbox"]', '[role="checkbox"]']:
        try:
            loc = page.locator(sel).first
            try:
                await loc.check(timeout=3000)
            except Exception:
                await loc.click(timeout=3000)
            return True
        except Exception:
            continue
    return False

async def click_final_confirm(page) -> bool:
    return await safe_click(page, ['button:has-text("Marquer comme traité")', 'text="Marquer comme traité"', 'span:has-text("Marquer comme traité")'], timeout=7000)

async def shopify_worker():
    set_status("preparing")
    log("Ouverture du navigateur Shopify du bot...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(user_data_dir=str(BOT_PROFILE_DIR), headless=False)
        page = await open_shopify(context)
        set_status("ready")
        log("Navigateur ouvert. Connecte-toi à Shopify si besoin, va sur Commandes, puis clique 'Démarrer le traitement Shopify'.")
        while True:
            with STATE_LOCK:
                start_event = STATE["start_event"]
                stop_event = STATE["stop_event"]
            if stop_event and stop_event.is_set():
                log("Préparation annulée.")
                break
            if start_event and start_event.is_set():
                break
            await asyncio.sleep(0.5)

        with STATE_LOCK:
            rows = [r for r in STATE["rows"] if r["statut"] == "ok"]

        if not rows and hydrate_state_from_latest_csv():
            with STATE_LOCK:
                rows = [r for r in STATE["rows"] if r["statut"] == "ok"]

        if not rows:
            log("Aucune ligne OK à traiter.")
            set_status("done")
            await context.close()
            return

        set_status("running")
        log(f"Démarrage du traitement Shopify sur {len(rows)} ligne(s).")
        try:
            store_handle = await ensure_orders_page(page)
            log(f"Boutique Shopify détectée : {store_handle}")
        except Exception as e:
            log(f"Impossible d'ouvrir la page Commandes : {e}")
            set_status("done")
            await context.close()
            return

        for idx, row in enumerate(rows, start=1):
            with STATE_LOCK:
                stop_event = STATE["stop_event"]
            if stop_event and stop_event.is_set():
                log("Traitement stoppé manuellement.")
                break

            nom_pdf = row["nom"].strip()
            tracking = row["tracking"].strip()
            log(f"[{idx}/{len(rows)}] Recherche : {nom_pdf} | suivi : {tracking}")
            try:
                orders = await fetch_orders_list(page, store_handle)
                best_score, best_order = best_order_candidate_from_api(nom_pdf, orders)
                if not best_order:
                    log("Aucune commande Shopify non traitée trouvée.")
                    continue
                best_name = order_display_name(best_order)
                log(f"Meilleur match : {best_order.get('name')} | {best_name} | score={best_score:.2f}")
                if best_score < MIN_AUTO_SCORE:
                    log("Score trop faible -> ligne sautée pour sécurité.")
                    continue
                fulfillment_order = await fetch_open_fulfillment_order(page, store_handle, best_order["id"])
                if not fulfillment_order:
                    log("Aucun fulfillment order ouvert trouvé pour cette commande.")
                    continue
                fulfillment = await create_shopify_fulfillment(
                    page,
                    store_handle,
                    fulfillment_order["id"],
                    fulfillment_order["line_items"],
                    tracking,
                )
                log(
                    f"Commande {best_order.get('name')} traitée avec succès. "
                    f"Fulfillment={fulfillment.get('id')} | suivi={tracking}"
                )
            except Exception as e:
                log(f"Erreur Shopify : {e}")

        set_status("done")
        log("Traitement terminé. La session Shopify reste stockée dans 'shopify_bot_profile'.")
        await context.close()

def start_prepare_thread() -> None:
    with STATE_LOCK:
        if STATE["worker_thread"] and STATE["worker_thread"].is_alive():
            return
        STATE["start_event"] = threading.Event()
        STATE["stop_event"] = threading.Event()
        t = threading.Thread(target=lambda: asyncio.run(shopify_worker()), daemon=True)
        STATE["worker_thread"] = t
        t.start()

@app.route("/", methods=["GET"])
def index():
    with STATE_LOCK:
        rows = list(STATE["rows"])
        csv_path = STATE["csv_path"]
        pdf_path = STATE["pdf_path"]
        logs = "\n".join(STATE["logs"][-200:])
        browser_status = STATE["browser_status"]
    ok_count = sum(1 for r in rows if r["statut"] == "ok")
    return render_template_string(
        HTML,
        rows=rows,
        csv_name=Path(csv_path).name if csv_path else None,
        pdf_name=Path(pdf_path).name if pdf_path else None,
        logs=logs,
        browser_status=browser_status,
        ok_count=ok_count,
    )

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("pdf_file")
    if not file or not file.filename.lower().endswith(".pdf"):
        log("Upload refusé : il faut un PDF.")
        return redirect(url_for("index"))
    pdf_path = UPLOAD_DIR / Path(file.filename).name
    file.save(pdf_path)
    try:
        rows = extract_from_pdf(pdf_path)
        csv_path = pdf_path.with_name(pdf_path.stem + "_extraction_colissimo.csv")
        write_csv(rows, csv_path)
        with STATE_LOCK:
            STATE["rows"] = rows
            STATE["csv_path"] = str(csv_path)
            STATE["pdf_path"] = str(pdf_path)
        ok_count = sum(1 for r in rows if r["statut"] == "ok")
        log(f"PDF chargé : {pdf_path.name}")
        log(f"Extraction terminée : {ok_count} ligne(s) OK.")
    except Exception as e:
        log(f"Erreur extraction PDF : {e}")
    return redirect(url_for("index"))

@app.route("/download-csv", methods=["GET"])
def download_csv():
    with STATE_LOCK:
        csv_path = STATE["csv_path"]
    if not csv_path or not Path(csv_path).exists():
        return redirect(url_for("index"))
    return send_file(csv_path, as_attachment=True)

@app.route("/prepare-shopify", methods=["POST"])
def prepare_shopify():
    start_prepare_thread()
    log("Demande de préparation Shopify envoyée.")
    return redirect(url_for("index"))

@app.route("/run-shopify", methods=["POST"])
def run_shopify():
    with STATE_LOCK:
        start_event = STATE["start_event"]
        status = STATE["browser_status"]
    if not start_event:
        log("Prépare d'abord Shopify avant de démarrer le traitement.")
    elif status not in ("ready", "running"):
        log(f"Shopify pas prêt. Statut actuel : {status}")
    else:
        start_event.set()
        log("Signal de démarrage envoyé au bot Shopify.")
    return redirect(url_for("index"))

@app.route("/clear", methods=["POST"])
def clear():
    with STATE_LOCK:
        stop_event = STATE["stop_event"]
        if stop_event:
            stop_event.set()
        STATE["rows"] = []
        STATE["csv_path"] = None
        STATE["pdf_path"] = None
        STATE["logs"] = []
        STATE["browser_status"] = "idle"
        STATE["worker_thread"] = None
        STATE["start_event"] = None
        STATE["stop_event"] = None
    return redirect(url_for("index"))

@app.route("/logs", methods=["GET"])
def logs():
    with STATE_LOCK:
        return Response("\n".join(STATE["logs"][-200:]), mimetype="text/plain; charset=utf-8")

if __name__ == "__main__":
    print(f"Plateforme lancée sur http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
