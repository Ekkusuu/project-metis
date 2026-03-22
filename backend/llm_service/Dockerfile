FROM nvidia/cuda:12.6.3-devel-ubuntu22.04

WORKDIR /app/backend/llm_service

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git make g++ python3 cmake \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY backend/llm_service/package.json backend/llm_service/package-lock.json ./
RUN npm ci --omit=dev

ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

RUN npx --no node-llama-cpp source download --gpu cuda

COPY backend/llm_service/server.js ./server.js
COPY config.yaml /app/config.yaml

EXPOSE 3000

CMD ["npm", "start"]
