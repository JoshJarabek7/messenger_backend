from typing import TypeAlias
from uuid import UUID, uuid4
from sqlmodel import Session, text

from app.models.domain import (
    File,
    FileEmbedding,
    Message,
    MessageEmbedding,
    User,
    UserEmbedding,
)
import json

# Type aliases for cleaner type hints
VectorFloat: TypeAlias = list[float]
SimilarityScore: TypeAlias = float
Content: TypeAlias = str


class VectorRepository:
    def __init__(self, db: Session) -> None:
        self.db: Session = db

    def _format_vector(self, embedding: list[float]) -> str:
        """Convert Python list to PostgreSQL vector format."""
        return f"ARRAY{str(embedding)}::vector"

    def _parse_vector(self, vector_str: str) -> list[float]:
        """Convert PostgreSQL vector string back to Python list."""
        # Remove any leading/trailing whitespace and 'ARRAY' prefix if present
        cleaned = vector_str.strip()
        if cleaned.startswith("["):
            # Parse the string representation of the array
            return json.loads(cleaned)
        return []

    def _process_row(self, row) -> dict:
        """Process a database row, safely handling null values and converting embeddings."""
        if row is None:
            raise ValueError("No row returned from database")
        row_dict = dict(row._mapping)
        if "embedding" in row_dict:
            row_dict["embedding"] = self._parse_vector(row_dict["embedding"])
        return row_dict

    def store_message_embedding(
        self, message_id: UUID, content: str, embedding: list[float]
    ) -> MessageEmbedding:
        query = text(f"""
            INSERT INTO messageembedding (id, message_id, content, embedding, created_at, updated_at)
            VALUES (:id, :message_id, :content, {self._format_vector(embedding)}, NOW(), NOW())
            RETURNING *
        """)
        params = {
            "id": uuid4(),
            "message_id": message_id,
            "content": content,
        }
        result = self.db.execute(query, params)
        return MessageEmbedding.model_validate(self._process_row(result.fetchone()))

    def store_user_embedding(
        self, user_id: UUID, content: str, embedding: VectorFloat
    ) -> UserEmbedding:
        """Store embedding for a user."""
        query = text(f"""
            INSERT INTO userembedding (id, user_id, content, embedding, created_at, updated_at)
            VALUES (:id, :user_id, :content, {self._format_vector(embedding)}, NOW(), NOW())
            RETURNING *
        """)
        params = {
            "id": uuid4(),
            "user_id": user_id,
            "content": content,
        }
        result = self.db.execute(query, params)
        return UserEmbedding.model_validate(self._process_row(result.fetchone()))

    def store_file_chunk_embedding(
        self, file_id: UUID, content: str, embedding: VectorFloat
    ) -> FileEmbedding:
        """Store embedding for a file chunk."""
        query = text(f"""
            INSERT INTO fileembedding (id, file_id, content, embedding, created_at, updated_at)
            VALUES (:id, :file_id, :content, {self._format_vector(embedding)}, NOW(), NOW())
            RETURNING *
        """)
        params = {
            "id": uuid4(),
            "file_id": file_id,
            "content": content,
        }
        result = self.db.execute(query, params)
        return FileEmbedding.model_validate(self._process_row(result.fetchone()))

    def find_similar_messages(
        self,
        embedding: VectorFloat,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[tuple[Message, SimilarityScore]]:
        """Find similar messages using cosine similarity."""
        query = text(f"""
            WITH similarity_scores AS (
                SELECT message_id, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity
                FROM messageembedding
                GROUP BY message_id, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            )
            SELECT message.*, similarity_scores.similarity
            FROM message
            JOIN similarity_scores ON message.id = similarity_scores.message_id
            LEFT JOIN channel ON message.channel_id = channel.id
            WHERE (
                (:workspace_ids IS NULL OR channel.workspace_id = ANY(:workspace_ids))
                AND (:channel_ids IS NULL OR message.channel_id = ANY(:channel_ids))
                AND (:dm_conversation_ids IS NULL OR message.dm_conversation_id = ANY(:dm_conversation_ids))
                AND (:ai_conversation_ids IS NULL OR message.ai_conversation_id = ANY(:ai_conversation_ids))
            )
            ORDER BY similarity_scores.similarity DESC
            LIMIT :limit
        """)
        params = {
            "workspace_ids": workspace_ids,
            "channel_ids": channel_ids,
            "dm_conversation_ids": dm_conversation_ids,
            "ai_conversation_ids": ai_conversation_ids,
            "min_similarity": min_similarity,
            "limit": limit,
        }
        result = self.db.execute(query, params)
        return [(Message.model_validate(row), row.similarity) for row in result]

    def find_similar_users(
        self,
        embedding: VectorFloat,
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[tuple[User, SimilarityScore]]:
        """Find similar users using cosine similarity."""
        query = text(f"""
            WITH similarity_scores AS (
                SELECT user_id, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity
                FROM userembedding
                GROUP BY user_id, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            )
            SELECT app_user.*, similarity_scores.similarity
            FROM app_user
            JOIN similarity_scores ON app_user.id = similarity_scores.user_id
            ORDER BY similarity_scores.similarity DESC
            LIMIT :limit
        """)
        params = {
            "min_similarity": min_similarity,
            "limit": limit,
        }
        result = self.db.execute(query, params)
        return [(User.model_validate(row), row.similarity) for row in result]

    def find_similar_files(
        self,
        embedding: VectorFloat,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[tuple[File, SimilarityScore, Content]]:
        """Find similar files using cosine similarity."""
        query = text(f"""
            WITH similarity_scores AS (
                SELECT file_id, fileembedding.content, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity
                FROM fileembedding
                GROUP BY file_id, fileembedding.content, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            )
            SELECT 
                file.id,
                file.name,
                file.mime_type,
                LOWER(file.file_type::text) as file_type,
                file.file_size,
                file.workspace_id,
                file.user_id,
                file.created_at,
                file.updated_at,
                similarity_scores.similarity,
                similarity_scores.content
            FROM file
            JOIN similarity_scores ON file.id = similarity_scores.file_id
            WHERE (
                (:workspace_ids IS NULL OR file.workspace_id = ANY(:workspace_ids))
                AND (:channel_ids IS NULL OR file.channel_id = ANY(:channel_ids))
                AND (:dm_conversation_ids IS NULL OR file.dm_conversation_id = ANY(:dm_conversation_ids))
                AND (:ai_conversation_ids IS NULL OR file.ai_conversation_id = ANY(:ai_conversation_ids))
            )
            ORDER BY similarity_scores.similarity DESC
            LIMIT :limit
        """)
        params = {
            "workspace_ids": workspace_ids,
            "channel_ids": channel_ids,
            "dm_conversation_ids": dm_conversation_ids,
            "ai_conversation_ids": ai_conversation_ids,
            "min_similarity": min_similarity,
            "limit": limit,
        }
        result = self.db.execute(query, params)
        return [
            (File.model_validate(row), row.similarity, row.content) for row in result
        ]

    def find_file_chunks(
        self,
        embedding: VectorFloat,
        workspace_ids: list[UUID],
        min_similarity: float = 0.7,
        limit: int = 5,
    ) -> list[tuple[File, list[tuple[Content, SimilarityScore]]]]:
        """Find similar file chunks and group them by file."""
        query = text(f"""
            WITH similarity_scores AS (
                SELECT file_id, fileembedding.content, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity
                FROM fileembedding
                GROUP BY file_id, fileembedding.content, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            )
            SELECT 
                file.id,
                file.name,
                file.mime_type,
                LOWER(file.file_type::text) as file_type,  -- Added explicit cast to text
                file.file_size,
                file.workspace_id,
                file.user_id,
                file.created_at,
                file.updated_at,
                similarity_scores.similarity,
                similarity_scores.content
            FROM file
            JOIN similarity_scores ON file.id = similarity_scores.file_id
            WHERE file.workspace_id = ANY(:workspace_ids)
            ORDER BY file.id, similarity_scores.similarity DESC
            LIMIT :limit
        """)
        params = {
            "workspace_ids": workspace_ids,
            "min_similarity": min_similarity,
            "limit": limit,
        }
        result = self.db.execute(query, params)

        files_dict: dict[UUID, tuple[File, list[tuple[Content, SimilarityScore]]]] = {}
        for row in result:
            file_id = row.id
            if file_id not in files_dict:
                files_dict[file_id] = (File.model_validate(row), [])
            files_dict[file_id][1].append((row.content, row.similarity))

        return list(files_dict.values())

    def get_mixed_chunks_for_rag(
        self,
        embedding: VectorFloat,
        workspace_ids: list[UUID] | None = None,
        channel_ids: list[UUID] | None = None,
        dm_conversation_ids: list[UUID] | None = None,
        ai_conversation_ids: list[UUID] | None = None,
        include_messages: bool = True,
        include_users: bool = True,
        include_files: bool = True,
        limit_per_type: int = 3,
        min_similarity: float = 0.7,
        limit: int | None = None,  # For backward compatibility
    ) -> list[tuple[Content, SimilarityScore, str]]:
        """Get mixed content chunks (messages and files) for RAG."""
        # Use limit if provided, otherwise use limit_per_type
        final_limit = limit if limit is not None else limit_per_type
        parts = []
        if include_messages:
            parts.append(f"""
                SELECT messageembedding.content, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity, 'message' as type
                FROM messageembedding
                JOIN message ON messageembedding.message_id = message.id
                LEFT JOIN channel ON message.channel_id = channel.id
                WHERE (
                    (:workspace_ids IS NULL OR channel.workspace_id = ANY(:workspace_ids))
                    AND (:channel_ids IS NULL OR message.channel_id = ANY(:channel_ids))
                    AND (:dm_conversation_ids IS NULL OR message.dm_conversation_id = ANY(:dm_conversation_ids))
                    AND (:ai_conversation_ids IS NULL OR message.ai_conversation_id = ANY(:ai_conversation_ids))
                )
                GROUP BY messageembedding.content, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            """)
        if include_files:
            parts.append(f"""
                SELECT fileembedding.content, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity, 'file' as type
                FROM fileembedding
                JOIN file ON fileembedding.file_id = file.id
                WHERE (
                    (:workspace_ids IS NULL OR file.workspace_id = ANY(:workspace_ids))
                    AND (:channel_ids IS NULL OR file.channel_id = ANY(:channel_ids))
                    AND (:dm_conversation_ids IS NULL OR file.dm_conversation_id = ANY(:dm_conversation_ids))
                    AND (:ai_conversation_ids IS NULL OR file.ai_conversation_id = ANY(:ai_conversation_ids))
                )
                GROUP BY fileembedding.content, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            """)
        if include_users:
            parts.append(f"""
                SELECT userembedding.content, 1 - (embedding <=> {self._format_vector(embedding)}) as similarity, 'user' as type
                FROM userembedding
                JOIN app_user ON userembedding.user_id = app_user.id
                JOIN workspacemember ON app_user.id = workspacemember.user_id
                WHERE (:workspace_ids IS NULL OR workspacemember.workspace_id = ANY(:workspace_ids))
                GROUP BY userembedding.content, embedding
                HAVING 1 - (embedding <=> {self._format_vector(embedding)}) >= :min_similarity
            """)

        query = text(f"""
            {" UNION ALL ".join(parts)}
            ORDER BY similarity DESC
            LIMIT :limit
        """)
        params = {
            "workspace_ids": workspace_ids,
            "channel_ids": channel_ids,
            "dm_conversation_ids": dm_conversation_ids,
            "ai_conversation_ids": ai_conversation_ids,
            "min_similarity": min_similarity,
            "limit": final_limit,
        }
        result = self.db.execute(query, params)
        return [(row.content, row.similarity, row.type) for row in result]
