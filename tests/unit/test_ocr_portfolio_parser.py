"""Unit tests for lightweight RapidOCR portfolio parser and API endpoints."""

import base64
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.llm.ocr_portfolio_parser import OCRPortfolioParser, CONFIDENCE_THRESHOLD


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
