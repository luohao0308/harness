FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ARG VITE_DEV_BEARER_TOKEN=dev-engineer-token
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_DEV_BEARER_TOKEN=$VITE_DEV_BEARER_TOKEN

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
