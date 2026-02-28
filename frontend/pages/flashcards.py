import os
from datetime import datetime

import requests
import streamlit as st

from config import CATEGORIES

# Resolve API base URL from secrets, env, or default.
_api_base = os.getenv("API_BASE_URL")
if not _api_base:
    try:
        _api_base = st.secrets["API_BASE_URL"]
    except Exception:
        _api_base = "http://localhost:8000/api/v1"
API_BASE_URL = _api_base


def fetch_flashcards(category: str, refresh: bool = False, limit: int = 5, timeout: int = 60):
    params = {"category": category, "limit": limit, "refresh": refresh}
    resp = requests.get(f"{API_BASE_URL}/flashcards/", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


st.title("🃏 Research Flashcards")
st.caption("Quick highlights of the latest papers per category.")

category = st.selectbox("Category", options=CATEGORIES, index=0)
refresh = st.checkbox("Force refresh (may be slower)", value=False)
limit = st.slider("Cards per category", 1, 10, 5)

if st.button("Load flashcards", type="primary"):
    with st.spinner("Fetching flashcards..."):
        try:
            data = fetch_flashcards(category=category, refresh=refresh, limit=limit)
            cards = data.get("cards", [])
            stale = data.get("stale", False)
            regenerated = data.get("regenerated", False)

            info = []
            if stale:
                info.append("stale")
            if regenerated:
                info.append("regenerated")
            if info:
                st.info(", ".join(info).capitalize())

            if not cards:
                st.warning("No flashcards available.")
            else:
                st.markdown(
                    """
                    <style>
                    .flashcard {
                        border: 1px solid #e0e0e0;
                        border-radius: 10px;
                        padding: 14px;
                        margin-bottom: 16px;
                        background: #fafafa;
                        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                cols = st.columns(2)
                for i, card in enumerate(cards):
                    col = cols[i % 2]
                    headline = card.get("headline") or "Untitled"
                    insight = (card.get("insight") or "").split("\n")[0].strip()
                    why = card.get("why_it_matters")

                    with col.container():
                        st.markdown(f"<div class='flashcard'>", unsafe_allow_html=True)
                        st.markdown(f"**{headline}**")
                        if insight:
                            st.markdown(insight)
                        if why:
                            st.caption(f"Why it matters: {why}")
                        if card.get("source_url"):
                            st.markdown(f"[Source]({card['source_url']})")
                        ts = card.get("generated_at")
                        if ts:
                            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            st.caption(f"Generated: {ts_dt:%Y-%m-%d %H:%M UTC}")
                        st.markdown("</div>", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Failed to load flashcards: {e}")
