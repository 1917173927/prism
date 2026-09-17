"""Historical trade imports and deterministic trading-style analysis."""

from .analysis import behavior_events_from_trades, calculate_trading_style
from .contracts import (
    HistoricalTradeRecord,
    TradeBatchListResponse,
    TradeConfirmRow,
    TradeAssetType,
    TradeImportBatch,
    TradeImportConfirmRequest,
    TradeImportConfirmResponse,
    TradeImportPreview,
    TradeListResponse,
    TradeMutationResponse,
    TradeRevisionRequest,
    TradeRecordStatus,
    TradeSide,
    TradeUpdateRequest,
    TradingStyleLookupResponse,
    TradingStyleProfile,
    TradingStyleStatus,
)
from .importer import ImportLimitError, ImportParseError, preview_trade_files

__all__ = [
    "HistoricalTradeRecord",
    "ImportLimitError",
    "ImportParseError",
    "TradeAssetType",
    "TradeBatchListResponse",
    "TradeConfirmRow",
    "TradeImportBatch",
    "TradeImportConfirmRequest",
    "TradeImportConfirmResponse",
    "TradeImportPreview",
    "TradeListResponse",
    "TradeMutationResponse",
    "TradeRevisionRequest",
    "TradeRecordStatus",
    "TradeSide",
    "TradeUpdateRequest",
    "TradingStyleLookupResponse",
    "TradingStyleProfile",
    "TradingStyleStatus",
    "calculate_trading_style",
    "behavior_events_from_trades",
    "preview_trade_files",
]
