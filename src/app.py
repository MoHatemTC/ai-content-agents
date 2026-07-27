
from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
from src.ingestion.loader import ContentLoader
from src.registry import AgentRegistry
from src.generation import MockGenerator
from src.schemas import FlashcardSet, StudyPlan, RevisionSession
from src.services.mentor_concept import MentorConceptService

# Initialize services
@st.cache_resource
def get_loader():
    return ContentLoader()

@st.cache_resource
def get_registry():
    return AgentRegistry()

@st.cache_resource
def get_generator():
    return MockGenerator(get_registry())

@st.cache_resource
def get_mentor_concept_service():
    return MentorConceptService()

# Set page config
st.set_page_config(page_title="AI Study Assistant", page_icon="📚", layout="wide")

# Sidebar
st.sidebar.title("📚 AI Study Assistant")
page = st.sidebar.radio(
    "Choose a page",
    [
        "🏠 Home",
        "📤 Upload Content",
        "🃏 Generate Flashcards",
        "📅 Study Plan",
        "🔄 Revision Plan",
        "🧭 Mentor",
        "💡 Concept Explanation",
    ]
)

loader = get_loader()
registry = get_registry()
generator = get_generator()
mentor_concept_service = get_mentor_concept_service()

# Page: Home
if page == "🏠 Home":
    st.title("Welcome to AI Study Assistant!")
    st.markdown("""
    This app combines:
    - **Content Ingestion**: Upload and process study materials (TXT, PDF, DOCX, Markdown)
    - **Flashcard Generator**: Create flashcards from your materials
    - **Study Plan Generator**: Build structured study plans
    - **Revision Plan Generator**: Generate spaced repetition revision plans
    """)

# Page: Upload Content
elif page == "📤 Upload Content":
    st.title("Upload Content")
    
    tab1, tab2 = st.tabs(["📁 Upload File", "📝 Paste Text"])
    
    with tab1:
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["txt", "pdf", "docx", "md"]
        )
        
        if uploaded_file is not None:
            try:
                with st.spinner("Processing file..."):
                    file_content = uploaded_file.read()
                    doc = loader.load_file(file_content, uploaded_file.name)
                    chunks = loader.store.get_chunks_by_document_id(doc.id)
                    
                    st.success(f"Successfully uploaded {doc.title}!")
                    st.session_state.current_doc = doc
                    st.session_state.current_chunks = chunks
                    
                    st.write(f"Document ID: {doc.id}")
                    st.write(f"Number of chunks: {len(chunks)}")
                    
                    with st.expander("View Document Content"):
                        st.text(doc.content[:2000] + "..." if len(doc.content) > 2000 else doc.content)
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
    
    with tab2:
        title = st.text_input("Title (optional)", "Pasted Text")
        pasted_text = st.text_area("Paste your text here", height=200)
        
        if st.button("Process Text") and pasted_text:
            try:
                with st.spinner("Processing text..."):
                    doc = loader.load_text(pasted_text, title)
                    chunks = loader.store.get_chunks_by_document_id(doc.id)
                    
                    st.success(f"Successfully processed {doc.title}!")
                    st.session_state.current_doc = doc
                    st.session_state.current_chunks = chunks
                    
                    st.write(f"Document ID: {doc.id}")
                    st.write(f"Number of chunks: {len(chunks)}")
                    
                    with st.expander("View Document Content"):
                        st.text(doc.content[:2000] + "..." if len(doc.content) > 2000 else doc.content)
            except Exception as e:
                st.error(f"Error processing text: {str(e)}")

# Page: Generate Flashcards
elif page == "🃏 Generate Flashcards":
    st.title("Generate Flashcards")
    
    if "current_doc" not in st.session_state:
        st.warning("Please upload or paste content first!")
    else:
        doc = st.session_state.current_doc
        st.subheader(f"Using document: {doc.title}")
        
        with st.form("flashcard_form"):
            count = st.number_input("Number of flashcards", min_value=1, max_value=20, value=5)
            submitted = st.form_submit_button("Generate Flashcards")
            
            if submitted:
                with st.spinner("Generating flashcards..."):
                    try:
                        flashcards: FlashcardSet = generator.generate(
                            "flashcard_generator",
                            {"material": doc.title, "count": count}
                        )
                        
                        st.success("Flashcards generated!")
                        st.subheader(flashcards.title)
                        if flashcards.description:
                            st.write(flashcards.description)
                        
                        for i, card in enumerate(flashcards.cards):
                            with st.expander(f"Card {i+1}"):
                                st.write("**Question:**", card.front)
                                st.write("**Answer:**", card.back)
                                if card.tags:
                                    st.write("**Tags:**", ", ".join(card.tags))
                    except Exception as e:
                        st.error(f"Error generating flashcards: {str(e)}")

