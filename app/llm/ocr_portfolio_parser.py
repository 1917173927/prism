"""Lightweight Open-Source OCR Engine for Brokerage Portfolio Screenshots.

Based on RapidOCR (ONNXRuntime) with deterministic confidence thresholds:
- Confidence >= 85.0%: High confidence, auto-accepted.
- Confidence < 85.0%: Low confidence, flagged for user review.
"""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any
from uuid import uuid4

from app.providers.live_market import A_SHARE_DATABASE, ETF_LOOKTHROUGH_DATABASE
from app.portfolio.contracts import (
    AssetType,
    FundHoldingSnapshot,
    LookThroughHolding,
    PortfolioImportBundle,
    Position,
    PositionSnapshot,
)

CONFIDENCE_THRESHOLD = 0.85

SUMMARY_KEYWORDS = ("总资产", "合计", "总计", "资产总计", "净资产", "可用资金", "资金余额", "可用现金", "可用", "可取")

# Traceable security identities used only for resolving names displayed by a
# broker.  No price, sector, valuation, or research field is supplied here.
_SECURITY_IDENTITY_SNAPSHOT = {
    "冠农股份": {"asset_id": "600251.SH", "market": "SSE", "source": "SSE listed-company directory"},
    "莲花控股": {"asset_id": "600186.SH", "market": "SSE", "source": "SSE listed-company directory"},
}


def _decimal_cell(text: str) -> Decimal | None:
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned or cleaned in {"-", ".", "-."} or cleaned.count(".") > 1:
        return None
    try:
        value = Decimal(cleaned)
    except ArithmeticError:
        return None
    return value if value.is_finite() else None


