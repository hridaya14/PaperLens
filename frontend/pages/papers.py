import streamlit as st
from api import search_papers, get_mindmap


# ======================
# Page setup & state
# ======================
st.title("📄 Research Papers")

st.session_state.setdefault("papers", [])
st.session_state.setdefault("active_pdf", None)
st.session_state.setdefault("active_pdf_title", None)
st.session_state.setdefault("bookmarks", set())
st.session_state.setdefault("active_mindmap", None)
st.session_state.setdefault("active_mindmap_title", None)


# ======================
# Card styling
# ======================
st.markdown(
    """
<style>
.paper-card {
    padding: 1rem;
    border-radius: 12px;
    border: 1px solid #e6e6e6;
    margin-bottom: 1.25rem;
    height: 220px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.paper-title {
    font-size: 1.05rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
}

.paper-authors {
    font-size: 0.85rem;
    color: #555;
    margin-bottom: 0.25rem;
}

.paper-meta {
    font-size: 0.8rem;
    color: #777;
}

.paper-tags {
    font-size: 0.75rem;
    color: #666;
    margin-top: 0.3rem;
}
</style>
""",
    unsafe_allow_html=True,
)


# ======================
# Mind map renderer
# ======================
def render_mindmap(mindmap: dict):
    """Renders the mind map as an interactive D3 collapsible tree."""
    import json as _json

    node_colors = {
        "root":         "#7c3aed",
        "problem":      "#dc2626",
        "approach":     "#2563eb",
        "concept":      "#0891b2",
        "finding":      "#16a34a",
        "contribution": "#d97706",
        "limitation":   "#9f1239",
    }

    colors_json = _json.dumps(node_colors)
    tree_json   = _json.dumps(mindmap["root"])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8"/>
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background: #0e1117; font-family: 'Segoe UI', sans-serif; overflow: hidden; }}

        #controls {{
          position: absolute; top: 12px; right: 16px; z-index: 10;
          display: flex; gap: 8px;
        }}
        #controls button {{
          background: #1e2130; color: #ccc; border: 1px solid #333;
          border-radius: 6px; padding: 6px 12px; cursor: pointer;
          font-size: 13px; transition: background 0.2s;
        }}
        #controls button:hover {{ background: #2d3148; color: #fff; }}

        svg {{ width: 100%; height: 780px; }}

        .node circle {{
          stroke-width: 2.5px;
          cursor: pointer;
          transition: r 0.2s;
        }}
        .node circle:hover {{ r: 10; }}

        .node text {{
          font-size: 13px;
          fill: #e2e8f0;
          cursor: pointer;
          font-weight: 500;
        }}
        .node .label-root text  {{ font-size: 16px; font-weight: 700; fill: #fff; }}
        .node .label-primary text {{ font-size: 14px; font-weight: 600; }}

        .tooltip {{
          position: absolute;
          background: #1e2130;
          border: 1px solid #3d4166;
          border-radius: 10px;
          padding: 12px 16px;
          max-width: 300px;
          pointer-events: none;
          opacity: 0;
          transition: opacity 0.2s;
          z-index: 20;
        }}
        .tooltip .tt-label {{
          font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 6px;
        }}
        .tooltip .tt-desc {{
          font-size: 12px; color: #94a3b8; line-height: 1.5;
        }}
        .tooltip .tt-type {{
          display: inline-block;
          font-size: 11px; padding: 2px 8px;
          border-radius: 99px; margin-bottom: 8px;
          font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
        }}

        .link {{
          fill: none;
          stroke: #334155;
          stroke-width: 1.5px;
        }}
      </style>
    </head>
    <body>
      <div id="controls">
        <button onclick="resetZoom()">⟳ Reset</button>
        <button onclick="expandAll()">+ Expand All</button>
        <button onclick="collapseAll()">− Collapse All</button>
      </div>
      <div class="tooltip" id="tooltip">
        <div class="tt-type" id="tt-type"></div>
        <div class="tt-label" id="tt-label"></div>
        <div class="tt-desc"  id="tt-desc"></div>
      </div>
      <svg id="tree"></svg>

      <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
      <script>
      const RAW   = {tree_json};
      const COLORS = {colors_json};

      const W = document.getElementById('tree').clientWidth || 1100;
      const H = 780;
      const MARGIN = {{ top: 40, right: 220, bottom: 40, left: 80 }};

      const svg = d3.select('#tree')
        .attr('viewBox', `0 0 ${{W}} ${{H}}`)
        .attr('preserveAspectRatio', 'xMidYMid meet');

      const zoomG = svg.append('g');

      const zoom = d3.zoom()
        .scaleExtent([0.2, 3])
        .on('zoom', e => zoomG.attr('transform', e.transform));
      svg.call(zoom);

      const g = zoomG.append('g')
        .attr('transform', `translate(${{MARGIN.left}},${{MARGIN.top}})`);

      const tooltip  = document.getElementById('tooltip');
      const ttType   = document.getElementById('tt-type');
      const ttLabel  = document.getElementById('tt-label');
      const ttDesc   = document.getElementById('tt-desc');

      // Build D3 hierarchy
      let root = d3.hierarchy(RAW, d => d.children && d.children.length ? d.children : null);
      root.x0 = (H - MARGIN.top - MARGIN.bottom) / 2;
      root.y0 = 0;

      // Collapse nodes beyond depth 1 initially
      root.descendants().forEach(d => {{
        if (d.depth > 1) {{
          d._children = d.children;
          d.children = null;
        }}
      }});

      const treeLayout = d3.tree()
        .size([H - MARGIN.top - MARGIN.bottom, W - MARGIN.left - MARGIN.right]);

      let i = 0;

      function update(source) {{
        treeLayout(root);
        const nodes = root.descendants();
        const links  = root.links();

        // Normalize depth spacing
        nodes.forEach(d => {{ d.y = d.depth * 220; }});

        // --- Links ---
        const link = g.selectAll('.link').data(links, d => d.target.id);

        link.enter().append('path')
          .attr('class', 'link')
          .attr('d', () => {{
            const o = {{ x: source.x0, y: source.y0 }};
            return diagonal(o, o);
          }})
          .merge(link)
          .transition().duration(400)
          .attr('d', d => diagonal(d.source, d.target));

        link.exit().transition().duration(400)
          .attr('d', () => {{
            const o = {{ x: source.x, y: source.y }};
            return diagonal(o, o);
          }})
          .remove();

        // --- Nodes ---
        const node = g.selectAll('.node').data(nodes, d => d.id || (d.id = ++i));

        const nodeEnter = node.enter().append('g')
          .attr('class', 'node')
          .attr('transform', () => `translate(${{source.y0}},${{source.x0}})`)
          .on('click', (event, d) => {{ toggle(d); update(d); }})
          .on('mousemove', (event, d) => {{
            const color = COLORS[d.data.node_type] || '#7c3aed';
            ttType.textContent  = d.data.node_type;
            ttType.style.background = color + '33';
            ttType.style.color = color;
            ttLabel.textContent = d.data.label;
            ttDesc.textContent  = d.data.description || '';
            tooltip.style.opacity = 1;
            tooltip.style.left = (event.pageX + 14) + 'px';
            tooltip.style.top  = (event.pageY - 10) + 'px';
          }})
          .on('mouseleave', () => {{ tooltip.style.opacity = 0; }});

        nodeEnter.append('circle')
          .attr('r', d => d.data.node_type === 'root' ? 12 : d.data.importance === 'primary' ? 9 : 6)
          .attr('fill', d => COLORS[d.data.node_type] || '#7c3aed')
          .attr('stroke', d => COLORS[d.data.node_type] || '#7c3aed')
          .attr('stroke-opacity', 0.4)
          .attr('stroke-width', d => d.data.importance === 'primary' ? 6 : 3);

        nodeEnter.append('text')
          .attr('dy', '0.35em')
          .attr('x', d => (d.children || d._children) ? -16 : 16)
          .attr('text-anchor', d => (d.children || d._children) ? 'end' : 'start')
          .text(d => d.data.label)
          .style('font-size', d => d.data.node_type === 'root' ? '15px' : d.data.importance === 'primary' ? '13px' : '12px')
          .style('font-weight', d => d.data.importance === 'primary' ? '600' : '400')
          .style('fill', d => d.data.node_type === 'root' ? '#fff' : '#e2e8f0');

        // Collapse indicator
        nodeEnter.append('text')
          .attr('class', 'collapse-indicator')
          .attr('dy', '0.35em')
          .attr('x', d => (d.children || d._children) ? -16 : 16)
          .style('font-size', '10px')
          .style('fill', '#64748b');

        const nodeUpdate = nodeEnter.merge(node);

        nodeUpdate.transition().duration(400)
          .attr('transform', d => `translate(${{d.y}},${{d.x}})`);

        nodeUpdate.select('.collapse-indicator')
          .text(d => d._children ? ' [+]' : '');

        node.exit().transition().duration(400)
          .attr('transform', () => `translate(${{source.y}},${{source.x}})`)
          .remove();

        nodes.forEach(d => {{ d.x0 = d.x; d.y0 = d.y; }});
      }}

      function diagonal(s, t) {{
        return `M ${{s.y}} ${{s.x}}
                C ${{(s.y + t.y) / 2}} ${{s.x}},
                  ${{(s.y + t.y) / 2}} ${{t.x}},
                  ${{t.y}} ${{t.x}}`;
      }}

      function toggle(d) {{
        if (d.children) {{ d._children = d.children; d.children = null; }}
        else             {{ d.children = d._children; d._children = null; }}
      }}

      function expandAll() {{
        root.descendants().forEach(d => {{
          if (d._children) {{ d.children = d._children; d._children = null; }}
        }});
        update(root);
      }}

      function collapseAll() {{
        root.descendants().forEach(d => {{
          if (d.depth > 0 && d.children) {{ d._children = d.children; d.children = null; }}
        }});
        update(root);
      }}

      function resetZoom() {{
        svg.transition().duration(400).call(
          zoom.transform, d3.zoomIdentity.translate(MARGIN.left, MARGIN.top)
        );
      }}

      update(root);
      </script>
    </body>
    </html>
    """
    st.components.v1.html(html, height=800, scrolling=False)


# ======================
# PDF preview
# ======================
if st.session_state["active_pdf"]:
    with st.container(border=True):
        header_col, close_col = st.columns([8, 1])

        with header_col:
            st.subheader(st.session_state["active_pdf_title"])

        with close_col:
            if st.button("❌ Close", key="close_pdf"):
                st.session_state["active_pdf"] = None
                st.session_state["active_pdf_title"] = None
                st.rerun()

        st.components.v1.iframe(
            st.session_state["active_pdf"],
            height=900,
            scrolling=True,
        )

    st.markdown("---")


# ======================
# Mind map preview
# ======================
if st.session_state["active_mindmap"]:
    with st.container(border=True):
        header_col, close_col = st.columns([8, 1])

        with header_col:
            st.subheader(f"🧠 {st.session_state['active_mindmap_title']}")

        with close_col:
            if st.button("❌ Close", key="close_mindmap"):
                st.session_state["active_mindmap"] = None
                st.session_state["active_mindmap_title"] = None
                st.rerun()

        sections = st.session_state["active_mindmap"].get("sections_covered", [])
        if sections:
            st.caption(f"Sections covered: {' • '.join(sections)}")

        render_mindmap(st.session_state["active_mindmap"])

    st.markdown("---")


# ======================
# Sidebar search
# ======================
with st.sidebar.form("paper_search_form"):
    st.header("Search & Filters")

    query = st.text_input("Search by title")

    CODE_TO_NAME = {
        "cs.AI": "Artificial Intelligence",
        "cs.CV": "Computer Vision",
        "cs.CL": "Natural Language Processing",
        "cs.LG": "Machine Learning",
        "cs.RO": "Robotics",
        "cs.SY": "Systems",
    }

    categories = st.multiselect(
        "Categories",
        options=list(CODE_TO_NAME.keys()),
        format_func=lambda c: CODE_TO_NAME[c],
    )

    pdf_processed = st.selectbox(
        "PDF Status",
        options=[None, True, False],
        format_func=lambda x: "Any"
        if x is None
        else "Processed"
        if x
        else "Not Processed",
    )

    limit = st.selectbox("Results per page", [10, 20, 50], index=1)

    submitted = st.form_submit_button("🔍 Search")


# ======================
# Fetch papers
# ======================
if submitted:
    try:
        response = search_papers(
            query=query or None,
            categories=categories or None,
            pdf_processed=pdf_processed,
            limit=limit,
            offset=0,
        )
        st.session_state["papers"] = response.get("papers", [])
    except Exception as e:
        st.error(f"Failed to load papers: {e}")

papers = st.session_state["papers"]


# ======================
# Tabs
# ======================
tab_all, tab_bookmarked = st.tabs(["All Papers", "⭐ Bookmarked"])


def render_cards(paper_list, context: str):
    if not paper_list:
        st.info("No papers to show.")
        return

    cols = st.columns(2)

    for idx, paper in enumerate(paper_list):
        col = cols[idx % 2]
        paper_id = str(paper["id"])
        arxiv_id = paper.get("arxiv_id") or paper_id
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        is_bookmarked = paper_id in st.session_state["bookmarks"]

        with col:
            st.markdown(
                f"""
<div class="paper-card">
    <div>
        <div class="paper-title">{paper['title']}</div>
        <div class="paper-authors">
            {", ".join(paper.get("authors", []))
                    if paper.get("authors") else ""}
        </div>
        <div class="paper-meta">
            PDF parsed: {"Yes" if paper.get("pdf_processed") else "No"}
        </div>
        <div class="paper-tags">
            {" • ".join(paper.get("categories", []))}
        </div>
    </div>
</div>
""",
                unsafe_allow_html=True,
            )

            action_cols = st.columns([1, 1, 1])

            with action_cols[0]:
                if st.button(
                    "⭐" if is_bookmarked else "☆",
                    key=f"bm_{context}_{paper_id}",
                    use_container_width=True,
                ):
                    if is_bookmarked:
                        st.session_state["bookmarks"].remove(paper_id)
                    else:
                        st.session_state["bookmarks"].add(paper_id)
                    st.rerun()

            with action_cols[1]:
                if st.button(
                    "Open PDF",
                    key=f"open_{context}_{paper_id}",
                    use_container_width=True,
                ):
                    st.session_state["active_pdf"] = pdf_url
                    st.session_state["active_pdf_title"] = paper["title"]
                    st.rerun()

            with action_cols[2]:
                if st.button(
                    "🧠 Mind Map",
                    key=f"mm_{context}_{paper_id}",
                    use_container_width=True,
                ):
                    with st.spinner("Generating mind map..."):
                        try:
                            mindmap = get_mindmap(arxiv_id)
                            st.session_state["active_mindmap"] = mindmap
                            st.session_state["active_mindmap_title"] = paper["title"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to generate mind map: {e}")


# ======================
# Render tabs
# ======================
with tab_all:
    render_cards(papers, context="all")

with tab_bookmarked:
    bookmarked_papers = [
        p for p in papers if str(p["id"]) in st.session_state["bookmarks"]
    ]
    render_cards(bookmarked_papers, context="bookmarked")
