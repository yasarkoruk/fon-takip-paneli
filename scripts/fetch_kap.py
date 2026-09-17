"""Official KAP archive. No browser live queries or keyword-based insolvency verdicts.

KAP's own current client uses FILTERYFBF/{memberOid}/ALL/{days} and
notification/attachment-detail/{index}. Full rolling list on every run recovers
missed runs; IDs deduplicate; failed details stay pending for the next run.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

from .common import ROOT, ISTANBUL, now_istanbul, read_json, write_json_atomic

ARCHIVE = ROOT / "data" / "kap" / "archive.json"
BASE = "https://www.kap.org.tr/tr/"


class BlockText(HTMLParser):
    """Extract published text blocks, not hidden editor UI or HTML scripts."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            classes = dict(attrs).get("class", "").split()
            if self.depth or "text-block-value" in classes:
                self.depth += 1
        if self.depth and tag in ("br", "p"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1
            if not self.depth:
                self.parts.append(" ")

    def handle_data(self, text):
        if self.depth:
            self.parts.append(text)


def body_text(bodies):
    parser = BlockText()
    for body in bodies:
        if not isinstance(body, str):
            raise ValueError("KAP bildirim gövdesi şeması değişti")
        parser.feed(body)
    return " ".join("".join(parser.parts).split())


def request_json(path, config):
    failure = None
    for attempt in range(config["max_retries"]):
        remaining = config.get("_deadline", time.monotonic() + 480) - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("KAP çalışma süresi sınırına ulaşıldı; eksik kayıtlar sonraki kontrolde yeniden denenecek")
        try:
            request = urllib.request.Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "FonTakipPaneli/2 KAP public disclosures"})
            with urllib.request.urlopen(request, timeout=min(config["timeout_seconds"], max(1, remaining))) as response:
                return json.load(response)
        except Exception as error:
            failure = error
            if attempt + 1 < config["max_retries"]:
                time.sleep(min(2 ** attempt, max(0, remaining)))
    raise RuntimeError(f"KAP sorgusu başarısız ({path}): {failure}")


def normalize(item, code):
    basic = item["disclosureBasic"]
    index = int(basic["disclosureIndex"])
    if index <= 0:
        raise ValueError("Geçersiz KAP bildirim numarası")
    timestamp = datetime.strptime(basic["publishDate"], "%d.%m.%Y %H:%M:%S").replace(tzinfo=ISTANBUL)
    stocks = {x.strip() for x in (basic.get("relatedStocks") or "").split(",")}
    direct = basic.get("stockCode") == code
    if not direct and code not in stocks:
        raise ValueError(f"KAP kaynak/fon eşleşmesi bulunamadı: {code}/{index}")
    return {"id": index, "published_at": timestamp.isoformat(), "title": basic.get("title") or "Bildirim",
            "summary": basic.get("summary") or "", "issuer": basic.get("companyTitle") or "",
            "code": code, "scope": "Fon" if direct else "İlişkili bildirim",
            "url": BASE + f"Bildirim/{index}", "body": None, "detail_checked_at": None,
            "candidate": False, "attachment_count": basic.get("attachmentCount", 0)}


def merge_records(old, new):
    merged = {row["id"]: dict(row) for row in old}
    for row in new:
        previous = merged.get(row["id"], {})
        # List metadata can be corrected; a failed/missing detail never erases it.
        merged[row["id"]] = {**previous, **{k: v for k, v in row.items() if k not in ("body", "detail_checked_at", "candidate")}}
        for key in ("body", "detail_checked_at", "candidate"):
            merged[row["id"]].setdefault(key, row[key])
    return sorted(merged.values(), key=lambda row: (row["published_at"], row["id"]), reverse=True)


def needs_review(text):
    # These are review candidates, not a confirmed default/bankruptcy label.
    return bool(re.search(r"temerrüt|likidite|tasfiye|iade ödem|işlem.*durdur|alım.*satım.*durdur|valör", text.casefold()))


def fetch_detail(index, config):
    result = request_json(f"api/notification/attachment-detail/{index}", config)
    if not isinstance(result, list) or not result:
        raise ValueError(f"KAP detay şeması değişti: {index}")
    first = result[0]
    basic = first["disclosure"]["disclosureBasic"]
    if int(basic["disclosureIndex"]) != index:
        raise ValueError("KAP detay numarası eşleşmedi")
    return body_text(first["disclosureBody"]), basic


def detail_timestamp(value):
    return datetime.strptime(value, "%Y.%m.%d %H:%M:%S").replace(tzinfo=ISTANBUL).isoformat()


