FROM python:latest

WORKDIR /app/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8501

COPY . .

CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]