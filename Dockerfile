FROM python:3.11-slim

WORKDIR /app

# Отключаем буферизацию вывода и генерацию .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Устанавливаем системные пакеты (таймзона)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Точка входа
CMD ["python", "main.py"]
