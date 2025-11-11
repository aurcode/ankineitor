# Stage 1: Build stage
FROM python:3.9-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies if any (e.g., for compiling packages)
# For now, we just need pip to be up-to-date
RUN pip install --upgrade pip

# Copy only the files necessary for installing dependencies
# This optimizes Docker's layer caching.
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final stage
FROM python:3.9-slim

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory
WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/

# Copy the application code
COPY app/ ./app/
COPY src/ ./src/

# Set ownership of the app directory
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Set the command to run the application
# The app is a streamlit app
CMD ["streamlit", "run", "app/app.py"]
