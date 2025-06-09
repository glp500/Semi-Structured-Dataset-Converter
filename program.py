import os
import re
import io
import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
import google.generativeai as genai
from io import BytesIO, StringIO
import csv
import json
import time

# ------------------------------------------------------------
# Helper: an improved error handler for API calls
# ------------------------------------------------------------
def handle_api_error(e, step_name="API call"):
    """
    Provides specific user feedback for common, fixable errors.
    """
    st.error(f"An error occurred during the {step_name}. The process cannot continue.")
    st.error(f"Error details: {e}")
    if "Illegal header value" in str(e):
        st.warning(
            "This error often points to a problem with your Python libraries. "
            "Please try stopping the app and running the following command in your terminal to fix it:\n\n"
            "```\n"
            "pip install --upgrade --force-reinstall google-generativeai google-auth grpcio\n"
            "```"
        )
    st.stop()


# ------------------------------------------------------------
# Helper: chunk long text so each piece stays within model limits
# ------------------------------------------------------------
def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    """
    Split text into chunks whose length does not exceed max_chars,
    attempting to break at whitespace for cleaner splits.
    """
    chunks = []
    current_pos = 0
    while current_pos < len(text):
        end_pos = current_pos + max_chars
        if end_pos >= len(text):
            chunk_to_add = text[current_pos:].strip()
            if chunk_to_add:
                 chunks.append(chunk_to_add)
            break
        
        split_idx = text.rfind("\n", current_pos, end_pos)
        if split_idx == -1 or split_idx < current_pos:
            split_idx = text.rfind(" ", current_pos, end_pos)
        
        if split_idx == -1 or split_idx < current_pos:
            split_idx = end_pos -1
        
        if split_idx < current_pos :
             split_idx = end_pos -1
             if split_idx < current_pos:
                 split_idx = len(text) -1

        chunk_to_add = text[current_pos : split_idx + 1].strip()
        if chunk_to_add:
            chunks.append(chunk_to_add)
        current_pos = split_idx + 1
        
    return [chunk for chunk in chunks if chunk]


# ------------------------------------------------------------
# Helper: robust CSV reader
# ------------------------------------------------------------
def robust_read_csv(csv_text: str, has_header: bool = True) -> pd.DataFrame:
    if not csv_text.strip():
        return pd.DataFrame()

    try:
        df = pd.read_csv(StringIO(csv_text), header=0 if has_header else None, on_bad_lines='skip', engine='python')
        return df
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (pd.errors.ParserError, csv.Error) as err:
        st.warning(f"Pandas/CSV ParserError, attempting manual fallback: {err}. Content snippet: '{csv_text[:200]}'")
        lines = csv_text.strip().splitlines()
        if not lines:
            return pd.DataFrame()

        try:
            try:
                 dialect = csv.Sniffer().sniff(lines[0] if len(lines)>0 else csv_text, delimiters=',;\t|')
                 reader = csv.reader(lines, dialect=dialect)
            except csv.Error:
                 reader = csv.reader(lines)
            all_rows = list(reader)
        except Exception as reader_err:
            st.warning(f"CSV reader failed during fallback: {reader_err}")
            return pd.DataFrame()

        if not all_rows:
            return pd.DataFrame()

        header_row_data = []
        data_rows_data = []

        if has_header:
            if all_rows:
                header_row_data = all_rows[0]
                data_rows_data = all_rows[1:]
            else: return pd.DataFrame()
        else:
            header_row_data = [f"col_{i}" for i in range(len(all_rows[0]))] if all_rows and all_rows[0] else []
            data_rows_data = all_rows
        
        if not header_row_data and not data_rows_data: return pd.DataFrame()
        if not header_row_data and data_rows_data :
            header_row_data = [f"col_{i}" for i in range(len(data_rows_data[0]))] if data_rows_data and data_rows_data[0] else []

        col_cnt = len(header_row_data)
        if col_cnt == 0 and data_rows_data:
             if data_rows_data[0]:
                 col_cnt = len(data_rows_data[0])
                 if not header_row_data: header_row_data = [f"col_{i}" for i in range(col_cnt)]
             else: return pd.DataFrame()
        elif col_cnt == 0 and not data_rows_data:
            return pd.DataFrame(columns=header_row_data)

        fixed_rows = []
        for r in data_rows_data:
            if not r: continue
            if len(r) == col_cnt: fixed_rows.append(r)
            elif len(r) > col_cnt and col_cnt > 0 :
                merged_last = ",".join(r[col_cnt-1:])
                fixed_rows.append(r[:col_cnt-1] + [merged_last])
            elif len(r) < col_cnt:
                fixed_rows.append(r + [""] * (col_cnt - len(r)))

        try:
            if fixed_rows: return pd.DataFrame(fixed_rows, columns=header_row_data)
            elif header_row_data: return pd.DataFrame(columns=header_row_data)
            else: return pd.DataFrame()
        except Exception as final_err:
            st.warning(f"Could not fully repair CSV after manual parsing: {final_err}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Robust CSV reading failed with unexpected error: {e}. CSV Text: {csv_text[:200]}")
        return pd.DataFrame()

