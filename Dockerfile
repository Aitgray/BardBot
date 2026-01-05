FROM pytorch/pytorch:2.2.2-cuda12.1-cudnn8-runtime

# Avoid Python 3.13 issues
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Python deps
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy your bot
COPY . .

CMD ["python", "local_bot.py"]
