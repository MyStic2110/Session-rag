FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway standard is 8080 or based on $PORT)
EXPOSE 8080

# Run the Main Application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
