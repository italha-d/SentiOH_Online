#!/usr/bin/env python3
"""
FSAI Food Recall Scraper
------------------------
Collects Food Safety Authority of Ireland food-recall alerts and writes
Excel-friendly CSV files using the same core fields as the supplied sample.

Main output columns:
Recall ID, Product Name, Brand, Pack Size, Batch Code, Use By,
Best Before, Hazard, Published Date, Source URL, Image URL

A second *_needs_review.csv file is created for records where the page layout
is ambiguous or important fields could not be extracted confidently.

Usage example:
    python fsai_recall_scraper.py \
        --from-date 2026-01-01 \
        --to-date 2026-09-07 \
        --output fsai_recalls.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE = "https://www.fsai.ie"
LIST_URL = BASE + "/news-and-alerts/food-alerts?page={page}"

OUTPUT_FIELDS = [
    "Recall ID",
    "Product Name",
    "Brand",
    "Pack Size",
    "Batch Code",
    "Use By",
    "Best Before",
    "Hazard",
    "Published Date",
    "Source URL",
    "Image URL",
]

DAY_RE = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
MONTH_RE = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)


@dataclass
class RecallRow:
    recall_id: str = ""
    product_name: str = ""
    brand: str = ""
    pack_size: str = ""
    batch_code: str = ""
    use_by: str = ""
    best_before: str = ""
    hazard: str = ""
    published_date: str = ""
    source_url: str = ""
    image_url: str = ""

    def csv_dict(self) -> Dict[str, str]:
        return {
            "Recall ID": self.recall_id,
            "Product Name": self.product_name,
            "Brand": self.brand,
            "Pack Size": self.pack_size,
            "Batch Code": self.batch_code,
            "Use By": self.use_by,
            "Best Before": self.best_before,
            "Hazard": self.hazard,
            "Published Date": self.published_date,
            "Source URL": self.source_url,
            "Image URL": self.image_url,
        }


def clean(value: Optional[str]) -> str:
    if not value:
        return ""
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n|")


def norm_header(value: str) -> str:
    s = clean(value).lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()

    if s in {"product", "product name", "product names"}:
        return "Product Name"
    if "product identification" in s:
        return "Product Name"
    if "brand" in s or "manufacturer" in s:
        return "Brand"
    if "pack size" in s or s == "pack":
        return "Pack Size"
    if "batch" in s and ("code" in s or "number" in s or s == "batch"):
        return "Batch Code"
    if "use by" in s:
        return "Use By"
    if "best before" in s:
        return "Best Before"
    if "expiry" in s or "expiration" in s:
        # Legacy 11-column output has no Expiry Date column, so preserve the
        # expiry constraint in Best Before rather than losing it.
        return "Best Before"
    return ""


def parse_iso_date(text: str) -> str:
    """Convert common FSAI publication date text to YYYY-MM-DD."""
    text = clean(text)
    text = re.sub(rf"^{DAY_RE},?\s+", "", text)
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def extract_published_date(soup: BeautifulSoup, text: str) -> str:
    # First prefer semantic <time> markup if FSAI provides it.
    time_el = soup.find("time")
    if time_el:
        if time_el.get("datetime"):
            raw = time_el["datetime"][:10]
            try:
                return datetime.fromisoformat(raw).date().isoformat()
            except ValueError:
                pass
        parsed = parse_iso_date(time_el.get_text(" ", strip=True))
        if parsed:
            return parsed

    m = re.search(
        rf"{DAY_RE},?\s+(\d{{1,2}}\s+{MONTH_RE}\s+\d{{4}})",
        text,
        flags=re.I,
    )
    if m:
        return parse_iso_date(m.group(1))
    return ""


def text_between(text: str, start_label: str, end_labels: Iterable[str]) -> str:
    start = re.search(re.escape(start_label) + r"\s*:?\s*", text, flags=re.I)
    if not start:
        return ""
    tail = text[start.end():]
    end_positions = []
    for label in end_labels:
        m = re.search(r"\n?\s*" + re.escape(label) + r"\s*:?\s*", tail, flags=re.I)
        if m:
            end_positions.append(m.start())
    end = min(end_positions) if end_positions else len(tail)
    return clean(tail[:end])


def extract_alert_id(text: str) -> str:
    m = re.search(r"Alert\s+Notification\s*:?\s*(\d{4}\.\d{1,3})", text, flags=re.I)
    return m.group(1) if m else ""


def extract_hazard(title: str, text: str) -> str:
    """
    Extract a concise hazard/cause without inventing information.
    Examples:
      '... due to the presence of Salmonella' -> 'Salmonella'
      '... due to incorrect sugar-free declaration' -> 'incorrect sugar-free declaration'
    """
    title = clean(title)
    m = re.search(r"\bdue to\s+(?:the\s+)?(?:possible\s+)?presence of\s+(.+)$", title, flags=re.I)
    if m:
        return clean(m.group(1)).rstrip(".")
    m = re.search(r"\bdue to\s+(.+)$", title, flags=re.I)
    if m:
        return clean(m.group(1)).rstrip(".")

    # Conservative fallback from the Message text.
    m = re.search(
        r"\b(?:recalled|recalling)\b.{0,180}?\bdue to\s+(?:the\s+)?(?:possible\s+)?presence of\s+([^.\n]+)",
        text,
        flags=re.I,
    )
    if m:
        return clean(m.group(1))
    return ""


def extract_image_url(soup: BeautifulSoup, page_url: str) -> str:
    """
    Prefer product/article media and avoid obvious site chrome.
    FSAI product images commonly use /getmedia/ or /getattachment/.
    """
    candidates: List[str] = []
    for container in (soup.find("main"), soup.find("article"), soup):
        if not container:
            continue
        for img in container.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if not src:
                continue
            full = urljoin(page_url, src)
            low = full.lower()
            alt = clean(img.get("alt", "")).lower()
            if any(x in low for x in ("logo", "icon", "sprite")):
                continue
            if any(x in alt for x in ("logo", "facebook", "twitter", "linkedin")):
                continue
            if "/getmedia/" in low or "/getattachment/" in low:
                return full
            candidates.append(full)
        if candidates:
            break
    return candidates[0] if candidates else ""


def parse_product_identification(text: str) -> Tuple[str, str]:
    raw = text_between(
        text,
        "Product Identification",
        ["Batch Code", "Country Of Origin", "Country of Origin", "Message"],
    )
    if not raw or "please see" in raw.lower():
        return "", ""

    pack = ""
    m = re.search(r"(?:pack\s*size)\s*:?\s*([^;]+)", raw, flags=re.I)
    if m:
        pack = clean(m.group(1))
        raw = clean(raw[:m.start()].rstrip(";"))
    return raw, pack



def parse_summary_batch(text: str) -> Tuple[str, str, str]:
    raw = text_between(
        text,
        "Batch Code",
        ["Country Of Origin", "Country of Origin", "Message"],
    )
    if (
        not raw
        or "please see" in raw.lower()
        or "see table" in raw.lower()
        or "see below" in raw.lower()
    ):
        return "", "", ""

    # Split labelled date clauses rather than greedily treating the remainder
    # of the summary as one date value.
    labels = list(
        re.finditer(
            r"\b(use[- ]?by(?:\s+date)?|best\s+before(?:\s+date)?|"
            r"expiry(?:\s+date)?)\s*:?\s*",
            raw,
            flags=re.I,
        )
    )

    batch = clean(raw[:labels[0].start()].rstrip(";,: ")) if labels else clean(raw)
    use_by = ""
    best_before = ""

    for idx, match in enumerate(labels):
        value_start = match.end()
        value_end = labels[idx + 1].start() if idx + 1 < len(labels) else len(raw)
        value = clean(raw[value_start:value_end].rstrip(";,: "))
        label = match.group(1).lower()

        if "use" in label:
            use_by = value
        else:
            # Legacy schema has no Expiry Date column. Keep an explicit expiry
            # constraint here rather than silently discarding it.
            best_before = value

    return batch, use_by, best_before


SUMMARY_LABEL_RE = re.compile(
    r"^(?:category\s*\d*|alert notification|product identification|"
    r"country of origin|country of origin:|batch code|message|"
    r"pack size|use[- ]?by(?: date)?|best before(?: date)?|"
    r"expiry date|approval number)\s*:?$",
    flags=re.I,
)


def is_label_like_product(value: str) -> bool:
    value = clean(value)
    return bool(value and SUMMARY_LABEL_RE.fullmatch(value))


def _table_matrix(table) -> List[List[str]]:
    """
    Expand an HTML table into a rectangular logical grid while respecting
    rowspan and colspan. This is essential for FSAI tables where a product,
    pack size, or date is visually shared across multiple batch rows.
    """
    rows: List[List[str]] = []
    active: Dict[int, Tuple[str, int]] = {}

    for tr in table.find_all("tr"):
        inherited = dict(active)
        logical: Dict[int, str] = {
            col: value
            for col, (value, remaining) in inherited.items()
            if remaining > 0
        }
        new_spans: Dict[int, Tuple[str, int]] = {}

        col = 0
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])

        for cell in cells:
            while col in logical:
                col += 1

            value = clean(cell.get_text(" ", strip=True))
            try:
                rowspan = max(int(cell.get("rowspan", 1)), 1)
            except (TypeError, ValueError):
                rowspan = 1
            try:
                colspan = max(int(cell.get("colspan", 1)), 1)
            except (TypeError, ValueError):
                colspan = 1

            for offset in range(colspan):
                logical[col + offset] = value
                if rowspan > 1:
                    new_spans[col + offset] = (value, rowspan - 1)

            col += colspan

        if logical:
            max_col = max(logical)
            rows.append([logical.get(i, "") for i in range(max_col + 1)])

        # Existing spans age by one row; newly created spans begin next row.
        next_active: Dict[int, Tuple[str, int]] = {}
        for span_col, (value, remaining) in inherited.items():
            if remaining - 1 > 0:
                next_active[span_col] = (value, remaining - 1)
        next_active.update(new_spans)
        active = next_active

    if not rows:
        return []

    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def _looks_like_alert_summary(matrix: List[List[str]]) -> bool:
    """
    FSAI pages commonly contain a two-column 'Alert Summary' key/value table.
    Product Identification / Batch Code / Country Of Origin are field labels,
    not product rows. Reject these tables before product parsing.
    """
    if not matrix:
        return False

    first_col = [
        clean(row[0])
        for row in matrix
        if row and clean(row[0])
    ]
    if not first_col:
        return False

    summary_labels = sum(
        bool(SUMMARY_LABEL_RE.fullmatch(value))
        for value in first_col
    )
    return (
        summary_labels >= 2
        and summary_labels / len(first_col) >= 0.4
    )


def table_to_rows(
    soup: BeautifulSoup,
    default_product: str,
    default_pack: str,
) -> List[Dict[str, str]]:
    """
    Parse only genuine product-detail tables.

    Key safeguards:
    - rejects Alert Summary key/value tables;
    - understands rowspan/colspan;
    - requires at least two recognised product-detail headers;
    - ignores retailer/category group rows such as 'Aldi' or 'Tesco';
    - never treats 'Batch Code' / 'Country Of Origin' labels as products.
    """
    results: List[Dict[str, str]] = []

    for table in soup.find_all("table"):
        matrix = _table_matrix(table)
        if len(matrix) < 2:
            continue

        if _looks_like_alert_summary(matrix):
            continue

        header_idx = None
        headers: List[str] = []

        for i, vals in enumerate(matrix[:6]):
            mapped = [norm_header(v) for v in vals]
            recognised = [x for x in mapped if x]

            # One recognised cell is too weak and was the main reason Alert
            # Summary tables were previously misclassified as product tables.
            if (
                len(recognised) >= 2
                and any(
                    x in recognised
                    for x in (
                        "Product Name",
                        "Batch Code",
                        "Use By",
                        "Best Before",
                    )
                )
            ):
                header_idx = i
                headers = mapped
                break

        if header_idx is None:
            continue

        last_product = default_product
        last_pack = default_pack

        for vals in matrix[header_idx + 1:]:
            if not vals or all(not clean(v) for v in vals):
                continue

            mapped_row: Dict[str, str] = {}
            for idx, val in enumerate(vals):
                if idx >= len(headers):
                    continue
                header = headers[idx]
                if not header:
                    continue
                value = clean(val)
                if value and header not in mapped_row:
                    mapped_row[header] = value

            if not mapped_row:
                continue

            # A colspan group heading is expanded to the same text in several
            # logical columns. It is not a product row.
            nonempty_values = [
                clean(value)
                for value in mapped_row.values()
                if clean(value)
            ]
            if (
                len(nonempty_values) >= 2
                and len(set(nonempty_values)) == 1
            ):
                continue

            raw_product = clean(mapped_row.get("Product Name", ""))
            raw_pack = clean(mapped_row.get("Pack Size", ""))
            batch = clean(mapped_row.get("Batch Code", ""))
            use_by = clean(mapped_row.get("Use By", ""))
            best_before = clean(mapped_row.get("Best Before", ""))

            # Reject label artefacts even if malformed HTML shifts them under
            # the Product Name column.
            if raw_product and is_label_like_product(raw_product):
                continue

            meaningful_scope = bool(
                raw_pack or batch or use_by or best_before
            )

            # A row containing only a retailer/category name is a group heading,
            # not a product. Rowspan-expanded real product rows normally also
            # have pack/batch/date evidence.
            if raw_product and not meaningful_scope:
                continue

            product = raw_product or last_product
            pack = raw_pack or last_pack

            if product and not is_label_like_product(product):
                last_product = product
            if pack:
                last_pack = pack

            record = {
                "Product Name": product,
                "Brand": clean(mapped_row.get("Brand", "")),
                "Pack Size": pack,
                "Batch Code": batch,
                "Use By": use_by,
                "Best Before": best_before,
            }

            if (
                record["Product Name"]
                and not is_label_like_product(record["Product Name"])
                and any(
                    record[k]
                    for k in (
                        "Pack Size",
                        "Batch Code",
                        "Use By",
                        "Best Before",
                    )
                )
            ):
                results.append(record)

    return results


def split_multi_value(value: str) -> List[str]:
    value = clean(value)
    if not value:
        return [""]
    # Semicolon is the safest separator because commas often occur inside names.
    parts = [clean(x) for x in re.split(r"\s*;\s*", value) if clean(x)]
    return parts or [""]


def explode_parallel_values(record: Dict[str, str]) -> List[Dict[str, str]]:
    """
    If a single HTML row stores multiple batch codes and multiple dates separated
    by semicolons, expand them into separate output rows when the counts align.
    """
    b = split_multi_value(record.get("Batch Code", ""))
    u = split_multi_value(record.get("Use By", ""))
    bb = split_multi_value(record.get("Best Before", ""))

    lengths = [len(x) for x in (b, u, bb) if len(x) > 1]
    if not lengths:
        return [record]

    n = max(lengths)
    if any(len(x) not in (1, n) for x in (b, u, bb)):
        return [record]

    out = []
    for i in range(n):
        r = dict(record)
        r["Batch Code"] = b[i] if len(b) == n else b[0]
        r["Use By"] = u[i] if len(u) == n else u[0]
        r["Best Before"] = bb[i] if len(bb) == n else bb[0]
        out.append(r)
    return out


def parse_alert_page(html: str, page_url: str) -> Tuple[List[RecallRow], List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("article") or soup
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)

    heading = main.find(["h1", "h2"]) or soup.find(["h1", "h2"])
    title = clean(heading.get_text(" ", strip=True)) if heading else clean(soup.title.string if soup.title else "")

    recall_id = extract_alert_id(text)
    published = extract_published_date(soup, text)
    hazard = extract_hazard(title, text)
    image_url = extract_image_url(soup, page_url)

    default_product, default_pack = parse_product_identification(text)
    summary_batch, summary_use_by, summary_best_before = parse_summary_batch(text)

    raw_table_rows = table_to_rows(soup, default_product, default_pack)
    table_rows: List[Dict[str, str]] = []
    for r in raw_table_rows:
        table_rows.extend(explode_parallel_values(r))

    reasons: List[str] = []
    if not recall_id:
        reasons.append("Recall ID not found")
    if not published:
        reasons.append("Published date not found")
    if not hazard:
        reasons.append("Hazard/cause not found")
    if not image_url:
        reasons.append("Product image URL not found")

    if table_rows:
        product_rows = table_rows
    else:
        product_rows = [{
            "Product Name": default_product,
            "Brand": "",
            "Pack Size": default_pack,
            "Batch Code": summary_batch,
            "Use By": summary_use_by,
            "Best Before": summary_best_before,
        }]
        # Summary-only pages often contain compressed multi-batch wording.
        raw_batch_area = text_between(
            text,
            "Batch Code",
            ["Country Of Origin", "Country of Origin", "Message"],
        )
        if re.search(r"\b(and|;)\b", raw_batch_area, flags=re.I):
            reasons.append("Batch details are compressed in summary text; check whether row expansion is required")

    rows: List[RecallRow] = []
    for r in product_rows:
        row = RecallRow(
            recall_id=recall_id,
            product_name=clean(r.get("Product Name", "")),
            brand=clean(r.get("Brand", "")),
            pack_size=clean(r.get("Pack Size", "")),
            batch_code=clean(r.get("Batch Code", "")),
            use_by=clean(r.get("Use By", "")),
            best_before=clean(r.get("Best Before", "")),
            hazard=hazard,
            published_date=published,
            source_url=page_url,
            image_url=image_url,
        )
        if not row.product_name:
            reasons.append("Product name not confidently extracted")
        rows.append(row)

    # Deduplicate while preserving order.
    unique: List[RecallRow] = []
    seen = set()
    for r in rows:
        key = tuple(r.csv_dict().values())
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique, sorted(set(reasons))


def within_date_range(iso_date: str, start: Optional[date], end: Optional[date]) -> bool:
    if not iso_date:
        return True  # keep it, but it will go to review
    try:
        d = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return True
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def write_csv(path: Path, rows: List[RecallRow]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.csv_dict())


def write_review_csv(path: Path, review_rows: List[Tuple[RecallRow, str]]) -> None:
    fields = OUTPUT_FIELDS + ["Review Reason"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row, reason in review_rows:
            d = row.csv_dict()
            d["Review Reason"] = reason
            writer.writerow(d)


def is_detail_alert_url(href: str) -> bool:
    p = urlparse(href)
    path = p.path.rstrip("/")
    prefix = "/news-and-alerts/food-alerts/"
    return path.startswith(prefix) and path != prefix.rstrip("/")


def discover_urls(page, max_pages: int, delay: float) -> List[str]:
    found: List[str] = []
    seen = set()
    empty_pages = 0

    for n in range(1, max_pages + 1):
        url = LIST_URL.format(page=n)
        print(f"[list] page {n}: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(700)

        hrefs = page.locator("a[href]").evaluate_all(
            "(els) => els.map(e => e.href)"
        )
        page_new = 0
        for href in hrefs:
            if is_detail_alert_url(href):
                href = href.split("#", 1)[0]
                if href not in seen:
                    seen.add(href)
                    found.append(href)
                    page_new += 1

        if page_new == 0:
            empty_pages += 1
        else:
            empty_pages = 0

        # Two consecutive pages with no unseen detail URLs usually means the end.
        if empty_pages >= 2:
            break
        time.sleep(delay)

    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape FSAI food recall alerts into Excel-friendly CSV.")
    ap.add_argument("--from-date", help="Earliest publication date, YYYY-MM-DD")
    ap.add_argument("--to-date", help="Latest publication date, YYYY-MM-DD")
    ap.add_argument("--max-pages", type=int, default=30, help="Maximum FSAI listing pages to scan")
    ap.add_argument("--delay", type=float, default=1.0, help="Delay between requests/pages in seconds")
    ap.add_argument("--output", default="fsai_recalls.csv", help="Main CSV output filename")
    ap.add_argument("--show-browser", action="store_true", help="Run Chromium visibly instead of headless")
    args = ap.parse_args()

    start = datetime.strptime(args.from_date, "%Y-%m-%d").date() if args.from_date else None
    end = datetime.strptime(args.to_date, "%Y-%m-%d").date() if args.to_date else None

    out_path = Path(args.output).resolve()
    review_path = out_path.with_name(out_path.stem + "_needs_review.csv")

    all_rows: List[RecallRow] = []
    review_rows: List[Tuple[RecallRow, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show_browser)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            locale="en-IE",
        )
        page = context.new_page()

        urls = discover_urls(page, args.max_pages, args.delay)
        print(f"[info] discovered {len(urls)} unique food-alert URLs")

        for idx, url in enumerate(urls, 1):
            try:
                print(f"[alert {idx}/{len(urls)}] {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(500)
                html = page.content()
                rows, reasons = parse_alert_page(html, url)

                if not rows:
                    continue

                if not within_date_range(rows[0].published_date, start, end):
                    continue

                # Only retain recall/update-to-recall pages; exclude unrelated food-alert notices.
                page_title = clean(page.title())
                body_heading = ""
                try:
                    body_heading = clean(page.locator("h1, h2").first.inner_text(timeout=2000))
                except Exception:
                    pass
                combined_title = (body_heading + " " + page_title).lower()
                if "recall" not in combined_title:
                    continue

                all_rows.extend(rows)
                if reasons:
                    reason = "; ".join(reasons)
                    for r in rows:
                        review_rows.append((r, reason))

                time.sleep(args.delay)

            except PlaywrightTimeoutError:
                print(f"[warning] timed out: {url}")
            except Exception as exc:
                print(f"[warning] failed: {url}: {exc}")

        browser.close()

    # Stable sorting: newest date first, then Recall ID and Product Name.
    all_rows.sort(
        key=lambda r: (r.published_date or "0000-00-00", r.recall_id, r.product_name),
        reverse=True,
    )

    # Deduplicate across pages.
    deduped: List[RecallRow] = []
    seen = set()
    for r in all_rows:
        key = tuple(r.csv_dict().values())
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    write_csv(out_path, deduped)
    write_review_csv(review_path, review_rows)

    print(f"\nSaved {len(deduped)} rows to: {out_path}")
    print(f"Review file: {review_path}")
    print(
        "\nImportant: the program does not guess missing Brand values. "
        "If FSAI does not explicitly state a brand/manufacturer in a structured field, "
        "Brand is left blank."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
