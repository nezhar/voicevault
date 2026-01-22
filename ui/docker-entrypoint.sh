#!/bin/sh
set -e

# Default values
API_URL=${API_URL:-http://api:8000}
NGINX_RESOLVER=${NGINX_RESOLVER:-127.0.0.11}
NGINX_LISTEN=${NGINX_LISTEN:-80}

export API_URL
export NGINX_RESOLVER
export NGINX_LISTEN

# Substitute environment variables in nginx config template
# Only substitute specific variables, leaving nginx variables ($uri, $host, etc.) intact
envsubst '${API_URL} ${NGINX_RESOLVER} ${NGINX_LISTEN}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

echo "Nginx configured with:"
echo "  NGINX_LISTEN: ${NGINX_LISTEN}"
echo "  API_URL: ${API_URL}"
echo "  NGINX_RESOLVER: ${NGINX_RESOLVER}"

# Execute the main command (nginx)
exec "$@"
