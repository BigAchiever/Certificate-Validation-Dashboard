import streamlit as st
import pandas as pd
from services.upload_service import upload_to_azure_ai

# Streamlit UI
st.title("Certificate Validation Dashboard")
st.write("Upload a PDF to extract fields using Azure AI Document Intelligence")

# Initialize session state for file processing
if "processed_file" not in st.session_state:
    st.session_state.processed_file = None
if "extracted_fields" not in st.session_state:
    st.session_state.extracted_fields = None

# File uploader
uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], key="pdf_uploader")

if uploaded_file and uploaded_file != st.session_state.processed_file:
    try:
        # Update status
        status = st.empty()
        status.write("Processing file...")

        # Read file bytes
        file_bytes = uploaded_file.read()
        file_name = uploaded_file.name

        # Process with Azure AI
        extracted_fields = upload_to_azure_ai(file_name, file_bytes)

        # Convert lists to strings for display
        display_fields = {
            key: ", ".join(value) if isinstance(value, list) else value
            for key, value in extracted_fields.items()
        }

        # Create a DataFrame (single row)
        df = pd.DataFrame([display_fields])

        # Transpose the DataFrame to place headers vertically
        df_transposed = df.transpose().reset_index()
        df_transposed.columns = ["Field", "Certificate Detail"]

        # Update session state
        st.session_state.processed_file = uploaded_file
        st.session_state.extracted_fields = df_transposed

        # Display results
        status.success("File processed successfully!")
        st.subheader("Extracted Fields")
        st.dataframe(df_transposed, use_container_width=True)

    except RuntimeError as e:
        status.error(f"Processing failed: {e}. Please try again or check your configuration.")
        st.session_state.processed_file = None
        st.session_state.extracted_fields = None
    except ValueError as e:
        status.error(f"Invalid input: {e}. Please upload a valid PDF file.")
        st.session_state.processed_file = None
        st.session_state.extracted_fields = None
    except Exception as e:
        status.error(f"An unexpected error occurred: {e}. Please try again or contact support.")
        st.session_state.processed_file = None
        st.session_state.extracted_fields = None
else:
    if st.session_state.extracted_fields is not None:
        st.subheader("Extracted Fields")
        st.dataframe(st.session_state.extracted_fields, use_container_width=True)
    else:
        st.info("Please upload a PDF file to begin.")