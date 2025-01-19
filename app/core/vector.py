from datetime import datetime
from uuid import UUID

from openai import OpenAI
from openai.types.create_embedding_response import CreateEmbeddingResponse

from app.core.config import get_settings

client = OpenAI(api_key=get_settings().OPENAI_API_KEY)


def vectorize(text: str) -> list[float]:
    response: CreateEmbeddingResponse = client.embeddings.create(
        input=[text], model="text-embedding-3-large", dimensions=1536
    )
    return response.data[0].embedding


def vectorize_message_prompt(
    user_id: UUID,
    display_name: str,
    username: str,
    email: str,
    created_at: datetime,
    content: str,
) -> str:
    prompt = f"""
    -----------
    Sent by:
    -----------
    User ID: {user_id}
    Display Name: {display_name}
    Username: {username}
    Email: {email}
    -----------
    Timestamp:
    -----------
    {created_at}
    -----------
    Message:
    -----------
    {content}
    -----------
    """
    return prompt


def vectorize_user_prompt(display_name: str, username: str, email: str) -> str:
    prompt = f"""
    -----------
    User:
    -----------
    Display Name: {display_name}
    Username: {username}
    Email: {email}
    -----------
    """
    return prompt


def vectorize_file_prompt(
    name: str, size: int, type: str, created_at: datetime, content: str
) -> str:
    prompt = f"""
    -----------
    File:
    -----------
    Name: {name}
    Size: {size}
    Type: {type}
    -----------
    Timestamp:
    -----------
    {created_at}
    -----------
    Content:
    -----------
    {content}
    -----------
    """
    return prompt
