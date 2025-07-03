# Usa una imagen oficial de Python como base
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia solo requirements primero para aprovechar la cache
COPY requirements.txt .

# Instala dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del proyecto
COPY . .

# Expone el puerto (opcional, Fly lo detecta automáticamente)
EXPOSE 8000

# Comando de inicio con uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]