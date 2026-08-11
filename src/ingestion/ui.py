from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the Python path if running standalone
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import streamlit as st

# Absolute imports: `streamlit run src/ingestion/ui.py` executes this file as
# __main__, where there is no parent package for a relative import to resolve
# against. The sys.path setup above is what makes these work standalone.
from src.ingestion.batch import BatchIngestion
from src.ingestion.demo_data import DemoDataLoader
from src.ingestion.library import ContentLibrary
from src.ingestion.loader import ContentLoader


@st.cache_resource
def get_loader():
    return ContentLoader()


@st.cache_resource
def get_batch():
    return BatchIngestion()


@st.cache_resource
def get_library():
    return ContentLibrary()


@st.cache_resource
def get_demo():
    return DemoDataLoader()


def render_upload_page():
    st.set_page_config(page_title="Upload Content", page_icon="📄")
    st.title("Upload Content")

    loader = get_loader()
    batch = get_batch()
    library = get_library()
    demo = get_demo()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📁 Upload File",
            "📝 Paste Text",
            "📂 Batch Upload",
            "📚 Content Library",
            "🎓 Demo Dataset",
        ]
    )

    with tab1:
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["txt", "pdf", "docx", "md"],
            key="single_file_upload",
        )

        if uploaded_file is not None:
            try:
                progress = st.progress(0, text="Starting upload...")

                progress.progress(20, text="Reading file...")
                file_content = uploaded_file.read()

                progress.progress(50, text="Processing content...")
                document = loader.load_file(file_content, uploaded_file.name)

                progress.progress(80, text="Generating chunks...")
                chunks = loader.store.get_chunks_by_document_id(document.id)

                progress.progress(100, text="Upload complete!")
                progress.empty()
                st.session_state.current_doc = document
                st.session_state.current_chunks = chunks
                st.success(f"Successfully uploaded {document.title}!")
                st.write(f"Document ID: {document.id}")
                st.write(f"Number of chunks: {len(chunks)}")

                with st.expander("View Document Content"):
                    st.text(
                        document.content[:2000] + "..."
                        if len(document.content) > 2000
                        else document.content
                    )
            except ValueError as e:
                st.error(str(e))

            except Exception as e:
                st.error(f"Unexpected error: {e!s}")

    with tab2:
        title = st.text_input("Title (optional)", "Pasted Text")
        pasted_text = st.text_area("Paste your text here", height=200)

        if st.button("Process Text", key="process_text_button"):
            if not pasted_text.strip():
                st.warning("Please enter some text.")

            else:
                try:
                    with st.spinner("Processing text..."):
                        document = loader.load_text(pasted_text, title)
                        chunks = loader.store.get_chunks_by_document_id(document.id)

                        st.session_state.current_doc = document
                        st.session_state.current_chunks = chunks
                        st.success(f"Successfully processed {document.title}!")
                        st.write(f"Document ID: {document.id}")
                        st.write(f"Number of chunks: {len(chunks)}")

                        with st.expander("View Document Content"):
                            st.text(
                                document.content[:2000] + "..."
                                if len(document.content) > 2000
                                else document.content
                            )
                except ValueError as e:
                    st.error(str(e))

                except Exception as e:
                    st.error(f"Unexpected error: {e!s}")

    with tab3:
        uploaded_files = st.file_uploader(
            "Choose multiple files",
            type=["txt", "pdf", "docx", "md"],
            accept_multiple_files=True,
            key="batch_file_upload",
        )

        if st.button(
            "Upload Files",
            key="upload_files_button",
        ):
            if not uploaded_files:
                st.warning("Please select one or more files.")

            else:
                files = [(file.name, file.read()) for file in uploaded_files]

                progress = st.progress(0, text="Preparing batch upload...")

                progress.progress(25, text="Reading selected files...")
                result = batch.ingest_files(files)

                progress.progress(100, text="Batch upload complete!")
                progress.empty()

                if result.documents:
                    st.session_state.current_doc = result.documents[0]
                    st.session_state.current_chunks = (
                        loader.store.get_chunks_by_document_id(result.documents[0].id)
                    )
                    st.success(
                        f"Successfully uploaded {len(result.documents)} file(s). Set '{result.documents[0].title}' as active content."
                    )

                if result.failed_files:
                    st.warning(
                        f"{len(result.failed_files)} file(s) could not be processed."
                    )

                    for failed in result.failed_files:
                        st.error(f"{failed.filename}: {failed.error}")

    with tab4:
        st.subheader("Content Library")

        # Optional refresh button
        st.button("Refresh Library", key="refresh_library_button")

        # Always load the documents
        documents = library.list_documents()

        if not documents:
            st.info("No documents have been uploaded yet.")

        else:
            current_id = getattr(st.session_state.get("current_doc"), "id", None)
            for doc in documents:
                col1, col2 = st.columns([4, 2])

                with col1:
                    active_badge = " 🟢 **[ACTIVE]**" if current_id == doc.id else ""
                    st.markdown(f"### {doc.title}{active_badge}")
                    st.write(f"**Source:** {doc.source_type}")
                    st.write(f"**Type:** {doc.file_type}")
                    st.write(f"**Size:** {doc.size}")
                    st.write(f"**Chunks:** {doc.chunk_count}")
                    st.write(
                        f"**Created:** {doc.created_at.strftime('%Y-%m-%d %H:%M')}"
                    )

                with col2:
                    if st.button("📌 Select Active", key=f"select_{doc.id}"):
                        loaded_doc = library.get_document(doc.id)
                        if loaded_doc:
                            chunks = loader.store.get_chunks_by_document_id(doc.id)
                            st.session_state.current_doc = loaded_doc
                            st.session_state.current_chunks = chunks
                            st.success(
                                f"Selected '{loaded_doc.title}' as active content!"
                            )
                            st.rerun()
                    if st.button("🗑️ Delete", key=f"delete_{doc.id}"):
                        if library.delete_document(doc.id):
                            if current_id == doc.id:
                                st.session_state.current_doc = None
                                st.session_state.current_chunks = []
                            st.success(f"{doc.title} deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to delete document.")

                st.divider()

    with tab5:
        st.subheader("Demo Dataset")

        st.write("Load a sample educational dataset into the content library.")

        if st.button("Load Demo Dataset", key="load_demo_button"):
            try:
                progress = st.progress(0, text="Loading demo dataset...")

                count = demo.load_demo_data()

                docs = library.list_documents()
                if docs:
                    loaded_doc = library.get_document(docs[0].id)
                    if loaded_doc:
                        chunks = loader.store.get_chunks_by_document_id(loaded_doc.id)
                        st.session_state.current_doc = loaded_doc
                        st.session_state.current_chunks = chunks

                progress.progress(100, text="Demo dataset loaded!")
                progress.empty()

                st.success(f"Successfully loaded {count} demo document(s).")

                st.rerun()
            except ValueError as e:
                st.error(str(e))

            except Exception as e:
                st.error(f"Failed to load demo dataset: {e!s}")


if __name__ == "__main__":
    render_upload_page()
