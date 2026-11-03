"""Light-themed Courtside home components. No new data source or model calculation."""
from __future__ import annotations
import html
import pandas as pd
import streamlit as st

PALETTE = {"Texas Tech":"#C6283A","Kansas":"#0051BA","Duke":"#003087",
           "North Carolina":"#4B9CD3","Houston":"#C8102E","Baylor":"#154734",
           "Arizona":"#AB0520","UConn":"#000E2F","Purdue":"#CEB888"}

def color_for(name):
    name = str(name)
    return next((color for school, color in PALETTE.items() if school.lower() in name.lower()), '#52677F')

def style():
    st.markdown('''<style>
    .stApp { background:#F5F6F8; color:#19283D; }
    [data-testid="stHeader"] { background:#F5F6F8; }
    [data-testid="stSidebar"] {background:#FFFFFF;}
    h1,h2,h3 { color:#19283D;letter-spacing:-.025em; }
    /* Navigation uses native Streamlit buttons; do not override button labels with the old dark-theme text. */
    div.stButton>button { border-radius:9px; font-weight:600; min-height:40px; }
    div.stButton>button[kind="secondary"] {
        background:#FFFFFF; border:1px solid #DCE3EC; color:#26364B;
    }
    div.stButton>button[kind="secondary"] p { color:#26364B !important; }
    div.stButton>button[kind="primary"] {
        background:#23354B; border:1px solid #23354B; color:#FFFFFF;
    }
    div.stButton>button[kind="primary"] p { color:#FFFFFF !important; }
    div.stButton>button:hover {border-color:#5F7895;}
    /* Ensure core text is readable even if the deployment's Streamlit theme defaults to dark. */
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#64748B !important;}
    [data-testid="stMetricLabel"] p {color:#526174 !important;}
    [data-testid="stMetricValue"] {color:#19283D !important;}
    [data-testid="stMetricValue"] * {color:#19283D !important;}
    div[data-testid="stMetric"] {background:#FFFFFF;border:1px solid #E4E9F0;border-radius:12px;padding:12px;}
    div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:13px;}
    /* Homepage ranking and highlight sections, deliberately independent of Streamlit dataframe dark mode. */
    .court-section-head {display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:20px 0 10px;}
    .court-section-head h3 {font-size:1.25rem;font-weight:750;margin:0;color:#19283D;}
    .court-section-head>span {font-size:.78rem;color:#718096;}
    .court-rank-card {overflow:hidden;background:#FFFFFF;border:1px solid #E3E8EF;border-radius:14px;margin-bottom:9px;}
    .court-rank-row {display:grid;grid-template-columns:44px minmax(0,1fr) 100px;align-items:center;gap:10px;min-height:54px;padding:10px 18px;border-bottom:1px solid #EEF1F5;color:#26364B;}
    .court-rank-row:last-child {border-bottom:0;}
    .court-rank-num {font-weight:750;color:#65758A;font-size:.9rem;}
    .court-rank-team {display:flex;align-items:center;gap:11px;font-weight:650;min-width:0;}
    .court-team-dot {display:inline-block;flex:0 0 9px;width:9px;height:9px;border-radius:50%;}
    .court-rank-score {text-align:right;font-variant-numeric:tabular-nums;font-weight:750;}
    .court-highlights {display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:16px;}
    .court-highlight-card {background:#FFFFFF;border:1px solid #E3E8EF;border-radius:13px;padding:16px;min-width:0;}
    .court-highlight-label {font-size:.68rem;color:#64748B;font-weight:750;letter-spacing:.06em;}
    .court-highlight-team {color:#26364B;font-size:.96rem;font-weight:700;margin:9px 0;}
    .court-highlight-team span {color:#8694A4;font-weight:400;}
    .court-highlight-margin {color:#63748A;font-size:.79rem;}
    .court-highlight-margin strong {color:#23354B;}
    @media (max-width:600px) {.court-rank-row{grid-template-columns:26px minmax(0,1fr) 72px;padding:10px 12px;gap:7px;}.court-section-head>span{display:none;}}


    /* V157: compact dashboard-like homepage cards and responsive two-column layout. */
    .cs157-home-banner {padding:15px 22px !important;margin-bottom:9px !important;}
    .cs157-home-banner h2 {font-size:1.55rem !important;margin:3px 0 !important;}
    .cs157-home-banner p {font-size:.82rem !important;}
    .cs157-home-banner .cs153-chips {margin-top:8px !important;}
    .cs157-home-banner .cs153-chip {font-size:10px !important;padding:3px 9px !important;}
    .court-rank-row {min-height:43px;padding:7px 12px;}
    .court-highlight-card {padding:10px !important;}
    .court-highlights {grid-template-columns:1fr;gap:7px;}
    @media (max-width:700px) {.cs157-home-banner {padding:13px 14px !important;}.cs157-home-banner h2 {font-size:1.35rem !important;}}
    /* V160: more readable compact featured matchup. */
    .cs160-feature-title {font-size:1.14rem;font-weight:750;color:#17345f;margin:7px 0 5px;}
    .cs160-matchup {display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:8px;margin-bottom:8px;}
    .cs160-team {min-width:0;padding:4px 8px;font-size:clamp(.8rem,1.1vw,1rem);font-weight:750;color:#193253;line-height:1.3;overflow-wrap:anywhere;}
    .cs160-away {text-align:right;}
    .cs160-tip {font-size:.7rem;color:#637994;text-align:center;max-width:110px;}
    .cs160-predictions {display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px;}
    .cs160-stat {min-width:0;background:#f6fbff;border:1px solid #d5e5f6;border-radius:10px;padding:8px 10px;}
    .cs160-stat span {display:block;color:#5c718c;font-size:.63rem;font-weight:650;letter-spacing:.02em;margin-bottom:3px;overflow-wrap:anywhere;}
    .cs160-stat strong {display:block;color:#153560;font-size:1.03rem;line-height:1.25;overflow-wrap:anywhere;}
    @media(max-width:700px){.cs160-tip{max-width:65px;}.cs160-stat strong{font-size:.9rem;}}
    /* V161: restore a restrained branded header without hiding the games. */
    .cs161-home-header {background:linear-gradient(110deg,#12306a,#1b469d 72%,#1e78b5);border-radius:12px;padding:12px 18px;color:#fff;margin:0 0 7px;box-shadow:0 3px 10px rgba(20,50,95,.08);border:1px solid rgba(255,255,255,.08);}
    .cs161-eyebrow {color:#c7daf8;font-size:.61rem;font-weight:800;letter-spacing:.12em;}
    .cs161-header-title {font-size:1.35rem;font-weight:800;letter-spacing:-.025em;line-height:1.28;margin:2px 0;}
    .cs161-header-sub {font-size:.75rem;color:#e6f0ff;}
    .cs160-feature-title {margin:0 0 5px !important;}
    .court-section-head {margin:0 0 10px !important;min-height:28px;align-items:center;}
    .court-section-head h3 {font-size:1.12rem !important;}
    @media(max-width:700px){.cs161-home-header{padding:10px 12px;}.cs161-header-title{font-size:1.16rem;}}
    /* V169: information-first schedule strip and tighter sports panels. */
    .cs169-summary {background:linear-gradient(105deg,#12306a,#1b469d 75%,#2577b7);border-radius:12px;color:#fff;padding:12px 17px;margin:0 0 10px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;}
    .cs169-summary strong {font-size:1.15rem;color:#fff;}
    .cs169-summary span {font-size:.79rem;color:#e5efff;}
    .cs169-games-title {font-size:1.16rem;font-weight:800;color:#17345f;margin:0 0 6px;}
    .cs160-feature-title {margin:5px 0 5px !important;}
    .cs160-matchup {margin-bottom:6px !important;}
    .cs160-stat {padding:6px 9px !important;}
    .cs160-predictions {gap:7px;margin-bottom:4px !important;}
    @media(max-width:700px){.cs169-summary{padding:10px 12px;gap:3px;}.cs169-summary strong{font-size:1rem;}.cs169-summary span{font-size:.71rem;}}
    /* V171: quiet-day game list and clickable upcoming matchup cards. */
    .cs171-upcoming {display:flex;flex-direction:column;gap:5px;}
    .cs171-upcoming-date {font-size:.68rem;color:#647894;font-weight:750;letter-spacing:.035em;}
    .cs171-upcoming strong {font-size:.91rem;color:#203b63;overflow-wrap:anywhere;}
    .cs171-upcoming strong span {color:#71859e;font-weight:450;}
    .cs171-upcoming-note {font-size:.76rem;color:#637894;}
    /* V174: make completed results the primary game-card content. */
    .cs174-final-card {border-left:4px solid #2054c5;padding:3px 0 5px 11px;}
    .cs174-final-status {display:inline-block;background:#173c83;color:white;font-weight:800;font-size:.64rem;letter-spacing:.09em;padding:3px 9px;border-radius:5px;}
    .cs174-scoreline {display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:7px;}
    .cs174-scoreline strong {font-size:1.5rem;color:#142d57;white-space:nowrap;}
    .cs174-team {font-size:.88rem;color:#62758f;font-weight:650;}
    .cs174-winner {color:#153b79;font-weight:850;}
    .cs174-final-winner {font-size:.75rem;font-weight:700;color:#0a8077;margin-top:2px;}
    @media(max-width:700px){.cs174-scoreline{gap:7px;}.cs174-scoreline strong{font-size:1.25rem;}}
    .cs175-live-card {border-left:4px solid #0e9f91;padding:6px 12px;background:#eefaf8;border-radius:6px;}
    .cs175-live-card>strong {font-size:.73rem;color:#087d73;letter-spacing:.06em;}
    .cs175-live-score {font-size:1.15rem;font-weight:800;color:#17345f;margin-top:4px;}
    /* V176: legible logos and narrow-screen controls. */
    .cs176-logo {width:24px;height:24px;object-fit:contain;flex:none;}
    .court-rank-team {display:flex;align-items:center;gap:8px;min-width:0;overflow-wrap:anywhere;}
    @media(max-width:700px) {
      .court-rank-row {grid-template-columns:24px minmax(0,1fr) 62px;gap:6px;padding:8px;}
      .cs176-logo {width:21px;height:21px;}
      .cs174-scoreline {flex-wrap:wrap;}
      .cs171-upcoming strong {line-height:1.4;}
    }
    .cs178-feature-team {display:flex;align-items:center;gap:8px;}
    .cs178-feature-team.cs160-away {justify-content:flex-end;}
    .cs178-feature-team span {min-width:0;}
    .cs178-feature-logo {width:38px;height:38px;object-fit:contain;flex:none;}
    @media(max-width:700px) {.cs178-feature-team{gap:5px;flex-wrap:wrap;}.cs178-feature-logo{width:27px;height:27px;}}
    /* V221: featured matchup is in a one-third width card. */
    .cs160-matchup{grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:5px;row-gap:1px;}
    .cs160-matchup .cs160-tip{grid-column:1/-1;grid-row:2;justify-self:center;max-width:none;}
    .cs160-predictions{grid-template-columns:1fr;}
    .cs160-team{font-size:.85rem;padding:4px;overflow-wrap:anywhere;}
    .cs178-feature-logo{width:26px;height:26px;}
    .cs178-feature-team{gap:5px;align-items:center;flex-wrap:wrap;}
    @media(max-width:950px){.cs160-team{font-size:.79rem}.cs178-feature-logo{width:22px;height:22px}}
    /* V222: tighter spacing in the unified independent-column homepage. */
    .cs222-divider{height:1px;border-top:1px solid #e5edf7;margin:3px 0;}
    .st-key-cs222_rankings_list [data-testid="stVerticalBlock"]{gap:.22rem!important;}
    .st-key-cs222_rankings_list [data-testid="stHorizontalBlock"]{align-items:center;gap:.35rem;}
    .st-key-cs222_rankings_list [data-testid="stImage"] img{max-height:25px;object-fit:contain;}
    .st-key-cs222_rankings_list button{min-height:32px!important;padding:3px 5px!important;font-size:.79rem!important;text-align:left;}
    .st-key-cs221_upcoming_tile [data-testid="stVerticalBlock"]{gap:.36rem!important;}
    .st-key-cs221_upcoming_tile button{min-height:30px!important;font-size:.78rem!important;}
    .st-key-cs221_upcoming_tile .cs171-upcoming{gap:3px;}
    @media(max-width:700px){
      .st-key-cs222_rankings_list [data-testid="stHorizontalBlock"]{gap:.25rem;}
      .st-key-cs222_rankings_list button{font-size:.78rem!important}
    }
    /* V223: all four original panels use the same surface and hierarchy as insights. */
    [class*="st-key-cs223_tile_"]{
      background:#fff!important;border:1px solid #dee7f2!important;
      border-top:3px solid #2b69b9!important;border-radius:12px!important;
      padding:12px 13px!important;min-width:0;
    }
    .st-key-cs223_tile_featured{border-top-color:#a45a90!important}
    .st-key-cs223_tile_rankings{border-top-color:#2d6cb9!important}
    .st-key-cs223_tile_upcoming{border-top-color:#0e8a83!important}
    [class*="st-key-cs223_tile_"] [data-testid="stVerticalBlock"]{gap:.46rem}
    [class*="st-key-cs223_tile_"] button{
      min-height:30px;font-size:.78rem!important;
    }
    [class*="st-key-cs223_tile_"] .cs219-card-head{margin-bottom:4px}
    [class*="st-key-cs223_tile_"] .cs219-sub{margin:0 0 8px}
    .st-key-cs223_tile_games .cs169-games-title{font-size:1.02rem}
    .st-key-cs223_tile_games [data-testid="stSelectbox"]{margin:0 0 3px}
    .st-key-cs223_tile_games [data-testid="stVerticalBlock"]{gap:.32rem}
    .st-key-cs223_tile_featured .cs160-matchup{margin:2px 0 8px!important}
    .st-key-cs223_tile_featured .cs160-predictions{margin-bottom:6px!important}
    .st-key-cs223_tile_rankings [data-testid="stVerticalBlock"]{gap:.27rem}
    .st-key-cs223_tile_rankings .st-key-cs222_rankings_list button{border:0!important;background:transparent!important;}
    .st-key-cs223_tile_upcoming .cs171-upcoming{gap:3px}
    @media(max-width:700px){
      [class*="st-key-cs223_tile_"]{padding:10px!important}
    }
    /* V224: compact home scoreboard tiles, with team-aligned result scores. */
    [class*="st-key-cs224_game_card_"]{
      background:#f8fbff;border:1px solid #e0e8f4;border-radius:10px;
      padding:9px 10px!important;margin-bottom:7px;min-width:0;
    }
    [class*="st-key-cs224_game_card_"] [data-testid="stVerticalBlock"]{gap:.3rem!important}
    [class*="st-key-cs224_game_card_"] button{
      min-height:28px!important;font-size:.76rem!important;
      border:1px solid #d3e2f7!important;background:#fff!important;
    }
    .cs224-game{min-width:0;color:#233e65}
    .cs224-game-head{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-bottom:6px}
    .cs224-status{font-size:.65rem;font-weight:850;letter-spacing:.035em;padding:3px 7px;
       color:#20549d;background:#e7f0ff;border-radius:5px;white-space:nowrap}
    .cs224-final .cs224-status{color:#fff;background:#1e4b94}
    .cs224-live .cs224-status{color:#06786c;background:#dff8f2}
    .cs224-game-meta{font-size:.68rem;color:#73869f;text-align:right;line-height:1.3}
    .cs224-teams{display:grid;gap:2px}
    .cs224-team-row{display:flex;align-items:center;gap:7px;min-width:0;
       min-height:32px;padding:4px 5px;border-radius:7px}
    .cs224-winner{background:#e8f2ff}
    .cs224-team-name{flex:1;min-width:0;overflow-wrap:anywhere;
       font-size:.84rem;font-weight:650;color:#2d4669;line-height:1.25}
    .cs224-winner .cs224-team-name{font-weight:850;color:#173d78}
    .cs224-logo{width:23px;height:23px;object-fit:contain;flex:none}
    .cs224-score{min-width:27px;flex:none;text-align:right;
       font-size:1.07rem;line-height:1;font-weight:750;color:#71829a;
       font-variant-numeric:tabular-nums}
    .cs224-winner .cs224-score{color:#163d83;font-weight:900}
    .cs224-win{font-size:.57rem;line-height:1;color:#1d61ab;font-weight:850;
       border:1px solid #bed3ec;border-radius:4px;padding:3px 4px}
    .cs224-side{font-size:.59rem;color:#8395ac;letter-spacing:.04em;font-weight:750}
    .cs224-prediction{border-top:1px solid #e7edf7;margin-top:5px;padding:7px 3px 0;
       font-size:.73rem;color:#526b90;line-height:1.3;overflow-wrap:anywhere}
    @media(max-width:850px){
      [class*="st-key-cs224_game_card_"]{padding:8px!important}
      .cs224-team-name{font-size:.81rem}
      .cs224-logo{width:21px;height:21px}
    }
    </style>''',unsafe_allow_html=True)

