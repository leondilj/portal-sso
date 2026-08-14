FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r portal && useradd -r -g portal portal

COPY pyproject.toml ./
COPY app ./app
COPY templates ./templates
COPY static ./static

RUN pip install --no-cache-dir .

USER portal
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
