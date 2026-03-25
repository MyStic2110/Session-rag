FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render sets this dynamically)
EXPOSE 10000

# Run with Gunicorn for production or Uvicorn directly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
