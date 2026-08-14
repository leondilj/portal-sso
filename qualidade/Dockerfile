FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r qualidade && useradd -r -g qualidade qualidade

COPY pyproject.toml ./
COPY app ./app
COPY templates ./templates
COPY static ./static

RUN pip install --no-cache-dir .

USER qualidade
EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
