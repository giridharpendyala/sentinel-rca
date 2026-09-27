FROM python:3.12-slim

WORKDIR /app

COPY services/incident_controller/requirements.txt .
COPY libs/telemetry /telemetry
RUN pip install --no-cache-dir -r requirements.txt /telemetry

COPY services/incident_controller/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
