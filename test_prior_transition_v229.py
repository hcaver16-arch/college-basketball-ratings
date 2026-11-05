"""V229: research-only no-leakage and preseason anchoring regression."""
from datetime import date
from unittest.mock import patch
import numpy as np
import pandas as pd

from prior_transition_research_v229 import (
    anchored_ridge, legacy_replay, normalize, evaluate, metrics,
    historical_prior, CAP, RIDGE, HOME_ADVANTAGE,
)

COLS = ["Game ID","Date","Home ID","Away ID","Home","Away","Home score",
        "Away score","Status","Venue"]
def game(gid, day, h, a, hs, aws, venue="Home"):
    return dict(zip(COLS,[str(gid),day,str(h),str(a),str(h),str(a),
                          hs,aws,"Final",venue]))

prior = {"356":18.0,"201":-10.0,"202":4.0,"203":0.0}
empty = pd.DataFrame(columns=COLS)
assert anchored_ridge(prior,empty) == prior
assert legacy_replay(prior,empty)[0] == prior
assert (CAP,RIDGE,HOME_ADVANTAGE) == (40.0,8.0,3.0)

win = pd.DataFrame([game(1,"2026-11-02",356,201,120,45)])
more = pd.DataFrame([game(1,"2026-11-02",356,201,150,45)])
r = anchored_ridge(prior,win)
assert r["356"] > prior["356"] and r["201"] < prior["201"]
assert np.isclose(r["356"], anchored_ridge(prior,more)["356"])
assert np.isclose(r["356"]-r["201"],.8*28+.2*37)
assert legacy_replay(prior,win)[0] == prior  # production <20 final gate
try:
    anchored_ridge(prior,win,ridge=0)
    raise AssertionError("Invalid ridge was accepted")
except ValueError:pass

raw = pd.DataFrame([game(1,"2026-11-02",356,201,120,45),
    {**game(2,"2026-11-02",356,203,90,50),"Status":"Scheduled"},
    game(3,"2026-11-02",356,203,90,50,"Unknown"),
    game(4,"2026-11-02",356,356,60,60)])
clean = normalize(raw,"synthetic")
assert clean["Game ID"].tolist() == ["1"]
try:
    normalize(pd.concat([clean,clean]),"duplicate")
    raise AssertionError("Duplicate final accepted")
except ValueError:pass

nov1 = [game(i+10,"2026-11-01",202 if i%2 else 201,203,
             81 if i%2 else 72,70) for i in range(25)]
season = pd.DataFrame(nov1 + [game(1,"2026-11-02",356,201,120,45),
    game(2,"2026-11-03",356,203,70,72),
    game(3,"2026-11-03",201,202,90,87)])
capped = normalize(season[season["Date"].le("2026-11-02")],"past")
old,counts = legacy_replay(prior,capped)
new = anchored_ridge(prior,capped)
assert counts["356"] == 1
assert old["356"] < prior["356"]
assert new["356"] > prior["356"]

d1={str(i) for i in range(200,530)}
with patch("prior_transition_research_v229.historical_prior",return_value=prior):
    matched,report = evaluate(pd.DataFrame(nov1),season,d1,date(2026,11,3))
assert report["matched_games"] == len(season)
assert report["status"] == "TOO_FEW_INFORMATIVE_MATCHUPS_FOR_MODEL_SELECTION"
assert 0 < report["informative_model_disagreement_games"] < len(matched)
assert set(report["metrics"]) == {"prior_only","legacy_replay","anchored_ridge8"}
assert all(r["latest_training_day"] is None or r["latest_training_day"] < r["day"]
           for r in matched.to_dict("records"))
ill = matched[matched.game_id.eq("1")].iloc[0]
assert ill.day == "2026-11-02" and ill.latest_training_day == "2026-11-01"
# Illinois had no prior season game, but opponent 201 already did.
# Therefore the whole matchup can move without leaking Illinois's future result.
before = normalize(pd.DataFrame(nov1),"Nov1")
legacy_pre,_ = legacy_replay(prior,before)
anchored_pre = anchored_ridge(prior,before)
assert np.isclose(ill.legacy_replay,legacy_pre["356"]-legacy_pre["201"]+3)
assert np.isclose(ill.anchored_ridge8,anchored_pre["356"]-anchored_pre["201"]+3)
assert not np.isclose(ill.anchored_ridge8,
    anchored_ridge(prior,capped)["356"]-anchored_ridge(prior,capped)["201"]+3)
next_game = matched[matched.game_id.eq("2")].iloc[0]
assert next_game.latest_training_day == "2026-11-02"
assert not np.isclose(next_game.anchored_ridge8,next_game.prior_only)
assert report["Illinois_diagnostic"]["team_id"] == "356"

with patch("prior_transition_research_v229.historical_prior",return_value=prior):
    reordered,_=evaluate(pd.DataFrame(nov1),
        season.sample(frac=1,random_state=2),d1,date(2026,11,3))
    truncated,_=evaluate(pd.DataFrame(nov1),season,d1,date(2026,11,2))
pd.testing.assert_frame_equal(
    matched.sort_values("game_id").reset_index(drop=True),
    reordered.sort_values("game_id").reset_index(drop=True))
assert set(truncated["game_id"]).isdisjoint({"2","3"})

with patch("prior_transition_research_v229.historical_prior",return_value=prior):
    try:
        evaluate(pd.DataFrame(nov1),season,{"356","201"},date(2026,11,3))
        raise AssertionError("Small D1 directory accepted")
    except ValueError:pass
try:
    historical_prior(pd.DataFrame(nov1))
    raise AssertionError("Insufficient previous season accepted")
except ValueError:pass

m=metrics([{"actual_margin":2,"pred":1},{"actual_margin":-4,"pred":-2}],"pred")
assert m["games"]==2 and np.isclose(m["mae"],1.5)
print("V229 early-season anchor, legacy replay, capped blowouts and no-lookahead tests passed")