# Page: Study Plan
elif page == "📅 Study Plan":
    st.title("Generate Study Plan")
    
    if "current_doc" not in st.session_state:
        st.warning("Please upload or paste content first!")
    else:
        doc = st.session_state.current_doc
        st.subheader(f"Using document: {doc.title}")
        
        with st.form("study_plan_form"):
            goal = st.text_input("Learning Goal", f"Learn about {doc.title}")
            topics = st.text_area("Topics (comma-separated)", "Introduction, Main Concepts, Practice")
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")
            
            submitted = st.form_submit_button("Generate Study Plan")
            
            if submitted:
                topics_list = [t.strip() for t in topics.split(",") if t.strip()]
                with st.spinner("Generating study plan..."):
                    try:
                        study_plan: StudyPlan = generator.generate(
                            "study_plan_generator",
                            {
                                "goal": goal,
                                "topics": topics_list,
                                "start_date": str(start_date),
                                "end_date": str(end_date)
                            }
                        )
                        
                        st.success("Study plan generated!")
                        st.subheader(study_plan.goal)
                        st.write(f"From {study_plan.start_date} to {study_plan.end_date}")
                        
                        for schedule in study_plan.topic_schedule:
                            with st.expander(schedule.topic):
                                st.write(f"Start: {schedule.start_date}")
                                st.write(f"End: {schedule.end_date}")
                                st.write(f"Duration: {schedule.duration_hours} hours")
                                if schedule.resources:
                                    st.write("Resources:", ", ".join(schedule.resources))
                    except Exception as e:
                        st.error(f"Error generating study plan: {str(e)}")

# Page: Revision Plan
elif page == "🔄 Revision Plan":
    st.title("Generate Revision Plan")
    
    if "current_doc" not in st.session_state:
        st.warning("Please upload or paste content first!")
    else:
        doc = st.session_state.current_doc
        st.subheader(f"Using document: {doc.title}")
        
        with st.form("revision_plan_form"):
            topics = st.text_area("Topics (comma-separated)", "Key Concept 1, Key Concept 2")
            start_date = st.date_input("Session Date")
            
            submitted = st.form_submit_button("Generate Revision Plan")
            
            if submitted:
                topics_list = [t.strip() for t in topics.split(",") if t.strip()]
                with st.spinner("Generating revision plan..."):
                    try:
                        revision_plan: RevisionSession = generator.generate(
                            "revision_plan_generator",
                            {
                                "topics": topics_list,
                                "start_date": str(start_date)
                            }
                        )
                        
                        st.success("Revision plan generated!")
                        st.subheader(f"Revision Session: {revision_plan.session_date}")
                        if revision_plan.notes:
                            st.write(revision_plan.notes)
                        
                        for item in revision_plan.items:
                            with st.expander(item.topic):
                                if item.description:
                                    st.write(item.description)
                                st.write(f"Next revision: {item.next_revision_date}")
                                st.write(f"Difficulty: {item.difficulty}")
                    except Exception as e:
                        st.error(f"Error generating revision plan: {str(e)}")

# Page: Mentor
elif page == "🧭 Mentor":
    st.title("Mentor")
    st.caption("Generate a grounded mentoring response for human review.")

    with st.form("mentor_form"):
        content = st.text_area("Content", height=220)
        user_question = st.text_input("User question")
        difficulty = st.selectbox(
            "Difficulty",
            ["beginner", "intermediate", "advanced"],
            key="mentor_difficulty",
        )
        submitted = st.form_submit_button("Generate Mentor Response")

    if submitted:
        if not content.strip():
            st.warning("Enter educational content before generating a response.")
        else:
            try:
                with st.spinner("Generating mentor response..."):
                    reviewable = mentor_concept_service.generate_mentor_reviewable(
                        content=content,
                        user_question=user_question or None,
                        difficulty=difficulty,
                    )
                payload = reviewable.payload
                st.warning("⚠️ Requires Human Review")
                st.write(f"Review status: **{reviewable.status.value.upper()}**")
                st.subheader("Explanation")
                st.write(payload.get("explanation", ""))
                st.subheader("Key points")
                for point in payload.get("key_points", []):
                    st.markdown(f"- {point}")
                st.subheader("Next steps")
                for step in payload.get("next_steps", []):
                    st.markdown(f"- {step}")
                st.subheader("Provenance references")
                for reference in payload.get("references", []):
                    st.write(f"**{reference['segment_id']}**: {reference['text']}")
            except Exception as error:
                st.error(f"Error generating mentor response: {error}")

# Page: Concept Explanation
elif page == "💡 Concept Explanation":
    st.title("Concept Explanation")
    st.caption("Generate a grounded concept explanation for human review.")

    with st.form("concept_form"):
        content = st.text_area("Content", height=220)
        user_question = st.text_input("Concept question")
        difficulty = st.selectbox(
            "Difficulty",
            ["beginner", "intermediate", "advanced"],
            key="concept_difficulty",
        )
        submitted = st.form_submit_button("Generate Concept Explanation")

    if submitted:
        if not content.strip():
            st.warning("Enter educational content before generating an explanation.")
        else:
            try:
                with st.spinner("Generating concept explanation..."):
                    reviewable = mentor_concept_service.generate_concept_reviewable(
                        content=content,
                        user_question=user_question or None,
                        difficulty=difficulty,
                    )
                payload = reviewable.payload
                st.warning("⚠️ Requires Human Review")
                st.write(f"Review status: **{reviewable.status.value.upper()}**")
                st.subheader("Definition")
                st.write(payload.get("definition", ""))
                st.subheader("Explanation")
                st.write(payload.get("explanation", ""))
                st.subheader("Key points")
                for point in payload.get("key_points", []):
                    st.markdown(f"- {point}")
                st.subheader("Provenance references")
                for reference in payload.get("references", []):
                    st.write(f"**{reference['segment_id']}**: {reference['text']}")
            except Exception as error:
                st.error(f"Error generating concept explanation: {error}")
