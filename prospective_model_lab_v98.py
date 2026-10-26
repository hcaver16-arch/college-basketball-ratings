"""V98 read-only Streamlit view for V97 immutable prospective forecast journal.
Does not recompute predictions or alter forecasts/results.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

SEASON = '2026-27'
ROOT = Path(__file__).resolve().parent


def _load():
    folder = ROOT / 'data' / 'prospective' / SEASON
    fpath, rpath, spath = folder / 'forecasts.csv', folder / 'results.csv', folder / 'summary.json'
    forecasts = pd.read_csv(fpath, dtype={'game_id': str, 'home_id': str, 'away_id': str}) if fpath.is_file() else pd.DataFrame()
    results = pd.read_csv(rpath, dtype={'game_id': str}) if rpath.is_file() else pd.DataFrame()
    import json
    summary = json.loads(spath.read_text()) if spath.is_file() else {}
    return forecasts, results, summary


def _valid_rows(forecasts, results):
    if forecasts.empty or results.empty:
        return pd.DataFrame(), 0
    required_f = {'division','game_id','model_id','forecast_created_utc','ratings_snapshot_utc','game_start_utc','predicted_home_margin'}
    required_r = {'division','game_id','actual_home_margin','status'}
    if not required_f.issubset(forecasts) or not required_r.issubset(results):
        raise ValueError('V97 journal columns do not match expected schema.')
    f = forecasts.copy()
    for c in ('forecast_created_utc','ratings_snapshot_utc','game_start_utc'):
        f[c] = pd.to_datetime(f[c], errors='coerce', utc=True)
    valid = f['ratings_snapshot_utc'].le(f['forecast_created_utc']) & f['forecast_created_utc'].lt(f['game_start_utc'])
    rejected = int((~valid).sum())
    f = f.loc[valid].copy()
    f = f.sort_values('forecast_created_utc').drop_duplicates(['division','game_id','model_id'], keep='first')
    r = results.loc[results['status'].astype(str).eq('Final')].copy()
    r = r.drop_duplicates(['division','game_id'],keep='first')
    out = f.merge(r[['division','game_id','actual_home_margin']],on=['division','game_id'],how='inner',validate='many_to_one')
    out['prediction'] = pd.to_numeric(out['predicted_home_margin'],errors='coerce')
    out['actual'] = pd.to_numeric(out['actual_home_margin'],errors='coerce')
    out = out.dropna(subset=['prediction','actual'])
    out['abs_error']=(out['prediction']-out['actual']).abs()
    out['bias']=out['actual']-out['prediction']
    out['winner_eligible']=(out['prediction']!=0) & (out['actual']!=0)
    out['winner_correct']=(out['prediction']>0)==(out['actual']>0)
    out['game_day'] = out['game_start_utc'].dt.date
    out['game_month'] = out['game_start_utc'].dt.strftime('%Y-%m')
    out['predicted_spread'] = out['prediction'].abs()
    out['spread_bucket'] = pd.cut(out['predicted_spread'],bins=[-0.001,3,7,12,20,float('inf')], labels=['0–3','3–7','7–12','12–20','20+'],right=False)
    return out, rejected


def _stats(df):
    if df.empty:return {'Games':0,'Margin MAE':None,'Winner accuracy':None,'Signed bias':None}
    eligible=df.loc[df['winner_eligible']]
    return {'Games':len(df),'Margin MAE':float(df['abs_error'].mean()),'Winner accuracy':float(eligible['winner_correct'].mean()) if len(eligible) else None,'Signed bias':float(df['bias'].mean())}


def _fmt(x,dec=2,suffix=''):
    return '—' if x is None or pd.isna(x) else f'{x:.{dec}f}{suffix}'


def render_prospective_model_lab(division=None):
    """Call inside the existing Model Lab section (existing UI unchanged)."""
    with st.container():
        st.markdown('### Prospective prediction tracking')
        st.caption('2026–27 · Saved before tipoff · Graded against final results · No reconstructed historical predictions')
        try: f,r,summary=_load()
        except Exception as exc:
            st.warning(f'Prospective archive could not be read: {exc}')
            return
        if not summary and f.empty and r.empty:
            st.info('No V97 archive yet. Run **Archive pregame forecasts and outcomes V97** in GitHub Actions to initialize tracking.')
            return
        asof=summary.get('as_of_utc')
        if asof:st.caption(f'Last tracker report: {asof}')
        c1,c2,c3=st.columns(3)
        c1.metric('Locked forecasts',len(f))
        c2.metric('Final games saved',len(r))
        try: rows,rejected=_valid_rows(f,r)
        except Exception as exc:
            st.error(f'Cannot grade V97 forecasts safely: {exc}')
            return
        c3.metric('Graded predictions',len(rows))
        if rejected:st.warning(f'{rejected} forecast row(s) excluded because they lacked valid pregame timestamps.')
        divs=['mens','womens']
        current=division if division in divs else 'mens'
        chosen=st.selectbox('Division',divs,index=divs.index(current),format_func=lambda d:"Men's" if d=='mens' else "Women's",key='v98_prospective_division')
        div_f=f.loc[f['division'].astype(str).eq(chosen)] if 'division' in f else pd.DataFrame()
        div_rows=rows.loc[rows['division'].eq(chosen)] if not rows.empty else pd.DataFrame()
        if div_f.empty:
            st.info('No locked pregame forecasts for this division yet. Tracking begins when eligible games appear.')
            _tracker_notes(summary,chosen)
            return
        models=sorted(div_f['model_id'].dropna().astype(str).unique().tolist())
        default='official_saved_v97' if 'official_saved_v97' in models else models[0]
        model=st.selectbox('Forecast model',models,index=models.index(default),key=f'v98_model_{chosen}')
        selected=div_rows.loc[div_rows['model_id'].eq(model)].copy() if not div_rows.empty else pd.DataFrame()
        if selected.empty:
            st.info('Forecasts are archived, but none are graded yet. Accuracy appears after these games finish and V97 collects their results.')
            _tracker_notes(summary,chosen)
            return
        selected['venue'] = selected['neutral'].astype(str).str.lower().map({'true':'Neutral','false':'Home/away'}).fillna('Unknown') if 'neutral' in selected else 'Unknown'
        a,b,c=st.columns(3)
        metrics=_stats(selected)
        a.metric('Graded games',metrics['Games'])
        b.metric('Margin MAE',_fmt(metrics['Margin MAE']))
        c.metric('Winner accuracy',_fmt(100*metrics['Winner accuracy'] if metrics['Winner accuracy'] is not None else None,1,'%'))
        st.caption(f"Signed error (actual − predicted): {_fmt(metrics['Signed bias'])} points. Winner accuracy excludes ties and predicted pushes.")
        tab1,tab2,tab3,tab4=st.tabs(['Monthly trend','By spread','By venue','Game history'])
        with tab1:
            monthly=selected.groupby('game_month',observed=True)['abs_error'].agg(['mean','count']).reset_index()
            st.line_chart(monthly.set_index('game_month')['mean'], y_label='Margin MAE', x_label='Month')
            st.dataframe(monthly.rename(columns={'game_month':'Month','mean':'Margin MAE','count':'Games'}).round(3),hide_index=True,use_container_width=True)
        with tab2:
            spread=selected.groupby('spread_bucket',observed=True).agg(games=('abs_error','size'),margin_mae=('abs_error','mean')).reset_index()
            st.dataframe(spread.rename(columns={'spread_bucket':'Predicted spread','games':'Games','margin_mae':'Margin MAE'}).round(3),hide_index=True,use_container_width=True)
        with tab3:
            venue=selected.groupby('venue').agg(games=('abs_error','size'),margin_mae=('abs_error','mean')).reset_index()
            st.dataframe(venue.rename(columns={'venue':'Venue','games':'Games','margin_mae':'Margin MAE'}).round(3),hide_index=True,use_container_width=True)
        with tab4:
            columns=['game_day','away_team','home_team','prediction','actual','abs_error','forecast_created_utc']
            existing=[x for x in columns if x in selected]
            st.dataframe(selected[existing].sort_values('game_day',ascending=False).rename(columns={'game_day':'Game date','away_team':'Away','home_team':'Home','prediction':'Predicted home margin','actual':'Actual home margin','abs_error':'Absolute error','forecast_created_utc':'Forecast saved UTC'}).round(2),hide_index=True,use_container_width=True)
            st.download_button('Download graded forecasts (CSV)',selected.to_csv(index=False).encode('utf-8'),file_name=f'courtside_{chosen}_{model}_graded_v98.csv',mime='text/csv',key=f'v98_download_{chosen}_{model}')
        _paired(rows,chosen,model)
        _tracker_notes(summary,chosen)


def _paired(rows,division,model):
    if rows.empty:return
    subset=rows.loc[rows['division'].eq(division)]
    others=[x for x in subset['model_id'].unique() if x!=model]
    if not others:return
    with st.expander('Compare models on identical completed games',expanded=False):
        other=st.selectbox('Compare against',sorted(others),key=f'v98_compare_{division}_{model}')
        left=subset.loc[subset['model_id'].eq(model),['game_id','abs_error']].rename(columns={'abs_error':'first_error'})
        right=subset.loc[subset['model_id'].eq(other),['game_id','abs_error']].rename(columns={'abs_error':'second_error'})
        both=left.merge(right,on='game_id',how='inner',validate='one_to_one')
        if both.empty:st.info('These models have no identical completed games to compare.');return
        st.write(f'**{len(both)} common games** · {model}: **{both.first_error.mean():.3f}** MAE · {other}: **{both.second_error.mean():.3f}** MAE')
        st.caption('Only games with valid pre-tip predictions from both models are included. Smaller MAE is better.')


def _tracker_notes(summary,division):
    today=summary.get('today',{}).get(division,{})
    if today:
        with st.expander('Archive health',expanded=False):
            st.write(f"Official ratings: {today.get('official_ratings','unknown')}")
            st.write(f"Experimental ratings: {today.get('experimental_ratings','not provided')}")
            st.caption(f"Games checked in latest run: {today.get('games_seen','—')} · Forecasts added: {today.get('forecasts_created','—')} · Results added: {today.get('results_added','—')}")
    st.caption('No win-probability calibration or Brier score is shown until genuine pregame probabilities are archived. Forecasts remain unchanged.')
