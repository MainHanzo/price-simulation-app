FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    BASE_PATH=/price-generator STATIC_DIR=/srv/static \
    LOGIN_PAGE_PATH=/srv/deploy/login.html
WORKDIR /srv
COPY deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home simulator
COPY app /srv/app
COPY deploy/login.html /srv/deploy/login.html
COPY frontend/dist/frontend/browser /srv/static
USER simulator
EXPOSE 8002
CMD ["uvicorn", "app.hosted:application", "--host", "0.0.0.0", "--port", "8002", "--workers", "1", "--timeout-graceful-shutdown", "5"]
