FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY README.md .

RUN mkdir -p downloads

CMD ["python", "bot.py"]