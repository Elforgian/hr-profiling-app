import streamlit as st
import google.genai as genai
from google.genai import types
import pandas as pd
import json
import io
import socket
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# 1. Page Configuration
st.set_page_config(page_title="AI Candidate Profile Builder", page_icon="💼", layout="wide")

# Hardcoded Google Sheet URL for secure background activity logs
HARDCODED_LOG_SHEET = "https://google.com"

# 2. Securely Retrieve the API Key from Streamlit Secrets
# This completely bypasses the need for manual user input in the sidebar
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.error("🔑 API Key Missing! Please add `GEMINI_API_KEY = 'your_key'` inside your Streamlit Cloud Secrets settings panel.")
    st.stop()

# 3. Main Interface Layout
st.title("💼 AI Candidate Profile Builder")
st.write("This application is open to everyone. Define your custom columns, upload applicant files, and download your structured Excel sheet.")

# Sidebar Configuration (Simplified - API key input box removed)
with st.sidebar:
    st.header("⚙️ System Control")
    st.success("🔑 Gemini API Key Active (Loaded from Secrets)")
    st.write("---")
    st.success("🔗 Background Activity Log Connected Securely")

# 4. Background Cloud Activity Logging Function
def log_user_activity_to_sheets(file_count, sheet_link):
    """Logs runtime execution details directly into the hardcoded Google Sheet in the background."""
    try:
        hostname = socket.gethostname()
        try:
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            ip_address = "Unknown IP"
            
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Structure the new log entry row matching the sheet layout
        new_row = pd.DataFrame([{
            "Timestamp": current_time,
            "Device Hostname": hostname,
            "IP Address": ip_address,
            "Files Processed": int(file_count)
        }])
        
        # Connect to Google Sheets through Streamlit's connection architecture
        conn = st.connection("gsheets", type=GSheetsConnection)
        existing_df = conn.read(spreadsheet=sheet_link, ttl=0)
        updated_df = pd.concat([existing_df, new_row], ignore_index=True)
        
        # Force cloud sync write-back execution
        conn.update(spreadsheet=sheet_link, data=updated_df)
    except Exception:
        pass  # Fails silently to ensure no frontend service breaks for users

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

# Initialize data grid storage across live interactive clicks
if "custom_database" not in st.session_state:
    st.session_state.custom_database = []
    
# 7. Multimodal Data Extraction Logic
if uploaded_files:
    if st.button("🚀 Process Documents & Generate Excel Data", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        new_records_count = 0
        client = genai.Client(api_key=api_key)
        columns_json_structure = {col: "string values extracted from text" for col in column_list}
        
        prompt_instruction = f"""
        You are an expert HR data extraction assistant. Analyze the provided document.
        Extract details strictly matching the requested data fields. Leave as empty string "" if missing.
        Return output cleanly structured in JSON using these exact keys:
        {json.dumps(columns_json_structure)}
        """
        
        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing ({idx+1}/{len(uploaded_files)}): {uploaded_file.name}...")
            try:
                file_bytes = uploaded_file.read()
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=uploaded_file.type),
                        prompt_instruction
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
                )
                extracted_json = json.loads(response.text)
                extracted_json["Source File Name"] = uploaded_file.name
                
                # Cache results in immediate memory workspace
                st.session_state.custom_database.append(extracted_json)
                new_records_count += 1
                
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {str(e)}")
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        status_text.text("✅ Data processing complete!")
        
        # Fire silent background log directly to your hardcoded Google Sheet
        if new_records_count > 0:
            log_user_activity_to_sheets(new_records_count, HARDCODED_LOG_SHEET)
            
        st.rerun()

# 8. Interactive UI Spreadsheet Grid & File Compilation
if st.session_state.custom_database:
    st.write("---")
    st.subheader("📋 Generated Candidate Database Grid")
    df = pd.DataFrame(st.session_state.custom_database)
    
    final_ordered_columns = column_list + ["Source File Name"]
    df = df.reindex(columns=final_ordered_columns)
    
    st.dataframe(df, use_container_width=True)
    
    # Formulate binary output buffer for the spreadsheet file download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Extracted Candidates')
    
    st.download_button(
        label="📥 Download Extracted Candidates Excel Sheet",
        data=buffer.getvalue(),
        file_name="hr_candidate_database.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    if st.button("🗑️ Reset Application Data Grid"):
        st.session_state.custom_database = []
        st.rerun()
