import os
import sys
import fitz  # PyMuPDF
import streamlit as st

# Add parent directory to path to import from services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import extractor, api
from services.api import handle_api_error
from services.transformer import parse_tables_from_csv
from examples.init import load_examples
from prompts.schema import OutputModel
from utils.chunk import chunk_text

# Page configuration
st.set_page_config(page_title="PDF ➜ Relational CSVs (Gemini)", layout="wide")
st.title("📄 PDF Tables → Relational CSVs (Gemini-powered)")

# Sidebar inputs
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
    configured = api.configure_api(google_api_key)
    if not configured:
        # API key configuration failed (error already shown in sidebar)
        google_api_key = None
else:
    # If a PDF is already uploaded, remind user to input API key
    if "uploaded_pdf" in st.session_state and st.session_state.uploaded_pdf is not None:
        st.sidebar.warning("Google AI API Key not found. Please enter it to proceed.")

# Table detection method selection
table_method = st.sidebar.selectbox(
    "Table detection method",
    options=["auto", "lattice", "matrix"],
    index=0,
    help="Choose the strategy for table extraction from PDF."
)

num_tables = st.sidebar.number_input(
    "Number of CSV tables to generate",
    min_value=1, max_value=5, value=1, step=1
)
table_names = []
for i in range(1, num_tables + 1):
    name = st.sidebar.text_input(f"Name for Table {i}", value=f"Table{i}")
    table_names.append(name.strip() or f"Table{i}")

st.sidebar.markdown("---")
st.sidebar.subheader("Few-Shot Examples (Optional)")
example_pdf_file = st.sidebar.file_uploader(
    "1. Example PDF Table",
    type=["pdf"],
    help="Upload a single-page PDF as an example of the table structure."
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
    help="Upload the final CSV file(s) from the example JSON (in table order)."
)

st.sidebar.markdown("---")
st.sidebar.subheader("Additional Context")
additional_context_file = st.sidebar.file_uploader(
    "Additional Context File (optional)",
    type=['txt', 'md', 'json', 'py', 'html', 'pdf'],
    help="Upload a file with extra context, rules, or data structure descriptions."
)

# Main panel
uploaded_pdf = st.file_uploader("Upload PDF containing tables", type=["pdf"], key="uploaded_pdf")

