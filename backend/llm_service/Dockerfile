FROM node:20-bookworm-slim

WORKDIR /app/backend/llm_service

LABEL org.opencontainers.image.source="https://github.com/Ekkusuu/project-metis" \
      org.opencontainers.image.description="Project Metis LLM service" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends git make g++ python3 cmake \
    && rm -rf /var/lib/apt/lists/*

COPY backend/llm_service/package.json backend/llm_service/package-lock.json ./
RUN npm ci --omit=dev

RUN npx --no node-llama-cpp source download

COPY backend/llm_service/server.js ./server.js
COPY config.yaml /app/config.yaml

EXPOSE 3000

CMD ["npm", "start"]
