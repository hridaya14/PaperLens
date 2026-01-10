import streamlit as st
from config import APP_TITLE

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
)

# -------------------------
# Header
# -------------------------
st.title(APP_TITLE)
st.caption(
    "A personal research workspace for ingesting, exploring, and reasoning over academic papers")

st.markdown("---")

# -------------------------
# Project description
# -------------------------
st.markdown(
    """
### 📚 What is PaperLens?

**PaperLens** is a research-focused workspace designed to help you **organize, explore, and reason over academic papers** efficiently.

Instead of juggling PDFs, notes, and external tools, PaperLens brings everything together into a single system:
- paper ingestion & indexing
- structured reading and exploration
- retrieval-augmented reasoning over your personal research corpus

This interface is a **prototype UI** built with Streamlit to validate workflows and user experience before transitioning to a full-fledged frontend.
"""
)

# -------------------------
# Core capabilities
# -------------------------
st.markdown("### 🚀 Core Capabilities")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
**📄 Research Paper Repository**
- Browse and read ingested papers
- Search papers by title
- Filter by research category
- Bookmark important papers
- Highlight text and attach notes *(local for now)*

**🧠 Structured Knowledge Access**
- Papers are indexed and retrievable
- Metadata-driven organization
- Designed for scale as your corpus grows
"""
    )

with col2:
    st.markdown(
        """
**💬 Retrieval-Augmented Chat** *(coming next)*
- Ask questions over individual papers
- Chat across your entire paper collection
- Grounded answers with source attribution

**📊 Automated Research Digest** *(coming soon)*
- Daily or periodic summaries of newly ingested papers
- Topic-wise research updates
- Designed to integrate with scheduled pipelines
"""
    )

# -------------------------
# Architecture note
# -------------------------
st.markdown("---")

st.markdown(
    """
### 🏗️ System Architecture (High-Level)

PaperLens is built as a **modular system**:

- **FastAPI** – backend APIs, RAG orchestration, data access  
- **PostgreSQL** – metadata & structured storage  
- **OpenSearch** – semantic search & retrieval  
- **Airflow** – scheduled ingestion and digest generation  
- **Streamlit (this UI)** – rapid prototyping layer  

The frontend is intentionally kept thin and stateless, acting purely as an interface over backend capabilities.
"""
)

# -------------------------
# Navigation hint
# -------------------------
st.markdown("---")

st.info(
    "👉 Use the **sidebar navigation** to explore available sections.\n\n"
    "Start with **📄 Papers** to browse and read your ingested research papers."
)

# -------------------------
# Sidebar branding
# -------------------------
st.sidebar.markdown("---")
st.sidebar.caption("PaperLens • Research Workspace (Prototype UI)")
