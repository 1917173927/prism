from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from PIL import Image

from app.trading_history import (
    HistoricalTradeRecord,
    ImportParseError,
    TradeRecordStatus,
    TradeSide,
    calculate_trading_style,
    preview_trade_files,
)


NOW = datetime(2026, 9, 17, 8, tzinfo=UTC)
OWNER = "trade-style-owner"


def trade(index: int, *, side: TradeSide, quantity: str = "100") -> HistoricalTradeRecord:
    traded_at = NOW - timedelta(days=300 - index * 6)
    return HistoricalTradeRecord(
        trade_id=f"trade-{index}",
        owner_id=OWNER,
        batch_id="batch-1",
        revision=1,
        status=TradeRecordStatus.ACTIVE,
        traded_at=traded_at,
        security_code="600000.SH",
        side=side,
        quantity=Decimal(quantity),
        price_cny=Decimal("10"),
        gross_amount_cny=Decimal(quantity) * Decimal("10"),
        source_row=index + 2,
        created_at=NOW,
        updated_at=NOW,
    )


def test_style_requires_minimum_sample_and_is_deterministic() -> None:
    insufficient = calculate_trading_style(OWNER, (trade(0, side=TradeSide.BUY),), calculated_at=NOW)
    assert insufficient.status.value == "INSUFFICIENT_DATA"
    assert insufficient.primary_style is None

    records = tuple(
        trade(index, side=TradeSide.BUY if index < 25 else TradeSide.SELL)
        for index in range(50)
    )
    first = calculate_trading_style(OWNER, records, calculated_at=NOW)
    second = calculate_trading_style(OWNER, records, calculated_at=NOW)
    assert first.model_copy(update={"profile_id": second.profile_id}) == second
    assert first.status.value == "CALCULATED"
    assert first.metrics.trade_count == 50
    assert first.metrics.matched_sell_coverage == Decimal("1.0000")
    assert first.metrics.turnover_90d_pct is None
    assert first.primary_style in {"主动波段型", "稳健均衡型", "低频长持型", "高频短线型"}


def test_fifo_holding_period_is_quantity_weighted_and_withdrawn_rows_are_ignored() -> None:
    buy = trade(0, side=TradeSide.BUY, quantity="100")
    sell_first = trade(1, side=TradeSide.SELL, quantity="40")
    sell_second = trade(2, side=TradeSide.SELL, quantity="60")
    withdrawn = trade(3, side=TradeSide.BUY).model_copy(update={"status": TradeRecordStatus.WITHDRAWN})
    profile = calculate_trading_style(OWNER, (buy, sell_first, sell_second, withdrawn), calculated_at=NOW)
    assert profile.metrics.trade_count == 3
    assert profile.metrics.median_holding_days == Decimal("12.00")
    assert profile.metrics.matched_sell_coverage == Decimal("1.0000")


def test_csv_and_xlsx_preview_apply_mapping_and_amount_tolerance() -> None:
    csv_data = (
        "成交日期,证券代码,证券名称,买卖方向,成交数量,成交价格,成交金额\n"
        "2026-01-02 09:31:00,600000,浦发银行,买入,100,10,1000\n"
        "2026-01-03 09:31:00,600000,浦发银行,卖出,100,10,1200\n"
    ).encode("utf-8")
    preview = preview_trade_files([("trades.csv", "text/csv", csv_data)])
    assert preview.source_type == "CSV"
    assert preview.rows[0].status == "PASS"
    assert preview.rows[1].status == "REVIEW_REQUIRED"
    assert any("0.1%" in issue for issue in preview.rows[1].issues)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "成交明细"
    sheet.append(["成交时间", "证券代码", "方向", "数量", "价格"])
    sheet.append(["2026-01-02 09:31:00", "600000", "买入", 100, 10])
    alternate = workbook.create_sheet("另一工作表")
    alternate.append(["成交时间", "证券代码", "方向", "数量", "价格"])
    alternate.append(["2026-01-03 09:31:00", "000001", "卖出", 20, 12])
    buffer = BytesIO()
    workbook.save(buffer)
    xlsx = preview_trade_files([(
        "trades.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer.getvalue(),
    )])
    assert xlsx.source_type == "XLSX"
    assert xlsx.selected_sheet == "成交明细"
    assert xlsx.rows[0].proposed["gross_amount_cny"] == "1000"
    alternate_xlsx = preview_trade_files([(
        "trades.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer.getvalue(),
    )], selected_sheet="另一工作表")
    assert alternate_xlsx.sheets == ("成交明细", "另一工作表")
    assert alternate_xlsx.selected_sheet == "另一工作表"
    assert alternate_xlsx.rows[0].proposed["security_code"] == "000001"


