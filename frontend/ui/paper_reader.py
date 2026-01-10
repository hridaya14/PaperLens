import streamlit as st


def render_paper_reader(paper: dict):
    st.subheader(paper["title"])

    if paper.get("authors"):
        st.caption(", ".join(paper["authors"]))

    if paper.get("categories"):
        st.markdown(
            "**Categories:** " + ", ".join(paper["categories"])
        )

    st.divider()

    if paper.get("abstract"):
        with st.expander("Abstract", expanded=True):
            st.write(paper["abstract"])

    st.divider()
    st.markdown("### Content")

    if paper.get("sections"):
        for section in paper["sections"]:
            st.markdown(f"#### {section.get('title', 'Section')}")
            st.write(section.get("content", ""))
    elif paper.get("raw_text"):
        st.text(paper["raw_text"])
    else:
        st.info("No parsed content available for this paper yet.")
