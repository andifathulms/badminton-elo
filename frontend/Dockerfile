# Build the Vite SPA, then serve it via nginx (which also proxies /api -> web).
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# /api is same-origin (nginx proxies it), so no CORS and no API base needed.
ENV VITE_API_BASE=/api
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
