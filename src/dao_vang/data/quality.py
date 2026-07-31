from decimal import Decimal

from dao_vang.data.schemas import (
    NormalizedBase,
    NormalizedFunding,
    NormalizedGlobalRatio,
    NormalizedKline,
    NormalizedOpenInterest,
    NormalizedTakerVolume,
    NormalizedTopRatio,
    QualityStatus,
)


def _apply_flag(obj: NormalizedBase, status: QualityStatus, flag: str):
    # Upgrades severity if necessary
    severity = {
        QualityStatus.VALID: 0,
        QualityStatus.QUARANTINED: 1,
        QualityStatus.WARNING: 2,
        QualityStatus.INVALID: 3,
    }
    if severity[status] > severity[obj.quality_status]:
        obj.quality_status = status
    if flag not in obj.quality_flags:
        obj.quality_flags.append(flag)


def assess_kline(kline: NormalizedKline) -> NormalizedKline:
    if kline.volume_base < Decimal("0") or kline.volume_quote < Decimal("0"):
        _apply_flag(kline, QualityStatus.INVALID, "negative_volume")

    if kline.high < kline.open or kline.high < kline.close or kline.high < kline.low:
        _apply_flag(kline, QualityStatus.INVALID, "invalid_high_price")

    if kline.low > kline.open or kline.low > kline.close or kline.low > kline.high:
        _apply_flag(kline, QualityStatus.INVALID, "invalid_low_price")

    if kline.trade_count < 0:
        _apply_flag(kline, QualityStatus.INVALID, "negative_trade_count")

    return kline


def assess_funding(funding: NormalizedFunding) -> NormalizedFunding:
    if abs(funding.funding_rate) > Decimal("0.1"):
        _apply_flag(funding, QualityStatus.WARNING, "extreme_funding_rate")

    if funding.mark_price is not None and funding.mark_price <= Decimal("0"):
        _apply_flag(funding, QualityStatus.INVALID, "invalid_mark_price")

    return funding


def assess_open_interest(oi: NormalizedOpenInterest) -> NormalizedOpenInterest:
    if oi.open_interest_contracts < Decimal("0"):
        _apply_flag(oi, QualityStatus.INVALID, "negative_open_interest")

    if oi.open_interest_value is not None and oi.open_interest_value < Decimal("0"):
        _apply_flag(oi, QualityStatus.INVALID, "negative_open_interest_value")

    return oi


def assess_taker_volume(tv: NormalizedTakerVolume) -> NormalizedTakerVolume:
    if tv.buy_volume < Decimal("0") or tv.sell_volume < Decimal("0"):
        _apply_flag(tv, QualityStatus.INVALID, "negative_taker_volume")

    if tv.buy_sell_ratio is not None and tv.buy_sell_ratio <= Decimal("0"):
        _apply_flag(tv, QualityStatus.INVALID, "invalid_buy_sell_ratio")

    return tv


def assess_global_ratio(gr: NormalizedGlobalRatio) -> NormalizedGlobalRatio:
    if gr.long_account is not None and gr.long_account < Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "negative_long_account")

    if gr.short_account is not None and gr.short_account < Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "negative_short_account")

    if gr.long_short_ratio <= Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "invalid_long_short_ratio")

    return gr


def assess_top_ratio(tr: NormalizedTopRatio) -> NormalizedTopRatio:
    if tr.long_account is not None and tr.long_account < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_long_account")

    if tr.short_account is not None and tr.short_account < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_short_account")

    if tr.long_short_ratio <= Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "invalid_long_short_ratio")

    return tr
