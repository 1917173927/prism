"""Lightweight Open-Source OCR Engine for Brokerage Portfolio Screenshots.

Based on RapidOCR (ONNXRuntime) with deterministic confidence thresholds:
- Confidence >= 85.0%: High confidence, auto-accepted.
- Confidence < 85.0%: Low confidence, flagged for user review.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from app.providers.live_market import A_SHARE_DATABASE, ETF_LOOKTHROUGH_DATABASE

CONFIDENCE_THRESHOLD = 0.85

SUMMARY_KEYWORDS = ("总资产", "合计", "总计", "资产总计", "净资产", "可用资金", "资金余额", "可用现金", "可用", "可取")


class OCRPortfolioParser:
    """Extracts structured portfolio holdings and available cash from images using RapidOCR."""

    _instance: OCRPortfolioParser | None = None
    _engine: Any = None

    @classmethod
    def get_instance(cls) -> OCRPortfolioParser:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_engine(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def parse_base64_image(self, base64_str: str) -> dict[str, Any]:
        """Decode base64 string (supports data URI schemes) and run OCR parsing."""
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]
        image_bytes = base64.b64decode(base64_str)
        return self.parse_image_bytes(image_bytes)

    def parse_image_bytes(self, image_bytes: bytes) -> dict[str, Any]:
        """Run OCR on image bytes, cluster bounding boxes into rows, and extract holdings."""
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        processed_bytes = buf.getvalue()

        engine = self._get_engine()
        ocr_result, elapse = engine(processed_bytes)

        if not ocr_result:
            return {
                "status": "EMPTY",
                "schema_version": "portfolio-ocr-bundle.v1",
                "total_value_cny": 0.0,
                "cash_cny": 0.0,
                "positions": [],
                "parsed_count": 0,
                "has_low_confidence_items": False,
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "raw_ocr_lines": [],
            }

        # 1. Spatial clustering into rows by Y-coordinate
        boxes = []
        for item in ocr_result:
            box, text, score = item
            y_center = (box[0][1] + box[2][1]) / 2.0
            x_min = box[0][0]
            boxes.append({
                "box": box,
                "text": text.strip(),
                "score": float(score),
                "yc": y_center,
                "xm": x_min,
            })

        boxes.sort(key=lambda b: b["yc"])
        rows: list[list[dict[str, Any]]] = []
        curr_row: list[dict[str, Any]] = []
        curr_yc = -999.0
        y_tolerance = 18.0

        for b in boxes:
            if not b["text"]:
                continue
            if abs(b["yc"] - curr_yc) > y_tolerance:
                if curr_row:
                    curr_row.sort(key=lambda x: x["xm"])
                    rows.append(curr_row)
                curr_row = [b]
                curr_yc = b["yc"]
            else:
                curr_row.append(b)
        if curr_row:
            curr_row.sort(key=lambda x: x["xm"])
            rows.append(curr_row)

        positions: list[dict[str, Any]] = []
        cash_cny = 0.0
        reported_total_assets = 0.0
        has_low_confidence = False

        # 2. Extract Cash and Summary Totals
        for row in rows:
            row_text = "".join(b["text"] for b in row)
            if any(k in row_text for k in ["可用资金", "资金余额", "可用现金", "可用", "可取"]):
                m = re.search(r"(?:可用资金余额|可用资金|资金余额|可用现金|可用|可取)[:：\s]*([¥￥]?\s*\d+(?:\.\d+)?)", row_text)
                if m:
                    num_str = re.sub(r"[^\d\.]", "", m.group(1))
                    if num_str:
                        cash_cny = float(num_str)
            if any(k in row_text for k in ["总资产合计", "总资产", "净资产", "资产总计"]):
                m = re.search(r"(?:总资产合计|总资产|净资产|资产总计)[:：\s]*([¥￥]?\s*\d+(?:\.\d+)?)", row_text)
                if m:
                    num_str = re.sub(r"[^\d\.]", "", m.group(1))
                    if num_str:
                        reported_total_assets = float(num_str)

        # 3. Extract Security Positions (Filter out summary/header rows)
        seen_codes: set[str] = set()

        for row in rows:
            row_text = "".join(b["text"] for b in row)
            # Skip header or summary rows
            if any(k in row_text for k in SUMMARY_KEYWORDS):
                continue
            if "证券代码" in row_text or "持仓市值" in row_text:
                continue

            row_tokens = [b["text"] for b in row]
            row_scores = [b["score"] for b in row]
            row_combined = " ".join(row_tokens)

            # Look for 6-digit security code
            code_match = re.search(r"\b([0-3568]\d{5})\b", row_combined)
            found_code = code_match.group(1) if code_match else None
            found_name = ""

            # Match against known databases if not found by regex
            if not found_code:
                for db_code, db_info in A_SHARE_DATABASE.items():
                    if db_code in row_combined or db_info["name"] in row_combined:
                        found_code = db_code
                        found_name = db_info["name"]
                        break

            if not found_code:
                for db_code, db_info in ETF_LOOKTHROUGH_DATABASE.items():
                    if db_code in row_combined or db_info["fund_name"] in row_combined:
                        found_code = db_code
                        found_name = db_info["fund_name"]
                        break

            if not found_code or found_code in seen_codes:
                continue

            seen_codes.add(found_code)

            # Determine exchange suffix and asset class
            if found_code.startswith(("6", "5", "688")):
                full_symbol = f"{found_code}.SH"
            elif found_code.startswith(("0", "3", "1")):
                full_symbol = f"{found_code}.SZ"
            else:
                full_symbol = f"{found_code}.BJ"

            is_fund = (
                found_code.startswith(("5", "15", "16"))
                or "ETF" in row_combined.upper()
                or "基金" in row_combined
                or found_code in ETF_LOOKTHROUGH_DATABASE
            )
            asset_class = "FUND_ETF" if is_fund else "EQUITY"

            # Resolve Name
            if not found_name:
                if found_code in A_SHARE_DATABASE:
                    found_name = A_SHARE_DATABASE[found_code]["name"]
                elif found_code in ETF_LOOKTHROUGH_DATABASE:
                    found_name = ETF_LOOKTHROUGH_DATABASE[found_code]["fund_name"]
                else:
                    for tok in row_tokens:
                        clean_tok = re.sub(r"[\d\.\s%¥,]+", "", tok)
                        if len(clean_tok) >= 2 and not any(k in clean_tok for k in ["代码", "名称", "持仓", "数量", "成本", "当前", "市值"]):
                            found_name = clean_tok
                            break
                    if not found_name:
                        found_name = f"证券标的({found_code})"

            # Extract numeric fields excluding code and numbers in the name
            pure_numbers: list[float] = []
            for tok in row_tokens:
                if tok == found_code or tok == found_name:
                    continue
                # If token matches the name or parts of it like '科创50ETF', skip it
                if found_name and tok in found_name:
                    continue
                num_matches = re.findall(r"\b\d+(?:\.\d+)?\b", tok)
                for nm in num_matches:
                    try:
                        n_val = float(nm)
                        if n_val != float(found_code):
                            pure_numbers.append(n_val)
                    except ValueError:
                        continue

            quantity = 1000
            cost_price = 10.0
            price = 10.0
            market_val = 10000.0

            # If tokens map neatly to standard table columns
            # e.g. [code, name, qty, cost, price, market_value]
            if len(pure_numbers) >= 4:
                quantity = int(pure_numbers[0])
                cost_price = pure_numbers[1]
                price = pure_numbers[2]
                market_val = pure_numbers[3]
            elif len(pure_numbers) == 3:
                quantity = int(pure_numbers[0])
                price = pure_numbers[1]
                market_val = pure_numbers[2]
                cost_price = price
            elif len(pure_numbers) == 2:
                quantity = int(pure_numbers[0])
                price = pure_numbers[1]
                cost_price = price
                market_val = round(quantity * price, 2)
            elif len(pure_numbers) == 1:
                quantity = int(pure_numbers[0])
                if found_code in A_SHARE_DATABASE:
                    price = A_SHARE_DATABASE[found_code]["price_cny"]
                elif found_code in ETF_LOOKTHROUGH_DATABASE:
                    price = ETF_LOOKTHROUGH_DATABASE[found_code]["net_asset_value_cny"]
                cost_price = price
                market_val = round(quantity * price, 2)
            else:
                if found_code in A_SHARE_DATABASE:
                    price = A_SHARE_DATABASE[found_code]["price_cny"]
                elif found_code in ETF_LOOKTHROUGH_DATABASE:
                    price = ETF_LOOKTHROUGH_DATABASE[found_code]["net_asset_value_cny"]
                cost_price = price
                market_val = round(quantity * price, 2)

            # Confidence assessment
            min_score = min(row_scores) if row_scores else 0.90
            item_confidence = round(float(min_score), 3)
            is_low_conf = item_confidence < CONFIDENCE_THRESHOLD

            if is_low_conf:
                has_low_confidence = True

            sector = "Technology"
            if found_code in A_SHARE_DATABASE:
                sector = A_SHARE_DATABASE[found_code].get("sector", "Technology")
            elif "宁德" in found_name or "比亚迪" in found_name:
                sector = "Industrials"
            elif "茅台" in found_name or "酒" in found_name:
                sector = "Consumer"

            positions.append({
                "asset_id": full_symbol,
                "name": found_name,
                "asset_class": asset_class,
                "sector": sector,
                "quantity": int(quantity),
                "cost_price": round(float(cost_price), 3),
                "price": round(float(price), 3),
                "market_value_cny": round(float(market_val), 2),
                "confidence": item_confidence,
                "confidence_pct": round(item_confidence * 100, 1),
                "needs_review": is_low_conf,
            })

        total_holdings_val = sum(p["market_value_cny"] for p in positions)
        total_val = round(reported_total_assets if reported_total_assets > 0 else (cash_cny + total_holdings_val), 2)

        return {
            "status": "SUCCESS",
            "schema_version": "portfolio-ocr-bundle.v1",
            "total_value_cny": total_val,
            "cash_cny": round(cash_cny, 2),
            "positions": positions,
            "parsed_count": len(positions),
            "has_low_confidence_items": has_low_confidence,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "raw_ocr_lines": [
                {
                    "text": b["text"],
                    "confidence": round(b["score"], 3),
                    "box": b["box"],
                }
                for b in boxes
            ],
        }
