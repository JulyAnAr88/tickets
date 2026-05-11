  GNU nano 7.2                                                                                      /home/investigacion/tickets/dockerfile                                                                                                
RUN mkdir -p /etc/dokploy/applications/tickets-tickets-cmzutb/code/home/investigacion/

FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero (mejor cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la aplicación
COPY . .

# Exponer puerto
EXPOSE 5151

# Comando de inicio
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:5151"]
