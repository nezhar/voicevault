# YouTube Authentication Setup

YouTube has implemented anti-bot measures that require authentication for many videos. This guide explains how to configure VoiceVault to handle YouTube downloads that require authentication.

## The Problem

You may see errors like:
```
ERROR: [youtube] u8Kt7fRa2Wc: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication.
```

This happens because:
- YouTube requires sign-in verification for many videos
- Age-restricted content requires authentication
- Some videos are geo-restricted or have other access controls

## Solutions

### Option 1: Use Alternative Video Sources (Recommended)
Instead of problematic YouTube videos, try:
- **Vimeo**: Generally more permissive for automated downloads
- **SoundCloud**: Good for audio content
- **Direct file uploads**: Upload audio/video files directly

### Option 2: Extract and Export YouTube Cookies

If you need to download from YouTube, you can export browser cookies:

#### Method A: Using Browser Extension
1. Install a cookie export extension like "Get cookies.txt LOCALLY"
2. Visit YouTube and log in to your account
3. Export cookies as `cookies.txt` format
4. Place the file in your VoiceVault deployment

#### Method B: Using yt-dlp Cookie Extraction
```bash
# Extract cookies from Chrome
yt-dlp --cookies-from-browser chrome --print-traffic

# Extract cookies from Firefox
yt-dlp --cookies-from-browser firefox --print-traffic
```

#### Method C: Manual Cookie Setup
1. Log in to YouTube in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage > Cookies > youtube.com
4. Export relevant cookies to a `cookies.txt` file

### Option 3: Configure VoiceVault with Cookies

#### For Docker Deployment:
1. **Create cookies.txt file** with your YouTube session cookies
2. **Mount the file** in your Docker container:

```yaml
# In your compose file
services:
  worker-download:
    volumes:
      - ./cookies.txt:/app/cookies.txt:ro
```

3. **Restart the worker**:
```bash
docker compose restart worker-download
```

#### For Production Deployment:
1. **Upload cookies.txt** to your server
2. **Copy to container**:
```bash
docker cp cookies.txt voicevault-worker-download-1:/app/cookies.txt
docker restart voicevault-worker-download-1
```

## Security Considerations

⚠️ **Important Security Notes:**
- **Never commit cookies.txt to version control**
- **Cookies contain authentication tokens** - treat them like passwords
- **Cookies expire** - you'll need to refresh them periodically
- **Use a dedicated YouTube account** for automation if possible

## Alternative Approaches

### 1. Content Curation
- **Pre-screen URLs** before allowing user submissions
- **Maintain a whitelist** of known-working video sources
- **Use content that doesn't require authentication**

### 2. Fallback Strategy
- **Try download without auth first**
- **Gracefully handle auth errors** with user-friendly messages
- **Suggest alternative video sources**

### 3. User Education
Inform users about video restrictions:
- Age-restricted content may not work
- Some YouTube videos require authentication
- Encourage use of Vimeo, direct uploads, or other sources

## Testing

Test your cookie setup:
```bash
# Test with a problematic YouTube URL
docker exec voicevault-worker-download-1 yt-dlp --cookies /app/cookies.txt "https://youtube.com/watch?v=VIDEO_ID"
```

## Troubleshooting

### Cookies Not Working
- **Check file permissions**: Ensure the container can read cookies.txt
- **Verify cookie format**: Must be in Netscape/Mozilla format
- **Check expiration**: Cookies may have expired
- **Test browser access**: Ensure you can access the video in your browser

### Still Getting Auth Errors
- **Try different cookie extraction method**
- **Use a different browser** for cookie extraction
- **Clear browser cache** and re-authenticate
- **Consider using a VPN** if geo-restricted

### Container Issues
```bash
# Check if cookies file exists in container
docker exec voicevault-worker-download-1 ls -la /app/cookies.txt

# Check container logs
docker logs voicevault-worker-download-1

# Restart worker
docker restart voicevault-worker-download-1
```

## Best Practices

1. **Use dedicated account**: Create a YouTube account specifically for automation
2. **Regular cookie refresh**: Set up automated cookie renewal
3. **Monitor errors**: Track authentication failures in logs
4. **Fallback gracefully**: Always provide alternative options to users
5. **Document limitations**: Be clear about what content works vs. doesn't

## User-Facing Error Messages

VoiceVault now provides user-friendly error messages for YouTube authentication issues:

> "YouTube requires authentication. This video may be age-restricted or require sign-in. Please try a different video or contact administrator to configure authentication."

This helps users understand the limitation without exposing technical details.