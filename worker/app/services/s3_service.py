import boto3
import tempfile
import os
from typing import Optional, BinaryIO
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
from loguru import logger

from app.core.config import settings


class S3Service:
    def __init__(self):
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name='us-east-1'  # MinIO default region
            )
            self.bucket_name = settings.s3_bucket_name
            self._ensure_bucket_exists()
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created S3 bucket: {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket {self.bucket_name}: {str(create_error)}")
                    raise
            else:
                logger.error(f"Error accessing bucket {self.bucket_name}: {str(e)}")
                raise
    
    def upload_file_from_path(self, local_path: str, key: str, content_type: Optional[str] = None) -> bool:
        """Upload file from local path to S3"""
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.upload_file(local_path, self.bucket_name, key, ExtraArgs=extra_args)
            logger.info(f"Successfully uploaded file to S3: {local_path} -> {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload file {local_path} to S3: {str(e)}")
            return False
    
    def upload_file(self, file_obj: BinaryIO, key: str, content_type: Optional[str] = None) -> bool:
        """Upload file object to S3"""
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.upload_fileobj(file_obj, self.bucket_name, key, ExtraArgs=extra_args)
            logger.info(f"Successfully uploaded file to S3: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload file {key} to S3: {str(e)}")
            return False
    
    def download_file(self, key: str, local_path: str) -> bool:
        """Download file from S3 to local path"""
        try:
            self.s3_client.download_file(self.bucket_name, key, local_path)
            logger.info(f"Successfully downloaded file from S3: {key} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download file {key} from S3: {str(e)}")
            return False
    
    def get_file_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate presigned URL for file access"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {key}: {str(e)}")
            return None
    
    def delete_file(self, key: str) -> bool:
        """Delete file from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Successfully deleted file from S3: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {key} from S3: {str(e)}")
            return False
    
    def file_exists(self, key: str) -> bool:
        """Check if file exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"Error checking file existence {key}: {str(e)}")
                return False
    
    def get_file_info(self, key: str) -> Optional[dict]:
        """Get file metadata from S3"""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return {
                'size': response['ContentLength'],
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'last_modified': response['LastModified'],
                'etag': response['ETag']
            }
        except Exception as e:
            logger.error(f"Failed to get file info for {key}: {str(e)}")
            return None
    
    def create_temp_download(self, key: str) -> Optional[str]:
        """Download file to temporary location and return path"""
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            # Download from S3
            if self.download_file(key, temp_path):
                return temp_path
            else:
                # Clean up temp file if download failed
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return None
        except Exception as e:
            logger.error(f"Failed to create temp download for {key}: {str(e)}")
            return None
    
    def cleanup_temp_file(self, temp_path: str):
        """Clean up temporary file"""
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.debug(f"Cleaned up temp file: {temp_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup temp file {temp_path}: {str(e)}")
    
    def generate_s3_key(self, entry_id: str, filename: str) -> str:
        """Generate S3 key for file storage"""
        return f"files/{entry_id}/{filename}"