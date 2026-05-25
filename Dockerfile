# ===== BASE =====
FROM node:20 AS base
WORKDIR /app
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

COPY package*.json ./
RUN npm install

COPY . .
RUN npx prisma generate

# ===== API =====
FROM base AS production
EXPOSE 3000
CMD ["npm", "run", "start"]

# ===== WORKER =====
FROM base AS worker
CMD ["node", "workers/worker.js"]

# ===== RECONCILER =====
FROM base AS reconciler
CMD ["node", "workers/reconciler.js"]
