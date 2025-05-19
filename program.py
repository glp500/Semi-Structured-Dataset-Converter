import os
import re
import io
import fitz                   # PyMuPDF
import pandas as pd
import streamlit as st
import openai
from io import BytesIO, StringIO

# ------------------------------------------------------------
# Helper: chunk long text so each piece stays within model limits
# ------------------------------------------------------------
def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    """
    Split text into chunks whose length does not exceed max_chars,
    attempting to break at whitespace for cleaner splits.
    """
    chunks = []
    while len(text) > max_chars:
        # find the last newline or space before the limit
        split_idx = text.rfind("\n", 0, max_chars)
        if split_idx == -1:
            split_idx = text.rfind(" ", 0, max_chars)
        if split_idx == -1:
            split_idx = max_chars  # fallback hard split
        chunks.append(text[:split_idx].strip())
        text = text[split_idx:].lstrip()
    if text.strip():
        chunks.append(text.strip())
    return chunks

# ------------------------------------------------------------
# 2. Streamlit page config
# ------------------------------------------------------------
st.set_page_config(page_title="PDF ➜ Relational CSVs", layout="wide")
st.title("📄 PDF Tables → Relational CSVs (GPT‑powered)")

# ------------------------------------------------------------
# 3. Sidebar – user inputs
# ------------------------------------------------------------

st.sidebar.header("Settings")

# (OpenAI key) --------------------------------------------------------------
api_key_input = st.sidebar.text_input(
    "OpenAI API Key",
    type="password",
    placeholder="sk-...",
    help="Enter your OpenAI key; it is used only for this session."
)
if api_key_input:
    openai.api_key = api_key_input.strip()
elif "OPENAI_API_KEY" in os.environ:
    openai.api_key = os.environ["OPENAI_API_KEY"]
else:
    openai.api_key = None

# (a) How many CSV tables to create
num_tables = st.sidebar.number_input(
    "Number of CSV tables to generate",
    min_value=1, max_value=5, value=1, step=1
)

# (b) Names for each table
table_names = []
for i in range(1, num_tables + 1):
    name = st.sidebar.text_input(f"Name for Table {i}", value=f"Table{i}")
    table_names.append(name.strip() or f"Table{i}")

# (c) Relationships description (optional)
relationships_desc = st.sidebar.text_area(
    "Describe relationships (PK/FK) between tables (optional)",
    placeholder="e.g., Table2.InvoiceID references Table1.ID"
)

# (d) Extra context / business rules
user_context = st.sidebar.text_area(
    "Extra context about the data (recommended)",
    placeholder=(
        "Describe what the PDF contains, meaning of fields, date formats, "
        "business rules, etc."
    ),
    height=150
)

# (e) Example CSVs for format guidance (optional – you may upload up to `num_tables`)
example_csv_files = st.sidebar.file_uploader(
    "Example CSVs (optional, one per target table – upload in table order)",
    type=["csv"],
    accept_multiple_files=True
)

# ------------------------------------------------------------
# 4. Main panel – PDF upload & processing
# ------------------------------------------------------------
uploaded_pdf = st.file_uploader("Upload PDF containing tables", type=["pdf"])

