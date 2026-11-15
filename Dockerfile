FROM python:3.12-slim
WORKDIR /app
COPY nba_data_pipeline ./nba_data_pipeline
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 DATA_DIR=/tmp/data
EXPOSE 8000
CMD ["sh", "-c", "python -m nba_data_pipeline.cli serve-web --db ${DATA_DIR}/nba.sqlite --host 0.0.0.0 --port ${PORT:-8000} --auto-update-hours ${UPDATE_HOURS:-0} --bootstrap-from ${BOOTSTRAP_FROM:-2026-10-01}"]
