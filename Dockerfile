FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8000
WORKDIR /app
RUN groupadd --gid 10001 meridian && useradd --uid 10001 --gid meridian --no-create-home meridian \
    && mkdir /app/data && chown meridian:meridian /app/data
COPY --chown=meridian:meridian server.py alpaca.py check_connection.py ./
COPY --chown=meridian:meridian static/ ./static/
USER meridian
EXPOSE 8000
CMD ["python3", "server.py"]
