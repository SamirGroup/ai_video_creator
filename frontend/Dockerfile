# syntax=docker/dockerfile:1
#
# Multi-stage Dockerfile for the React + Vite frontend.
# Two runtime targets (mirrors backend/Dockerfile convention):
#   dev  -> used by ../docker-compose.yml (bind-mounted source, Vite dev server, HMR)
#   prod -> used by ../docker-compose.prod.yml (static build served by nginx)

########################################
# deps — install once, reused by dev/build
########################################
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

########################################
# dev — local development, hot reload via bind mount
########################################
FROM deps AS dev

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

########################################
# build — compiles the production bundle
########################################
FROM deps AS build

COPY . .
RUN npm run build

########################################
# prod — small, immutable, nginx serving the static bundle
########################################
FROM nginx:1.27-alpine AS prod

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
