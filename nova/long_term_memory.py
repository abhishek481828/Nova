"""
Long-Term Memory (LTM) subsystem for Nova AI Assistant.
Manages persistent memories independent of Working Memory.
Supports structured storage, metadata tracking, SQLite backend, indexes, schema migrations,
semantic memory category classification, query-based memory retrieval, and relevance ranking.
"""

from __future__ import annotations

import time
import uuid
import sqlite3
import json
import logging
import threading
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nova")


class MemoryCategory:
    """
    Standard memory categories supported by LTM.
    """
    USER_PROFILE = "user_profile"
    PREFERENCES = "preferences"
    PROJECTS = "projects"
    DEVICES = "devices"
    GOALS = "goals"
    SKILLS = "skills"
    RELATIONSHIPS = "relationships"
    FACTS = "facts"
    KNOWLEDGE = "knowledge"
    CUSTOM = "custom"

    SYSTEM_CATEGORIES = {
        USER_PROFILE,
        PREFERENCES,
        PROJECTS,
        DEVICES,
        GOALS,
        SKILLS,
        RELATIONSHIPS,
        FACTS,
        KNOWLEDGE,
        CUSTOM
    }


class MemoryClassifier:
    """
    Handles memory category registration, validation, and heuristic-based text classification.
    """
    def __init__(self, custom_categories: Optional[List[str]] = None) -> None:
        self._categories = set(MemoryCategory.SYSTEM_CATEGORIES)
        if custom_categories:
            for cat in custom_categories:
                self.register_category(cat)

    def register_category(self, category: str) -> None:
        """Registers a new custom category."""
        category_clean = category.strip().lower()
        if not category_clean:
            raise ValueError("Category name cannot be empty.")
        self._categories.add(category_clean)
        logger.info(f"Registered custom memory category: '{category_clean}'")

    def get_registered_categories(self) -> List[str]:
        """Returns list of registered categories."""
        return sorted(list(self._categories))

    def validate_category(self, category: str) -> bool:
        """Validates if a category is registered."""
        return category.strip().lower() in self._categories

    def classify_text(self, text: str) -> str:
        """
        Suggests a category for raw text using heuristic patterns.
        """
        text_lower = text.lower()
        
        # Heuristics mapping rules
        if any(kw in text_lower for kw in ("name is", "born in", "live in", "i am a", "my age", "profile")):
            return MemoryCategory.USER_PROFILE
            
        if any(kw in text_lower for kw in ("like", "dislike", "prefer", "favorite", "hobby", "love to", "loves to")):
            return MemoryCategory.PREFERENCES
            
        if any(kw in text_lower for kw in ("project", "repo", "codebase", "develop", "build", "task")):
            return MemoryCategory.PROJECTS
            
        if any(kw in text_lower for kw in ("phone", "computer", "laptop", "device", "server", "hardware")):
            return MemoryCategory.DEVICES
            
        if any(kw in text_lower for kw in ("want to", "goal", "plan to", "aim", "target", "aspire")):
            return MemoryCategory.GOALS
            
        if any(kw in text_lower for kw in ("python", "javascript", "program", "fluent in", "know how to", "expert")):
            return MemoryCategory.SKILLS
            
        if any(kw in text_lower for kw in ("friend", "spouse", "wife", "husband", "son", "daughter", "mother", "father", "colleague", "sister", "brother", "boss", "manager")):
            return MemoryCategory.RELATIONSHIPS
            
        if any(kw in text_lower for kw in ("did you know", "fact", "definition", "capital of", "sun rises")):
            return MemoryCategory.FACTS
            
        return MemoryCategory.KNOWLEDGE


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
    def query_memories(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True
    ) -> List[Memory]:
        """Queries stored memories using structural filter attributes."""
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
        return self.query_memories(category=category, active_only=active_only)

    def query_memories(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True
    ) -> List[Memory]:
        query = "SELECT * FROM long_term_memories WHERE 1=1"
        params: List[Any] = []

        if category is not None:
            query += " AND category = ?"
            params.append(category)

        if active_only:
            query += " AND active = 1"

        if title is not None:
            query += " AND title LIKE ?"
            params.append(f"%{title}%")

        if tags is not None:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')

        if keywords is not None:
            for kw in keywords:
                query += " AND (title LIKE ? OR content LIKE ?)"
                params.extend([f"%{kw}%", f"%{kw}%"])

        if metadata is not None:
            for key, val in metadata.items():
                if key in ("importance", "confidence", "source", "version", "access_count"):
                    query += f" AND {key} = ?"
                    params.append(val)

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
        memories = []
        for row in rows:
            try:
                memories.append(self._row_to_memory(row))
            except Exception as e:
                logger.error(f"Failed to parse query memory row: {e}")
        return memories

    def close(self) -> None:
        with self._lock:
            self.conn.close()
        logger.info("SQLite connection closed.")


class BaseSemanticRetriever(ABC):
    """
    Abstract interface for future Vector/Semantic search implementations.
    """
    @abstractmethod
    def retrieve_semantic(self, query: str, limit: int = 5) -> List[Memory]:
        pass


class BaseMemoryRanker(ABC):
    """
    Abstract interface for LTM ranking algorithms.
    """
    @abstractmethod
    def rank(self, memories: List[Memory]) -> List[Memory]:
        """Ranks list of memories returning them sorted by relevance."""
        pass


