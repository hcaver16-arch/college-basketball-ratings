"""V140: interactive bracket presentation. All matchups provisional; no result forecasts."""
from __future__ import annotations
import json
from math import erf, sqrt
import streamlit as st
from tournament_resume_v139 import opening_round_slots
from tournament_brackets import _seeding_order


REGIONS = ("East", "West", "South", "Midwest")


def win_probability(power_a, power_b):
    """Neutral-court normal margin assumption, uncalibrated and illustrative."""
    return 0.5 * (1 + erf((float(power_a)-float(power_b))/(11.0*sqrt(2))))


def bracket_payload(field):
    if len(field)!=76 or field["Team ID"].nunique()!=76:
        raise ValueError("Complete unique 76-team projection required")
    pairings, slots = opening_round_slots(field)
    if len(pairings)!=12 or len(slots)!=64:
        raise ValueError("Opening Round must yield 12 games and 64 slots")
    teams = {str(r["Team"]): {
        "name": str(r["Team"]), "conference": str(r["Conference"]),
        "power": round(float(r["Current power"]),2),
        "sor": round(float(r["SOR score"]),3) if not __import__("pandas").isna(r["SOR score"]) else None,
        "games": int(r["SOR games"]) if not __import__("pandas").isna(r["SOR games"]) else None,
        "selection": round(float(r["Selection score"]),3),
        "bid": str(r["Bid type"]), "overall": int(r["Overall seed list"]),
        "basis": str(r["Selection basis"])}
        for _,r in field.iterrows()}
    open_round=[]
    for i,(left,right) in enumerate(pairings,1):
        probability=win_probability(teams[left]["power"],teams[right]["power"])
        open_round.append({"game":i,"a":left,"b":right,"p":round(probability,3)})
    entrants=slots["Team"].astype(str).tolist()
    # Snake seed list over four regions to distribute strong and weak entrants.
    region_teams={name:[] for name in REGIONS}
    for i,team in enumerate(entrants):
        region=REGIONS[i%4] if (i//4)%2==0 else REGIONS[3-(i%4)]
        region_teams[region].append(team)
    # Ensure each region has exactly 16 (round-robin snake by groups of 4).
    if any(len(x)!=16 for x in region_teams.values()):
        raise ValueError("Invalid region sizes")
    regions=[]
    for name in REGIONS:
        ordered=region_teams[name]
        seeded=[ordered[i-1] for i in _seeding_order(16)]
        pairs=[]
        for index in range(0,16,2):
            a,b=seeded[index:index+2]
            if a in teams and b in teams:
                p=round(win_probability(teams[a]["power"],teams[b]["power"]),3)
            else:
                p=None
            pairs.append({"a":a,"b":b,"p":p})
        regions.append({"name":name,"games":pairs})
    return {"regions":regions,"opening":open_round,"teams":teams}


def render_interactive_bracket(field):
    try:
        payload=bracket_payload(field)
    except (ValueError,TypeError,KeyError) as e:
        st.warning(f"Bracket unavailable: {e}")
        return
    st.subheader("National bracket · Interactive preview")
    st.caption("Hypothetical regions and matchups — not NCAA placement. Percentages are uncalibrated neutral-court first-round estimates from Courtside power ratings (11-point margin SD), not tournament advancement probabilities. Click a team for its résumé.")
    # Escape script end-tags; the JSON includes user-facing team names, never executable HTML.
    data=json.dumps(payload,ensure_ascii=True).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    markup=r"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#1e2d40;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.layout{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}.regions{min-width:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.regional{background:#fff;border:1px solid #e1e7f0;border-radius:13px;margin-bottom:0;padding:12px;overflow-x:auto}
.region-title{font-size:16px;font-weight:800;margin:0 0 12px}.rounds{display:flex;gap:18px;min-width:680px;align-items:stretch}
.round{flex:1;min-width:150px;display:flex;flex-direction:column;justify-content:space-around;gap:8px}
.round-title{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#718096;font-weight:800;margin-bottom:6px}
.match{border:1px solid #dce4ec;border-radius:8px;background:#fff;position:relative;min-height:69px;overflow:visible}
.match:after{content:"";position:absolute;top:50%;left:100%;width:18px;border-top:1px solid #8b9bad}
.round:last-child .match:after{display:none}
.team{display:flex;align-items:center;gap:5px;padding:9px 8px;border:0;background:transparent;color:#26364b;font:inherit;width:100%;text-align:left;cursor:pointer}
.team+.team{border-top:1px solid #e7edf3}.team:hover{background:#e9f3ff}.seed{font-size:10px;color:#75849b}
.name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pct{font-size:11px;font-weight:800;color:#1c62ac;background:#e4f0ff;border-radius:3px;padding:2px}
.pending{color:#98a4b5;cursor:default}.detail{background:#fff;border:1px solid #e1e7f0;border-radius:12px;padding:14px;align-self:start;position:static;border-left:4px solid #2364a4}
.detail h3{margin:0 0 14px;font-size:18px}.detail p{margin:9px 0;color:#52657d}.detail strong{color:#1e2d40}.summary{text-align:center;padding:20px;border:1px solid #dce4ed;border-radius:12px;background:#fff;margin:12px 0}
.opening{background:#fff;border:1px solid #e1e7f0;border-radius:12px;padding:12px;margin-top:12px}
.open-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:8px}
.open-game{border:1px solid #dce4ed;border-radius:8px;overflow:hidden}.opening h3{margin:0 0 10px}
@media(max-width:1250px){.regions{grid-template-columns:1fr}}@media(max-width:780px){.layout{display:block}.rounds{min-width:680px}}
</style></head><body>
<div class="layout">
<aside class="detail" id="detail"><h3>Team details</h3><p>Click any team name in a region or Opening Round to view its power rating, strength of record, and projected seed order here.</p></aside>
<div class="regions" id="regions"></div>
<div class="summary"><strong>Final Four → National Championship</strong><p>Projected regional champions and championship paths are not selected until a simulation model is added.</p></div>
<div class="opening"><h3>Opening Round · 12 projected games</h3><div class="open-grid" id="opening"></div></div>
</div>
<script>const data=__DATA__;
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const showTeam=name=>{const t=data.teams[name];if(!t)return;document.getElementById('detail').innerHTML='<h3>'+escapeHTML(t.name)+'</h3><p><strong>Conference:</strong> '+escapeHTML(t.conference)+'</p><p><strong>Overall projected order:</strong> #'+t.overall+'</p><p><strong>Power rating:</strong> '+t.power+'</p><p><strong>Strength of record:</strong> '+(t.sor===null?'Not eligible yet':t.sor+' ('+t.games+' D1 games)')+'</p><p><strong>Selection score:</strong> '+t.selection+'</p><p><strong>Bid:</strong> '+escapeHTML(t.bid)+'</p><p>'+escapeHTML(t.basis)+'</p>';document.getElementById('detail').scrollIntoView({behavior:'smooth',block:'start'});};
function button(name,p){const t=data.teams[name];const el=document.createElement('button');el.className='team'+(t?'':' pending');el.disabled=!t;const a=document.createElement('span');a.className='name';a.textContent=name;el.appendChild(a);if(p!==null){let n=document.createElement('span');n.className='pct';n.textContent=Math.round(p*100)+'%';el.appendChild(n)}if(t)el.onclick=()=>showTeam(name);return el}
function match(a,b,p){const el=document.createElement('div');el.className='match';el.appendChild(button(a,p));el.appendChild(button(b,p===null?null:1-p));return el}
function region(r){const wrap=document.createElement('section');wrap.className='regional';const title=document.createElement('h2');title.className='region-title';title.textContent=r.name+' · Projected region';wrap.appendChild(title);const rounds=document.createElement('div');rounds.className='rounds';let games=r.games;const names=['Round of 64','Round of 32','Sweet 16','Elite Eight'];for(let round=0;round<4;round++){const col=document.createElement('div');col.className='round';const label=document.createElement('div');label.className='round-title';label.textContent=names[round];col.appendChild(label);games.forEach(g=>col.appendChild(match(g.a,g.b,g.p)));rounds.appendChild(col);games=Array.from({length:games.length/2},(_,i)=>({a:'Winner R'+(round+1)+' G'+(2*i+1),b:'Winner R'+(round+1)+' G'+(2*i+2),p:null}));}wrap.appendChild(rounds);return wrap}
data.regions.forEach(r=>document.getElementById('regions').appendChild(region(r)));
data.opening.forEach(g=>{let el=document.createElement('div');el.className='open-game';el.appendChild(match(g.a,g.b,g.p));document.getElementById('opening').appendChild(el)});
</script></body></html>"""
    import streamlit.components.v1 as components
    components.html(markup.replace("__DATA__", data),height=2700,scrolling=True)
