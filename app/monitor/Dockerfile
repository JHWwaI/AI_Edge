FROM python:3.11.10-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY monitor.py .
CMD ["python", "-u", "monitor.py"]
