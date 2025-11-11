# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Define volumes for persistent data and media
# This allows you to mount local directories into the container
VOLUME /app/data
VOLUME /app/media
VOLUME /app/output

# Run main.py when the container launches
# This will be the main entry point for the deck generation process
CMD ["python", "main.py"]
