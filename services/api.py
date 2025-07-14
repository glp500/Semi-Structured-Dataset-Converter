"""
Wrapper functions for Google Generative AI API calls and error handling.
"""
import streamlit as st
import google.generativeai as genai

# Use Gemini model name for all requests
_MODEL_NAME = "gemini-2.5-pro-preview-06-05"

__all__ = ["handle_api_error", "configure_api", "generate_structured_json", "generate_csv_from_json"]

def handle_api_error(e: Exception, step_name: str = "API call") -> None:
    """
    Handle exceptions from API calls by displaying user-friendly error messages and suggestions.
    
    :param e: The exception raised during the API call.
    :param step_name: A descriptive name of the step in which the error occurred.
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

def configure_api(api_key: str) -> bool:
    """
    Configure the Google Generative AI client with the provided API key.
    
    :param api_key: Google AI API key.
    :return: True if configuration succeeded, False if it failed.
    """
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.sidebar.error(f"Failed to configure Google AI API: {e}")
        return False

def generate_structured_json(
    pages_text: list[str],
    context_text: str,
    relationships_text: str,
    additional_context_text: str,
    manual_context_text: str,
    examples: list[tuple[str, str]] = None
) -> str:
    """
    Send the PDF text (possibly chunked) to the LLM to generate a structured JSON string following the schema.
    
    Optionally includes few-shot examples in the prompt, and ensures the output JSON conforms to the schema.
    
    :param pages_text: List of page text strings extracted from the PDF.
    :param context_text: Context prompt text (user-edited or auto-generated).
    :param relationships_text: Relationships description text.
    :param additional_context_text: Additional context text.
    :param manual_context_text: Manual context input from user.
    :param examples: Optional list of (example_pdf_text, example_json_text) pairs for few-shot prompting.
    :return: The JSON output as a string.
    """
    full_text = "\n".join(pages_text)
    from utils.chunk import chunk_text
    text_chunks = chunk_text(full_text)
    all_responses: list[str] = []
    from prompts.schema import SCHEMA_JSON
    example_prompt = ""
    if examples:
        for i, (ex_pdf, ex_json) in enumerate(examples, start=1):
            example_prompt += (
                f"--- START OF EXAMPLE {i} ---\n"
                f"**EXAMPLE INPUT (TEXT FROM A PDF PAGE):**\n```text\n{ex_pdf}\n```\n"
                f"**EXAMPLE OUTPUT (THE DESIRED JSON):**\n{ex_json}\n"
                f"--- END OF EXAMPLE {i} ---\n"
            )
        example_prompt += "Now, apply the same logic and structure from these example(s) to the real input below.\n"
    for idx, chunk in enumerate(text_chunks, start=1):
        st.info(f"Processing chunk {idx}/{len(text_chunks)}...")
        prompt = (
            f"{example_prompt}"
            "You are a data extraction expert. Convert the following text extracted from a PDF into a single, well-structured JSON object.\n"
            "The JSON output must strictly follow the given schema:\n"
            f"```json\n{SCHEMA_JSON}\n```\n"
            "All required fields must be present. If a required field is missing or null, double-check the input and do not omit the field.\n"
            "Optional fields can be omitted if no data, but include a \"missing\": true flag within the field object to indicate it is missing.\n"
            f"CONTEXT:\n{context_text}\n\nRELATIONSHIPS:\n{relationships_text}\n\nADDITIONAL CONTEXT:\n{additional_context_text}\n\nMANUAL CONTEXT:\n{manual_context_text}\n"
            "Ensure the JSON is valid and accurately captures all tables and hierarchical relationships.\n"
            f"PDF TEXT CHUNK:\n```text\n{chunk}\n```"
        )
        try:
            model = genai.GenerativeModel(model_name=_MODEL_NAME)
            config = genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.1)
            response = model.generate_content(prompt, generation_config=config)
            all_responses.append(response.text)
        except Exception as e:
            handle_api_error(e, f"JSON generation on chunk {idx}")
    if not all_responses:
        st.error("No JSON was generated from the PDF text.")
        st.stop()
    from services.transformer import merge_json_fragments
    final_json = merge_json_fragments(all_responses)
    return final_json

def generate_csv_from_json(
    json_text: str,
    table_names: list[str],
    context_text: str,
    relationships_text: str,
    additional_context_text: str,
    manual_context_text: str,
    example_snippets: list[str] = None
) -> str:
    """
    Use the LLM to convert the structured JSON into relational CSV tables.
    
    Instructs the model to produce CSV outputs for each table, delineated by markers for parsing.
    
    :param json_text: The JSON data as a string.
    :param table_names: List of expected table names.
    :param context_text: Context prompt text.
    :param relationships_text: Relationships description text.
    :param additional_context_text: Additional context text.
    :param manual_context_text: Manual context from user input.
    :param example_snippets: Optional list of example CSV snippet strings.
    :return: A single string containing all tables in the specified output format.
    """
    csv_examples_section = ""
    if example_snippets and len(example_snippets) > 0:
        csv_examples_section = "CSV EXAMPLES:\n" + "\n".join(example_snippets)
    else:
        csv_examples_section = "No CSV examples provided."
    prompt = (
        "You are a data transformation expert. Your task is to convert the provided JSON data into multiple, distinct, relational CSV tables as specified.\n"
        f"You must generate exactly {len(table_names)} CSV table(s).\n"
        f"The required table names are: {', '.join(table_names)}.\n"
        "Use the provided context, relationships, and CSV examples to determine the correct columns and data for each table.\n"
        f"CONTEXT:\n{context_text}\n\nRELATIONSHIPS:\n{relationships_text}\n\nADDITIONAL CONTEXT:\n{additional_context_text}\n\nMANUAL CONTEXT:\n{manual_context_text}\n"
        f"{csv_examples_section}\n"
        "Follow these output instructions precisely:\n"
        "1. For each table, start with a header line: `=== START OF TABLE: [TableName] ===`\n"
        "2. Then, provide the CSV data for that table, with a header row and comma-separated values.\n"
        "3. End each table's data with a footer line: `=== END OF TABLE: [TableName] ===`\n"
        "4. Ensure the data is properly normalized across the tables as per the relational schema description.\n"
        f"JSON DATA TO TRANSFORM:\n```json\n{json_text}\n```"
    )
    try:
        model = genai.GenerativeModel(model_name=_MODEL_NAME)
        config = genai.types.GenerationConfig(temperature=0.0)
        response = model.generate_content(prompt, generation_config=config)
        return response.text
    except Exception as e:
        handle_api_error(e, "CSV generation from JSON")
        return ""