class HeuristicMemoryRanker(BaseMemoryRanker):
    """
    Standard relevance score ranking system utilizing weighted scores,
    half-life time decays, category priorities, and access counters.
    """
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        category_priorities: Optional[Dict[str, float]] = None,
        decay_half_life: float = 86400.0
    ) -> None:
        self.weights = weights or {
            "importance": 0.3,
            "confidence": 0.2,
            "recency": 0.2,
            "frequency": 0.1,
            "category": 0.2
        }
        self.category_priorities = category_priorities or {
            "user_profile": 1.5,
            "preferences": 1.3,
            "goals": 1.2,
            "relationships": 1.2,
            "skills": 1.1,
            "projects": 1.0,
            "devices": 1.0,
            "facts": 1.0,
            "knowledge": 0.8
        }
        self.decay_half_life = decay_half_life

    def calculate_score(self, memory: Memory, now: float) -> float:
        """Computes relevance score for a given memory record."""
        # 1. Normalized Importance (1 to 5 scale -> 0.2 to 1.0)
        s_imp = memory.importance / 5.0
        
        # 2. Confidence (0.0 to 1.0)
        s_conf = memory.confidence
        
        # 3. Recency Time Decay (Exponential half-life decay)
        delta_t = max(0.0, now - memory.updated_at)
        decay_constant = 0.69314718 / self.decay_half_life  # ln(2)/half_life
        s_rec = math.exp(-decay_constant * delta_t)
        
        # 4. Access Frequency (asymptote scaling: x/(x+1) -> 0.0 to 1.0)
        s_freq = memory.access_count / (memory.access_count + 1.0)
        
        # 5. Category Priority Weights
        s_cat = self.category_priorities.get(memory.category.lower(), 1.0)
        
        # Combined weighted sum
        score = (
            self.weights["importance"] * s_imp +
            self.weights["confidence"] * s_conf +
            self.weights["recency"] * s_rec +
            self.weights["frequency"] * s_freq +
            self.weights["category"] * s_cat
        )
        return score

    def rank(self, memories: List[Memory]) -> List[Memory]:
        now = time.time()
        # Sort in descending order of relevance score
        return sorted(memories, key=lambda m: self.calculate_score(m, now), reverse=True)


class MemoryRetriever:
    """
    Modular retrieval engine supporting structural search and semantic overrides.
    """
    def __init__(
        self,
        storage: BaseMemoryStorage,
        semantic_backend: Optional[BaseSemanticRetriever] = None,
        ranker: Optional[BaseMemoryRanker] = None
    ) -> None:
        self.storage = storage
        self.semantic_backend = semantic_backend
        self.ranker = ranker or HeuristicMemoryRanker()
        logger.info("Memory Retriever initialized.")

    def retrieve(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True,
        use_semantic: bool = True
    ) -> List[Memory]:
        """
        Executes query retrieval across tags, keywords, categories, and titles,
        and applies relevance ranking before returning results.
        """
        # 1. Execute retrieval (semantic or structural)
        results = []
        if query and use_semantic and self.semantic_backend:
            try:
                logger.info(f"Executing semantic retrieval for query: '{query}'")
                semantic_results = self.semantic_backend.retrieve_semantic(query)
                
                # Apply post-retrieval structural filters
                for mem in semantic_results:
                    if active_only and not mem.active:
                        continue
                    if category and mem.category != category:
                        continue
                    if tags and not all(t in mem.tags for t in tags):
                        continue
                    if title and title.lower() not in mem.title.lower():
                        continue
                    if metadata:
                        match = True
                        for k, v in metadata.items():
                            if getattr(mem, k, None) != v:
                                match = False
                                break
                        if not match:
                            continue
                    results.append(mem)
            except Exception as e:
                logger.error(f"Semantic search failed: {e}. Falling back to standard query.")
                results = self.storage.query_memories(
                    category=category,
                    tags=tags,
                    keywords=keywords,
                    title=title,
                    metadata=metadata,
                    active_only=active_only
                )
        else:
            results = self.storage.query_memories(
                category=category,
                tags=tags,
                keywords=keywords,
                title=title,
                metadata=metadata,
                active_only=active_only
            )

        # 2. Apply ranking sorting
        return self.ranker.rank(results)


class LongTermMemoryManager:
    """
    Coordinates LTM operations using injected storage, classifier, and retrieval components.
    """

    def __init__(
        self,
        storage: BaseMemoryStorage,
        classifier: Optional[MemoryClassifier] = None,
        retriever: Optional[MemoryRetriever] = None
    ) -> None:
        self.storage = storage
        self.classifier = classifier or MemoryClassifier()
        self.retriever = retriever or MemoryRetriever(self.storage)
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
        Creates and stores a new Memory after validating its category.
        """
        category_clean = category.strip().lower()
        if not self.classifier.validate_category(category_clean):
            raise ValueError(f"Category '{category}' is not a registered category.")

        now = time.time()
        memory = Memory(
            category=category_clean,
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
        logger.info(f"Created new memory: [{category_clean}] '{title}' (ID: {memory.id})")
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

        # Validate category if changing
        if "category" in kwargs:
            category_clean = kwargs["category"].strip().lower()
            if not self.classifier.validate_category(category_clean):
                raise ValueError(f"Category '{kwargs['category']}' is not a registered category.")
            kwargs["category"] = category_clean

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
        category_clean = category.strip().lower() if category is not None else None
        return self.storage.list_all(category=category_clean, active_only=active_only)

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

                category_clean = item.get("category", "general").strip().lower()
                if not self.classifier.validate_category(category_clean):
                    self.classifier.register_category(category_clean)

                mem = Memory(
                    id=item.get("id", str(uuid.uuid4())),
                    category=category_clean,
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
