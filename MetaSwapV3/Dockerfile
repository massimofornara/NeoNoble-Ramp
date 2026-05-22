FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY package.json README.md ./
COPY src ./src
COPY docs ./docs
COPY public ./public
RUN mkdir -p /app/.data && chown -R node:node /app
EXPOSE 8080
USER node
CMD ["node", "src/server.js"]