def featured_choice(upcoming, ratings, d1_ids):
    """Prefer D1 games with two rated teams; strong teams and close projections."""
    if upcoming.empty:return None
    shortlist=upcoming[upcoming['Home ID'].astype(str).isin(d1_ids) & upcoming['Away ID'].astype(str).isin(d1_ids)].copy()
    if shortlist.empty:return None
    shortlist=shortlist[shortlist['Home ID'].astype(str).isin(ratings) & shortlist['Away ID'].astype(str).isin(ratings)].copy()
    if shortlist.empty:return None
    def value(row):
        h,a=ratings[str(row['Home ID'])],ratings[str(row['Away ID'])]
        margin=h-a+(0 if row['Venue']=='Neutral' else 3)
        return max(h,a)*0.4+min(h,a)*0.2-abs(margin)*0.45
    shortlist['_interesting']=shortlist.apply(value,axis=1)
    return shortlist.sort_values('_interesting',ascending=False).iloc[0]

def select_home_games(visible, ratings, top25_names, mode="Featured"):
    """Prioritize competitive rated games on busy days; retain final scores in All."""
    if visible.empty:
        return visible.copy()
    candidates = visible.copy()
    candidates["_game_order"] = range(len(candidates))
    def interest(row):
        hid, aid = str(row["Home ID"]), str(row["Away ID"])
        if hid in ratings and aid in ratings and row["Status"] == "Scheduled":
            margin = ratings[hid] - ratings[aid] + (0 if row["Venue"] == "Neutral" else 3)
            return abs(margin)
        return float("inf")
    candidates["_margin_abs"] = candidates.apply(interest, axis=1)
    candidates["_top25"] = candidates["Home"].astype(str).isin(top25_names) | candidates["Away"].astype(str).isin(top25_names)
    if mode == "Top 25":
        candidates = candidates[candidates["_top25"]]
    elif mode == "Closest":
        candidates = candidates[candidates["_margin_abs"] != float("inf")]
    if mode in ("Featured", "Top 25", "Closest"):
        candidates = candidates.sort_values(["_top25", "_margin_abs", "_game_order"], ascending=[False, True, True]) if mode == "Featured" else candidates.sort_values(["_margin_abs", "_game_order"])
    return candidates.drop(columns=["_game_order", "_margin_abs", "_top25"])


