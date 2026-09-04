FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates ./templates
ENV PYTHONUNBUFFERED=1
# ensure_schema runs once at boot, then gunicorn serves.
#
# gthread, not the default sync worker. A sync worker handles exactly one
# connection at a time and blocks in recv() until that connection sends a
# request -- so a browser preconnect socket, which opens early and may never
# send anything, occupies a whole worker until the 30s timeout kills it. With
# only two workers a browser could tie up both, and the next click returned an
# error page; retrying worked because replacement workers had booted by then.
# gthread parks idle connections in a poller instead, so they cost a socket
# rather than a worker.
#
# --timeout 60 then only applies to genuinely stuck request handling, since
# waiting for a client no longer blocks the worker's heartbeat.
CMD ["sh", "-c", "python -c 'import app; app.ensure_schema()' &&      gunicorn -b 0.0.0.0:8080        --worker-class gthread --workers 2 --threads 8        --timeout 60 --graceful-timeout 30 --keep-alive 5        --access-logfile - --error-logfile - app:app"]
