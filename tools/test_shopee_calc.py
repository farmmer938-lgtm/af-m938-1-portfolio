"""Tests for the Shopee TH seller calculator — the math must be exact."""
import json
import pytest
import shopee_calc as s


def test_suggest_price_hits_target_margin_exactly():
    for m in (10, 20, 30, 40, 50):
        p = s.suggest_price(100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=m)
        r = s.profit_at(p, 100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=m)
        assert r["margin_pct"] == pytest.approx(m, abs=0.15), f"margin drift at {m}%"


def test_known_value_from_official_formula():
    # (100+30) / (1 - 0.20 - 0.13) = 130 / 0.67 = 194.0298...
    assert s.suggest_price(100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=20) == 194.03


def test_breakeven_is_below_target_price():
    be = s.breakeven_price(100, 30, commission_pct=8, service_fee_pct=5)
    p20 = s.suggest_price(100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=20)
    assert be < p20
    assert s.profit_at(be, 100, 30, commission_pct=8, service_fee_pct=5)["net_profit"] == pytest.approx(0, abs=0.05)


def test_discount_raises_required_price():
    plain = s.suggest_price(100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=20)
    disc = s.suggest_price(100, 30, commission_pct=8, service_fee_pct=5, target_margin_pct=20, discount_pct=10)
    assert disc > plain
    assert disc == pytest.approx(plain / 0.9, abs=0.02)


def test_no_fees_margin_is_cost_plus_target():
    p = s.suggest_price(100, 0, target_margin_pct=20)
    assert p == pytest.approx(125.0, abs=0.01)


def test_zero_cost_zero_shipping_gives_zero_price():
    assert s.suggest_price(0, 0, target_margin_pct=20) == 0.0


def test_impossible_fee_combination_raises():
    with pytest.raises(ValueError):
        s.suggest_price(100, 0, commission_pct=60, service_fee_pct=50, target_margin_pct=20)


def test_loss_detected_at_low_price():
    r = s.profit_at(50, 100, 30, commission_pct=8, service_fee_pct=5)
    assert r["net_profit"] < 0


def test_table_covers_all_margins_and_is_json_serialisable():
    rows = s.table(100, 30, commission_pct=8, service_fee_pct=5)
    assert [r["target_margin_pct"] for r in rows] == [10, 20, 30, 40, 50]
    json.dumps(rows, ensure_ascii=False)
    for r in rows:
        assert r["margin_pct"] == pytest.approx(r["target_margin_pct"], abs=0.15)


def test_cli_outputs_valid_json(capsys):
    rc = s.main(["--cost", "100", "--shipping", "30", "--commission", "8",
                 "--service-fee", "5", "--margin", "20"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["suggested_price"] == 194.03
    assert out["at_suggested"]["margin_pct"] == pytest.approx(20, abs=0.15)
