import streamlit as st
from api import search_papers


# ======================
# Page setup & state
# ======================
st.title("📄 Research Papers")

st.session_state.setdefault("papers", [])
st.session_state.setdefault("active_pdf", None)
st.session_state.setdefault("active_pdf_title", None)
st.session_state.setdefault("bookmarks", set())


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

            action_cols = st.columns([1, 2])

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
