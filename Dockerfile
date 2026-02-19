FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy dependency spec first for layer caching
COPY pyproject.toml .

# Install production dependencies only (no dev extras)
RUN uv pip install --system .

# Copy only what's needed at runtime
COPY main.py .
COPY src/ src/

CMD ["python", "main.py"]
