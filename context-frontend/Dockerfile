# Production image: build the static site, serve it with nginx, and proxy
# /backend/* to the FastAPI container (same origin, so no CORS setup).

FROM node:22.20.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27.3-alpine
# Templates in /etc/nginx/templates are rendered with envsubst at start-up.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV BACKEND_URL=http://contextapi-app-api-1:8000
EXPOSE 80
