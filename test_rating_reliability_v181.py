"""V181 reliability regression tests; no production data written."""
import pandas as pd
import numpy as np
from rating_engine import calculate_power

def games(n=25):
    return pd.DataFrame([{
        "Game ID": str(i), "Status": "Final",
        "Home ID": str(100+i%6), "Away ID": str(100+(i+1)%6),
        "Home": f"Home{i%6}", "Away": f"Away{(i+1)%6}",
        "Home score": 77+i%5, "Away score": 69+i%3,
        "Venue": "Neutral" if i%3==0 else "Home"
    } for i in range(n)])

base=games()
reference,_=calculate_power(base)
numeric=base.copy()
numeric["Home ID"]=numeric["Home ID"].astype(int)
numeric["Away ID"]=numeric["Away ID"].astype(int)
normalized,meta=calculate_power(numeric)
assert meta["games"]==25
assert set(normalized["Team ID"])==set(reference["Team ID"])
pd.testing.assert_frame_equal(reference, normalized)

mixed=base.copy()
mixed.loc[0,"Home ID"]=int(mixed.loc[0,"Home ID"])
mixed.loc[1,"Away ID"]=int(mixed.loc[1,"Away ID"])
mixed_result,_=calculate_power(mixed)
pd.testing.assert_frame_equal(reference,mixed_result)

unknown=base.copy()
unknown.loc[0,"Venue"]="Unknown"
_,meta=calculate_power(unknown)
assert meta["unknown_venue_games"]==1 and meta["games"]==24
assert calculate_power(unknown)[0].shape[0] > 0
missing=base.copy()
missing.loc[0,"Venue"]=None
_,meta=calculate_power(missing)
assert meta["unknown_venue_games"]==1
invalid=base.copy()
invalid.loc[0,"Home ID"]=None
assert calculate_power(invalid)[1]["games"]==24

for n in (0,1,19,20):
    _,stats=calculate_power(games(n))
    assert stats["games"]==n
print("V181 rating reliability tests passed")