# ------------------------------------------------------------
# Streamlit page config
# ------------------------------------------------------------
st.set_page_config(page_title="PDF ➜ Relational CSVs (Gemini)", layout="wide")
st.title("📄 PDF Tables → Relational CSVs (Gemini-powered)")

# ------------------------------------------------------------
# Sidebar – user inputs
# ------------------------------------------------------------
st.sidebar.header("Settings")

api_key_input = st.sidebar.text_input(
    "Google AI API Key",
    type="password",
    placeholder="Enter your Google AI API Key...",
    help="Enter your Google AI API key; it is used only for this session."
)

google_api_key = None
if api_key_input:
    google_api_key = api_key_input.strip()
elif "GOOGLE_API_KEY" in os.environ:
    google_api_key = os.environ["GOOGLE_API_KEY"]

if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
    except Exception as e:
        st.sidebar.error(f"Failed to configure Google AI API: {e}")
        google_api_key = None # Invalidate if configuration fails
else:
    if "uploaded_pdf" in st.session_state and st.session_state.uploaded_pdf is not None :
         st.sidebar.warning("Google AI API Key not found. Please enter it to proceed.")


num_tables = st.sidebar.number_input(
    "Number of CSV tables to generate",
    min_value=1, max_value=5, value=1, step=1
)

table_names = []
for i in range(1, num_tables + 1):
    name = st.sidebar.text_input(f"Name for Table {i}", value=f"Table{i}")
    table_names.append(name.strip() or f"Table{i}")

st.sidebar.markdown("---")
st.sidebar.subheader("Few-Shot Example (Optional)")
example_pdf_file = st.sidebar.file_uploader(
    "1. Example PDF Table",
    type=["pdf"],
    help="Upload a single-page PDF showing an example of the table structure."
)
example_json_file = st.sidebar.file_uploader(
    "2. Example Target JSON",
    type=["json"],
    help="Upload the ideal JSON output corresponding to the example PDF."
)
example_csv_files = st.sidebar.file_uploader(
    "3. Example Target CSVs",
    type=["csv"],
    accept_multiple_files=True,
    help="Upload the final CSV file(s) that should be generated from the example JSON (upload in table order)."
)

st.sidebar.markdown("---")
st.sidebar.subheader("Additional Context")
additional_context_file = st.sidebar.file_uploader(
    "Additional Context File (optional)",
    type=['txt', 'md', 'json', 'py', 'html', 'pdf'],
    help="Upload a file (including PDF) with extra context, syntax rules, or data structure descriptions."
)


# ------------------------------------------------------------
# Main panel – PDF upload & processing
# ------------------------------------------------------------
uploaded_pdf = st.file_uploader("Upload PDF containing tables", type=["pdf"], key="uploaded_pdf_widget")

