# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a PDF table extraction and transformation application that converts structured PDF documents into relational CSV tables using Google's Gemini AI. The application is built with Streamlit for the web interface and uses PyMuPDF for PDF processing.

## Common Development Commands

- **Run the application**: `streamlit run app/main.py` or `make run`
- **Run tests**: `pytest -q` or `make test`
- **Format and lint code**: `black . && ruff --fix .` or `make format`
- **Type checking**: `mypy .` (ensure mypy is installed)

## Architecture Overview

The application follows a modular service-oriented architecture:

### Core Components

1. **app/main.py** - Streamlit web interface handling user interactions, file uploads, and workflow orchestration
2. **services/extractor.py** - PDF table extraction using PyMuPDF with multiple detection strategies (auto, lattice, matrix)
3. **services/api.py** - Google Gemini API integration for JSON generation and CSV transformation
4. **services/transformer.py** - Data transformation utilities for merging JSON fragments and parsing CSV responses
5. **prompts/schema.py** - Pydantic models and JSON schema definitions for structured output validation
6. **utils/chunk.py** - Text chunking utilities for handling large PDF content
7. **utils/io.py** - Robust CSV parsing with error handling and repair mechanisms

### Data Flow

1. PDF upload → Table extraction (PyMuPDF) → Text chunks
2. Text chunks → Gemini API → Structured JSON (validated against schema)
3. JSON → Gemini API → Multiple relational CSV tables
4. CSV parsing → Pandas DataFrames → User download

### Key Features

- **Multi-strategy table detection**: Auto, lattice (line-based), and matrix (text-based) extraction modes
- **Few-shot learning**: Optional example PDFs and target outputs for better AI performance
- **Context generation**: Automatic analysis of PDF content to generate processing context
- **Chunked processing**: Handles large PDFs by processing in chunks and merging results
- **Robust error handling**: Comprehensive error handling for API calls and CSV parsing
- **Schema validation**: Pydantic models ensure consistent JSON structure

## Development Notes

### API Integration
- Uses Google Gemini 2.5 Pro model (`gemini-2.5-pro-preview-06-05`)
- API key can be provided via environment variable `GOOGLE_API_KEY` or Streamlit input
- All API calls include proper error handling with user-friendly messages

### PDF Processing
- Supports multiple table detection strategies through PyMuPDF
- Falls back to raw text extraction if no tables detected
- Handles multi-page PDFs by processing each page separately

### Data Validation
- JSON output is validated against a strict schema defined in `prompts/schema.py`
- CSV parsing includes fallback mechanisms for malformed content
- Entity-relationship model with hierarchical support

### Testing Structure
- Tests located in `tests/` directory
- Covers API integration, extraction, schema validation, and transformation logic
- Run with `pytest -q` for quick execution

## Dependencies

Key dependencies include:
- `streamlit` - Web interface framework
- `pymupdf` - PDF processing and table extraction
- `google-generativeai` - Google Gemini API client
- `pydantic` - Data validation and schema enforcement
- `pandas` - Data manipulation and CSV handling
- `pytest`, `black`, `ruff`, `mypy` - Development and testing tools