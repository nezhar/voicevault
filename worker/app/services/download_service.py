import os
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import yt_dlp
from loguru import logger

from app.core.config import settings
from app.services.s3_service import S3Service

class DownloadService:
    def __init__(self):
        self.download_dir = Path(settings.download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.s3_service = S3Service()
    
    def _is_supported_url(self, url: str) -> bool:
        """Check if URL is from supported domains"""
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            return any(supported in domain for supported in settings.supported_url_domains)
            
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {str(e)}")
            return False
    
    def _get_ydl_opts(self, entry_id: str) -> dict:
        """Get yt-dlp options for download"""
        
        opts = {
            'format': 'bestaudio/best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best',
            'outtmpl': str(self.download_dir / f'{entry_id}.%(ext)s'),
            'max_filesize': settings.max_file_size,
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,  # Keep original format, will convert to MP3 later
            'writeinfojson': False,
            'writesubtitles': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip,deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Connection': 'keep-alive',
            },
            'socket_timeout': 30,
            'retries': 3,
            # Anti-bot measures
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'sleep_interval_requests': 1,
        }
        
        # Add cookie support if available
        cookie_file = Path('/app/cookies.txt')
        if cookie_file.exists():
            opts['cookiefile'] = str(cookie_file)
            logger.info(f"Using cookie file for entry {entry_id}")
        
        return opts
    
    async def download_from_url(self, url: str, entry_id: str) -> Tuple[bool, Optional[Tuple[str, str]], Optional[str]]:
        """
        Download video/audio from URL and upload to S3
        
        Returns:
            Tuple[success, (s3_key, filename), error_message]
        """
        
        if not self._is_supported_url(url):
            error_msg = f"Unsupported URL domain. Supported: {', '.join(settings.supported_url_domains)}"
            logger.warning(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        ydl_opts = self._get_ydl_opts(entry_id)
        
        try:
            # Run yt-dlp in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._download_sync, 
                url, 
                ydl_opts,
                entry_id
            )
            
            success, local_file_info, error_msg = result
            
            if success and local_file_info:
                local_file_path, filename = local_file_info
                
                # Upload to S3
                s3_key = self.s3_service.generate_s3_key(entry_id, filename)
                upload_success = self.s3_service.upload_file_from_path(local_file_path, s3_key)
                
                # Clean up local file
                try:
                    os.unlink(local_file_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup local file {local_file_path}: {str(e)}")
                
                if upload_success:
                    logger.info(f"Entry {entry_id}: Successfully downloaded and uploaded to S3: {s3_key}")
                    return True, (s3_key, filename), None
                else:
                    return False, None, "Failed to upload file to S3"
            else:
                logger.error(f"Entry {entry_id}: Download failed - {error_msg}")
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Unexpected download error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
    
    def _download_sync(self, url: str, ydl_opts: dict, entry_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Synchronous download function to run in executor"""
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get filename
                info = ydl.extract_info(url, download=False)
                
                # Check file size if available
                if 'filesize' in info and info['filesize']:
                    if info['filesize'] > settings.max_file_size:
                        return False, None, f"File too large: {info['filesize']} bytes (max: {settings.max_file_size} bytes)"
                
                # Download the file
                ydl.download([url])
                
                # Find the downloaded file - use the entry_id passed as parameter
                downloaded_files = list(self.download_dir.glob(f'{entry_id}.*'))
                
                if downloaded_files:
                    downloaded_file = downloaded_files[0]
                    file_path = str(downloaded_file)
                    
                    # Extract original filename from video info
                    original_filename = info.get('title', f'video_{entry_id}')
                    # Sanitize filename for filesystem
                    safe_filename = "".join(c for c in original_filename if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_filename = safe_filename[:100]  # Limit length
                    
                    # Get file extension from downloaded file
                    file_extension = downloaded_file.suffix
                    full_filename = f"{safe_filename}{file_extension}"
                    
                    # Create symbolic link with original filename
                    link_path = self.download_dir / full_filename
                    
                    # Remove existing link if it exists
                    if link_path.exists() or link_path.is_symlink():
                        link_path.unlink()
                    
                    try:
                        # Create symbolic link
                        link_path.symlink_to(downloaded_file.name)
                        logger.info(f"Created link: {link_path} -> {downloaded_file.name}")
                    except Exception as e:
                        logger.warning(f"Failed to create symbolic link: {str(e)}")
                    
                    return True, (file_path, full_filename), None
                else:
                    return False, None, "Downloaded file not found"
                    
        except yt_dlp.DownloadError as e:
            error_msg = f"yt-dlp error: {str(e)}"
            
            # Check if it's a YouTube authentication error
            if "Sign in to confirm you're not a bot" in str(e):
                logger.warning(f"YouTube requires authentication for entry {entry_id}. Consider adding cookies.txt file.")
                error_msg += " (Tip: Add cookies.txt file to /app/cookies.txt for authenticated downloads)"
            
            return False, None, error_msg
        except Exception as e:
            return False, None, f"Download error: {str(e)}"
    
    def cleanup_failed_download(self, entry_id: str):
        """Clean up any partial downloads for failed entries"""
        
        try:
            pattern = f'{entry_id}.*'
            for file_path in self.download_dir.glob(pattern):
                file_path.unlink()
                logger.info(f"Cleaned up partial download: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up files for entry {entry_id}: {str(e)}")
    
    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if an error is permanent and should not be retried"""
        
        permanent_error_patterns = [
            "Unsupported URL domain",
            "Private video",
            "Video unavailable",
            "This video is not available",
            "Invalid URL",
            "File too large",
            "Unsupported file format",
            "Sign in to confirm you're not a bot"  # YouTube auth error
        ]
        
        return any(pattern.lower() in error_message.lower() for pattern in permanent_error_patterns)
    
    def is_youtube_auth_error(self, error_message: str) -> bool:
        """Check if error is related to YouTube authentication"""
        
        auth_error_patterns = [
            "Sign in to confirm you're not a bot",
            "Use --cookies-from-browser",
            "--cookies for the authentication",
            "This video is private",
            "Video unavailable"
        ]
        
        return any(pattern.lower() in error_message.lower() for pattern in auth_error_patterns)
    
    def get_file_info(self, file_path: str) -> dict:
        """Get basic file information"""
        
        try:
            path = Path(file_path)
            if not path.exists():
                return {}
            
            stat = path.stat()
            return {
                'size': stat.st_size,
                'extension': path.suffix,
                'name': path.name,
                'exists': True
            }
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            return {'exists': False}