if uploaded_pdf is not None:
    # State management to reset everything for a new file
    if "last_uploaded_pdf_name" not in st.session_state or st.session_state.last_uploaded_pdf_name != uploaded_pdf.name:
        st.session_state.last_uploaded_pdf_name = uploaded_pdf.name
        keys_to_clear = [
            'pages_text', 'additional_context_text', 'suggestions_just_generated',
            'suggested_context', 'suggested_relationships', 'csv_tables_generated',
            'generated_json_data'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

    if not google_api_key:
        st.error("Please enter your Google AI API key in the sidebar.")
        st.stop()

    if 'pages_text' not in st.session_state:
        try:
            with st.spinner("Extracting text from PDF..."):
                doc = fitz.open(stream=uploaded_pdf.read(), filetype="pdf")
                st.session_state.pages_text = [page.get_text() for page in doc]
                doc.close()
            st.success(f"PDF text extracted from {len(st.session_state.pages_text)} page(s).")
        except Exception as e:
            st.error(f"Failed to read PDF: {e}")
            st.stop()
    
    pages_text = st.session_state.pages_text

    if 'additional_context_text' not in st.session_state:
        if additional_context_file is not None:
            raw_context_text = ""
            try:
                if additional_context_file.name.lower().endswith('.pdf'):
                    with st.spinner(f"Extracting text from context PDF: {additional_context_file.name}..."):
                        context_pdf_stream = BytesIO(additional_context_file.getvalue())
                        with fitz.open(stream=context_pdf_stream, filetype="pdf") as doc:
                            context_pages = [page.get_text() for page in doc]
                        raw_context_text = "\n".join(context_pages)
                else:
                    raw_context_text = additional_context_file.getvalue().decode("utf-8")
                
                CONTEXT_SUMMARY_THRESHOLD = 15000
                if len(raw_context_text) > CONTEXT_SUMMARY_THRESHOLD:
                    with st.spinner(f"Context file is large, summarizing it first..."):
                        context_chunks = chunk_text(raw_context_text)
                        summaries = []
                        model_summarizer = genai.GenerativeModel(model_name='gemini-2.5-pro-preview-06-05')
                        
                        for i, chunk in enumerate(context_chunks):
                            st.info(f"Summarizing context chunk {i+1}/{len(context_chunks)}...")
                            try:
                                prompt = f"Summarize the key information, rules, and syntax from this piece of technical documentation:\n\n{chunk}"
                                resp = model_summarizer.generate_content(prompt)
                                summaries.append(resp.text)
                                time.sleep(1) 
                            except Exception as e:
                                handle_api_error(e, f"context summarization on chunk {i+1}")
                        
                        if summaries:
                            st.info("Creating final summary of context...")
                            try:
                                final_summary_prompt = "Consolidate the following summaries into a single, coherent set of instructions and context:\n\n" + "\n---\n".join(summaries)
                                final_resp = model_summarizer.generate_content(final_summary_prompt)
                                st.session_state.additional_context_text = final_resp.text
                                st.success("Large context file has been summarized.")
                            except Exception as e:
                                handle_api_error(e, "final context summarization")
                        else:
                            st.session_state.additional_context_text = ""
                else:
                    st.session_state.additional_context_text = raw_context_text
                
            except Exception as e:
                st.warning(f"Could not read or process the additional context file: {e}")
                st.session_state.additional_context_text = ""
        else:
            st.session_state.additional_context_text = ""
            
    additional_context_text = st.session_state.get('additional_context_text', "")

    example_pdf_text = ""
    if example_pdf_file:
        try:
            with fitz.open(stream=example_pdf_file.read(), filetype="pdf") as doc:
                if doc: example_pdf_text = "\n".join([page.get_text() for page in doc])
                else: st.sidebar.warning("Example PDF is empty.")
        except Exception as e:
            st.sidebar.error(f"Failed to read example PDF: {e}")

    example_json_text = ""
    if example_json_file:
        try:
            example_json_text = example_json_file.getvalue().decode("utf-8")
        except Exception as e:
            st.sidebar.error(f"Failed to read example JSON: {e}")

    if (
        pages_text and not st.session_state.get('suggestions_just_generated')
    ):
        with st.spinner("Analyzing tables with Gemini to generate context (runs once per file)..."):
            try:
                model_context_gen = genai.GenerativeModel(model_name='gemini-2.5-pro-preview-06-05')
                generation_config_context = genai.types.GenerationConfig(max_output_tokens=4096, temperature=0.3)
                first_page_for_context = pages_text[0][:8000]
                
                ctx_prompt = f"Based on the following extracted table data, write a detailed instructional prompt describing the overall context, data types, and business rules so another model can use it. Be thorough.\n\n{first_page_for_context}"
                ctx_resp = model_context_gen.generate_content(ctx_prompt, generation_config=generation_config_context)
                
                rel_prompt = f"Using the same extracted table data, describe in detail the plausible PK/FK relationships, hierarchical links, and relational schema that would help build a relational dataset. Be thorough.\n\n{first_page_for_context}"
                rel_resp = model_context_gen.generate_content(rel_prompt, generation_config=generation_config_context)
                
                st.session_state["suggested_context"] = ctx_resp.text.strip()
                st.session_state["suggested_relationships"] = rel_resp.text.strip()
                st.session_state.suggestions_just_generated = True
                st.rerun()
            except Exception as e:
                handle_api_error(e, "auto-context generation")

    st.markdown("---")
    st.subheader("Step 1: Review and Edit Context")
    expand_suggestions = st.session_state.get('suggestions_just_generated', False)

    with st.expander("🧠 Suggested Context (editable)", expanded=expand_suggestions):
        edited_context = st.text_area("Context prompt", value=st.session_state.get("suggested_context", ""), height=200, key="edited_context_area", help="This text is automatically generated. You can edit it before generating the final CSVs.")
    with st.expander("🔗 Suggested Table Relationships (editable)", expanded=expand_suggestions):
        edited_relationships = st.text_area("Relationships description", value=st.session_state.get("suggested_relationships", ""), height=200, key="edited_relationships_area", help="This text is automatically generated. You can edit it before generating the final CSVs.")
    user_context = st.text_area("Your Additional Context (manual input)", placeholder=("Add any other context here..."), height=150)

    example_snippets = []
    if example_csv_files:
        for i, csv_file in enumerate(example_csv_files):
            try:
                csv_file.seek(0)
                df_ex = pd.read_csv(BytesIO(csv_file.getvalue()))
                headers = list(df_ex.columns)
                first_row = df_ex.iloc[0].tolist() if not df_ex.empty else []
                if i < len(table_names):
                    table_name = table_names[i]
                    snippet = f"Example for Table '{table_name}':\nHeaders: {headers}\nFirst row: {first_row}\n"
                    example_snippets.append(snippet)
            except Exception as e:
                st.sidebar.warning(f"Could not read example CSV {csv_file.name}: {e}")

    st.markdown("---")
    st.subheader("Step 2: Generate Final CSVs")
    
    if st.button("Generate CSV tables", key="generate_csv_button"):
        
        few_shot_for_json_prompt = ""
        if example_pdf_text and example_json_text:
            few_shot_for_json_prompt = f"""Here is a one-shot example to guide you.

--- START OF EXAMPLE ---
**EXAMPLE INPUT (TEXT FROM A PDF PAGE):**
```text
{example_pdf_text}

EXAMPLE OUTPUT (THE DESIRED JSON):
{example_json_text}
--- END OF EXAMPLE ---
Now, apply the same logic and structure from the example to the real input below.
"""
# --- PART 1: Place this entire section INSIDE the if st.button(...) block ---

        all_pages_text = "\n".join(pages_text)
        text_chunks = chunk_text(all_pages_text)

        st.session_state.generated_json_data = None
        st.session_state.csv_tables_generated = None

        with st.spinner(f"Asking Gemini to convert PDF text to structured JSON... (processing {len(text_chunks)} chunk(s))"):
            all_json_responses = []
            model_json = genai.GenerativeModel(model_name='gemini-2.5-pro-preview-06-05')
            generation_config_json = genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
            
            for i, chunk in enumerate(text_chunks):
                st.info(f"Processing chunk {i+1}/{len(text_chunks)}...")
                prompt_parts = [
                    few_shot_for_json_prompt,
                    "You are a data extraction expert. Convert the following text extracted from a PDF into a single, well-structured JSON object.",
                    "The JSON should represent all the tables and their relationships as described in the context.",
                    f"CONTEXT:\n{edited_context}\n\nRELATIONSHIPS:\n{edited_relationships}\n\nADDITIONAL CONTEXT:\n{additional_context_text}\n\nMANUAL CONTEXT:\n{user_context}",
                    "Ensure the JSON is valid and accurately captures all data points, including hierarchical structures.",
                    f"PDF TEXT CHUNK:\n```text\n{chunk}\n```"
                ]
                try:
                    final_prompt = "\n".join(filter(None, prompt_parts))
                    response = model_json.generate_content(final_prompt, generation_config=generation_config_json)
                    all_json_responses.append(response.text)
                    time.sleep(1)
                except Exception as e:
                    handle_api_error(e, f"JSON generation on chunk {i+1}")
            
            if len(all_json_responses) > 1:
                st.warning("Multiple text chunks were processed. Attempting to merge JSON outputs. Review the result carefully.")
                merged_data = {}
                for json_str in all_json_responses:
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict):
                            merged_data.update(data)
                        else:
                            st.warning(f"Cannot merge JSON response of type {type(data)}. Appending as string.")
                    except json.JSONDecodeError:
                        st.error(f"Failed to decode a JSON chunk. The chunk will be skipped:\n{json_str[:500]}")
                final_json_text = json.dumps(merged_data, indent=2)
            elif all_json_responses:
                final_json_text = all_json_responses[0]
            else:
                st.error("No JSON was generated from the PDF text.")
                st.stop()
                
            st.session_state.generated_json_data = final_json_text
            st.success("Successfully generated structured JSON from PDF text.")

