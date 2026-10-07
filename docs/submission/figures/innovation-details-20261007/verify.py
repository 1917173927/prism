"""Verify image deliverables and deterministic examples without business writes."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal as D

ROOT = Path(__file__).resolve().parents[4]
ASSETS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from PIL import Image
from app.service.investment_hypotheses import judge_hypothesis
from app.service.funding_goals import FundingGoalsInput, calculate_funding_schedule
from app.service.research_lab_store import digest

def main():
    margin = D("20") / D("100") * 100
    assert margin == D("20") and margin >= D("15")
    config = {"condition": "AT_LEAST", "threshold": "15"}
    for value, expected in [("20", "SUPPORTED"), ("12", "CONTRADICTED")]:
        result = judge_hypothesis(config, [{"status": "CALCULATED", "unit": "%", "value": value}])
        assert result == expected
    assert judge_hypothesis(config, [{"status": "UNAVAILABLE", "unit": None}]) == "INSUFFICIENT_DATA"
    before = {"config": config, "status": "SUPPORTED", "sources": [{"actual_source": "A"}], "values": ["20"]}
    assert digest(before) == digest(json.loads(json.dumps(before)))
    assert digest(before) != digest({**before, "sources": [{"actual_source": "B"}]})
    assert digest(before) != digest({**before, "values": ["12"]})
    indirect = D("10000") * D("10") / 100
    known = D("10000") + indirect
    assert indirect == 1000 and known == 11000 and known / D("20000") * 100 == 55
    assert D("10000") - indirect == 9000
    funding = FundingGoalsInput(name="image-example",
        goals=({"goal_id": "near", "name": "near", "amount_cny": "40000", "due_date": "2026-10-08", "priority": 1},),
        confirmed_cashflows=({"flow_id": "later", "name": "later", "amount_cny": "20000", "due_date": "2026-11-07", "direction": "INCOME"},))
    schedule = calculate_funding_schedule(funding, D("30000"), date(2026, 10, 7))
    assert schedule["timeline"][0]["funded_cny"] == "30000"
    assert schedule["timeline"][0]["shortfall_cny"] == "10000"
    assert schedule["timeline"][0]["remaining_cash_cny"] == "0"
    assert schedule["remaining_cash_cny"] == "20000"
    assert schedule["current_cash_gap_cny"] == "10000"
    assert schedule["status"] == "SHORTFALL"
    images = []
    for path in sorted(ASSETS.glob("*.png")):
        with Image.open(path) as img:
            width, height = img.size
            assert img.format == "PNG"
            img.verify()
        assert abs(width / height - 16 / 9) < 0.01
        assert width >= 1600 and height >= 900
        assert (ASSETS / "prompts" / (path.stem + ".txt")).is_file()
        images.append({"file": path.name, "width": width, "height": height,
                       "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(images) == 5
    sources = ["app/service/research_method_builder.py", "app/service/personal_research.py",
               "app/service/investment_hypotheses.py", "app/service/research_lab_store.py",
               "app/service/announcement_impact.py", "app/portfolio/exposure.py",
               "app/service/shadow_portfolios.py", "app/service/portfolio_rebalancing.py",
               "app/service/funding_goals.py", "app/research/cross_validation.py", "app/gates/pipeline.py"]
    evidence = {"status": "PASS", "generator": "built-in image_gen", "images": images,
        "examples": {"margin_pct": str(margin), "indirect_exposure_cny": str(indirect),
                     "known_exposure_cny": str(known), "known_exposure_pct": "55",
                     "funding_schedule": schedule},
        "checks": ["decimal_examples", "hypothesis_states", "content_signature", "dated_funding", "png_decode", "aspect_ratio", "prompt_presence"],
        "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources}}
    (ASSETS / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "image_count": len(images), "sizes": [[i["width"], i["height"]] for i in images], "checks": evidence["checks"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
