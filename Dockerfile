FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Explicitly do NOT set CMD here to allow Railway / Render / PaaS 
# to inject their own start commands for different services.
