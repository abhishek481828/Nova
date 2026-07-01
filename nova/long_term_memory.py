"""
Long-Term Memory (LTM) subsystem for Nova AI Assistant.
Manages persistent memories independent of Working Memory.
Supports structured storage, metadata tracking, SQLite backend, indexes, and schema migrations.
"""

from __future__ import annotations

import time
import uuid
import sqlite3
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nova")


@dataclass
class Memory:
    """
    Represents a structured long-term memory entity.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "general"
    title: str = ""
    content: str = ""
    importance: int = 1
    confidence: float = 1.0
    source: str = "user"
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    version: int = 1
    active: bool = True
    meta_notes: str = ""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """
        Performs validation checks on Memory attributes.
        Raises ValueError or TypeError on violations.
        """
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Memory ID must be a non-empty string.")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("Memory category must be a non-empty string.")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Memory title must be a non-empty string.")
        if not isinstance(self.content, str):
            raise TypeError("Memory content must be a string.")
            
        if not isinstance(self.importance, int) or not (1 <= self.importance <= 5):
            raise ValueError("Memory importance must be an integer between 1 and 5.")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Memory confidence must be a float between 0.0 and 1.0.")
            
        if not isinstance(self.tags, list):
            raise TypeError("Memory tags must be a list of strings.")
        for tag in self.tags:
            if not isinstance(tag, str):
                raise TypeError("All items in tags must be strings.")

        if not isinstance(self.created_at, (int, float)) or self.created_at <= 0:
            raise ValueError("created_at must be a positive number.")
        if not isinstance(self.updated_at, (int, float)) or self.updated_at <= 0:
            raise ValueError("updated_at must be a positive number.")
        if not isinstance(self.accessed_at, (int, float)) or self.accessed_at <= 0:
            raise ValueError("accessed_at must be a positive number.")
        if not isinstance(self.access_count, int) or self.access_count < 0:
            raise ValueError("access_count must be a non-negative integer.")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer starting at 1.")
        if not isinstance(self.active, bool):
            raise TypeError("active must be a boolean.")
        if not isinstance(self.meta_notes, str):
            raise TypeError("meta_notes must be a string.")


class BaseMemoryStorage(ABC):
    """
    Abstract Base Class defining interface for Long-Term Memory backends.
    """

    @abstractmethod
    def save(self, memory: Memory) -> None:
        """Saves or updates a Memory object."""
        pass

    @abstractmethod
    def load(self, memory_id: str) -> Optional[Memory]:
        """Loads a Memory object by ID."""
        pass

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Deletes a Memory object by ID."""
        pass

    @abstractmethod
    def list_all(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        """Lists all stored Memory objects, optionally filtered by category and active flag."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes any open backend storage connections."""
        pass


class SQLiteMemoryStorage(BaseMemoryStorage):
    """
    SQLite concrete database implementation for LTM storage.
    Uses a persistent, thread-safe connection design with schema migrations and indexing.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._initialize_db()

    def _initialize_db(self) -> None:
        """
        Configures WAL journal and synchronous modes, starts schema version control table,
        and applies sequential migrations under transaction locks.
        """
        with self._lock:
            # WAL mode performance optimization
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("PRAGMA foreign_keys = ON;")
            
            # Setup schema meta version table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                )
            """)
            self.conn.commit()

            # Read current schema version
            cursor = self.conn.cursor()
            cursor.execute("SELECT MAX(version) FROM schema_info")
            row = cursor.fetchone()
            current_version = row[0] if (row and row[0] is not None) else 0

            # Target migration index
            target_version = 3
            for step in range(current_version + 1, target_version + 1):
                try:
                    logger.info(f"Applying schema migration step {step} for LTM Storage...")
                    self._apply_migration_step(step)
                    logger.info(f"Successfully migrated LTM database to version {step}.")
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"Failed to apply database migration step {step}: {e}")
                    raise e

    def _apply_migration_step(self, step: int) -> None:
        """Applies a single, isolated schema migration step."""
        if step == 1:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    active INTEGER NOT NULL
                )
            """)
        elif step == 2:
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON long_term_memories (category);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON long_term_memories (created_at);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON long_term_memories (importance);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_active ON long_term_memories (active);")
        elif step == 3:
            self.conn.execute("ALTER TABLE long_term_memories ADD COLUMN meta_notes TEXT DEFAULT ''")
            
        self.conn.execute("INSERT INTO schema_info (version, applied_at) VALUES (?, ?)", (step, time.time()))
        self.conn.commit()

    def _row_to_memory(self, row: tuple) -> Memory:
        meta_notes = row[14] if len(row) > 14 else ""
        return Memory(
            id=row[0],
            category=row[1],
            title=row[2],
            content=row[3],
            importance=row[4],
            confidence=row[5],
            source=row[6],
            tags=json.loads(row[7]),
            created_at=row[8],
            updated_at=row[9],
            accessed_at=row[10],
            access_count=row[11],
            version=row[12],
            active=bool(row[13]),
            meta_notes=meta_notes
        )

    def save(self, memory: Memory) -> None:
        memory.validate()
        with self._lock:
            # Check table structure to see if meta_notes column is ready
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(long_term_memories)")
            columns = [col[1] for col in cursor.fetchall()]
            
            try:
                if "meta_notes" in columns:
                    self.conn.execute("""
                        INSERT OR REPLACE INTO long_term_memories (
                            id, category, title, content, importance, confidence, source, tags,
                            created_at, updated_at, accessed_at, access_count, version, active, meta_notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        memory.id,
                        memory.category,
                        memory.title,
                        memory.content,
                        memory.importance,
                        memory.confidence,
                        memory.source,
                        json.dumps(memory.tags),
                        memory.created_at,
                        memory.updated_at,
                        memory.accessed_at,
                        memory.access_count,
                        memory.version,
                        int(memory.active),
                        memory.meta_notes
                    ))
                else:
                    self.conn.execute("""
                        INSERT OR REPLACE INTO long_term_memories (
                            id, category, title, content, importance, confidence, source, tags,
                            created_at, updated_at, accessed_at, access_count, version, active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        memory.id,
                        memory.category,
                        memory.title,
                        memory.content,
                        memory.importance,
                        memory.confidence,
                        memory.source,
                        json.dumps(memory.tags),
                        memory.created_at,
                        memory.updated_at,
                        memory.accessed_at,
                        memory.access_count,
                        memory.version,
                        int(memory.active)
                    ))
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Transaction rolled back. Failed to save LTM: {e}")
                raise e

    def load(self, memory_id: str) -> Optional[Memory]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM long_term_memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_memory(row)
        return None

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("DELETE FROM long_term_memories WHERE id = ?", (memory_id,))
                self.conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Transaction rolled back. Failed to delete memory '{memory_id}': {e}")
                raise e

    def list_all(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        query = "SELECT * FROM long_term_memories WHERE 1=1"
        params: List[Any] = []

        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if active_only:
            query += " AND active = 1"

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
        memories = []
        for row in rows:
            try:
                memories.append(self._row_to_memory(row))
            except Exception as e:
                logger.error(f"Failed to parse memory row: {e}")
        return memories

    def close(self) -> None:
        with self._lock:
            self.conn.close()
        logger.info("SQLite connection closed.")


class LongTermMemoryManager:
    """
    Coordinates LTM operations using an injected storage adapter.
    """

    def __init__(self, storage: BaseMemoryStorage) -> None:
        self.storage = storage
        logger.info("Long-Term Memory Manager initialized.")

    def create_memory(
        self,
        category: str,
        title: str,
        content: str,
        importance: int = 1,
        confidence: float = 1.0,
        source: str = "user",
        tags: Optional[List[str]] = None,
        meta_notes: str = ""
    ) -> Memory:
        """
        Creates and stores a new Memory.
        """
        now = time.time()
        memory = Memory(
            category=category,
            title=title,
            content=content,
            importance=importance,
            confidence=confidence,
            source=source,
            tags=tags or [],
            created_at=now,
            updated_at=now,
            accessed_at=now,
            access_count=0,
            version=1,
            active=True,
            meta_notes=meta_notes
        )
        self.storage.save(memory)
        logger.info(f"Created new memory: [{category}] '{title}' (ID: {memory.id})")
        return memory

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """
        Loads memory and updates tracking logs (accessed_at and access_count).
        """
        memory = self.storage.load(memory_id)
        if memory:
            memory.accessed_at = time.time()
            memory.access_count += 1
            self.storage.save(memory)
            logger.debug(f"Retrieved memory '{memory_id}' (Access count: {memory.access_count})")
        return memory

    def update_memory(self, memory_id: str, **kwargs) -> Memory:
        """
        Loads existing memory, applies updates, increments version number, and saves.
        """
        memory = self.storage.load(memory_id)
        if not memory:
            logger.error(f"Cannot update memory: ID '{memory_id}' not found.")
            raise ValueError(f"Memory with ID '{memory_id}' does not exist.")

        # Exclude internal properties from dynamic updates
        read_only = {"id", "created_at", "accessed_at", "access_count", "version"}
        for key, value in kwargs.items():
            if key in read_only:
                continue
            if hasattr(memory, key):
                setattr(memory, key, value)

        memory.updated_at = time.time()
        memory.version += 1
        memory.validate()
        
        self.storage.save(memory)
        logger.info(f"Updated memory '{memory_id}' to version {memory.version}.")
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        """
        Deletes a memory record permanently from storage.
        """
        success = self.storage.delete(memory_id)
        if success:
            logger.info(f"Deleted memory '{memory_id}' successfully.")
        else:
            logger.warning(f"Attempted to delete non-existent memory '{memory_id}'.")
        return success

    def list_memories(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        """
        Lists stored memories.
        """
        return self.storage.list_all(category=category, active_only=active_only)

    def import_memories(self, data: List[Dict[str, Any]]) -> int:
        """
        Bulk imports a list of serialized Memory dictionaries.
        """
        imported_count = 0
        for item in data:
            try:
                # Reconstruct tags correctly if passed as JSON string
                tags = item.get("tags", [])
                if isinstance(tags, str):
                    tags = json.loads(tags)

                mem = Memory(
                    id=item.get("id", str(uuid.uuid4())),
                    category=item.get("category", "general"),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    importance=item.get("importance", 1),
                    confidence=item.get("confidence", 1.0),
                    source=item.get("source", "user"),
                    tags=tags,
                    created_at=item.get("created_at", time.time()),
                    updated_at=item.get("updated_at", time.time()),
                    accessed_at=item.get("accessed_at", time.time()),
                    access_count=item.get("access_count", 0),
                    version=item.get("version", 1),
                    active=bool(item.get("active", True)),
                    meta_notes=item.get("meta_notes", "")
                )
                self.storage.save(mem)
                imported_count += 1
            except Exception as e:
                logger.error(f"Failed to import memory entry: {e}")
                
        logger.info(f"Imported {imported_count} memories successfully.")
        return imported_count

    def export_memories(self) -> List[Dict[str, Any]]:
        """
        Exports all stored memories as a list of dictionaries.
        """
        memories = self.storage.list_all(active_only=False)
        exported = [asdict(m) for m in memories]
        logger.info(f"Exported {len(exported)} memories.")
        return exported
