FROM python:3.12-slim

WORKDIR /app

COPY services/checkout_service/requirements.txt .
COPY libs/telemetry /telemetry
RUN pip install --no-cache-dir -r requirements.txt /telemetry

COPY services/checkout_service/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
