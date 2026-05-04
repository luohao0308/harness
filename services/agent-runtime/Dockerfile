FROM python:3.11-slim

RUN useradd --create-home --uid 10001 non-root

WORKDIR /workspace

USER non-root

CMD ["sleep", "infinity"]
