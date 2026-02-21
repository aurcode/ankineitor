# Stage 1: Build stage
FROM python:3.9-bullseye AS builder

# Set working directory
WORKDIR /app

# System deps needed to build Python packages like pi-heif
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif-dev \
    pkg-config \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install build dependencies if any (e.g., for compiling packages)
# For now, we just need pip to be up-to-date
RUN pip install --upgrade pip

# Copy only the files necessary for installing dependencies
# This optimizes Docker's layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final stage
FROM python:3.9-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libmagic1 \
    libheif1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    gosu \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory
WORKDIR /app
ENV HOME=/app

# Copy installed packages and executables from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy the application code
COPY app/ ./app/
COPY src/ ./src/
COPY pyproject.toml ./

# Install the local package
RUN pip install .

# Create a temporary directory for unstructured and set TMPDIR
RUN mkdir /app/tmp
ENV TMPDIR=/app/tmp

# Set ownership of the app directory
RUN chown -R appuser:appuser /app

# Copy the entrypoint script and make it executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Set the command to run the application
# The app is a streamlit app
CMD ["streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