def test_screenshot_preview_uses_ocr_only_as_reviewable_input(monkeypatch) -> None:
    from app.llm.ocr_portfolio_parser import OCRPortfolioParser

    labels = ["成交日期", "证券代码", "买卖方向", "成交数量", "成交价格"]
    values = ["2026-01-02", "600000", "买入", "100", "10"]

    def box(column: int, row: int):
        left, top = column * 120, row * 24
        return [[left, top], [left + 100, top], [left + 100, top + 10], [left, top + 10]]

    result = [
        *[(box(index, 0), text, 0.99) for index, text in enumerate(labels)],
        *[(box(index, 1), text, 0.80 if index == 4 else 0.99) for index, text in enumerate(values)],
    ]

    class FakeEngine:
        def __call__(self, _data):
            return result, 0.01

    parser = OCRPortfolioParser.get_instance()
    monkeypatch.setattr(parser, "_engine", FakeEngine())
    image = Image.new("RGB", (640, 80), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    preview = preview_trade_files([("trade.png", "image/png", buffer.getvalue())])
    assert preview.source_type == "IMAGE"
    assert preview.rows[0].status == "REVIEW_REQUIRED"
    assert preview.rows[0].proposed["gross_amount_cny"] == "1000"
    assert any("85%" in issue for issue in preview.rows[0].issues)


def test_mobile_statement_two_line_rows_are_normalized(monkeypatch) -> None:
    from app.llm.ocr_portfolio_parser import OCRPortfolioParser

    def box(x: int, y: int):
        return [[x - 40, y - 5], [x + 40, y - 5], [x + 40, y + 5], [x - 40, y + 5]]

    cells = [
        (100, 10, "本月操作"), (500, 10, "价格/数量"), (800, 10, "金额/税费①"),
        (100, 35, "2026-09"),
        (100, 65, "证券买入-莲花控股"), (500, 65, "11.440"), (800, 65, "-13733.14"),
        (100, 85, "买09-1010:05"), (500, 85, "1200"), (800, 85, "5.14"),
    ]
    result = [(box(x, y), text, 0.99) for x, y, text in cells]

    class FakeEngine:
        def __call__(self, _data):
            return result, 0.01

    parser = OCRPortfolioParser.get_instance()
    monkeypatch.setattr(parser, "_engine", FakeEngine())
    image = Image.new("RGB", (900, 120), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    preview = preview_trade_files([("statement.png", "image/png", buffer.getvalue())])
    assert len(preview.rows) == 1
    assert preview.rows[0].status == "PASS"
    assert preview.rows[0].proposed["traded_at"] == "2026-09-10T10:05:00+08:00"
    assert preview.rows[0].proposed["security_name"] == "莲花控股"
    assert preview.rows[0].proposed["side"] == "BUY"
    assert preview.rows[0].proposed["quantity"] == "1200"
    assert preview.rows[0].proposed["price_cny"] == "11.440"
    assert preview.rows[0].proposed["gross_amount_cny"] == "13728.000"
    assert preview.rows[0].proposed["fee_cny"] == "5.14"

    result[6] = (box(800, 65), "-13000.00", 0.99)
    review = preview_trade_files([("statement.png", "image/png", buffer.getvalue())])
    assert review.rows[0].status == "REVIEW_REQUIRED"
    assert "截图净发生额与成交金额及税费不一致" in review.rows[0].issues


def test_screenshot_without_trade_rows_is_not_reported_as_pass(monkeypatch) -> None:
    from app.llm.ocr_portfolio_parser import OCRPortfolioParser

    class EmptyEngine:
        def __call__(self, _data):
            return [], 0.01

    parser = OCRPortfolioParser.get_instance()
    monkeypatch.setattr(parser, "_engine", EmptyEngine())
    image = Image.new("RGB", (320, 120), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    with pytest.raises(ImportParseError, match="未识别到可导入的交易明细"):
        preview_trade_files([("empty.png", "image/png", buffer.getvalue())])
