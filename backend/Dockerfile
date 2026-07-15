FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.docker.txt .

RUN python -m pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 && \
    pip install -r requirements.docker.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