def _parse_two_line_broker_layout(
    rows: list[list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse slash-header broker tables with two vertically stacked values."""
    header_index = next((index for index, row in enumerate(rows)
        if "持仓/可用" in "".join(cell["text"] for cell in row)
        and "成本/现价" in "".join(cell["text"] for cell in row)), None)
    if header_index is None:
        return [], []

    headers = [cell for cell in rows[header_index]
               if any(label in cell["text"] for label in
                      ("市值", "持仓/可用", "成本/现价", "盈亏"))]
    if len(headers) != 4:
        return [], []

    def column(cell):
        center = (cell["box"][0][0] + cell["box"][2][0]) / 2
        return min(headers, key=lambda h: abs(
            center - (h["box"][0][0] + h["box"][2][0]) / 2))["text"]

    def values(row, label):
        return [(value, cell) for cell in row if label in column(cell)
                and (value := _decimal_cell(cell["text"])) is not None]

    primary_rows = []
    for index, row in enumerate(rows[header_index + 1:], header_index + 1):
        text = "".join(cell["text"] for cell in row)
        if any(marker in text for marker in ("查看已清仓", "持仓管理", "批量买入", "持仓资讯")):
            break
        if any("市值" in column(cell) and re.search(r"[\u4e00-\u9fff]", cell["text"])
               for cell in row):
            primary_rows.append((index, row))

    positions: list[dict[str, Any]] = []
    zero_positions: list[dict[str, Any]] = []
    for row_index, primary in primary_rows:
        name_cells = [cell for cell in primary
            if "市值" in column(cell) and re.search(r"[\u4e00-\u9fff]", cell["text"])]
        name = "".join(cell["text"] for cell in name_cells).strip()
        primary_y = sum(cell["yc"] for cell in primary) / len(primary)
        secondary: list[dict[str, Any]] = []
        if row_index + 1 < len(rows):
            following = rows[row_index + 1]
            following_y = sum(cell["yc"] for cell in following) / len(following)
            text_height = median(abs(cell["box"][2][1] - cell["box"][0][1])
                                 for cell in primary)
            if (0.6 * text_height <= following_y - primary_y <= 1.9 * text_height
                    and not any(re.search(r"[\u4e00-\u9fff]", cell["text"])
                                for cell in following)):
                secondary = following

        quantities = values(primary, "持仓/可用")
        available = values(secondary, "持仓/可用")
        costs = values(primary, "成本/现价")
        prices = values(secondary, "成本/现价")
        market_values = values(secondary, "市值")
        pnls = values(primary, "盈亏")
        pnl_pcts = values(secondary, "盈亏")
        if not name or not quantities or not costs or not prices:
            continue

        identity = _SECURITY_IDENTITY_SNAPSHOT.get(name)
        identity_candidates = [dict(identity)] if identity else []
        quantity = quantities[0][0]
        available_quantity = available[0][0] if available else None
        cost = costs[0][0]
        price = prices[0][0]
        market_value = market_values[0][0] if market_values else quantity * price
        confidence = round(min(cell["score"] for cell in primary + secondary), 3)
        field_confidence_pct = {
            "asset_id": round(min(cell["score"] for cell in name_cells) * 100, 1),
            "name": round(min(cell["score"] for cell in name_cells) * 100, 1),
            "quantity": round(quantities[0][1]["score"] * 100, 1),
            "cost_price": round(costs[0][1]["score"] * 100, 1),
            "price": round(prices[0][1]["score"] * 100, 1),
        }
        if available:
            field_confidence_pct["available_quantity"] = round(available[0][1]["score"] * 100, 1)
        if market_values:
            field_confidence_pct["market_value_cny"] = round(market_values[0][1]["score"] * 100, 1)
        reasons = []
        if identity is None:
            reasons.append("SECURITY_IDENTITY_REQUIRED")
        if not market_values:
            reasons.append("MISSING_REPORTED_MARKET_VALUE")
        reasons.append("MISSING_OBSERVED_AT")
        parsed = {
            "asset_id": identity["asset_id"] if identity else "",
            "name": name,
            "asset_class": "EQUITY",
            "sector": "Unclassified",
            "quantity": int(quantity),
            "available_quantity": int(available_quantity) if available_quantity is not None else None,
            "cost_price": float(cost),
            "price": float(price),
            "market_value_cny": float(market_value.quantize(Decimal("0.01"))),
            "day_pnl_cny": float(pnls[0][0]) if pnls else None,
            "day_pnl_pct": float(pnl_pcts[0][0]) if pnl_pcts else None,
            "confidence": confidence,
            "confidence_pct": round(confidence * 100, 1),
            "needs_review": bool(reasons) or confidence < CONFIDENCE_THRESHOLD,
            "original_code": None,
            "review_reasons": reasons,
            "identity_candidates": identity_candidates,
            "field_sources": {
                "identity": identity["source"] if identity else "unresolved broker display name",
                "quantity": "broker screenshot OCR",
                "available_quantity": "broker screenshot OCR",
                "cost_price": "broker screenshot OCR",
                "price": "broker screenshot OCR",
                "market_value_cny": "broker screenshot OCR" if market_values else "quantity × price",
            },
            "field_confidence_pct": field_confidence_pct,
            "zero_position": quantity == 0,
        }
        if not any("当日" in h["text"] for h in headers):
            parsed["pnl_cny"] = parsed.pop("day_pnl_cny")
            parsed["pnl_pct"] = parsed.pop("day_pnl_pct")
        (zero_positions if quantity == 0 else positions).append(parsed)
    return positions, zero_positions


def _broker_account_summary(rows: list[list[dict[str, Any]]]) -> dict[str, float]:
    """Read labeled account values above the table; available shares are not cash."""
    summary = {}
    for index, row in enumerate(rows):
        if any("持仓股" in cell["text"] or "持仓/可用" in cell["text"] for cell in row):
            break
        for cell in row:
            label = re.sub(r"\s+", "", cell["text"])
            key = ("account_total_value_cny" if label == "总资产" else
                   "cash_cny" if label in {"可用", "可用逆回购", "可用资金", "可用现金"} else None)
            if key is None or index + 1 >= len(rows):
                continue
            height = abs(cell["box"][2][1] - cell["box"][0][1])
            candidates = [value for below in rows[index + 1]
                          if 0.6 * height <= below["yc"] - cell["yc"] <= 2.5 * height
                          and abs(below["xm"] - cell["xm"]) <= height * 0.5
                          and re.fullmatch(r"[\d,]+(?:\.\d+)?", below["text"])
                          and (value := _decimal_cell(below["text"])) is not None]
            if len(candidates) == 1:
                summary[key] = float(candidates[0])
    return summary


def levenshtein_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def _normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).upper()
    value = re.sub(r"股份有限公司|股份|股票|[\s*·（）()\-]", "", value)
    return value


def levenshtein_similarity(left: str, right: str) -> float:
    """Return a length-aware Levenshtein ratio in the closed interval [0, 1]."""
    denominator = len(left) + len(right)
    if denominator == 0:
        return 1.0
    return 1 - levenshtein_distance(left, right) / denominator


def resolve_security_name(tokens: list[str]) -> str | None:
    candidates = []
    for code, info in {**A_SHARE_DATABASE, **ETF_LOOKTHROUGH_DATABASE}.items():
        names = [info.get("name", info.get("fund_name", "")), *info.get("aliases", [])]
        score = max((levenshtein_similarity(
                         _normalized_name(token), _normalized_name(name)
                     )
                     for token in tokens for name in names), default=0)
        if score >= CONFIDENCE_THRESHOLD:
            candidates.append((score, code))
    candidates.sort(reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        return None
    return candidates[0][1]


def validate_portfolio_values(positions: list[dict[str, Any]], cash_cny: float,
                              total_asset: float) -> dict[str, Any]:
    """Deterministic value reconciliation, including cash in total weight conservation."""
    total = Decimal(str(total_asset))
    weight_sum = Decimal(str(cash_cny)) / total if total > 0 else Decimal(0)
    for position in positions:
        quantity = Decimal(str(position["quantity"]))
        price = Decimal(str(position["price"]))
        value = quantity * price
        reported = Decimal(str(position["market_value_cny"]))
        issues = list(position.get("review_reasons", []))
        if quantity <= 0 or quantity != quantity.to_integral_value() or price <= 0:
            issues.append("INVALID_QUANTITY_OR_PRICE")
        if value <= 0 or abs(value - reported) > value * Decimal("0.005"):
            issues.append("MARKET_VALUE_MISMATCH")
        if position.get("asset_class") == "EQUITY" and quantity % 100:
            issues.append("ODD_LOT_REVIEW: 零股持仓请核对；买入须整手，清仓可卖出零股")
        weight = value / total if total > 0 else Decimal(0)
        position.update(weight=float(weight), calculated_market_value_cny=float(value),
                        review_reasons=list(dict.fromkeys(issues)))
        weight_sum += weight
    balanced = total > 0 and abs(weight_sum - 1) <= Decimal("0.01")
    for position in positions:
        if not balanced:
            position["review_reasons"].append("TOTAL_ASSET_MISMATCH")
        review = bool(position.get("needs_review") or position["review_reasons"])
        position.update(needs_review=review, confidence_level="REVIEW_REQUIRED" if review else "HIGH")
    return {"weight_sum": float(weight_sum), "weights_balanced": balanced,
            "has_low_confidence_items": any(p["needs_review"] for p in positions)}


def recalculate_portfolio_values(
    positions: list[dict[str, Any]], cash_cny: Decimal, owner_id: str,
    *, allow_synthetic_lookthrough: bool = True,
    validate_reported_market_value: bool = False,
) -> dict[str, Any]:
    """Recalculate edited OCR rows and build one owner-scoped portfolio contract."""
    observed_at = datetime.now(UTC)
    recalculated: list[dict[str, Any]] = []
    contract_positions: list[Position] = []
    fund_snapshots: list[FundHoldingSnapshot] = []
    holdings_total = Decimal("0")
    for index, raw in enumerate(positions, 1):
        row = dict(raw)
        sector_verified = bool(row.pop("_sector_verified", False))
        for optional_price in ("cost_price", "previous_close"):
            if row.get(optional_price) is not None:
                number = Decimal(str(row[optional_price]))
                if not number.is_finite() or number < 0 or (optional_price == "previous_close" and number == 0):
                    raise ValueError(f"{optional_price} must be finite and valid")
        quantity = Decimal(str(row.get("quantity", 0)))
        price = Decimal(str(row.get("price", row.get("cost_price", 0))))
        if (
            not quantity.is_finite()
            or not price.is_finite()
            or quantity <= 0
            or quantity != quantity.to_integral_value()
            or price <= 0
        ):
            raise ValueError("quantity must be a positive integer and price must be positive")
        market_value = (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reported_value = row.get("market_value_cny")
        if validate_reported_market_value and reported_value is not None:
            reported_market_value = Decimal(str(reported_value))
            market_value_tolerance = max(Decimal("0.01"), market_value * Decimal("0.005"))
            if (
                not reported_market_value.is_finite()
                or reported_market_value <= 0
                or abs(reported_market_value - market_value) > market_value_tolerance
            ):
                raise ValueError("market_value_cny must match quantity multiplied by price")
        available_quantity = row.get("available_quantity")
        if available_quantity is not None:
            available = Decimal(str(available_quantity))
            if (
                not available.is_finite()
                or available < 0
                or available != available.to_integral_value()
                or available > quantity
            ):
                raise ValueError("available_quantity must be an integer between zero and quantity")
            row["available_quantity"] = int(available)
        position_observed_at = observed_at
        if row.get("observed_at"):
            try:
                position_observed_at = datetime.fromisoformat(
                    str(row["observed_at"]).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("observed_at must be a valid timestamp") from exc
            if position_observed_at.tzinfo is None or position_observed_at.utcoffset() is None:
                raise ValueError("observed_at must be timezone-aware")
        asset_id = str(row.get("asset_id", "")).strip().upper()
        code = asset_id.split(".", 1)[0]
        is_fund = row.get("asset_class") == "FUND_ETF" or code in ETF_LOOKTHROUGH_DATABASE
        asset_type = AssetType.ETF if is_fund else AssetType.STOCK
        security = ETF_LOOKTHROUGH_DATABASE.get(code) if is_fund else A_SHARE_DATABASE.get(code)
        if (
            not allow_synthetic_lookthrough
            and not is_fund
            and re.fullmatch(r"(?:(?:600|601|603|605|688)\d{3}\.SH|(?:000|001|002|003|300|301)\d{3}\.SZ)", asset_id)
        ):
            security = {
                "name": row.get("name") or asset_id,
                "sector": "Unclassified",
            }
        # User-confirmed domestic equities need not exist in the demo catalogue.
        # Unknown industry stays unclassified so downstream suitability cannot infer it.
        if security is None and not is_fund and re.fullmatch(r"(?:(?:600|601|603|605|688)\d{3}\.SH|(?:000|001|002|003|300|301)\d{3}\.SZ)", asset_id):
            security = {"name": asset_id, "sector": "Unclassified"}
        if not asset_id or security is None:
            raise ValueError(f"unsupported security: {asset_id or 'missing asset_id'}")
        name = str(row.get("name") or security.get("fund_name") or security.get("name") or asset_id)
        provided_sector = str(row.get("sector") or "").strip()
        sector = None if is_fund else (
            provided_sector if sector_verified and provided_sector
            and provided_sector.casefold() not in {"unknown", "unclassified"}
            else str(security.get("sector") or "Unclassified")
        )
        row["sector"] = sector
        row["market_value_cny"] = float(market_value)
        row["price"] = float(price)
        row["quantity"] = int(quantity)
        holdings_total += market_value
        recalculated.append(row)
        position_id = f"ocr-position-{index}-{code}"
        contract_positions.append(Position(
            position_id=position_id,
            owner_id=owner_id,
            asset_id=asset_id,
            asset_type=asset_type,
            asset_name=name,
            sector=sector,
            quantity=quantity,
            market_value=market_value,
            currency="CNY",
            as_of=position_observed_at,
            source=str(row.get("price_source") or "user-confirmed OCR import"),
        ))
        if is_fund and allow_synthetic_lookthrough:
            sector_exposure = security.get("sector_exposure", {})
            if not sector_exposure:
                raise ValueError(f"missing packaged look-through baseline for {asset_id}")
            fund_snapshots.append(FundHoldingSnapshot(
                snapshot_id=f"ocr-lookthrough-{index}-{code}",
                owner_id=owner_id,
                parent_asset_id=asset_id,
                parent_asset_type=AssetType.ETF,
                as_of=observed_at,
                source="packaged ETF sector baseline",
                coverage_pct=Decimal("100"),
                holdings=tuple(
                    LookThroughHolding(
                        holding_id=f"ocr-holding-{index}-{code}-{sector_name}",
                        parent_asset_id=asset_id,
                        underlying_asset_id=f"SECTOR:{sector_name.upper()}",
                        underlying_name=f"{name} / {sector_name}",
                        asset_type=AssetType.OTHER,
                        weight_pct=Decimal(str(weight)),
                        sector=sector_name,
                        as_of=observed_at,
                        source="packaged ETF sector baseline",
                    )
                    for sector_name, weight in sector_exposure.items()
                ),
            ))
    total = (cash_cny + holdings_total).quantize(Decimal("0.01"))
    if cash_cny > 0:
        contract_positions.append(Position(
            position_id="ocr-position-cash-cny",
            owner_id=owner_id,
            asset_id="CASH-CNY",
            asset_type=AssetType.CASH,
            asset_name="可用现金",
            sector="Cash",
            quantity=cash_cny,
            market_value=cash_cny,
            currency="CNY",
            as_of=observed_at,
            source="user-confirmed OCR import",
        ))
    if not contract_positions:
        raise ValueError("at least one position is required")
    import_id = uuid4().hex
    snapshot = PositionSnapshot(
        snapshot_id=f"ocr-position-snapshot-{owner_id}-{import_id}",
        owner_id=owner_id,
        as_of=observed_at,
        base_currency="CNY",
        source="user-confirmed OCR import",
        positions=tuple(contract_positions),
    )
    portfolio = PortfolioImportBundle(
        bundle_id=f"ocr-portfolio-{owner_id}-{import_id}",
        owner_id=owner_id,
        created_at=observed_at,
        position_snapshot=snapshot,
        fund_holdings=tuple(fund_snapshots),
    )
    validation = validate_portfolio_values(recalculated, float(cash_cny), float(total))
    return {
        "status": "SUCCESS",
        "positions": recalculated,
        "cash_cny": float(cash_cny),
        "total_value_cny": float(total),
        "parsed_count": len(recalculated),
        "portfolio": portfolio.model_dump(mode="json"),
        **validation,
    }


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
        y_tolerance = 0.4 * median(abs(b["box"][2][1] - b["box"][0][1]) for b in boxes)

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

        two_line_positions, zero_positions = _parse_two_line_broker_layout(rows)
        if two_line_positions or zero_positions:
            holdings_value = round(sum(item["market_value_cny"] for item in two_line_positions), 2)
            summary = _broker_account_summary(rows)
            cash = summary.get("cash_cny", 0.0)
            total = summary.get("account_total_value_cny", holdings_value + cash)
            validation = validate_portfolio_values(two_line_positions, cash, total)
            return {
                "status": "SUCCESS" if two_line_positions else "EMPTY",
                "schema_version": "portfolio-ocr-bundle.v1",
                "total_value_cny": total,
                "account_total_value_cny": summary.get("account_total_value_cny"),
                "account_total_observed": "account_total_value_cny" in summary,
                "cash_cny": cash,
                "cash_observed": "cash_cny" in summary,
                "positions": two_line_positions,
                "zero_positions": zero_positions,
                "parsed_count": len(two_line_positions),
                **validation,
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "raw_ocr_lines": [{
                    "text": box["text"],
                    "confidence": round(box["score"], 3),
                    "box": box["box"],
                } for box in boxes],
            }

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

        # Some broker screenshots render summary labels as icons or unsupported
        # glyphs. A numeric-only two-cell footer is still structurally usable.
        if cash_cny == 0 and reported_total_assets == 0:
            for row in reversed(rows):
                numeric = []
                for cell in row:
                    cleaned = re.sub(r"[^\d.]", "", cell["text"].replace(",", ""))
                    if cleaned and cleaned.count(".") <= 1:
                        numeric.append(float(cleaned))
                if len(numeric) == 2 and numeric[1] >= numeric[0] > 0:
                    cash_cny, reported_total_assets = numeric
                    break

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
            original_code = found_code
            found_name = ""

            if found_code not in A_SHARE_DATABASE and found_code not in ETF_LOOKTHROUGH_DATABASE:
                corrected_code = resolve_security_name(row_tokens)
                if corrected_code is None:
                    continue
                found_code = corrected_code

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
                if tok in (found_code, original_code, found_name) or re.search(r"[\u4e00-\u9fffA-Za-z]", tok):
                    continue
                # If token matches the name or parts of it like '科创50ETF', skip it
                if found_name and tok in found_name:
                    continue
                num_matches = re.findall(r"(?<!\w)-?\d+(?:\.\d+)?\b", tok.replace(",", ""))
                for nm in num_matches:
                    try:
                        n_val = float(nm)
                        if n_val != float(found_code):
                            pure_numbers.append(n_val)
                    except ValueError:
                        continue

            quantity = 0
            cost_price = 0.0
            price = 0.0
            market_val = 0.0

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
            reasons = []
            if original_code != found_code:
                reasons.append("SECURITY_CODE_CORRECTED")
            if found_code not in A_SHARE_DATABASE and found_code not in ETF_LOOKTHROUGH_DATABASE:
                reasons.append("UNKNOWN_SECURITY")
            if len(pure_numbers) < 2:
                reasons.append("MISSING_OBSERVED_FIELDS")
            if pure_numbers and pure_numbers[0] != int(pure_numbers[0]):
                reasons.append("FRACTIONAL_SHARES")

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
                "field_confidence_pct": {
                    field: round(item_confidence * 100, 1)
                    for field in ("asset_id", "name", "quantity", "cost_price", "price", "market_value_cny")
                },
                "needs_review": is_low_conf,
                "original_code": original_code,
                "review_reasons": reasons,
            })

        total_holdings_val = sum(p["market_value_cny"] for p in positions)
        total_val = round(reported_total_assets if reported_total_assets > 0 else (cash_cny + total_holdings_val), 2)
        validation = validate_portfolio_values(positions, cash_cny, total_val)

        return {
            "status": "SUCCESS" if positions else "EMPTY",
            "schema_version": "portfolio-ocr-bundle.v1",
            "total_value_cny": total_val,
            "cash_cny": round(cash_cny, 2),
            "positions": positions,
            "parsed_count": len(positions),
            **validation,
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
