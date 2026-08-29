import streamlit as st
import google.genai as genai
from google.genai import types
import pandas as pd
import json
import socket
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# 1. Page Configuration
st.set_page_config(page_title="DIRD HR - Candidate Profiling App", page_icon="💼", layout="wide")

# 2. Securely Retrieve the Gemini API Key from Streamlit Secrets
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.error("🔑 API Key Missing! Please add `GEMINI_API_KEY = 'your_key'` inside your Streamlit Cloud Secrets settings panel.")
    st.stop()

# 3. Main Interface Layout
st.title("💼 DIRD HR - Candidate Profiling App")
st.write("Define your custom columns, upload applicant CVs (1 or 2 at a time), and download as Excel File.")

with st.sidebar:
    st.header("⚙️ System Control")
    st.success("🔑 Gemini 3.6 Flash Active")
    st.write("---")
    st.success("🔗 Google Sheet Authorized")

# 4. Streamlined Storage Function using Repository Configurations
def append_candidate_to_google_sheet(extracted_profiles, defined_columns):
    """Saves candidate records directly onto your tracking cloud Google Sheet spreadsheet."""
    if not extracted_profiles:
        return
        
    try:
        new_df = pd.DataFrame(extracted_profiles)
        
        # Structure out metadata columns
        hostname = socket.gethostname()
        try:
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            ip_address = "Unknown IP"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        new_df["Saved Timestamp"] = current_time
        new_df["Device Name"] = hostname
        new_df["Uploader IP"] = ip_address
        
        final_cols_order = defined_columns + ["Source File Name", "Saved Timestamp", "Device Name", "Uploader IP"]
        new_df = new_df.reindex(columns=final_cols_order)
        
        # Establish Google Sheet sync tunnel connection using the secrets configuration
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        try:
            # Reads using the repository sheet configuration blueprint directly
            existing_df = conn.read(ttl=0)
            if existing_df is not None:
                existing_df = existing_df.dropna(how='all')
            
            if existing_df is None or existing_df.empty:
                updated_df = new_df
            else:
                updated_df = pd.concat([existing_df, new_df], ignore_index=True)
        except Exception:
            updated_df = new_df
            
        # Pushes data straight back to your live tracking database
        conn.update(data=updated_df)
        st.success("🎉 Candidate entries successfully appended to Google Sheet!")
    except Exception as e:
        st.error(f"Cloud Sheet Synchronization Failure: {str(e)}")

# 5. Custom Data Points Configuration
st.subheader("1. Custom Database Columns")
default_columns = "Full Name, Email, Phone Number, Total Years of Experience, Highest Level of Education, Technical Skills"
custom_columns_input = st.text_area(
    "Type the target data fields you want the AI to extract (separated by commas):",
    value=default_columns,
    key="data_points_input"
)
column_list = [col.strip() for col in custom_columns_input.split(",") if col.strip()]

# 6. File Uploader Interface
st.subheader("2. Upload Scanned CVs / Cover Letters")
uploaded_files = st.file_uploader(
    "Drag and drop PDFs or images here:", 
    type=["pdf", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if "custom_database" not in st.session_state:
    st.session_state.custom_database = []
    
# 7. Data Extraction Execution Logic
if uploaded_files:
    if st.button("🚀 Process Documents & Sync to Sheet", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        batch_records = []
        client = genai.Client(api_key=api_key)
        columns_json_structure = {col: "string values extracted from text" for col in column_list}
        
        prompt_instruction = f"""
        You are an expert HR data extraction assistant. Analyze the provided document layout.
        Extract details matching these exact keys. Leave text as empty string "" if missing.
        Return output strictly structured in clean JSON using these keys:
        {json.dumps(columns_json_structure)}
        """
        
        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing ({idx+1}/{len(uploaded_files)}): {uploaded_file.name}...")
            try:
                file_bytes = uploaded_file.read()
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=uploaded_file.type),
                        prompt_instruction
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
                )
                extracted_json = json.loads(response.text)
                extracted_json["Source File Name"] = uploaded_file.name
                
                st.session_state.custom_database.append(extracted_json)
                batch_records.append(extracted_json)
                
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {str(e)}")
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        status_text.text("✅ Batch processing completed!")
        
        if batch_records:
            append_candidate_to_google_sheet(batch_records, column_list)
            
        st.rerun()

# 8. Session Output Grid Display
if st.session_state.custom_database:
    st.write("---")
    st.subheader("📋 Session Extraction Summary View")
    df = pd.DataFrame(st.session_state.custom_database)
    
    final_ordered_columns = column_list + ["Source File Name"]
    df = df.reindex(columns=final_ordered_columns)
    st.dataframe(df, use_container_width=True)
    
    if st.button("🗑️ Clear Local Summary Grid View"):
        st.session_state.custom_database = []
        st.rerun()
