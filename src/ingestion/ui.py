from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the Python path if running standalone
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import streamlit as st
from .loader import ContentLoader


def render_upload_page():
    st.set_page_config(page_title="Upload Content", page_icon="📄")
    st.title("Upload Content")

    loader = ContentLoader()

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
                    document = loader.load_file(file_content, uploaded_file.name)
                    chunks = loader.store.get_chunks_by_document_id(document.id)

                    st.success(f"Successfully uploaded {document.title}!")
                    st.write(f"Document ID: {document.id}")
                    st.write(f"Number of chunks: {len(chunks)}")

                    with st.expander("View Document Content"):
                        st.text(document.content[:2000] + "..." if len(document.content) > 2000 else document.content)
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")

    with tab2:
        title = st.text_input("Title (optional)", "Pasted Text")
        pasted_text = st.text_area("Paste your text here", height=200)

        if st.button("Process Text") and pasted_text:
            try:
                with st.spinner("Processing text..."):
                    document = loader.load_text(pasted_text, title)
                    chunks = loader.store.get_chunks_by_document_id(document.id)

                    st.success(f"Successfully processed {document.title}!")
                    st.write(f"Document ID: {document.id}")
                    st.write(f"Number of chunks: {len(chunks)}")

                    with st.expander("View Document Content"):
                        st.text(document.content[:2000] + "..." if len(document.content) > 2000 else document.content)
            except Exception as e:
                st.error(f"Error processing text: {str(e)}")


if __name__ == "__main__":
    render_upload_page()
