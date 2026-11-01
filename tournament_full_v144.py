"""V144 full-bracket overview using read-only HTML, with native detail controls elsewhere."""
from __future__ import annotations
import html
import streamlit as st
from tournament_region_labels_v147 import seeded_label, region_site, game_site_label

def _region_markup(region, teams, league, mirrored=False):
    """Fixed-coordinate regional tree: SVG connects actual card center points."""
    games=region["games"]
    site, _ = region_site(region["name"], league)
    card_w, card_h, step, col_gap = 144, 84, 116, 30
    centers=[[step * (2**level * (i+0.5) - 0.5) + card_h/2
              for i in range(8//(2**level))] for level in range(4)]
    height=8*step
    width=4*card_w+3*col_gap
    def xpos(level):
        col=3-level if mirrored else level
        return col*(card_w+col_gap)
    segments=[]
    for level in range(3):
        for j in range(len(centers[level+1])):
            y1=centers[level][2*j]
            y2=centers[level][2*j+1]
            ymid=centers[level+1][j]
            if mirrored:
                x0=xpos(level)
                x1=xpos(level+1)+card_w
                elbow=(x0+x1)/2
                points=[(x0,y1),(elbow,y1),(elbow,y2),(x0,y2)]
                middle=[(elbow,ymid),(x1,ymid)]
            else:
                x0=xpos(level)+card_w
                x1=xpos(level+1)
                elbow=(x0+x1)/2
                points=[(x0,y1),(elbow,y1),(elbow,y2),(x0,y2)]
                middle=[(elbow,ymid),(x1,ymid)]
            for a,b in zip(points,points[1:]):
                segments.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}"/>')
            segments.append(f'<line x1="{middle[0][0]}" y1="{middle[0][1]}" x2="{middle[1][0]}" y2="{middle[1][1]}"/>')
    out=['<section class="rgn"><h4>'+html.escape(region["name"]+' · '+site)+'</h4>',
         f'<div class="tree-fixed" style="width:{width}px;height:{height}px">',
         f'<svg class="bracket-wires" viewBox="0 0 {width} {height}" aria-hidden="true">', *segments, '</svg>']
    for level in range(4):
        for i,y in enumerate(centers[level]):
            if level==0:
                g=games[i]
                a=html.escape(seeded_label(g["a"],i,0,teams))
                b=html.escape(seeded_label(g["b"],i,1,teams))
                p=g["p"]
                lines=[a+(" · "+str(round(p*100))+"%" if p is not None else ""),
                       b+(" · "+str(round((1-p)*100))+"%" if p is not None else "")]
            else:
                lines=["Winner TBD",""]
            location=html.escape(game_site_label(level,region["name"],league))
            out.append(f'<div class="node level{level}" style="left:{xpos(level)}px;top:{y-card_h/2}px;width:{card_w}px;min-height:{card_h}px"><div>'+lines[0]+'</div><div>'+lines[1]+'</div><small class="venue">'+location+'</small></div>')
    out.append('</div></section>')
    return ''.join(out)

def render_full_overview(data, league="Men's"):
    st.markdown("### Full national bracket · Overview")
    st.caption("Scroll horizontally on smaller screens. Region placements are hypothetical; round winners are undecided. Select a region below to inspect teams and open résumé details.")
    left=data["regions"][:2]
    right=data["regions"][2:]
    markup="""<style>
.cs144-view{overflow-x:auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;padding:12px}
.cs144-grid{min-width:1660px;display:grid;grid-template-columns:minmax(0,1fr) 180px minmax(0,1fr);gap:12px;align-items:center}
.cs144-side{display:flex;flex-direction:column;gap:28px}
.cs144-view .rgn{border:1px solid #e8edf3;border-radius:10px;padding:8px;background:#fbfcfd}
.cs144-view h4{color:#23354b;margin:0 0 6px;font-size:13px}
.cs144-view .tree-fixed{position:relative;flex:none}
.cs144-view .bracket-wires{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;stroke:#849ab4;stroke-width:2;fill:none;stroke-linecap:round}
.cs144-view .node{position:absolute;box-sizing:border-box;background:#fff;border:1px solid #cbd8e6;border-radius:6px;z-index:1;overflow:hidden}
.cs144-view .node>div{padding:3px 5px;color:#22364c;font-size:10px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}
.cs144-view .node>div+div{border-top:1px solid #e7edf3}
.cs144-view .node .venue{display:block;color:#667b92;font-size:10px;line-height:1.3;font-weight:600;padding:5px 4px;border-top:1px solid #edf1f5;white-space:normal;overflow-wrap:anywhere}
.cs144-view .center{text-align:center;border:1px solid #ccdbea;border-radius:12px;background:#f1f6fc;padding:20px 10px;color:#1e3550}
.cs144-view .center strong{display:block;font-size:15px}.cs144-view .center small{display:block;margin-top:12px;color:#667b92}
</style><div class="cs144-view"><div class="cs144-grid"><div class="cs144-side">"""
    markup+=''.join(_region_markup(r, data['teams'], league) for r in left)
    markup+='</div><div class="center"><strong>FINAL FOUR</strong><small>Semifinalists TBD</small><strong style="margin-top:20px">NATIONAL CHAMPIONSHIP</strong><small>Champion TBD</small></div><div class="cs144-side">'
    markup+=''.join(_region_markup(r, data['teams'], league, True) for r in right)
    markup+='</div></div></div>'
    st.markdown(markup,unsafe_allow_html=True)