def rapid_needed(archive):
    reviewed = {event["disclosure_id"] for event in archive.get("reviewed_events", [])}
    return (not archive or archive.get("status", {}).get("state") != "ok"
            or any(event["state"] == "active" for event in archive.get("reviewed_events", []))
            or any(row.get("candidate") and row["id"] not in reviewed
                   for rows in archive.get("funds", {}).values() for row in rows))


def collect(config=None):
    config = dict(config or read_json(ROOT / "config" / "kap.json", {}))
    config["_deadline"] = time.monotonic() + config.get("max_runtime_seconds", 480)
    archive = read_json(ARCHIVE, {"funds": {}, "reviewed_events": [], "status": {}})
    started = now_istanbul().isoformat()
    errors, new_count = [], 0
    for source in config["sources"]:
        code = source["code"]
        old = archive["funds"].get(code, [])
        try:
            rows = request_json(f"api/disclosure/filter/FILTERYFBF/{source['member_oid']}/ALL/{config['lookback_days']}", config)
            if not isinstance(rows, list):
                raise ValueError("KAP liste şeması değişti")
            normalized = [normalize(row, code) for row in rows]
            new_count += len({r["id"] for r in normalized} - {r["id"] for r in old})
            archive["funds"][code] = merge_records(old, normalized)
        except Exception as error:
            errors.append(str(error))
        records = archive["funds"].get(code, [])
        pending = [r for r in records if not r.get("detail_checked_at") and (r["scope"] == "Fon" and (r["title"] == "Genel Açıklama" or needs_review(r["summary"])))]
        for row in pending[:config["max_details_per_run"]]:
            try:
                text, _ = fetch_detail(row["id"], config)
                if not text:
                    raise ValueError(f"KAP açıklama metni alınamadı: {row['id']}")
                row.update(body=text, detail_checked_at=started, candidate=row.get("candidate", False) or needs_review(text))
            except Exception as error:
                errors.append(str(error))
        if len(pending) > config["max_details_per_run"]:
            errors.append(f"{code}: {len(pending)-config['max_details_per_run']} detay sonraki kontrolde tamamlanacak")
    # Explicitly reviewed events persist on outages. No news never means resolved.
    previous_events = {event["disclosure_id"]: event for event in archive.get("reviewed_events", [])}
    for event in config["reviewed_events"]:
        index = event["disclosure_id"]
        try:
            if event["state"] not in ("active", "resolved"):
                raise ValueError("Geçersiz incelenmiş olay durumu")
            text, basic = fetch_detail(index, config)
            if not text or "temerrüt" not in text.casefold():
                raise ValueError(f"İncelenmiş olayın resmi metni doğrulanamadı: {index}")
            if event["code"] != "PUSULA" and basic.get("stockCode") != event["code"]:
                raise ValueError("İncelenmiş olay fon eşleşmesi başarısız")
            if event["code"] == "PUSULA" and "PUSULA" not in basic["companyTitle"]:
                raise ValueError("İncelenmiş olay kurucu eşleşmesi başarısız")
            if event["state"] != "active":
                resolution = event.get("resolution_disclosure_id")
                if not resolution:
                    raise ValueError("Olayın kapanması resmi çözüm bildirimi gerektirir")
                resolution_text, resolution_basic = fetch_detail(resolution, config)
                if not resolution_text or resolution_basic.get("stockCode") != basic.get("stockCode") or resolution_basic["companyTitle"] != basic["companyTitle"] or detail_timestamp(resolution_basic["publishDate"]) <= detail_timestamp(basic["publishDate"]):
                    raise ValueError("Resmi çözüm bildiriminin kapsamı eşleşmedi")
            previous_events[index] = {**event, "url": BASE + f"Bildirim/{index}", "verified_at": started,
                                      "published_at": detail_timestamp(basic["publishDate"]), "source_text": text}
        except Exception as error:
            errors.append(str(error))
    archive["reviewed_events"] = list(previous_events.values())
    old_status = archive.get("status", {})
    archive["status"] = {"state": "error" if errors else "ok", "last_attempt_at": started,
                          "last_success_at": old_status.get("last_success_at") if errors else started,
                          "new_count": new_count, "errors": errors,
                          "coverage": "Yapılandırılmış fonların 365 günlük KAP bildirim listesi; ek dosyalar otomatik yorumlanmaz.",
                          "consecutive_failures": old_status.get("consecutive_failures", 0)+1 if errors else 0}
    write_json_atomic(ARCHIVE, archive)
    return archive


if __name__ == "__main__":
    result = collect()
    print(json.dumps(result["status"], ensure_ascii=False))
    raise SystemExit(1 if result["status"]["state"] == "error" else 0)