def _load_home_cards(league, team_ratings, d1_ids):
    """Read existing research snapshots once per homepage refresh."""
    from home_insights_v219 import load_home_insight_cards
    sport = "womens-college-basketball" if league == "Women's" else "mens-college-basketball"
    return {card.id: card for card in load_home_insight_cards(
        team_ratings, d1_ids, league,
        sos=st.session_state.get(f"sos_{sport}"),
        sor=st.session_state.get(f"sor_{sport}"),
    )}


def _show_home_card(cards, name, league):
    from home_insights_v219 import render_home_insight_card
    if name in cards:
        render_home_insight_card(cards[name], league)


def home_game_scoreboard_markup(row, d1: bool, proj=None, show_logos=True):
    """Compact two-team result display; scores and winner are always attached to a team.

    This is display-only. Actual scores, statuses, projections and team IDs still
    come from the existing scoreboard / rating sources.
    """
    def score_value(value):
        try:
            numeric = pd.to_numeric(value, errors="coerce")
            if pd.notna(numeric) and float(numeric) >= 0 and float(numeric).is_integer():
                return int(numeric)
        except (TypeError, ValueError, OverflowError):
            pass
        return None

    status = str(row.get("Status", "Scheduled"))
    is_final = row["Status"] == "Final"
    is_live = row["Status"] == "Live"
    started = is_final or is_live
    away_score = score_value(row.get("Away score")) if started else None
    home_score = score_value(row.get("Home score")) if started else None
    has_scores = away_score is not None and home_score is not None
    away_won = is_final and has_scores and away_score > home_score
    home_won = is_final and has_scores and home_score > away_score

    badge = "FINAL" if is_final else "● LIVE" if is_live else status.upper()
    status_class = "final" if is_final else "live" if is_live else "scheduled"
    when = row.get("Display time")
    if when is None or pd.isna(when) or not str(when).strip():
        when = row.get("Time (ET)", "")
    details = "D1 vs D1" if d1 else "Other matchup"
    if not started and pd.notna(when) and str(when).strip():
        details = f"{when} · {details}"

    def team_line(side, name, identifier, points, won):
        ident = str(identifier)
        logo = (
            f'<img class="cs224-logo" src="https://a.espncdn.com/i/teamlogos/ncaa/500/{ident}.png" '
            'alt="" loading="lazy">'
            if show_logos and ident.isdigit() else ""
        )
        score = str(points) if points is not None else "—" if started else ""
        position = "" if started else f'<span class="cs224-side">{side}</span>'
        winner = '<span class="cs224-win">W</span>' if won else ""
        css_class = " cs224-winner" if won else ""
        return (
            f'<div class="cs224-team-row{css_class}">'
            f'{logo}<span class="cs224-team-name">{html.escape(str(name))}</span>{winner}'
            f'<span class="cs224-score">{score}</span>{position}</div>'
        )

    away = team_line("AWAY", row.get("Away", "—"), row.get("Away ID", ""),
                     away_score, away_won)
    home = team_line("HOME", row.get("Home", "—"), row.get("Home ID", ""),
                     home_score, home_won)

    footer = ""
    if not started:
        description = "Model: " + str(proj) if proj else "No D1 model line"
        footer = f'<div class="cs224-prediction">{html.escape(description)}</div>'
    elif not has_scores:
        footer = '<div class="cs224-prediction">Score unavailable</div>'

    return (
        f'<div class="cs224-game cs224-{status_class}">'
        f'<div class="cs224-game-head"><span class="cs224-status">{html.escape(badge)}</span>'
        f'<span class="cs224-game-meta">{html.escape(details)}</span></div>'
        f'<div class="cs224-teams">{away}{home}</div>'
        f'{footer}</div>'
    )