if uploaded_pdf is not None:
    # Reset state when a new PDF is uploaded
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

    # Extract text/tables from PDF if not already done
    if 'pages_text' not in st.session_state:
        try:
            with st.spinner("Extracting tables from PDF..."):
                pdf_bytes = uploaded_pdf.getvalue()
                st.session_state.pages_text = extractor.extract_tables_from_pdf(pdf_bytes, method=table_method)
            st.success(f"Extracted content from {len(st.session_state.pages_text)} page(s).")
        except Exception as e:
            st.error(f"Failed to read PDF: {e}")
            st.stop()
    pages_text = st.session_state.pages_text

    # Determine built-in examples usage if no user example provided
    built_in_examples = []
    n_examples = 0
    if not example_pdf_file or not example_json_file:
        built_in_examples = load_examples(max_examples=10)
        if built_in_examples:
            n_examples = st.sidebar.number_input(
                "Number of built-in examples to use",
                min_value=0,
                max_value=min(len(built_in_examples), 10),
                value=0
            )

    # Read user example PDF and JSON if provided
    example_pdf_text = ""
    if example_pdf_file is not None:
        try:
            with fitz.open(stream=example_pdf_file.read(), filetype="pdf") as doc:
                example_pdf_text = "\n".join(page.get_text() for page in doc)
        except Exception as e:
            st.sidebar.error(f"Failed to read example PDF: {e}")
    example_json_text = ""
    if example_json_file is not None:
        try:
            example_json_text = example_json_file.getvalue().decode("utf-8")
        except Exception as e:
            st.sidebar.error(f"Failed to read example JSON: {e}")

    # Auto-generate context suggestions once per file
    if pages_text and not st.session_state.get('suggestions_just_generated'):
        with st.spinner("Analyzing tables with Gemini to generate context (runs once)..."):
            try:
                model_context = api.genai.GenerativeModel(model_name="gemini-2.5-pro-preview-06-05")
                gen_conf = api.genai.types.GenerationConfig(max_output_tokens=4096, temperature=0.3)
                first_page_snippet = pages_text[0][:8000] if pages_text else ""
                ctx_prompt = f"Based on the following extracted table data, write a detailed prompt describing the overall context, data types, and business rules.\n\n{first_page_snippet}"
                rel_prompt = f"Using the same extracted table data, describe plausible primary/foreign key relationships and hierarchical links in detail.\n\n{first_page_snippet}"
                ctx_resp = model_context.generate_content(ctx_prompt, generation_config=gen_conf)
                rel_resp = model_context.generate_content(rel_prompt, generation_config=gen_conf)
                st.session_state["suggested_context"] = ctx_resp.text.strip()
                st.session_state["suggested_relationships"] = rel_resp.text.strip()
                st.session_state["suggestions_just_generated"] = True
                st.rerun()
            except Exception as e:
                handle_api_error(e, "auto-context generation")

    st.markdown("---")
    st.subheader("Step 1: Review and Edit Context")
    expand_suggestions = st.session_state.get('suggestions_just_generated', False)
    with st.expander("🧠 Suggested Context (editable)", expanded=expand_suggestions):
        edited_context = st.text_area("Context prompt", value=st.session_state.get("suggested_context", ""), height=200, key="edited_context_area", help="Automatically generated context. You can edit it.")
    with st.expander("🔗 Suggested Table Relationships (editable)", expanded=expand_suggestions):
        edited_relationships = st.text_area("Relationships description", value=st.session_state.get("suggested_relationships", ""), height=200, key="edited_relationships_area", help="Automatically generated relationships. You can edit it.")
    user_context = st.text_area("Your Additional Context (manual input)", placeholder="Add any other context here...", height=150)

    # Prepare example CSV snippet descriptions if any
    example_snippets: list[str] = []
    if example_csv_files:
        for i, csv_file in enumerate(example_csv_files):
            try:
                csv_file.seek(0)
                import pandas as pd
                df_ex = pd.read_csv(csv_file)
                headers = list(df_ex.columns)
                first_row = df_ex.iloc[0].tolist() if not df_ex.empty else []
                table_label = table_names[i] if i < len(table_names) else f"Table{i+1}"
                snippet = f"Example for Table '{table_label}':\nHeaders: {headers}\nFirst row: {first_row}\n"
                example_snippets.append(snippet)
            except Exception as e:
                st.sidebar.warning(f"Could not read example CSV {csv_file.name}: {e}")

    st.markdown("---")
    st.subheader("Step 2: Generate Final CSVs")

    if st.button("Generate CSV tables", key="generate_csv_button"):
        few_shot_examples = None
        if example_pdf_text and example_json_text:
            few_shot_examples = [(example_pdf_text, example_json_text)]
        else:
            if built_in_examples and n_examples > 0:
                few_shot_examples = built_in_examples[:n_examples]
        # Generate JSON from PDF text
        st.session_state.generated_json_data = None
        st.session_state.csv_tables_generated = None
        with st.spinner("Asking Gemini to convert PDF to structured JSON..."):
            json_output_text = api.generate_structured_json(
                pages_text=pages_text,
                context_text=edited_context,
                relationships_text=edited_relationships,
                additional_context_text=additional_context_text if 'additional_context_text' in st.session_state else "",
                manual_context_text=user_context,
                examples=few_shot_examples
            )
        # Validate JSON output
        try:
            parsed_model = OutputModel.model_validate_json(json_output_text)
        except Exception as e:
            # Display validation errors
            errors = e.errors() if hasattr(e, 'errors') else [{"msg": str(e)}]
            st.error("JSON validation failed. Please review the output and context.")
            for err in errors:
                loc = err.get('loc', None)
                msg = err.get('msg', '')
                if loc:
                    st.error(f"{loc}: {msg}")
                else:
                    st.error(f"{msg}")
            st.stop()
        else:
            # Reformat JSON for consistent indentation
            try:
                json_pretty = parsed_model.model_dump_json(indent=2, exclude_none=True)
            except Exception:
                import json as pyjson
                json_pretty = pyjson.dumps(parsed_model.model_dump(), indent=2)
            st.session_state.generated_json_data = json_pretty
            st.success("Successfully generated structured JSON from PDF text.")

    # After JSON generation, proceed to CSV generation
    if 'generated_json_data' in st.session_state and st.session_state.generated_json_data:
        st.subheader("View Generated JSON")
        st.json(st.session_state.generated_json_data)
        
        # Only generate CSV tables if not already generated
        if 'csv_tables_generated' not in st.session_state or not st.session_state.csv_tables_generated:
            with st.spinner("Asking Gemini to convert JSON to CSV tables..."):
                try:
                    csv_output_text = api.generate_csv_from_json(
                        json_text=st.session_state.generated_json_data,
                        table_names=table_names,
                        context_text=edited_context,
                        relationships_text=edited_relationships,
                        additional_context_text=additional_context_text if 'additional_context_text' in st.session_state else "",
                        manual_context_text=user_context,
                        example_snippets=example_snippets
                    )
                except Exception as e:
                    handle_api_error(e, "CSV generation")
                else:
                    tables_dict = parse_tables_from_csv(csv_output_text)
                    if not tables_dict:
                        st.error("The model did not return any data in the expected format. Generation failed.")
                        st.code(csv_output_text, language='text')
                    else:
                        st.session_state.csv_tables_generated = tables_dict
                        st.success(f"Successfully generated {len(tables_dict)} CSV table(s).")

    if 'csv_tables_generated' in st.session_state and st.session_state.csv_tables_generated:
        st.markdown("---")
        st.subheader("Step 3: Review and Download Generated CSVs")
        generated_tables = st.session_state.csv_tables_generated
        if generated_tables:
            tab_titles = list(generated_tables.keys())
            tabs = st.tabs(tab_titles)
            for i, table_name in enumerate(tab_titles):
                with tabs[i]:
                    st.markdown(f"#### {table_name}")
                    df_to_display = generated_tables[table_name]
                    st.dataframe(df_to_display)
                    csv_buffer = df_to_display.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label=f"Download {table_name}.csv",
                        data=csv_buffer,
                        file_name=f"{table_name}.csv",
                        mime="text/csv",
                        key=f"download_{table_name}"
                    )
        else:
            st.warning("No tables were generated or data was empty.")