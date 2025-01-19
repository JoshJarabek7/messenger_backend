from uuid import UUID

from sqlmodel import Session

from app.models.domain import File, Message, User
from app.repositories.vector_repository import VectorRepository
from app.services.embedding_service import EmbeddingService


class VectorService:
    """
    Service for managing vector operations and semantic search functionality.

    This service provides high-level operations for:
    1. Generating and storing embeddings for messages, users, and files
    2. Performing semantic searches across different content types
    3. Supporting RAG (Retrieval Augmented Generation) operations
    """

    def __init__(self, db: Session, embedding_service: EmbeddingService):
        self.db = db
        self.vector_repository = VectorRepository(db)
        self.embedding_service = embedding_service

    def index_message(self, message: Message) -> None:
        """Index a message by generating and storing its embedding."""
        if message.content:
            embedding = self.embedding_service.generate_embedding(message.content)
            self.vector_repository.store_message_embedding(
                message_id=message.id, content=message.content, embedding=embedding
            )

    def index_user(self, user: User) -> None:
        """Index a user by generating and storing their embedding."""
        # Combine relevant user information for embedding
        user_content = f"{user.display_name} {user.username}"
        embedding = self.embedding_service.generate_embedding(user_content)
        self.vector_repository.store_user_embedding(
            user_id=user.id, content=user_content, embedding=embedding
        )

    def index_file(self, file: File, content: str) -> None:
        """Index a file by generating and storing embeddings for its content chunks."""
        # Generate embeddings for each chunk of content
        chunks = self.embedding_service.chunk_text(content)
        for chunk in chunks:
            embedding = self.embedding_service.generate_embedding(chunk)
            self.vector_repository.store_file_chunk_embedding(
                file_id=file.id, content=chunk, embedding=embedding
            )

    def search_messages(
        self,
        query: str,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[tuple[Message, float]]:
        """
        Search for semantically similar messages.

        Args:
            query: The search query
            workspace_ids: Optional workspaces to scope the search
            channel_ids: Optional channels to scope the search
            dm_conversation_ids: Optional DM conversations to scope the search
            ai_conversation_ids: Optional AI conversations to scope the search
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of tuples containing (Message, similarity_score)
        """
        query_embedding = self.embedding_service.generate_embedding(query)
        return self.vector_repository.find_similar_messages(
            embedding=query_embedding,
            workspace_ids=workspace_ids,
            channel_ids=channel_ids,
            dm_conversation_ids=dm_conversation_ids,
            ai_conversation_ids=ai_conversation_ids,
            min_similarity=min_similarity,
            limit=limit,
        )

    def search_users(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[tuple[User, float]]:
        """
        Search for semantically similar users.

        Args:
            query: The search query
            workspace_id: Optional workspace to scope the search
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of tuples containing (User, similarity_score)
        """
        query_embedding = self.embedding_service.generate_embedding(query)
        return self.vector_repository.find_similar_users(
            embedding=query_embedding,
            min_similarity=min_similarity,
            limit=limit,
        )

    def search_files(
        self,
        query: str,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[tuple[File, float, str]]:
        """
        Search for semantically similar files.

        Args:
            query: The search query
            workspace_ids: Optional workspaces to scope the search
            channel_ids: Optional channels to scope the search
            dm_conversation_ids: Optional DM conversations to scope the search
            ai_conversation_ids: Optional AI conversations to scope the search
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of tuples containing (File, similarity_score, matching_chunk)
        """
        query_embedding = self.embedding_service.generate_embedding(query)
        return self.vector_repository.find_similar_files(
            embedding=query_embedding,
            workspace_ids=workspace_ids,
            channel_ids=channel_ids,
            dm_conversation_ids=dm_conversation_ids,
            ai_conversation_ids=ai_conversation_ids,
            min_similarity=min_similarity,
            limit=limit,
        )

    def get_context_for_rag(
        self,
        query: str,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        include_messages: bool = True,
        include_users: bool = True,
        include_files: bool = True,
        limit_per_type: int = 3,
        min_similarity: float = 0.7,
    ) -> list[tuple[str, float, str]]:
        """
        Get mixed content chunks for RAG operations.

        Args:
            query: The context query
            workspace_ids: Optional workspaces to scope the search
            channel_ids: Optional channels to scope the search
            dm_conversation_ids: Optional DM conversations to scope the search
            ai_conversation_ids: Optional AI conversations to scope the search
            include_messages: Whether to include message chunks
            include_users: Whether to include user information
            include_files: Whether to include file chunks
            limit_per_type: Maximum chunks per content type
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of tuples containing (content_chunk, similarity_score, source_type)
        """
        query_embedding = self.embedding_service.generate_embedding(query)
        return self.vector_repository.get_mixed_chunks_for_rag(
            embedding=query_embedding,
            workspace_ids=workspace_ids,
            channel_ids=channel_ids,
            dm_conversation_ids=dm_conversation_ids,
            ai_conversation_ids=ai_conversation_ids,
            include_messages=include_messages,
            include_users=include_users,
            include_files=include_files,
            min_similarity=min_similarity,
            limit_per_type=limit_per_type,
        )