def _classic_home_card_heading(title: str, subtitle: str, badge: str = ""):
    """Match the newer insight tiles; titles and values are HTML-escaped."""
    badge_html = f'<span>{html.escape(badge)}</span>' if badge else ""
    st.html(
        '<div class="cs219-card-head">'
        f'<strong>{html.escape(title)}</strong>{badge_html}</div>'
        f'<div class="cs219-sub">{html.escape(subtitle)}</div>'
    )


def render_home(games, ratings, team_ratings, d1_ids, league, window):
    time_zone = st.session_state.get("courtside_timezone", "Central")
    today=pd.Timestamp.now(tz='America/New_York').date()
    visible=games[games['Date'].eq(str(today))].copy()
    # Before the season, offer next available games instead of a fake 'today' list.
    if visible.empty:
        remaining=games[games['Status'].eq('Scheduled')].copy()
        remaining=remaining[remaining['Date']>=str(today)]
        if not remaining.empty:
            target=remaining['Date'].min()
            visible=remaining[remaining['Date'].eq(target)].copy()
            st.info(f"No games are listed today in the selected window. Showing the next scheduled date: {target}.")
        else:st.info('No games are listed for today in the selected schedule window.')
    rated_count=len(team_ratings) if isinstance(team_ratings,pd.DataFrame) else 0
    d1_visible=visible[visible['Home ID'].astype(str).isin(d1_ids)&visible['Away ID'].astype(str).isin(d1_ids)]
    if visible.empty:
        st.caption("No games available for today in the current schedule window. Try another date in Games.")
    game_date = pd.to_datetime(visible.iloc[0]['Date'], errors='coerce') if not visible.empty else pd.NaT
    date_label = game_date.strftime('%b %-d') if pd.notna(game_date) else 'Today'
    st.markdown(
        f'<div class="cs169-summary"><strong>{html.escape(date_label)} · {len(visible)} game{"s" if len(visible) != 1 else ""}</strong>'
        f'<span>{html.escape(league)} Division I · {len(d1_visible)} D1 matchup{"s" if len(d1_visible) != 1 else ""} · {html.escape(time_zone)} time</span></div>',
        unsafe_allow_html=True)

    # V222: genuine three-column magazine layout, not three height-locked rows.
    # Each column stacks independently, so a long scoreboard/upcoming panel
    # cannot leave empty space beside shorter insights in another column.
    from home_insights_v219 import STYLE as HOME_INSIGHT_STYLE
    st.markdown(HOME_INSIGHT_STYLE, unsafe_allow_html=True)
    cards = _load_home_cards(league, team_ratings, d1_ids)
    home_columns = st.columns(3, gap="small")
    with home_columns[0]:
        with st.container(border=True, key="cs223_tile_games"):
            top25_names = set()
            if isinstance(team_ratings, pd.DataFrame) and {"Team", "Current power"}.issubset(team_ratings.columns):
                top25_names = set(team_ratings.sort_values("Current power", ascending=False).head(25)["Team"].astype(str))
            _classic_home_card_heading("Today’s matchups", "Scores, schedules and model lines", f"{len(visible)} games")
            busy = len(visible) > 30
            mode = "Featured"
            if busy:
                mode = st.selectbox("Homepage games", ["Featured", "Top 25", "Closest", "All"],
                                key="cs170_game_filter", label_visibility="collapsed")
            home_display = select_home_games(visible, ratings, top25_names, mode) if busy else visible.copy()
            if busy and mode == "Featured":
                home_display = home_display.head(12)
            elif busy and mode != "All":
                home_display = home_display.head(25)
            if home_display.empty:
                st.caption("No games match this filter. Choose All to see the complete schedule.")
            with (st.container(height=320,border=False) if len(visible) > 5 else st.container(border=False)):
                for ix, row in home_display.reset_index(drop=True).iterrows():
                    home,away=str(row['Home']),str(row['Away'])
                    h_id,a_id=str(row['Home ID']),str(row['Away ID'])
                    d1=h_id in d1_ids and a_id in d1_ids
                    proj=None
                    if d1 and h_id in ratings and a_id in ratings and row['Status']=='Scheduled':
                        m=ratings[h_id]-ratings[a_id]+(0 if row['Venue']=='Neutral' else 3)
                        proj=f"{home if m>=0 else away} -{abs(m):.1f}"
                    with st.container(key=f"cs224_game_card_{ix}"):
                        st.html(home_game_scoreboard_markup(
                            row, d1, proj,
                            show_logos=st.session_state.get("courtside_logos_enabled", True),
                        ))
                        if st.button('Details →', key=f'court_game_{row["Game ID"]}_{ix}',
                                     use_container_width=True):
                            st.session_state['courtside_selected_game'] = str(row['Game ID'])
                            st.session_state['courtside_requested_page'] = 'Games'
                            st.rerun()
            if len(visible) > 5 and busy:
                st.caption(f"Showing {len(home_display)} of {len(visible)} games · Choose All for the full day.")
            if st.button("View complete schedule →", key="cs170_all_games", use_container_width=True):
                st.session_state["courtside_requested_page"] = "Games"
                st.rerun()
        with st.container(border=True, key="cs223_tile_upcoming"):
            _classic_home_card_heading("Coming up", "Closest games · Next 7 days", "Next 7 days")
            # Avoid repeating the featured game or today's games in Highlights.
            # Only use later dates already loaded from the selected schedule window.
            later = games[(games["Date"] > str(today)) &
                          (games["Date"] <= str(today + pd.Timedelta(days=7))) &
                          (games["Status"] == "Scheduled")]
            upcoming = later[later["Home ID"].astype(str).isin(d1_ids) &
                             later["Away ID"].astype(str).isin(d1_ids)]
            highlight_scores = []
            for _, game in upcoming.iterrows():
                hid, aid = str(game["Home ID"]), str(game["Away ID"])
                if hid not in ratings or aid not in ratings:
                    continue
                margin = ratings[hid] - ratings[aid] + (0 if game["Venue"] == "Neutral" else 3)
                highlight_scores.append((abs(margin), game))
            if highlight_scores:
                with st.container(border=False, key="cs221_upcoming_tile"):
                    for index, (closeness, game) in enumerate(sorted(highlight_scores, key=lambda entry: (entry[0], str(entry[1]["Date"])))[:3]):
                        away, home = str(game["Away"]), str(game["Home"])
                        when = str(game.get("Display time", game["Time (ET)"]))
                        game_date = str(game["Date"])
                        hid, aid = str(game["Home ID"]), str(game["Away ID"])
                        margin = ratings[hid] - ratings[aid] + (0 if game["Venue"] == "Neutral" else 3)
                        from math import erf, sqrt
                        home_probability = .5 * (1 + erf(margin / (11 * sqrt(2))))
                        favorite = home if margin >= 0 else away
                        favorite_probability = home_probability if margin >= 0 else 1 - home_probability
                        margin_note = f"{favorite} win probability: {favorite_probability:.0%}"
                        if index:
                            st.markdown('<div class="cs222-divider"></div>', unsafe_allow_html=True)
                        st.markdown(
                            '<div class="cs171-upcoming">'
                            f'<span class="cs171-upcoming-date">{html.escape(game_date)} · {html.escape(when)}</span>'
                            f'<strong>{html.escape(away)} <span>at</span> {html.escape(home)}</strong>'
                            f'<span class="cs171-upcoming-note">{html.escape(margin_note)} · {html.escape(str(game["Venue"]))} venue</span>'
                            '</div>', unsafe_allow_html=True)
                        if st.button('View matchup →', key=f'cs171_highlight_{index}_{game["Game ID"]}', use_container_width=False):
                            # Pass the exact selected row: Games may load a different date range.
                            st.session_state["courtside_selected_game"] = str(game["Game ID"])
                            st.session_state["courtside_selected_game_payload"] = game.to_dict()
                            st.session_state["courtside_requested_page"] = "Games"
                            st.rerun()
            else:
                with st.container(border=False, key="cs221_upcoming_tile"):
                    st.caption("No upcoming rated D1 matchups are available in the loaded schedule.")
    with home_columns[1]:
        with st.container(border=True, key="cs223_tile_featured"):
            _classic_home_card_heading("Featured game · Model preview", "Courtside projected matchup", "Model")
            scheduled=visible[visible['Status']=='Scheduled']
            featured=featured_choice(scheduled,ratings,d1_ids)
            if featured is not None:
                h,a=str(featured['Home']),str(featured['Away'])
                hid,aid=str(featured['Home ID']),str(featured['Away ID'])
                home_color,away_color=color_for(h),color_for(a)
                margin=ratings[hid]-ratings[aid]+(0 if featured['Venue']=='Neutral' else 3)
                from math import erf,sqrt
                chance=.5*(1+erf(margin/(11*sqrt(2))))
                favorite=h if margin>=0 else a
                show_feature_logos = st.session_state.get("courtside_logos_enabled", True)
                home_logo = (f'<img class="cs178-feature-logo" src="https://a.espncdn.com/i/teamlogos/ncaa/500/{hid}.png" alt="" loading="lazy"/>'
                             if show_feature_logos and hid.isdigit() else "")
                away_logo = (f'<img class="cs178-feature-logo" src="https://a.espncdn.com/i/teamlogos/ncaa/500/{aid}.png" alt="" loading="lazy"/>'
                             if show_feature_logos and aid.isdigit() else "")
                with st.container(border=False):
                    st.markdown(f'''<div class="cs160-matchup">
                      <div class="cs160-team cs178-feature-team" style="border-left:4px solid {home_color}">{home_logo}<span>{html.escape(h)}</span></div>
                      <div class="cs160-tip">VS · {html.escape(str(featured.get('Display time',featured['Time (ET)'])))}</div>
                      <div class="cs160-team cs160-away cs178-feature-team" style="border-right:4px solid {away_color}">{away_logo}<span>{html.escape(a)}</span></div>
                    </div>''',unsafe_allow_html=True)
                    st.markdown('<div class="cs160-predictions">'
                        f'<div class="cs160-stat"><span>PROJECTED SPREAD</span><strong>{html.escape(favorite)} -{abs(margin):.1f}</strong></div>'
                        f'<div class="cs160-stat"><span>{html.escape(h)} WIN PROBABILITY</span><strong>{chance:.0%}</strong></div>'
                        '</div>', unsafe_allow_html=True)
                    st.progress(float(max(0,min(1,chance))))
                    st.caption('Experimental prediction · Not a sportsbook line')
                    if st.button('Game details →',key='courtside_feature_details',use_container_width=True):
                        st.session_state['courtside_selected_game']=str(featured['Game ID'])
                        st.session_state['courtside_requested_page']='Games'
                        st.rerun()
            else:
                st.caption('A featured matchup will appear when both D1 opponents have published ratings.')
        _show_home_card(cards, "polls", league)
        _show_home_card(cards, "movers", league)
        _show_home_card(cards, "strength", league)
    with home_columns[2]:
        with st.container(border=True, key="cs223_tile_rankings"):
            _classic_home_card_heading("Power rankings", "Tap a team to view its profile", "Top 5")
            # Integrated light-theme rankings card: native st.dataframe rendered dark on some deployments.
            if isinstance(team_ratings,pd.DataFrame) and {'Team','Current power'}.issubset(team_ratings.columns) and not team_ratings.empty:
                top=team_ratings.sort_values('Current power',ascending=False).head(5).copy()
                with st.container(border=False, key="cs222_rankings_list"):
                    for rank, (_, team) in enumerate(top.iterrows(), start=1):
                        name = str(team["Team"])
                        rating = float(team["Current power"])
                        team_id = str(team.get("Team ID", ""))
                        rank_col, logo_col, team_col, rating_col = st.columns([0.45, 0.55, 3.3, 1.0], vertical_alignment="center", gap="small")
                        with rank_col:
                            st.markdown(f'**{rank}**')
                        with logo_col:
                            if st.session_state.get("courtside_logos_enabled", True) and team_id.isdigit():
                                st.image(f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png", width=25)
                            else:
                                st.markdown('<span class="court-team-dot" style="background:' + color_for(name) + '"></span>', unsafe_allow_html=True)
                        with team_col:
                            if st.button(f"{name} →", key=f"cs177_team_{rank}_{team_id}",
                                         use_container_width=True, type="tertiary"):
                                st.session_state["courtside_requested_team"] = name
                                st.session_state["courtside_requested_team_id"] = team_id
                                st.session_state["courtside_requested_page"] = "Teams"
                                st.rerun()
                        with rating_col:
                            st.markdown(f'<div style="text-align:right;font-weight:750;color:#17345f">{rating:+.2f}</div>',unsafe_allow_html=True)
                        if rank < len(top):
                            st.markdown('<div class="cs222-divider"></div>', unsafe_allow_html=True)
                if st.button('View full rankings →',key='courtside_rankings',use_container_width=True):
                    st.session_state['courtside_requested_page']='Rankings';st.rerun()
            else:
                st.info('Power rankings will appear when saved ratings are available.')
        _show_home_card(cards, "conferences", league)
        _show_home_card(cards, "tournament", league)
        _show_home_card(cards, "players", league)
