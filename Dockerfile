# syntax=docker/dockerfile:1.6
# =============================================================================
# Chaeshin — chaeshin-monitor (Next.js 15 + standalone)
# Case/Tool Registry 대시보드 + REST API
# /api/chaeshin/*, /api/tools/* 엔드포인트 제공
# =============================================================================

# ── Dependencies ──
FROM node:22-alpine AS deps
WORKDIR /app

COPY chaeshin-monitor/package.json chaeshin-monitor/package-lock.json* ./

RUN --mount=type=cache,target=/root/.npm \
    npm ci || npm install

# ── Build ──
FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY chaeshin-monitor/ ./

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Production ──
FROM node:22-alpine AS runner
WORKDIR /app

ARG UID=1001
ARG GID=1001

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid ${GID} nodejs && \
    adduser --system --uid ${UID} nextjs

COPY --from=builder --chown=${UID}:${GID} /app/public ./public
COPY --from=builder --chown=${UID}:${GID} /app/.next/standalone ./
COPY --from=builder --chown=${UID}:${GID} /app/.next/static ./.next/static

# 케이스 데이터 저장 디렉토리 (PVC 마운트 포인트)
RUN mkdir -p /app/data && chown ${UID}:${GID} /app/data

USER ${UID}:${GID}

EXPOSE 3060
ENV PORT=3060
ENV HOSTNAME="0.0.0.0"
ENV CHAESHIN_DATA_DIR=/app/data

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3060/api/chaeshin/stats || exit 1

CMD ["node", "server.js"]
