"""Unit tests for lightweight RapidOCR portfolio parser and API endpoints."""

import base64
from decimal import Decimal
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import (
    OCRPortfolioParser,
    CONFIDENCE_THRESHOLD,
    recalculate_portfolio_values,
)


def _create_sample_holdings_image(low_contrast: bool = False) -> bytes:
    """Generate a clean synthetic brokerage holdings screenshot."""
    font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    try:
        font = ImageFont.truetype(font_path, 18)
    except Exception:
        font = ImageFont.load_default()

    img = Image.new("RGB", (900, 320), color="white")
    draw = ImageDraw.Draw(img)

    text_color = "#94a3b8" if low_contrast else "#0f172a"

    draw.text((20, 20), "持仓查询 - 真实A股与基金持仓", fill=text_color, font=font)
    draw.line([(20, 50), (880, 50)], fill="#cbd5e1", width=1)

    draw.text((30, 65), "证券代码", fill=text_color, font=font)
    draw.text((150, 65), "证券名称", fill=text_color, font=font)
    draw.text((300, 65), "持仓数量", fill=text_color, font=font)
    draw.text((430, 65), "成本价", fill=text_color, font=font)
    draw.text((560, 65), "当前价", fill=text_color, font=font)
    draw.text((700, 65), "持仓市值", fill=text_color, font=font)

    draw.text((30, 110), "300750", fill=text_color, font=font)
    draw.text((150, 110), "宁德时代", fill=text_color, font=font)
    draw.text((300, 110), "1000", fill=text_color, font=font)
    draw.text((430, 110), "240.00", fill=text_color, font=font)
    draw.text((560, 110), "250.00", fill=text_color, font=font)
    draw.text((700, 110), "250000.00", fill=text_color, font=font)

    draw.text((30, 160), "588000", fill=text_color, font=font)
    draw.text((150, 160), "科创50ETF", fill=text_color, font=font)
    draw.text((300, 160), "20000", fill=text_color, font=font)
    draw.text((430, 160), "0.950", fill=text_color, font=font)
    draw.text((560, 160), "1.000", fill=text_color, font=font)
    draw.text((700, 160), "20000.00", fill=text_color, font=font)

    draw.line([(20, 210), (880, 210)], fill="#cbd5e1", width=1)
    draw.text((30, 230), "可用资金余额: 50000.00 元", fill=text_color, font=font)
    draw.text((400, 230), "总资产合计: 320000.00 元", fill=text_color, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_portfolio_parser_extracts_positions():
    """Verify OCR correctly detects A-share and ETF holdings and cash balance."""
    image_bytes = _create_sample_holdings_image()
    parser = OCRPortfolioParser.get_instance()
    result = parser.parse_image_bytes(image_bytes)

    assert result["status"] == "SUCCESS"
    assert result["schema_version"] == "portfolio-ocr-bundle.v1"
    assert result["parsed_count"] == 2
    assert result["cash_cny"] == 50000.0
    assert result["total_value_cny"] == 320000.0

    symbols = [p["asset_id"] for p in result["positions"]]
    assert "300750.SZ" in symbols
    assert "588000.SH" in symbols

    ningde = next(p for p in result["positions"] if p["asset_id"] == "300750.SZ")
    assert ningde["name"] == "宁德时代"
    assert ningde["quantity"] == 1000
    assert ningde["cost_price"] == 240.0
    assert ningde["price"] == 250.0
    assert ningde["market_value_cny"] == 250000.0
    assert ningde["confidence"] >= CONFIDENCE_THRESHOLD
    assert ningde["needs_review"] is False


def test_ocr_api_base64_endpoint():
    """Verify POST /api/v1/copilot/parse-portfolio-ocr endpoint."""
    app = create_app()
    client = TestClient(app)

    image_bytes = _create_sample_holdings_image()
    b64_str = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64_str}"

    resp = client.post(
        "/api/v1/copilot/parse-portfolio-ocr",
        json={"image_base64": data_uri},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["parsed_count"] == 2
    assert data["cash_cny"] == 50000.0
    assert len(data["positions"]) == 2


def test_ocr_api_upload_file_endpoint():
    """Verify POST /api/v1/copilot/upload-portfolio-ocr multipart endpoint."""
    app = create_app()
    client = TestClient(app)

    image_bytes = _create_sample_holdings_image()
    files = {"file": ("screenshot.png", image_bytes, "image/png")}

    resp = client.post(
        "/api/v1/copilot/upload-portfolio-ocr",
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["parsed_count"] == 2
    assert data["cash_cny"] == 50000.0


@pytest.mark.parametrize("scale", [0.6, 1, 2.1, 3])
def test_ocr_extracts_two_line_name_only_broker_layout_and_excludes_zero_position(scale):
    """Regression for the broker layout where each slash header maps to two rows."""
    def item(x, y, text, score=0.99):
        width = 10 if text == "0" else 70
        return ([[x, y], [x + width, y], [x + width, y + 20], [x, y + 20]], text, score)

    result_rows = [
        item(20, 85, "市值"), item(186, 85, "持仓/可用"),
        item(359, 85, "成本/现价"), item(529, 85, "当日盈亏"),
        item(21, 135, "冠农股份"), item(240, 135, "6500"),
        item(384, 135, "11.580"), item(514, 135, "-3,051.00"),
        item(21, 165, "67,730.00"), item(239, 165, "3300"),
        item(384, 165, "10.420"), item(524, 165, "-4.310%"),
        item(22, 213, "莲花控股"), item(277, 213, "0", 0.826),
        item(384, 213, "13.262"), item(528, 213, "1,440.00"),
        item(20, 243, "0.00"), item(384, 243, "13.180"),
        item(526, 243, "10.017%"), item(450, 297, "查看已清仓股票"),
    ]

    result_rows = [([[x * scale, y * scale] for x, y in box], text, score)
                   for box, text, score in result_rows]

    class FakeEngine:
        def __call__(self, _):
            return result_rows, 0.01

    parser = OCRPortfolioParser()
    parser._engine = FakeEngine()
    image = Image.new("RGB", (int(613 * scale), int(340 * scale)), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    parsed = parser.parse_image_bytes(buffer.getvalue())

    assert parsed["cash_observed"] is False
    assert parsed["account_total_value_cny"] is None
    assert parsed["parsed_count"] == 1
    position = parsed["positions"][0]
    assert position["name"] == "冠农股份"
    assert position["asset_id"] == "600251.SH"
    assert position["quantity"] == 6500
    assert position["available_quantity"] == 3300
    assert position["cost_price"] == 11.58
    assert position["price"] == 10.42
    assert position["market_value_cny"] == 67730.0
    assert parsed["zero_positions"][0]["name"] == "莲花控股"
    assert parsed["zero_positions"][0]["zero_position"] is True


@pytest.mark.parametrize("scale", [0.5, 1, 2])
def test_fullscreen_reordered_columns_and_account_summary(scale):
    """Geometry from a full-screen broker table, without storing account images."""
    def item(x, y, width, text):
        return ([[x * scale, y * scale], [(x + width) * scale, y * scale],
                 [(x + width) * scale, (y + 50) * scale], [x * scale, (y + 50) * scale]], text, .99)

    cells = [
        item(520, 188, 280, "证券账户"),
        item(47, 574, 183, "总资产"), item(458, 574, 124, "总盈亏"),
        item(875, 574, 284, "当日参考盈亏"),
        item(46, 650, 223, "91,135.53"), item(464, 650, 249, "-10,440.45"),
        item(875, 650, 354, "-2,850.00 -3.03%"),
        item(46, 775, 125, "总市值"), item(459, 775, 226, "可用逆回购"),
        item(872, 775, 191, "可取 转账"),
        item(47, 851, 222, "67,201.00"), item(459, 851, 223, "23,933.53"),
        item(44, 1009, 154, "持仓股"),
        item(44, 1126, 93, "市值"), item(523, 1126, 94, "盈亏"),
        item(731, 1126, 222, "持仓/可用"), item(1097, 1126, 202, "成本/现价"),
        item(47, 1231, 192, "冠农股份"), item(391, 1231, 223, "-10,440.45"),
        item(845, 1231, 109, "6700"), item(1148, 1231, 141, "11.588"),
        item(47, 1295, 198, "67,201.00"), item(410, 1295, 206, "-13.447%"),
        item(919, 1295, 34, "0"), item(1148, 1295, 141, "10.030"),
        item(956, 1411, 278, "查看已清仓股票"), item(71, 1527, 188, "持仓管理"),
    ]
    parser = OCRPortfolioParser()
    parser._engine = lambda _: (cells, .01)
    buffer = io.BytesIO()
    Image.new("RGB", (int(1320 * scale), int(2868 * scale)), "white").save(buffer, format="PNG")
    result = parser.parse_image_bytes(buffer.getvalue())
    assert result["parsed_count"] == 1
    assert result["cash_observed"] is True
    assert result["cash_cny"] == 23933.53
    assert result["account_total_observed"] is True
    assert result["total_value_cny"] == result["account_total_value_cny"] == 91135.53
    assert result["weights_balanced"] is True
    position = result["positions"][0]
    assert position["quantity"] == 6700
    assert position["available_quantity"] == 0
    assert position["cost_price"] == 11.588
    assert position["price"] == 10.03
    assert position["market_value_cny"] == 67201
    assert position["pnl_cny"] == -10440.45
    assert position["pnl_pct"] == -13.447
    assert position.get("day_pnl_cny") is None
    assert "MISSING_OBSERVED_AT" in position["review_reasons"]
    assert set(position["field_confidence_pct"]) >= {
        "asset_id", "name", "quantity", "available_quantity",
        "cost_price", "price", "market_value_cny",
    }


def test_confirmed_editable_fields_are_preserved_and_cross_validated():
    result = recalculate_portfolio_values([{
        "asset_id": "600251.SH",
        "name": "用户核对后的名称",
        "quantity": 100,
        "available_quantity": 60,
        "cost_price": 11.58,
        "price": 10.42,
        "market_value_cny": 1042,
    }], Decimal("0"), "editable-owner", validate_reported_market_value=True)

    position = result["positions"][0]
    assert position["name"] == "用户核对后的名称"
    assert position["available_quantity"] == 60
    assert position["market_value_cny"] == 1042

    with pytest.raises(ValueError, match="market_value_cny"):
        recalculate_portfolio_values([{
            "asset_id": "600251.SH", "quantity": 100, "price": 10.42,
            "market_value_cny": 9999,
        }], Decimal("0"), "editable-owner", validate_reported_market_value=True)

    with pytest.raises(ValueError, match="available_quantity"):
        recalculate_portfolio_values([{
            "asset_id": "600251.SH", "quantity": 100, "available_quantity": 101,
            "price": 10.42, "market_value_cny": 1042,
        }], Decimal("0"), "editable-owner", validate_reported_market_value=True)
