"""Modulo de deduplicacion de noticias.

Implementa tres estrategias complementarias:
1. Hash de URL (SHA256) para deteccion exacta.
2. Similitud de titulos por relacion de caracteres.
3. Similitud semantica via pgvector + Sentence Transformers.

Las tres se combinan con umbrales configurables.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.news import News

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Configuracion de umbrales
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class DedupConfig:
    """Umbrales configurables para cada estrategia de deduplicacion.

    Todos los valores van de 0.0 a 1.0, donde 1.0 es coincidencia exacta.
    """

    # Similitud de titulo (metodo heuristico)
    title_similarity_threshold: float = 0.85
    # Similitud semantica (Sentence Transformers + cosine)
    semantic_similarity_threshold: float = 0.92
    # Ventana de tiempo en horas para buscar duplicados
    time_window_hours: int = 48
    # Longitud minima del titulo para considerar dedup
    min_title_length: int = 15


# ──────────────────────────────────────────────────────────────────────────────
# Resultado de deduplicacion
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class DedupResult:
    """Resultado de la verificacion de duplicado para un item."""

    is_duplicate: bool = False
    duplicate_of: Optional[str] = None  # UUID del duplicado original
    similarity_score: Optional[float] = None
    strategy: Optional[str] = None  # 'url_hash', 'title', 'semantic', 'none'
    matched_title: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Deduplicador
# ──────────────────────────────────────────────────────────────────────────────
class Deduplicator:
    """Pipeline de deduplicacion de noticias con tres estrategias."""

    def __init__(
        self,
        config: Optional[DedupConfig] = None,
        use_semantic: bool = False,
    ) -> None:
        self.config = config or DedupConfig()
        self.use_semantic = use_semantic
        self._semantic_model: Any = None  # Cargado lazy

    # ── Estrategia 1: Hash de URL ────────────────────────────────────────────

    @staticmethod
    def _url_hash(url: Optional[str]) -> Optional[str]:
        """Calcula SHA256 de una URL normalizada."""
        if not url:
            return None
        try:
            parsed = urlparse(url)
            # Normalizar: lowercase scheme+netloc, eliminar fragment, ordenar query
            normalized = (
                f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
                f"{parsed.path.rstrip('/') or '/'}"
            )
            if parsed.query:
                # Ordenar parametros de query
                params = sorted(parsed.query.split("&"))
                normalized += "?" + "&".join(params)
            return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception as exc:
            logger.debug("Error normalizando URL '%s': %s", url, exc)
            return None

    async def check_url_hash(
        self, session: AsyncSession, url: Optional[str], source_id: str,
    ) -> DedupResult:
        """Verifica si la URL ya existe en la base de datos."""
        url_hash = self._url_hash(url)
        if not url_hash:
            return DedupResult()

        # Buscar por URL exacta en la misma fuente
        result = await session.execute(
            select(News).where(
                News.url == url,
                News.source_id == source_id,
                News.status != "duplicate",
            ).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return DedupResult(
                is_duplicate=True,
                duplicate_of=str(existing.id),
                similarity_score=1.0,
                strategy="url_hash",
                matched_title=existing.title or existing.original_title,
            )

        return DedupResult()

    # ── Estrategia 2: Similitud de titulo ────────────────────────────────────

    async def check_title_similarity(
        self, session: AsyncSession, title: Optional[str],
    ) -> DedupResult:
        """Busca noticias recientes con titulos similares."""
        if not title or len(title.strip()) < self.config.min_title_length:
            return DedupResult()

        title_clean = title.strip().lower()

        # Obtener noticias recientes no duplicadas
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.time_window_hours)
        result = await session.execute(
            select(News).where(
                News.created_at >= cutoff,
                News.status != "duplicate",
                News.original_title.isnot(None),
            ).order_by(News.created_at.desc()).limit(100)
        )
        candidates = result.scalars().all()

        best_score = 0.0
        best_match: Optional[News] = None

        for candidate in candidates:
            cand_title = (candidate.original_title or "").strip().lower()
            if not cand_title or len(cand_title) < self.config.min_title_length:
                continue

            score = self._title_similarity(title_clean, cand_title)
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_score >= self.config.title_similarity_threshold and best_match:
            return DedupResult(
                is_duplicate=True,
                duplicate_of=str(best_match.id),
                similarity_score=round(best_score, 4),
                strategy="title",
                matched_title=best_match.original_title,
            )

        # Devolver el mejor score aunque no supere el umbral,
        # para que el llamador pueda combinar estrategias
        return DedupResult(
            is_duplicate=False,
            similarity_score=round(best_score, 4) if best_score > 0 else None,
            strategy="title" if best_score > 0 else None,
        )

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """Calcula similitud entre dos titulos usando caracteres comunes.

        Usa una combinacion de:
        - Coeficiente de Jaccard sobre conjuntos de palabras
        - Relacion de subsecuencia comun mas larga (LCS) normalizada
        """
        # Jaccard sobre palabras
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b
        jaccard = len(intersection) / len(union) if union else 0.0

        # LCS normalizado por longitud
        lcs_len = Deduplicator._longest_common_subsequence(a, b)
        max_len = max(len(a), len(b))
        lcs_ratio = lcs_len / max_len if max_len > 0 else 0.0

        # Combinacion ponderada
        return 0.4 * jaccard + 0.6 * lcs_ratio

    @staticmethod
    def _longest_common_subsequence(a: str, b: str) -> int:
        """Calcula la longitud de la subsecuencia comun mas larga."""
        m, n = len(a), len(b)
        # Optimizacion: solo dos filas
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev

        return prev[n]

    # ── Estrategia 3: Similaridad semantica (pgvector + Sentence Transformers) ──

    async def check_semantic_similarity(
        self, session: AsyncSession, title: str, summary: Optional[str] = None,
    ) -> DedupResult:
        """Usa Sentence Transformers + pgvector para encontrar duplicados semanticos.

        Requiere que la tabla 'news' tenga una columna 'embedding vector(384)' y
        un indice IVFFlat para busqueda aproximada.
        """
        if not self.use_semantic:
            return DedupResult()

        if not title or len(title.strip()) < self.config.min_title_length:
            return DedupResult()

        try:
            embedding = await self._compute_embedding(title, summary)

            # Busqueda por similitud coseno en pgvector
            from datetime import datetime, timedelta, timezone

            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.time_window_hours)

            stmt = text("""
                SELECT n.id, n.original_title,
                       1 - (n.embedding <=> :embedding) AS similarity
                FROM news n
                WHERE n.created_at >= :cutoff
                  AND n.status != 'duplicate'
                  AND n.embedding IS NOT NULL
                  AND 1 - (n.embedding <=> :embedding) >= :threshold
                ORDER BY similarity DESC
                LIMIT 1
            """)

            result = await session.execute(
                stmt,
                {
                    "embedding": embedding,
                    "cutoff": cutoff,
                    "threshold": self.config.semantic_similarity_threshold,
                },
            )
            row = result.fetchone()

            if row:
                return DedupResult(
                    is_duplicate=True,
                    duplicate_of=str(row[0]),
                    similarity_score=round(float(row[2]), 4),
                    strategy="semantic",
                    matched_title=row[1],
                )

        except Exception as exc:
            logger.warning("Error en dedup semantico: %s", exc)

        return DedupResult()

    async def _compute_embedding(self, title: str, summary: Optional[str] = None) -> List[float]:
        """Computa el embedding de un texto usando Sentence Transformers.

        Carga el modelo bajo demanda (lazy) para evitar consumo de memoria
        innecesario si no se usa dedup semantico.
        """
        if self._semantic_model is None:
            logger.info("Cargando modelo Sentence Transformers (perezoso)...")
            from sentence_transformers import SentenceTransformer

            self._semantic_model = SentenceTransformer(
                "intfloat/multilingual-e5-small",  # ~118MB, soporta espanol
                device="cpu",
            )

        text_to_embed = f"passage: {title}"
        if summary:
            text_to_embed += f" {summary}"

        embedding = self._semantic_model.encode(text_to_embed, normalize_embeddings=True)
        return embedding.tolist()

    # ── Pipeline completo ────────────────────────────────────────────────────

    async def check_all(
        self,
        session: AsyncSession,
        url: Optional[str],
        title: Optional[str],
        summary: Optional[str],
        source_id: str,
    ) -> DedupResult:
        """Ejecuta todas las estrategias en orden y retorna el mejor match.

        Orden: URL hash -> titulo -> semantico.
        Si alguna da positivo, se retorna inmediatamente.
        """
        # 1. URL hash (mas preciso)
        if url:
            result = await self.check_url_hash(session, url, source_id)
            if result.is_duplicate:
                logger.debug(
                    "Duplicado por URL hash: '%s' -> %s",
                    title[:50] if title else "", result.duplicate_of,
                )
                return result

        # 2. Similitud de titulo
        if title:
            result = await self.check_title_similarity(session, title)
            if result.is_duplicate:
                logger.debug(
                    "Duplicado por titulo (%.4f): '%s' -> %s",
                    result.similarity_score or 0,
                    title[:50],
                    result.duplicate_of,
                )
                return result

        # 3. Semantico (solo si esta habilitado)
        if self.use_semantic and title:
            result = await self.check_semantic_similarity(session, title, summary)
            if result.is_duplicate:
                logger.debug(
                    "Duplicado semantico (%.4f): '%s' -> %s",
                    result.similarity_score or 0,
                    title[:50],
                    result.duplicate_of,
                )
                return result

        return DedupResult(strategy="none")

    async def compute_and_store_embedding(
        self, session: AsyncSession, news_id: str, title: str, summary: Optional[str] = None,
    ) -> bool:
        """Computa y almacena el embedding de una noticia.

        Debe llamarse despues de insertar la noticia, solo si use_semantic=True.
        """
        if not self.use_semantic:
            return False

        try:
            embedding = await self._compute_embedding(title, summary)

            stmt = text("""
                UPDATE news
                SET embedding = :embedding::vector
                WHERE id = :news_id::uuid
            """)
            await session.execute(stmt, {
                "embedding": embedding,
                "news_id": news_id,
            })
            await session.commit()
            return True
        except Exception as exc:
            logger.warning("Error almacenando embedding para %s: %s", news_id, exc)
            return False

    @staticmethod
    def extract_urls_from_batch(items: List[Dict[str, Any]]) -> Set[str]:
        """Extrae todas las URLs de un lote de items para pre-chequeo."""
        urls: Set[str] = set()
        for item in items:
            url = item.get("url") or item.get("link", "")
            if url:
                urls.add(url)
        return urls