if uploaded_pdf is not None:
    # Verify API key is set
    if not openai.api_key:
        st.error("Please enter your OpenAI API key in the sidebar.")
        st.stop()
    # ---- 4A. Extract text from PDF ----
    try:
        doc = fitz.open(stream=uploaded_pdf.read(), filetype="pdf")
        # extract page texts
        pages_text = [page.get_text() for page in doc]
        doc.close()
        pdf_text_full = "\n".join(pages_text)
    except Exception as e:
        st.error(f"Failed to read PDF: {e}")
        st.stop()

    # Chunk the combined text
    chunks = chunk_text(pdf_text_full, max_chars=12000)
    st.success(f"PDF text extracted and split into {len(chunks)} chunk(s).")

    # ---- 4B. Auto‑generate suggested context & relationships -----------------
    if (
        "suggested_context" not in st.session_state
        or "suggested_relationships" not in st.session_state
        or st.session_state.get("context_source_name") != uploaded_pdf.name
    ):
        with st.spinner("Analyzing tables to generate context…"):
            try:
                # ----- first call: contextual summary as an instructional prompt
                ctx_resp = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "You write concise instructional prompts for downstream data‑extraction models."
                        },
                        {
                            "role": "user",
                            "content": (
                                "Based on the following extracted table data, write a short instructional prompt "
                                "that describes the overall context of the data so another model can use it:\n\n"
                                f"{chunks[0][:8000]}"
                            )
                        },
                    ],
                    temperature=0.3,
                )
                # ----- second call: infer table relationships
                rel_resp = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "You infer relational structure between tables."
                        },
                        {
                            "role": "user",
                            "content": (
                                "Using the same extracted table data, describe plausible relationships (e.g., primary/foreign "
                                "keys, hierarchical links) between tables that would help build a relational dataset:\n\n"
                                f"{chunks[0][:8000]}"
                            )
                        },
                    ],
                    temperature=0.3,
                )
                st.session_state["suggested_context"] = ctx_resp.choices[0].message.content.strip()
                st.session_state["suggested_relationships"] = rel_resp.choices[0].message.content.strip()
                st.session_state["context_source_name"] = uploaded_pdf.name
            except Exception as e:
                st.warning(f"Auto‑context generation failed: {e}")
                st.session_state["suggested_context"] = ""
                st.session_state["suggested_relationships"] = ""

    suggested_context = st.session_state.get("suggested_context", "")
    suggested_relationships = st.session_state.get("suggested_relationships", "")

    # ---- Editable expanders --------------------------------------------------
    with st.expander("🧠 Suggested Context (editable)", expanded=False):
        edited_context = st.text_area(
            "Context prompt for downstream model",
            value=suggested_context,
            height=150,
            key="edited_context"
        )

    with st.expander("🔗 Suggested Table Relationships (editable)", expanded=False):
        edited_relationships = st.text_area(
            "Relationships description",
            value=suggested_relationships,
            height=150,
            key="edited_relationships"
        )

    # ---- 4C. Parse example CSVs if provided ----
    example_snippets = []
    if example_csv_files:
        for file_idx, csv_file in enumerate(example_csv_files, start=1):
            try:
                df_ex = pd.read_csv(csv_file)
                headers = list(df_ex.columns)
                first_row = df_ex.iloc[0].tolist() if not df_ex.empty else []
                snippet = (
                    f"Example CSV for Table {file_idx} headers: {headers}\n"
                    f"Example CSV for Table {file_idx} first row: {first_row}\n"
                )
                example_snippets.append(snippet)
            except Exception as e:
                st.warning(f"Could not read example CSV {csv_file.name}: {e}")

    # ---- 4C. Build prompt ----
    schema_desc_lines = [
        f"Table {idx}: {name}" for idx, name in enumerate(table_names, start=1)
    ]
    prompt_parts = [
        f"Extract structured data from the PDF text into {num_tables} CSV tables.",
        "Table schema:",
        *schema_desc_lines
    ]
    if user_context:
        prompt_parts.append("User‑supplied context: " + user_context.strip())
    if edited_context:
        prompt_parts.append("System‑suggested context: " + edited_context.strip())
    if edited_relationships:
        prompt_parts.append("System‑suggested relationships: " + edited_relationships.strip())
    if example_snippets:
        prompt_parts.append("Example CSV formats:")
        prompt_parts.extend(s.strip() for s in example_snippets)
    prompt_parts.append("PDF text follows:\n" + pdf_text_full.strip())

    user_prompt = "\n\n".join(prompt_parts)

    # Show prompt preview (optional)
    with st.expander("Prompt preview"):
        st.write(user_prompt[:800] + ("…" if len(user_prompt) > 800 else ""))

    # ---- 4D. Call OpenAI ----
    if st.button("Generate CSV tables"):
        # we will collect raw CSV content from each chunk and concatenate per table
        accumulated_tables = {i: [] for i in range(1, num_tables + 1)}

        with st.spinner("Processing chunks with OpenAI…"):
            for chunk_idx, chunk_text_part in enumerate(chunks, start=1):
                # Build a chunk‑specific prompt (include header only in first chunk)
                chunk_prompt = (
                    user_prompt.replace("PDF text follows:", f"Chunk {chunk_idx}/{len(chunks)} PDF text:") +
                    "\n\n" + chunk_text_part
                )
                if chunk_idx > 1:
                    chunk_prompt += (
                        "\n\nIMPORTANT: For this chunk output rows ONLY (no header rows) "
                        "for each CSV section."
                    )
                try:
                    resp = openai.chat.completions.create(
                        model="o4-mini-2025-04-16",
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You convert unstructured text into multiple CSV tables. "
                                    "For each table output, start with 'CSV X:' (X = table number), "
                                    "then raw CSV data. Do not add explanations."
                                ),
                            },
                            {"role": "user", "content": chunk_prompt},
                        ],
                        temperature=1.0,
                    )
                    raw_output = resp.choices[0].message.content.strip()
                except Exception as e:
                    st.error(f"OpenAI error (chunk {chunk_idx}): {e}")
                    st.stop()

                # ---- Split output into CSV sections for this chunk ----
                sections = re.split(r"(?=CSV\s*\d+:)", raw_output)
                for sec in sections:
                    sec = sec.strip()
                    if not sec:
                        continue
                    m = re.match(r"CSV\s*(\d+):", sec)
                    if not m:
                        continue
                    idx = int(m.group(1))
                    if idx < 1 or idx > num_tables:
                        continue
                    csv_content = sec.split(":", 1)[1].lstrip()
                    accumulated_tables[idx].append(csv_content)

        # ------------------------------------------------------------
        # Helper: robust CSV reader to handle inconsistent row lengths
        # ------------------------------------------------------------
        import csv
        def robust_read_csv(csv_text: str) -> pd.DataFrame:
            """
            Attempt to read CSV text. If pandas raises a tokenization error due to
            inconsistent row lengths, fix rows to the modal column count.
            """
            try:
                return pd.read_csv(StringIO(csv_text))
            except Exception as err:
                # fallback: manual parsing
                lines = csv_text.splitlines()
                if not lines:
                    return pd.DataFrame()
                reader = csv.reader(lines)
                rows = list(reader)
                header = rows[0]
                col_cnt = len(header)

                # if some rows have different length, try to fix
                fixed_rows = []
                for r in rows[1:]:
                    if len(r) == col_cnt:
                        fixed_rows.append(r)
                    elif len(r) > col_cnt:
                        # merge extra columns into last field
                        merged_last = ",".join(r[col_cnt-1:])
                        fixed_rows.append(r[:col_cnt-1] + [merged_last])
                    else:  # len(r) < col_cnt
                        fixed_rows.append(r + [""] * (col_cnt - len(r)))
                try:
                    return pd.DataFrame(fixed_rows, columns=header)
                except Exception:
                    # give up and return empty df
                    st.warning(f"Could not fully repair CSV: {err}")
                    return pd.DataFrame()

        # ---- Combine accumulated CSV parts and parse into DataFrames ----
        csv_tables = {}
        for idx in range(1, num_tables + 1):
            combined_csv = "\n".join(accumulated_tables[idx]).strip()
            if not combined_csv:
                csv_tables[idx] = pd.DataFrame()
                continue
            df_read = robust_read_csv(combined_csv)
            csv_tables[idx] = df_read

        # ---- 4F. Display and download each table ----
        for i in range(1, num_tables + 1):
            df_show = csv_tables.get(i, pd.DataFrame())
            with st.expander(f"CSV {i}: {table_names[i-1]}", expanded=(i == 1)):
                st.dataframe(df_show, use_container_width=True)
                st.download_button(
                    label=f"Download {table_names[i-1]}.csv",
                    data=df_show.to_csv(index=False).encode("utf-8"),
                    file_name=f"{table_names[i-1]}.csv",
                    mime="text/csv",
                    key=f"csv_download_{i}"
                )
else:
    st.info("Upload a PDF file to begin.")