# Base ultra ligera y estable
FROM python:3.11-slim-bullseye

# Directorio de trabajo en el contenedor
WORKDIR /app

# Optimización para que Python no guarde basura (.pyc) y lance logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalar dependencias del sistema operativo (necesarias para psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar primero solo los requerimientos para usar caché de Docker
COPY requirements.txt .

# Instalar librerías
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del búnker
COPY . .

# Exponer el puerto estándar de Google Cloud Run
EXPOSE 8080

# Comando de arranque militar: Gunicorn amarrado a app_elite.py
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "app_elite:app"]