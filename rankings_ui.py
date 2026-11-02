"""Courtside V56: searchable paginated public rankings without modifying ratings."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st


MOBILE_CARD_STYLE = '''<style>
.cs79-grid{display:grid!important;grid-template-columns:38px minmax(0,1fr) minmax(76px,max-content)!important;align-items:center!important;gap:12px!important;width:100%!important;min-width:0!important;color:#23354b}
.cs79-rank{color:#64748b;font-weight:750;font-size:.9rem}
.cs79-team{min-width:0!important;overflow-wrap:anywhere!important}
.cs79-name{font-weight:700;font-size:.96rem;line-height:1.25;color:#23354b}
.cs79-meta{font-size:.77rem;color:#718096;margin-top:4px}
.cs79-result{text-align:right!important;min-width:0!important;justify-self:end!important}
.cs79-number{font-size:1.08rem;color:#23354b;font-weight:750;white-space:nowrap}
.cs79-label{color:#718096;font-size:.69rem;line-height:1.22;overflow-wrap:anywhere}
@media(max-width:640px){.cs79-grid{grid-template-columns:29px minmax(0,1fr) 80px!important;gap:8px!important}.cs79-name{font-size:.87rem}.cs79-meta{font-size:.71rem}.cs79-number{font-size:1rem}.cs79-label{font-size:.63rem}}
</style>'''

def _fmt(value, signed=False):
    try:
        x=float(value)
        if not math.isfinite(x): return '—'
        return f'{x:+.1f}' if signed else f'{x:.1f}'
    except (TypeError, ValueError):
        return '—'



def _tile_markup(item, value, metric_label, logos_enabled):
    """Safe, data-only markup for the optional dense rankings tile view."""
    name = html.escape(str(item.get("Team", "Unknown")))
    conf = html.escape(str(item.get("Conference", "Unassigned")))
    tid = str(item.get("Team ID", "")).strip()
    rank = item.get("Rank")
    try:
        rank_label = f"#{int(rank)}" if pd.notna(rank) else "—"
    except (TypeError, ValueError):
        rank_label = "—"
    if logos_enabled and tid.isdigit():
        logo = (
            f'<img class="cr195-logo" '
            f'src="https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png" '
            'alt="" loading="lazy"/>'
        )
    else:
        initials = "".join(piece[0] for piece in str(item.get("Team", "")).split()[:2]) or "?"
        logo = f'<span class="cr195-monogram">{html.escape(initials.upper())}</span>'
    played = item.get("Games played")
    try:
        played_label = str(int(played)) if pd.notna(played) else "—"
    except (TypeError, ValueError):
        played_label = "—"
    # These are model values, not movement in an official poll.
    if metric_label == "Experimental":
        context = f'Baseline {_fmt(item.get("Current power"), True)}'
    else:
        change = _fmt(item.get("Rating change"), True)
        context = f'Vs preseason {change}' if change != "—" else (
            f'Preseason {_fmt(item.get("Preseason rating"), True)}'
        )
    return (
        '<div class="cr195-tile">'
        '<div class="cr195-top"><span class="cr195-rank">' + html.escape(rank_label) +
        '</span><span class="cr195-conf">' + conf + '</span></div>'
        '<div class="cr195-identity">' + logo +
        '<span class="cr195-name">' + name + '</span></div>'
        '<div class="cr195-metrics">'
        '<div><span class="cr195-metric-label">' + html.escape(metric_label) +
        '</span><strong class="cr195-metric-value">' + html.escape(_fmt(value, True)) +
        '</strong></div>'
        '<div class="cr195-played"><span class="cr195-metric-label">Games</span>'
        '<strong>' + played_label + '</strong></div></div>'
        '<div class="cr195-context">' + html.escape(context) + '</div>'
        '</div>'
    )


def render_rankings(ratings: pd.DataFrame, preliminary: pd.DataFrame, league: str, verified_d1_ids: set[str]):
    st.markdown('''<style>
    .cr-head{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:17px 20px;margin-bottom:14px}
    .cr-head h2{font-size:1.5rem;color:#243449;margin:0 0 5px}
    .cr-sub{font-size:.86rem;color:#69798c}
    .cr-row{background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:10px 15px;margin:0 0 4px;min-height:60px;display:flex;align-items:center;gap:14px}
    .cr-rank{width:35px;font-weight:700;color:#64748b;flex-shrink:0}
    .cr-dot{width:8px;height:8px;border-radius:50%;background:#34465f;flex-shrink:0}
    .cr-name{font-size:.96rem;color:#23354b;font-weight:650;overflow-wrap:anywhere}
    .cr-conf{font-size:.76rem;color:#728096}
    .cr-value{font-weight:750;color:#23354b;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
    .cr-label{font-size:.71rem;color:#728096;text-align:right}

    /* V195: three-up rankings tiles, keeping the original list available. */
    .st-key-cr195_tile_grid [class*="st-key-cr195_tile_"]{
      background:#fff;border:1px solid #d8e3f2;border-top:3px solid #2760b8;
      border-radius:12px;padding:10px 12px 8px;min-width:0;
      box-shadow:0 2px 7px rgba(27,61,109,.05)
    }
    .cr195-tile{min-height:132px}
    .cr195-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .cr195-rank{font-size:.82rem;font-weight:850;color:#1a478a;background:#edf3fc;
      border-radius:7px;padding:3px 7px}
    .cr195-conf{font-size:.71rem;color:#6c7b90;text-align:right;overflow-wrap:anywhere}
    .cr195-identity{display:flex;align-items:center;gap:9px;margin:10px 0;min-height:38px}
    .cr195-logo{width:38px;height:38px;object-fit:contain;flex:none}
    .cr195-monogram{width:38px;height:38px;display:grid;place-items:center;flex:none;
      border-radius:9px;background:#e4edf9;color:#28518a;font-size:.86rem;font-weight:800}
    .cr195-name{font-size:.98rem;line-height:1.22;font-weight:800;color:#20385e;
      overflow-wrap:anywhere;min-width:0}
    .cr195-metrics{display:flex;justify-content:space-between;gap:10px;
      border-top:1px solid #e7edf5;padding-top:8px}
    .cr195-metric-label{font-size:.69rem;color:#697c97;display:block}
    .cr195-metric-value{font-size:1.23rem;font-weight:850;color:#19457f;
      font-variant-numeric:tabular-nums}
    .cr195-played{text-align:right;min-width:42px}
    .cr195-played strong{font-size:1rem;color:#23436a;font-variant-numeric:tabular-nums}
    .cr195-context{font-size:.69rem;color:#667a96;margin-top:5px;min-height:13px}
    .st-key-cr195_tile_grid [class*="st-key-cr195_tile_"] button{
      min-height:30px!important;font-size:.78rem!important;margin-top:1px
    }
    @media(max-width:700px){.cr195-name{font-size:.9rem}.cr195-logo,.cr195-monogram{width:30px;height:30px}}
    </style>''',unsafe_allow_html=True)
    st.markdown(MOBILE_CARD_STYLE, unsafe_allow_html=True)
    st.markdown(f'<div class="cr-head"><h2>National Power Rankings</h2><div class="cr-sub">{html.escape(league)} Division I · Saved baseline ratings · Select a team for its scouting report</div></div>',unsafe_allow_html=True)
    if not isinstance(ratings,pd.DataFrame) or ratings.empty:
        st.info('Rankings will appear once saved ratings are available.')
        return
    data=ratings.copy()
    if 'Team' not in data or 'Current power' not in data:
        st.warning('Saved ratings do not contain the expected team and rating columns.')
        return
    data['Current power']=pd.to_numeric(data['Current power'],errors='coerce')
    data=data.dropna(subset=['Team','Current power']).copy()
    # D1 membership comes from the current-season ESPN conference hierarchy,
    # not the rated schedule or the conference label in the saved snapshot.
    # Fail closed instead of treating unverified/non-D1 opponents as D1.
    if 'Team ID' not in data.columns:
        st.warning('Cannot verify Division I membership: saved ratings lack Team ID.')
        return
    if not verified_d1_ids:
        st.warning('Division I membership is currently unavailable. Rankings are hidden rather than including unverified schools.')
        return
    allowed = {str(team_id) for team_id in verified_d1_ids}
    data['Team ID'] = data['Team ID'].astype(str)
    data = data[data['Team ID'].isin(allowed)].copy()
    if data.empty:
        st.info('No rated, verified Division I teams are available yet.')
        return
    if 'Conference' not in data: data['Conference']='Unassigned'
    data['Conference']=data['Conference'].fillna('Unassigned').astype(str)
    exp_available=isinstance(preliminary,pd.DataFrame) and not preliminary.empty and {'Team ID','Experimental power'}.issubset(preliminary.columns) and 'Team ID' in data.columns
    if exp_available:
        extra=preliminary[['Team ID','Experimental power','Roster adjustment']].copy() if 'Roster adjustment' in preliminary else preliminary[['Team ID','Experimental power']].copy()
        extra['Team ID']=extra['Team ID'].astype(str)
        data['Team ID']=data['Team ID'].astype(str)
        data=data.merge(extra.drop_duplicates('Team ID'),on='Team ID',how='left',suffixes=('','_experiment'))
    c1,c2,c3=st.columns([2.3,1.7,1.5])
    with c1: query=st.text_input('Search teams',placeholder='Search by school or mascot…',key='cr_search')
    with c2:
        conferences=['All conferences']+sorted(c for c in data['Conference'].unique() if c and c!='Unassigned')
        conference=st.selectbox('Conference',conferences,key='cr_conference')
    with c3:
        sorts=['Power rating','School name','Games played']
        if exp_available: sorts.append('Experimental rating')
        sort=st.selectbox('Sort by',sorts,key='cr_sort')
    if query.strip(): data=data[data['Team'].astype(str).str.contains(query.strip(),case=False,regex=False,na=False)]
    if conference!='All conferences': data=data[data['Conference']==conference]
    order_col={'Power rating':'Current power','School name':'Team','Games played':'Games played','Experimental rating':'Experimental power'}.get(sort,'Current power')
    if order_col not in data:order_col='Current power'
    data=data.sort_values(order_col,ascending=(sort=='School name'),na_position='last',kind='stable')
    total=len(data)
    st.caption(f'{total:,} matching verified Division I teams · Rankings are model estimates, not NCAA NET rankings.')
    if not total:
        st.info('No teams match these filters.')
        return

    # V195: dense three-column tiles are the default, while the original list
    # remains selectable for scanning one team at a time.
    view_mode = st.segmented_control(
        "Display rankings", ["Tiles", "Compact list"],
        default="Tiles", key="cr195_view_mode"
    )
    per_page=25
    max_page=max(1,math.ceil(total/per_page))
    if "cr_page" in st.session_state:
        try:
            st.session_state["cr_page"] = max(1, min(max_page, int(st.session_state["cr_page"])))
        except (ValueError, TypeError):
            st.session_state["cr_page"] = 1
    page=st.number_input('Page',min_value=1,max_value=max_page,value=1,step=1,key='cr_page') if max_page>1 else 1
    start=(int(page)-1)*per_page
    shown=data.iloc[start:start+per_page]
    logos_enabled = st.session_state.get("courtside_logos_enabled", True)
    if view_mode == "Tiles":
        with st.container(key="cr195_tile_grid"):
            for row_start in range(0, len(shown), 3):
                tile_cols = st.columns(3, gap="small")
                tile_rows = list(shown.iloc[row_start:row_start + 3].iterrows())
                for col_index, (_, item) in enumerate(tile_rows):
                    j = row_start + col_index
                    value = item.get("Experimental power") if sort == "Experimental rating" else item["Current power"]
                    label = "Experimental" if sort == "Experimental rating" else "Power rating"
                    with tile_cols[col_index]:
                        with st.container(
                            key=f'cr195_tile_{league}_{str(item["Team ID"])}_{start+j}',
                            border=True
                        ):
                            st.html(_tile_markup(item, value, label, logos_enabled))
                            if st.button(
                                "View team →",
                                key=f'cr_open_{league}_{item.get("Team ID",str(item["Team"]))}_{start+j}',
                                use_container_width=True
                            ):
                                st.session_state['v12_team_pick'] = str(item['Team'])
                                st.session_state['courtside_page'] = 'Teams'
                                st.rerun()
    else:
        for j,(_,item) in enumerate(shown.iterrows()):
            rank=item.get('Rank')
            try: rank_label=f'#{int(rank)}' if pd.notna(rank) else '—'
            except (TypeError,ValueError):rank_label='—'
            v=item.get('Experimental power') if sort=='Experimental rating' else item['Current power']
            label='Experimental' if sort=='Experimental rating' else 'Power rating'
            with st.container(border=True):
                st.html(
                    '<div class="cs79-grid">'
                    f'<div class="cs79-rank">{html.escape(rank_label)}</div>'
                    '<div class="cs79-team">'
                    f'<div class="cs79-name">{html.escape(str(item["Team"]))}</div>'
                    f'<div class="cs79-meta">{html.escape(str(item["Conference"]))}</div>'
                    '</div><div class="cs79-result">'
                    f'<div class="cs79-number">{html.escape(_fmt(v, True))}</div>'
                    f'<div class="cs79-label">{html.escape(label)}</div>'
                    '</div></div>'
                )
                if st.button('View team →',key=f'cr_open_{league}_{item.get("Team ID",str(item["Team"]))}_{start+j}',use_container_width=True):
                    st.session_state['v12_team_pick']=str(item['Team'])
                    st.session_state['courtside_page']='Teams'
                    st.rerun()
    if max_page>1:st.caption(f'Page {page} of {max_page} · Showing {start+1}–{min(total,start+per_page)}')
    with st.expander('Advanced rankings and downloads',expanded=False):
        cols=[c for c in ['Rank','Team','Conference','Current power','Games played','Preseason rating','Experimental power','Roster adjustment'] if c in data]
        st.dataframe(data[cols],hide_index=True,use_container_width=True,height=400)
        st.download_button('Download filtered rankings CSV',data[cols].to_csv(index=False).encode('utf-8'),f'{league.lower().replace(" ", "_")}_courtside_rankings.csv','text/csv')
        st.caption('Experimental player effects are preliminary and unvalidated; default ordering uses baseline power ratings.')
