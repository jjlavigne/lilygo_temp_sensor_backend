FROM python:3.12-slim

WORKDIR /app

# Dependencies first so code edits don't invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion.py .

# Unbuffered, or "docker logs" appears frozen while Python holds output.
ENV PYTHONUNBUFFERED=1

CMD ["python", "ingestion.py"]
