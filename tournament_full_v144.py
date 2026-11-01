"""V144 full-bracket overview using read-only HTML, with native detail controls elsewhere."""
from __future__ import annotations
import html
import streamlit as st

def _region_markup(region, mirrored=False):
    games=region["games"]
    out=['<section class="rgn"><h4>'+html.escape(region["name"])+'</h4><div class="tree'+(' mirror' if mirrored else '')+'">']
    for round_index in range(4):
        count=8//(2**round_index)
        cells=['<div class="round"><div class="rlabel">'+["R64","R32","Sweet 16","Elite Eight"][round_index]+'</div>']
        for i in range(count):
            if round_index==0:
                g=games[i]
                a,b=html.escape(g["a"]),html.escape(g["b"])
                p=g["p"]
                lines=[a+(" · "+str(round(p*100))+"%" if p is not None else ""),b+(" · "+str(round((1-p)*100))+"%" if p is not None else "")]
            else:
                lines=["Winner TBD",""]
            cells.append('<div class="node level'+str(round_index)+'"><div>'+lines[0]+'</div><div>'+lines[1]+'</div></div>')
        cells.append('</div>')
        out.extend(cells)
    out.append('</div></section>')
    return ''.join(out)

def render_full_overview(data):
    st.markdown("### Full national bracket · Overview")
    st.caption("Scroll horizontally on smaller screens. Region placements are hypothetical; round winners are undecided. Select a region below to inspect teams and open résumé details.")
    left=data["regions"][:2]
    right=data["regions"][2:]
    markup="""<style>
.cs144-view{overflow-x:auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;padding:12px}
.cs144-grid{min-width:1180px;display:grid;grid-template-columns:minmax(0,1fr) 180px minmax(0,1fr);gap:12px;align-items:center}
.cs144-side{display:flex;flex-direction:column;gap:28px}
.cs144-view .rgn{border:1px solid #e8edf3;border-radius:10px;padding:8px;background:#fbfcfd}
.cs144-view h4{color:#23354b;margin:0 0 6px;font-size:13px}
.cs144-view .tree{display:flex;gap:9px;min-width:0}
.cs144-view .tree.mirror{flex-direction:row-reverse}
.cs144-view .round{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:space-around;gap:4px}
.cs144-view .rlabel{font-size:10px;color:#72829a;text-align:center;font-weight:700}
.cs144-view .node{min-height:48px;background:#fff;border:1px solid #cbd8e6;border-radius:5px;position:relative;overflow:visible}
.cs144-view .node>div{padding:4px 5px;color:#22364c;font-size:10px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}
.cs144-view .node>div+div{border-top:1px solid #e7edf3}
.cs144-view .node:after{content:"";position:absolute;width:9px;border-top:1px solid #91a4bc;left:100%;top:50%}
.cs144-view .mirror .node:after{left:auto;right:100%}
.cs144-view .round:last-child .node:after{display:none}
.cs144-view .center{text-align:center;border:1px solid #ccdbea;border-radius:12px;background:#f1f6fc;padding:20px 10px;color:#1e3550}
.cs144-view .center strong{display:block;font-size:15px}.cs144-view .center small{display:block;margin-top:12px;color:#667b92}
</style><div class="cs144-view"><div class="cs144-grid"><div class="cs144-side">"""
    markup+=''.join(_region_markup(r) for r in left)
    markup+='</div><div class="center"><strong>FINAL FOUR</strong><small>Semifinalists TBD</small><strong style="margin-top:20px">NATIONAL CHAMPIONSHIP</strong><small>Champion TBD</small></div><div class="cs144-side">'
    markup+=''.join(_region_markup(r,True) for r in right)
    markup+='</div></div></div>'
    st.markdown(markup,unsafe_allow_html=True)
