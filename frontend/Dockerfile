FROM node:24-alpine AS build
WORKDIR /app
RUN npm install --global pnpm@11.24.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Railway exposes service variables as build arguments. This is a public URL.
ARG API_BASE_URL
RUN node tools/configure-production.mjs && pnpm build

FROM nginx:stable-alpine
ENV PORT=8080
ENV NGINX_ENVSUBST_FILTER=PORT
COPY deployment/railway.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
EXPOSE 8080
