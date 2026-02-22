FROM python:3.9-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libmagic1 \
    libheif1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY app ./app
COPY web/backend ./web/backend

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app/web/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "web/backend/manage.py", "runserver", "0.0.0.0:8000"]
