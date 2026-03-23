FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/Ekkusuu/project-metis" \
      org.opencontainers.image.description="Project Metis backend" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --index-url ${TORCH_INDEX_URL} torch torchvision torchaudio \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY config.yaml ./config.yaml
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
