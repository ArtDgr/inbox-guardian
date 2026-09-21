FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# server needs fastapi uvicorn
RUN pip install --no-cache-dir fastapi uvicorn
COPY . .
# headless: run scheduler + API on $PORT (Azure Container Apps expects 8000)
ENV PORT=8000
EXPOSE 8000
CMD ["python", "-m", "email_agent.server"]
