# Build context: `execution/` (the parent directory).
# Coolify: set "Base directory / build context" to `execution`, and
# "Dockerfile location" to `execution/field_rep/Dockerfile`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching
COPY field_rep/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY hub/        ./hub/
COPY field_rep/  ./field_rep/

EXPOSE 8000

CMD ["uvicorn", "field_rep.app:app", "--host", "0.0.0.0", "--port", "8000"]
