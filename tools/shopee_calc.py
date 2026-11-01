#!/usr/bin/env python3
"""Shopee TH seller calculator — fees, profit, and the reverse price formula.

Uses the official Shopee TH pricing relationship (Aug 2026 fee schedule):

    ราคาขาย = (ต้นทุนสินค้า + ค่าขนส่ง) / (1 - กำไร% - ค่าคอม% - ค่าธรรมเนียม% - อื่นๆ%) / (1 - ส่วนลด%)

Zero dependencies.
"""
import argparse
import json
import sys

DEFAULT_FEES = {
    "commission_pct": 0.0,      # ค่าคอมมิชชั่นแพลตฟอร์ม
    "service_fee_pct": 0.0,     # ค่าธรรมเนียมการขาย
    "transaction_fee_pct": 0.0, # ค่าธรรมเนียมชำระเงิน
    "other_pct": 0.0,           # อื่น ๆ
    "discount_pct": 0.0,        # ส่วนลดที่ให้ลูกค้า
    "target_margin_pct": 20.0,  # กำไรที่ต้องการ
}


def fees_from(kwargs):
    f = dict(DEFAULT_FEES)
    for k in f:
        if k in kwargs and kwargs[k] is not None:
            f[k] = float(kwargs[k])
    return f


def total_fee_pct(fees):
    """Sum of platform-side percentages (excludes discount and margin)."""
    return (fees["commission_pct"] + fees["service_fee_pct"]
            + fees["transaction_fee_pct"] + fees["other_pct"]) / 100.0


def suggest_price(cost, shipping=0.0, **kw):
    """Reverse-solve the listing price that hits the target margin."""
    f = fees_from(kw)
    denom = 1 - (f["target_margin_pct"] / 100.0) - total_fee_pct(f)
    if denom <= 0:
        raise ValueError("ค่าธรรมเนียม+กำไร รวมกันเกิน 100% — ตั้งราคาไม่ได้")
    price = (float(cost) + float(shipping)) / denom
    price /= (1 - f["discount_pct"] / 100.0)
    return round(price, 2)


def profit_at(price, cost, shipping=0.0, **kw):
    """Forward-calculate the seller's take-home and margin at a given price."""
    f = fees_from(kw)
    gross = float(price) * (1 - f["discount_pct"] / 100.0)
    platform_fees = gross * total_fee_pct(f)
    net = gross - platform_fees - float(cost) - float(shipping)
    margin = (net / gross * 100.0) if gross else 0.0
    return {
        "price": round(float(price), 2),
        "gross_after_discount": round(gross, 2),
        "platform_fees": round(platform_fees, 2),
        "cost": round(float(cost), 2),
        "shipping": round(float(shipping), 2),
        "net_profit": round(net, 2),
        "margin_pct": round(margin, 2),
    }


def breakeven_price(cost, shipping=0.0, **kw):
    """Lowest price that avoids a loss."""
    f = fees_from(kw)
    denom = 1 - total_fee_pct(f)
    if denom <= 0:
        raise ValueError("ค่าธรรมเนียมรวมเกิน 100%")
    price = (float(cost) + float(shipping)) / denom
    price /= (1 - f["discount_pct"] / 100.0)
    return round(price, 2)


def table(cost, shipping=0.0, margins=None, **kw):
    margins = margins or [10, 20, 30, 40, 50]
    out = []
    for m in margins:
        kk = dict(kw)
        kk["target_margin_pct"] = m
        p = suggest_price(cost, shipping, **kk)
        row = profit_at(p, cost, shipping, **kk)
        row["target_margin_pct"] = m
        out.append(row)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="คำนวณราคาขายและกำไร Shopee TH")
    p.add_argument("--cost", type=float, required=True, help="ต้นทุนสินค้า (บาท)")
    p.add_argument("--shipping", type=float, default=0.0, help="ค่าขนส่งที่เราออก (บาท)")
    p.add_argument("--commission", type=float, default=0.0)
    p.add_argument("--service-fee", type=float, default=0.0)
    p.add_argument("--transaction-fee", type=float, default=0.0)
    p.add_argument("--other", type=float, default=0.0)
    p.add_argument("--discount", type=float, default=0.0)
    p.add_argument("--margin", type=float, default=20.0)
    p.add_argument("--table", action="store_true", help="ตารางกำไร 10-50%")
    a = p.parse_args(argv)
    kw = dict(commission_pct=a.commission, service_fee_pct=a.service_fee,
              transaction_fee_pct=a.transaction_fee, other_pct=a.other,
              discount_pct=a.discount, target_margin_pct=a.margin)
    if a.table:
        print(json.dumps(table(a.cost, a.shipping, **kw), ensure_ascii=False, indent=2))
    else:
        price = suggest_price(a.cost, a.shipping, **kw)
        print(json.dumps({
            "suggested_price": price,
            "breakeven_price": breakeven_price(a.cost, a.shipping, **kw),
            "at_suggested": profit_at(price, a.cost, a.shipping, **kw),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
