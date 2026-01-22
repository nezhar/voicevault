# Build stage
FROM node:18-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy nginx config template (will be processed at runtime)
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy built app
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Environment variables with defaults
ENV API_URL=http://api:8000
ENV NGINX_RESOLVER=127.0.0.11
ENV NGINX_LISTEN=80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]