FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (separate layer so Docker caches them —
# the layer only rebuilds if requirements.txt changes, not on every code change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker source code
COPY . .

CMD ["python", "scheduler.py"]
