.PHONY: run test format

run:
	streamlit run app/main.py

test:
	pytest -q

format:
	black . && ruff --fix .