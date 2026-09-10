FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN npm ci --omit=dev
COPY src ./src

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3010 \
    WHATSAPP_AUTH_PATH=/data/auth \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

RUN mkdir -p /data/auth && chown -R node:node /app /data
USER node
EXPOSE 3010
CMD ["npm", "start"]
