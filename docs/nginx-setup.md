# Nginx SSL Proxy Setup for VoiceVault

This guide shows how to set up nginx as an HTTPS-only reverse proxy for VoiceVault containers with Let's Encrypt SSL.

## Prerequisites

- VoiceVault containers running on 127.0.0.1:3000 (UI) and 127.0.0.1:8000 (API)
- Nginx installed on your server
- Certbot installed (`sudo apt install certbot python3-certbot-nginx`)
- Domain name pointing to your server
- Port 80 and 443 open in firewall

## Quick Setup

### 1. Copy and Configure Nginx Config

```bash
# Copy the config file
sudo cp docs/nginx-proxy.conf /etc/nginx/sites-available/voicevault

# Edit the config and replace YOUR_DOMAIN.COM with your actual domain
sudo nano /etc/nginx/sites-available/voicevault
```

### 2. Enable the Site

```bash
# Create symlink to enable the site
sudo ln -s /etc/nginx/sites-available/voicevault /etc/nginx/sites-enabled/

# Remove default nginx site (optional)
sudo rm /etc/nginx/sites-enabled/default
```

### 3. Setup SSL Certificate

```bash
# Install certbot if not already installed
sudo apt update
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Test nginx configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Configuration

The nginx config uses **single domain with path-based routing**:
- Frontend: `https://yourdomain.com`
- API: `https://yourdomain.com/api/`

## DNS Setup

Ensure your DNS has these records:

```
A     yourdomain.com      -> YOUR_SERVER_IP
A     www.yourdomain.com  -> YOUR_SERVER_IP
```

## SSL Certificate Renewal

Let's Encrypt certificates auto-renew. To test renewal:

```bash
# Test renewal
sudo certbot renew --dry-run

# Check renewal service
sudo systemctl status certbot.timer
```

## Frontend API Configuration

The frontend is already configured to use `/api` paths - no changes needed! The nginx config routes:
- `yourdomain.com/api/*` → API container (127.0.0.1:8000)
- `yourdomain.com/*` → Frontend container (127.0.0.1:3000)

## Troubleshooting

### Check nginx status
```bash
sudo systemctl status nginx
```

### View nginx logs
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Verify containers are running
```bash
docker compose -f compose.registry.yml ps
curl http://127.0.0.1:3000  # Should return HTML
curl http://127.0.0.1:8000/health  # Should return {"status": "healthy"}
```

### Test HTTPS proxy
```bash
# Test frontend
curl https://yourdomain.com/

# Test API
curl https://yourdomain.com/api/health

# Test HTTP redirect
curl -I http://yourdomain.com/
```

## Security Features

- **HTTPS-only**: All HTTP traffic redirected to HTTPS
- **HSTS enabled**: Strict-Transport-Security header
- **Security headers**: XSS protection, content security, etc.
- **File upload limit**: 500MB for large audio/video files
- **Extended timeouts**: For file processing
- **Let's Encrypt**: Free, automated SSL certificates

## Additional Security (Recommended)

```bash
# Install fail2ban for intrusion prevention
sudo apt install fail2ban

# Configure firewall (if using ufw)
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP (Let's Encrypt)
sudo ufw allow 443   # HTTPS
sudo ufw enable
```