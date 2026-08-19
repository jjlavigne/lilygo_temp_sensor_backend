FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates ./templates
ENV PYTHONUNBUFFERED=1
# ensure_schema runs once at boot, then gunicorn serves.
CMD ["sh", "-c", "python -c 'import app; app.ensure_schema()' && gunicorn -b 0.0.0.0:8080 -w 2 --access-logfile - app:app"]
