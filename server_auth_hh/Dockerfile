# Use official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (and their dependencies)
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8001

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
