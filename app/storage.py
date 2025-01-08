import boto3
from os import getenv
from botocore.exceptions import ClientError
import logging
from uuid import uuid4
from typing import Optional, Dict, Any
import mimetypes

BUCKET_NAME = getenv("AWS_BUCKET_NAME")
AWS_REGION = getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = getenv("AWS_SECRET_ACCESS_KEY")

class Storage:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )

    def get_upload_details(self, filename: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate upload details including presigned URL and file metadata
        
        :param filename: Original filename from user
        :param content_type: Optional MIME type (if known)
        :return: Dictionary containing upload details and file metadata
        """
        # Generate a UUID for the S3 key
        s3_key = str(uuid4())
        
        # Determine content type
        if not content_type:
            content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        # Generate the presigned POST URL
        conditions = [
            {"bucket": BUCKET_NAME},
            ["starts-with", "$key", s3_key],
            ["starts-with", "$Content-Type", content_type.split('/')[0]],
            ["content-length-range", 1, 100 * 1024 * 1024]  # 100MB max
        ]
        
        try:
            response = self.s3_client.generate_presigned_post(
                BUCKET_NAME,
                s3_key,
                Fields={
                    'Content-Type': content_type,
                },
                Conditions=conditions,
                ExpiresIn=3600
            )
            
            return {
                "upload_data": response,
                "metadata": {
                    "s3_key": s3_key,
                    "mime_type": content_type,
                    "original_filename": filename
                }
            }
        except ClientError as e:
            logging.error(f"Error generating presigned URL: {e}")
            raise

    def create_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL to read an S3 object
        
        :param s3_key: The key of the object in S3
        :param expiration: Time in seconds for the presigned URL to remain valid
        :return: Presigned URL as string. If error, returns None.
        """
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return response
        except ClientError as e:
            logging.error(f"Error generating presigned URL: {e}")
            return None

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3
        
        :param s3_key: The key of the object in S3
        :return: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
            return True
        except ClientError as e:
            logging.error(f"Error deleting file: {e}")
            return False

