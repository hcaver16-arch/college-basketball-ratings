"""Read-only resume blending and provisional 76-to-64 national bracket."""
import pandas as pd
import streamlit as st
from tournament_brackets import _render_rounds, provisional_all_teams_bracket


def add_resume(data, sor, weight=0.35):
    out = data.copy()
    out["Power percentile"] = out["Current power"].rank(pct=True)
    out["SOR score"] = float("nan")
    out["SOR games"] = float("nan")
    if isinstance(sor, pd.DataFrame) and {"Team ID", "SOR score", "SOR games"}.issubset(sor.columns):
        resume = sor[["Team ID", "SOR score", "SOR games"]].copy()
        resume["Team ID"] = resume["Team ID"].astype(str)
        resume["SOR score"] = pd.to_numeric(resume["SOR score"], errors="coerce")
        resume["SOR games"] = pd.to_numeric(resume["SOR games"], errors="coerce")
        out = out.drop(columns=["SOR score", "SOR games"]).merge(
            resume.drop_duplicates("Team ID"), on="Team ID", how="left")
    eligible = out["SOR games"].ge(5) & out["SOR score"].notna()
    out["SOR eligible"] = eligible
    out["Resume percentile"] = float("nan")
    if eligible.sum() >= 2:
        out.loc[eligible, "Resume percentile"] = out.loc[eligible, "SOR score"].rank(pct=True)
    out["Selection score"] = out["Power percentile"]
    usable = out["Resume percentile"].notna()
    out.loc[usable, "Selection score"] = ((1-weight)*out.loc[usable, "Power percentile"]
        + weight*out.loc[usable, "Resume percentile"])
    out["Selection basis"] = "Power only — SOR pending"
    out.loc[usable, "Selection basis"] = "Power + provisional SOR"
    return out


def opening_round_slots(field):
    """12 hypothetical opening matchups; 52 direct teams + 12 winner slots."""
    play = field[field["Opening Round (proxy)"]]
    pairings = []
    direct = field[~field["Opening Round (proxy)"]][["Team","Selection score"]].copy()
    for bid in ("Projected automatic (scenario)", "Projected at-large (scenario)"):
        group = play[play["Bid type"].eq(bid)].sort_values("Overall seed list")
        names = group["Team"].astype(str).tolist()
        for index in range(0, len(names), 2):
            if index+1 < len(names):
                pairings.append((names[index], names[index+1]))
    winners = []
    for i, (left,right) in enumerate(pairings, 1):
        strength = float(play[play["Team"].astype(str).isin([left,right])]["Selection score"].max())
        winners.append({"Team":f"Winner OR{i}: {left} / {right}", "Selection score":strength})
    slots = pd.concat([direct, pd.DataFrame(winners)], ignore_index=True)
    slots = slots.sort_values("Selection score",ascending=False).reset_index(drop=True)
    return pairings,slots


def render_national_bracket(field):
    pairings, slots = opening_round_slots(field)
    if len(pairings)!=12 or len(slots)!=64:
        st.warning("Cannot render a complete provisional bracket from the current field.")
        return
    st.markdown("### Illustrative national bracket")
    st.caption("Not official NCAA region placements or matchups. Winners are placeholders; no game outcomes have been simulated.")
    with st.expander("Opening Round — 12 matchups",expanded=True):
        _render_rounds([("Opening Round",pairings)])
    with st.expander("64-team bracket — seeded illustration",expanded=True):
        _render_rounds(provisional_all_teams_bracket(slots))