# --- PART 2: Place this section AFTER the if st.button(...) block, at the same indentation level ---

    if 'generated_json_data' in st.session_state and st.session_state.generated_json_data:
        st.subheader("View Generated JSON")
        st.json(st.session_state.generated_json_data)
        
        with st.spinner("Asking Gemini to convert JSON to final CSV tables..."):
            try:
                model_csv = genai.GenerativeModel(model_name='gemini-2.5-pro-preview-06-05')
                generation_config_csv = genai.types.GenerationConfig(temperature=0.0)

                csv_prompt_parts = [
                    "You are a data transformation expert. Your task is to convert the provided JSON data into multiple, distinct, relational CSV tables as specified.",
                    f"You must generate exactly {num_tables} CSV table(s).",
                    f"The required table names are: {', '.join(table_names)}.",
                    "Use the provided context, relationships, and CSV examples to determine the correct columns and data for each table.",
                    f"CONTEXT:\n{edited_context}\n\nRELATIONSHIPS:\n{edited_relationships}\n\nADDITIONAL CONTEXT:\n{additional_context_text}\n\nMANUAL CONTEXT:\n{user_context}",
                    "CSV EXAMPLES:\n" + "\n".join(example_snippets) if example_snippets else "No CSV examples provided.",
                    "Follow these output instructions precisely:",
                    "1. For each table, start with a header line: `=== START OF TABLE: [TableName] ===`",
                    "2. Then, provide the CSV data for that table, with a header row and comma-separated values.",
                    "3. End each table's data with a footer line: `=== END OF TABLE: [TableName] ===`",
                    "4. Ensure the data is properly normalized across the tables as per the relational schema description.",
                    f"JSON DATA TO TRANSFORM:\n```json\n{st.session_state.generated_json_data}\n```"
                ]

                final_csv_prompt = "\n".join(filter(None, csv_prompt_parts))
                csv_response = model_csv.generate_content(final_csv_prompt, generation_config=generation_config_csv)
                
                table_pattern = re.compile(r"=== START OF TABLE: (.*?) ===\n(.*?)\n=== END OF TABLE: \1 ===", re.DOTALL)
                matches = table_pattern.findall(csv_response.text)

                if not matches:
                    st.error("The model did not return any data in the expected format. The generation failed.")
                    st.code(csv_response.text, language='text')
                else:
                    generated_tables = {}
                    for name, csv_data in matches:
                        df = robust_read_csv(csv_data)
                        if not df.empty:
                            generated_tables[name.strip()] = df
                    
                    st.session_state.csv_tables_generated = generated_tables
                    st.success(f"Successfully generated {len(generated_tables)} CSV table(s).")
            
            except Exception as e:
                handle_api_error(e, "CSV generation from JSON")

    if 'csv_tables_generated' in st.session_state and st.session_state.csv_tables_generated:
        st.markdown("---")
        st.subheader("Step 3: Review and Download Generated CSVs")
        
        generated_tables_data = st.session_state.csv_tables_generated
        
        if generated_tables_data:
            tab_titles = list(generated_tables_data.keys())
            tabs = st.tabs(tab_titles)
            
            for i, table_name in enumerate(tab_titles):
                with tabs[i]:
                    st.markdown(f"#### {table_name}")
                    df_to_display = generated_tables_data[table_name]
                    st.dataframe(df_to_display)
                    
                    csv_buffer = StringIO()
                    df_to_display.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label=f"Download {table_name}.csv",
                        data=csv_buffer.getvalue(),
                        file_name=f"{table_name}.csv",
                        mime="text/csv",
                        key=f"download_{table_name}"
                    )
        else:
            st.warning("No tables were generated or data was empty after processing.")