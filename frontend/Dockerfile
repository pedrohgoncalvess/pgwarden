# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS base

WORKDIR /app

FROM base AS dependencies

COPY package.json package-lock.json .npmrc ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

FROM dependencies AS builder

COPY . .
RUN npm run build

# Prune separately so the final image only contains runtime dependencies.
FROM dependencies AS production-dependencies

RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM base AS runtime

COPY --from=production-dependencies /app/package.json ./
COPY --from=production-dependencies /app/node_modules ./node_modules

COPY --from=builder /app/build ./build

ENV PORT=3000
ENV NODE_ENV=production

EXPOSE 3000

CMD ["node", "build/index.js"]
