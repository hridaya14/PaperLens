import streamlit as st
from api import ask_question

st.title("💬 Research Assistant")
st.caption("Ask questions over your paper collection using Retrieval-Augmented Generation")

# ----------------------
# Session state
# ----------------------
st.session_state.setdefault("chat_history", [])

# ----------------------
# Sidebar – RAG controls
# ----------------------
with st.sidebar:
    st.header("RAG Settings")

    top_k = st.slider(
        "Top K Chunks",
        min_value=1,
        max_value=10,
        value=3,
        help="Number of retrieved chunks used for answering",
    )

    use_hybrid = st.checkbox(
        "Use hybrid search (BM25 + Vector)",
        value=True,
    )

    model = st.selectbox(
        "Model",
        options=[
            "meta/llama-3.3-70b-instruct",
        ],
    )

    categories = st.multiselect(
        "Filter by categories (optional)",
        [
            "cs.AI",
            "cs.CL",
            "cs.CV",
            "cs.LG",
            "cs.RO",
        ],
    )

# ----------------------
# Render chat history
# ----------------------
for msg in st.session_state["chat_history"]:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.write(msg["content"])

            st.caption(
                f"🔎 Search mode: {msg['search_mode']} | "
                f"📄 Chunks used: {msg['chunks_used']}"
            )

            if msg["sources"]:
                with st.expander("Sources"):
                    for src in msg["sources"]:
                        st.markdown(f"- [{src}]({src})")

# ----------------------
# Chat input
# ----------------------
query = st.chat_input("Ask a question about your papers...")

if query:
    # Add user message
    st.session_state["chat_history"].append(
        {"role": "user", "content": query}
    )

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                payload = {
                    "query": query,
                    "top_k": top_k,
                    "use_hybrid": use_hybrid,
                    "model": model,
                    "categories": categories or None,
                }

                response = ask_question(payload)

                answer = response["answer"]

                st.write(answer)

                st.caption(
                    f"🔎 Search mode: {response['search_mode']} | "
                    f"📄 Chunks used: {response['chunks_used']}"
                )

                if response["sources"]:
                    with st.expander("Sources"):
                        for src in response["sources"]:
                            st.markdown(f"- [{src}]({src})")

                # Save assistant message
                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": response["sources"],
                        "chunks_used": response["chunks_used"],
                        "search_mode": response["search_mode"],
                    }
                )

            except Exception as e:
                st.error(f"Failed to get answer: {e}")

