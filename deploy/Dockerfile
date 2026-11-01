FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    BASE_PATH=/price-generator HOST=0.0.0.0 PORT=8002 REQUIRE_AUTH=1
WORKDIR /srv
RUN useradd --create-home simulator
COPY server.py /srv/server.py
COPY price_generator /srv/price_generator
COPY web /srv/web
USER simulator
EXPOSE 8002
CMD ["python", "server.py"]
