import asyncio
import signal
import sys
from loguru import logger

from app.core.config import settings
from app.services.worker_service import WorkerService
from app.services.database import engine
from app.models import entry  # Import models to register them

def setup_logging():
    """Configure logging"""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

async def main():
    """Main worker entry point"""
    
    setup_logging()
    
    # Create database tables on startup
    try:
        from app.services.database import Base
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created/verified")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        sys.exit(1)
    
    logger.info("Starting VoiceVault Worker")
    logger.info(f"Worker configuration:")
    logger.info(f"  - Mode: {settings.worker_mode.value.upper()}")
    logger.info(f"  - Interval: {settings.worker_interval}s")
    logger.info(f"  - Batch size: {settings.batch_size}")
    logger.info(f"  - Download dir: {settings.download_dir}")
    logger.info(f"  - Supported domains: {', '.join(settings.supported_url_domains)}")
    if settings.worker_mode.value == "asr":
        logger.info(f"  - Groq model: {settings.groq_model}")
        logger.info(f"  - Groq API key: {'***configured***' if settings.groq_api_key else 'NOT SET'}")
    
    worker = WorkerService()
    
    # Handle shutdown signals
    def signal_handler():
        logger.info("Received shutdown signal")
        worker.stop()
    
    # Register signal handlers
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda s, f: signal_handler())
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker crashed: {str(e)}")
        sys.exit(1)
    
    logger.info("Worker shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())