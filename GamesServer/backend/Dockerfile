FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser

WORKDIR /home/appuser/app

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000


CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
