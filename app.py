import streamlit as st
import asyncio
import pandas as pd
from typing import List
import os
from dotenv import load_dotenv
from multi_agent_system import MultiAgentSystem, SearchResult

# Load environment variables
load_dotenv()

# Configure page settings
st.set_page_config(
    page_title="Research Assistant",
    page_icon="🔍",
    layout="wide"
)

def init_session_state():
    """Initialize session state variables"""
    if 'search_history' not in st.session_state:
        st.session_state.search_history = []
    if 'current_results' not in st.session_state:
        st.session_state.current_results = None

def render_search_results(results: List[SearchResult]):
    """Render search results in a clean format"""
    if not results:
        st.warning("No results found")
        return

    for result in results:
        with st.expander(f"📄 {result.title}"):
            if result.authors:
                st.write("**Authors:** " + ", ".join(result.authors))
            if result.published:
                st.write(f"**Published:** {result.published}")
            if result.abstract:
                st.write("**Abstract:**", result.abstract)
            if result.arxiv_url:
                st.write(f"[View on arXiv]({result.arxiv_url})")
            if result.pdf_url:
                st.write(f"[Download PDF]({result.pdf_url})")
            
            # Add ClinicalTrials.gov link
            clinical_trials_url = f"https://clinicaltrials.gov/search?term={'+'.join(result.title.split())}"
            st.write(f"[Search on ClinicalTrials.gov]({clinical_trials_url})")

async def run_async_operations(system, search_query, max_results=3):
    """Handle all async operations"""
    if st.session_state.get('search_type') == "Literature Review":
        # Run literature review
        review = await system.run_literature_review(search_query)
        return {"type": "review", "data": review}
    else:
        # For quick search, wrap the synchronous function in an async context
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: system.search_tool.arxiv_search(search_query, max_results=max_results)
        )
        return {"type": "search", "data": results}

def main():
    """Main application function"""
    st.title("📚 Research Assistant")
    
    init_session_state()

    # Sidebar configuration
    with st.sidebar:
        st.header("Search Settings")
        st.session_state.search_type = st.selectbox(
            "Select Search Type",
            ["Literature Review", "Quick Search"]
        )
        
        max_results = st.slider(
            "Maximum Results",
            min_value=1,
            max_value=10,
            value=3
        )

        # API Status
        st.header("API Status")
        if os.getenv('GOOGLE_API_KEY') and os.getenv('GOOGLE_SEARCH_ENGINE_ID'):
            st.success("APIs configured")
        else:
            st.error("APIs not configured. Please check .env file")

    # Main search interface
    search_col1, search_col2 = st.columns([3, 1])
    
    with search_col1:
        search_query = st.text_input(
            "Enter your research topic",
            placeholder="e.g., 'recent advances in deep learning'"
        )
    
    with search_col2:
        search_button = st.button("Search", type="primary", use_container_width=True)

    # Handle search
    if search_button and search_query:
        with st.spinner("Searching and analyzing..."):
            try:
                system = MultiAgentSystem()
                
                # Use asyncio to properly handle coroutines
                result = asyncio.run(run_async_operations(
                    system, 
                    search_query,
                    max_results
                ))
                
                if result["type"] == "review":
                    st.markdown(result["data"])
                    # Add to search history
                    st.session_state.search_history.append({
                        "query": search_query,
                        "type": "Literature Review",
                        "timestamp": pd.Timestamp.now()
                    })
                else:  # Quick Search results
                    render_search_results(result["data"])
                    st.session_state.current_results = result["data"]
                    # Add to search history
                    st.session_state.search_history.append({
                        "query": search_query,
                        "type": "Quick Search",
                        "timestamp": pd.Timestamp.now()
                    })
                    
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.error(f"Error details: {type(e).__name__}")

    # Show search history
    if st.session_state.search_history:
        st.header("Search History")
        history_df = pd.DataFrame(st.session_state.search_history)
        st.dataframe(
            history_df,
            hide_index=True,
            column_config={
                "timestamp": st.column_config.DatetimeColumn(
                    "Time",
                    format="D MMM, YYYY, HH:mm"
                )
            }
        )

if __name__ == "__main__":
    main()