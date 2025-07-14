# PDF Relational CSVs App

This application extracts tables from PDF files and converts them into a structured JSON and multiple relational CSV tables using Google's Generative AI (Gemini).

## Setup

1. Ensure you have Python 3.10+ installed.
2. Install dependencies:  
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

### Using the Makefile (Recommended)

The project includes a Makefile for common development tasks:

```bash
# Run the Streamlit application
make run

# Run tests
make test

# Format and lint code
make format
```

### Manual Commands

If you prefer to run commands directly:

```bash
# Run the application
streamlit run app/main.py

# Run tests
pytest -q

# Format and lint code
black . && ruff --fix .
```