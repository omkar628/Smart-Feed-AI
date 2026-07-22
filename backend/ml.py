from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer

from preference_expander import PreferenceExpander


ENABLE_PROFILING = False


@dataclass(frozen=True, slots=True)
class TopicBatch:
    """Reusable topic data cached for a specific ordered interest set."""

    topic_names: Tuple[str, ...]
    matched_concepts: Dict[str, Tuple[str, ...]]
    topic_matrix: torch.Tensor


class AIRanker:
    """
    Rank YouTube videos against user interests using a single embedding model.

    Public API must remain stable for `main.py`:
    - class name: AIRanker
    - method: rank_videos(videos, interests)
    """

    def __init__(self) -> None:
        print("Loading model...")

        self.model = SentenceTransformer("BAAI/bge-base-en-v1.5")
        self.bge_threshold = 0.55
        self.expander = PreferenceExpander()

        # Cache full preference expansions because the expander considers
        # all topics together to reduce semantic overlap.
        self.preference_cache: Dict[Tuple[str, ...], Dict[str, Tuple[str, ...]]] = {}

        # Cache topic document embeddings by their exact semantic document.
        self.embedding_cache: Dict[str, torch.Tensor] = {}

        # Cache reusable topic matrices so repeated requests do not rebuild
        # topic documents or restack topic embeddings.
        self.topic_batch_cache: Dict[Tuple[str, ...], TopicBatch] = {}

    def rank_videos(
        self,
        videos: Sequence[Mapping[str, object]],
        interests: Sequence[str],
    ) -> List[Dict[str, object]]:
        """Return ranked videos in the frontend-compatible response format."""

        if not videos:
            print("Returning 0 videos...")
            return []

        timings: Dict[str, float] | None = {} if ENABLE_PROFILING else None
        interest_topics = self._normalize_interests(interests)
        if not interest_topics:
            response_start = self._profile_start()
            final_feed = self._mark_all_unknown(videos)
            self._profile_end(timings, "response generation", response_start)
            self._report_profile(timings)
            print(f"Returning {len(final_feed)} videos...")
            return final_feed

        print("Expanding preferences...")
        expansion_start = self._profile_start()
        expanded_preferences = self.get_expanded_preferences(interest_topics)
        self._profile_end(timings, "preference expansion", expansion_start)

        topic_batch_start = self._profile_start()
        topic_batch = self._get_topic_batch(
            interest_topics,
            expanded_preferences,
        )
        self._profile_end(timings, "topic embedding generation", topic_batch_start)

        print(f"Ranking {len(videos)} videos...")
        video_embedding_start = self._profile_start()
        video_embeddings = self._encode_video_batch(videos)
        self._profile_end(timings, "video embedding generation", video_embedding_start)

        similarity_start = self._profile_start()
        best_indices, best_scores = self._compute_best_matches(
            video_embeddings,
            topic_batch,
        )
        self._profile_end(timings, "similarity computation", similarity_start)

        response_start = self._profile_start()
        final_feed = self._build_ranked_feed(
            videos,
            topic_batch,
            best_indices,
            best_scores,
        )
        self._profile_end(timings, "response generation", response_start)
        self._report_profile(timings)

        print(f"Returning {len(final_feed)} videos...")
        return final_feed

    def get_expanded_preferences(
        self,
        preferences: Sequence[str],
    ) -> Dict[str, Tuple[str, ...]]:
        """Expand interests once per preference set and cache the result."""

        ordered_preferences = list(dict.fromkeys(preferences))
        cache_key = tuple(sorted(ordered_preferences, key=str.lower))

        if cache_key not in self.preference_cache:
            expanded = self.expander.expand_preferences(ordered_preferences)
            self.preference_cache[cache_key] = self._clean_expanded_preferences(
                ordered_preferences,
                expanded,
            )

        return self.preference_cache[cache_key]

    def _get_topic_batch(
        self,
        topics: Sequence[str],
        expanded_preferences: Mapping[str, Sequence[str]],
    ) -> TopicBatch:
        """Build or reuse cached topic documents and stacked embeddings."""

        cache_key = tuple(topics)
        cached_batch = self.topic_batch_cache.get(cache_key)
        if cached_batch is not None:
            return cached_batch

        topic_names = tuple(topics)
        documents = tuple(
            self._build_topic_document(
                topic,
                expanded_preferences.get(topic, (topic,)),
            )
            for topic in topic_names
        )

        self._cache_missing_topic_embeddings(documents)

        topic_batch = TopicBatch(
            topic_names=topic_names,
            matched_concepts={
                topic: tuple(expanded_preferences.get(topic, (topic,))[:10])
                for topic in topic_names
            },
            topic_matrix=torch.stack(
                [self.embedding_cache[document] for document in documents]
            ),
        )

        self.topic_batch_cache[cache_key] = topic_batch
        return topic_batch

    def _cache_missing_topic_embeddings(
        self,
        documents: Sequence[str],
    ) -> None:
        """Encode only uncached topic documents and store normalized vectors."""

        missing_documents = [
            document
            for document in documents
            if document not in self.embedding_cache
        ]

        if not missing_documents:
            return

        encoded = self._encode_texts(missing_documents)
        for index, document in enumerate(missing_documents):
            self.embedding_cache[document] = encoded[index]

    def _encode_video_batch(
        self,
        videos: Sequence[Mapping[str, object]],
    ) -> torch.Tensor:
        """Encode each video once using title, description, and channel."""

        video_texts = [self._build_video_text(video) for video in videos]
        return self._encode_texts(video_texts)

    def _encode_texts(self, texts: Sequence[str]) -> torch.Tensor:
        """Encode text and return L2-normalized embeddings."""

        batch_texts = texts if isinstance(texts, list) else list(texts)
        with torch.inference_mode():
            embeddings = self.model.encode(
                batch_texts,
                convert_to_tensor=True,
            )

        if embeddings.ndim == 1:
            embeddings = embeddings.unsqueeze(0)

        return F.normalize(embeddings, p=2, dim=1)

    def _compute_best_matches(
        self,
        video_embeddings: torch.Tensor,
        topic_batch: TopicBatch,
    ) -> Tuple[List[int], List[float]]:
        """Compute best topic indices and raw confidence scores in one pass."""

        with torch.inference_mode():
            similarity_matrix = torch.matmul(video_embeddings, topic_batch.topic_matrix.T)
            best_indices_tensor = torch.argmax(similarity_matrix, dim=1)
            best_scores_tensor = similarity_matrix.gather(
                1,
                best_indices_tensor.unsqueeze(1),
            ).squeeze(1)

        return best_indices_tensor.tolist(), best_scores_tensor.tolist()

    def _build_ranked_feed(
        self,
        videos: Sequence[Mapping[str, object]],
        topic_batch: TopicBatch,
        best_indices: Sequence[int],
        best_scores: Sequence[float],
    ) -> List[Dict[str, object]]:
        """
        Accept videos above the semantic threshold and rank them globally.
        """

        accepted_videos: List[Dict[str, object]] = []
        hidden_videos: List[Dict[str, object]] = []

        for video, best_index, best_score in zip(videos, best_indices, best_scores):
            best_topic = topic_batch.topic_names[best_index]

            if best_score < self.bge_threshold:
                hidden_videos.append(
                    self._build_unknown_result(
                        video,
                        confidence=best_score,
                        candidate_topic=best_topic,
                        action="Hide",
                    )
                )
                continue

            accepted_videos.append(
                self._build_accepted_result(
                    video,
                    topic=best_topic,
                    confidence=best_score,
                    matched_concepts=topic_batch.matched_concepts[best_topic],
                    action="Show",
                )
            )

        accepted_videos.sort(
            key=lambda video: float(video["confidence"]),
            reverse=True,
        )
        hidden_videos.sort(
            key=lambda video: float(video["confidence"]),
            reverse=True,
        )

        return [*accepted_videos, *hidden_videos]

    def _mark_all_unknown(
        self,
        videos: Sequence[Mapping[str, object]],
    ) -> List[Dict[str, object]]:
        """Fallback for empty interest payloads."""

        return [
            self._build_unknown_result(
                video,
                confidence=0.0,
                candidate_topic=None,
                action="Hide",
            )
            for video in videos
        ]

    def _build_video_text(self, video: Mapping[str, object]) -> str:
        """Create the single semantic document used for each video."""

        title = self._string_value(video.get("title"))
        description = self._string_value(video.get("description"))
        channel = self._string_value(video.get("channel"))

        return (
            f"Title:\n{title}\n\n"
            f"Video Title:\n{title}\n\n"
            f"Description:\n{description}\n\n"
            f"Channel:\n{channel}"
        )

    def _build_topic_document(
        self,
        topic: str,
        concepts: Sequence[str],
    ) -> str:
        """Create one semantic document with light topic context."""

        cleaned_concepts = self._clean_concepts([topic, *concepts])
        concept_lines = "\n".join(cleaned_concepts)
        return f"Topic: {topic}\n\n{topic} includes\n\n{concept_lines}"

    def _build_accepted_result(
        self,
        video: Mapping[str, object],
        topic: str,
        confidence: float,
        matched_concepts: Sequence[str],
        action: str,
    ) -> Dict[str, object]:
        """Shape an accepted video for the existing frontend contract."""

        result = dict(video)
        result.update(
            {
                "topic": topic,
                "confidence": round(confidence, 3),
                "matched_concepts": list(matched_concepts),
                "action": action,
            }
        )
        return result

    def _build_unknown_result(
        self,
        video: Mapping[str, object],
        confidence: float,
        candidate_topic: str | None,
        action: str | None = None,
    ) -> Dict[str, object]:
        """Shape a rejected video for the existing frontend contract."""

        result = dict(video)
        result.update(
            {
                "topic": "Unknown",
                "confidence": round(confidence, 3),
                "candidate_topic": candidate_topic,
            }
        )

        if action is not None:
            result["action"] = action

        return result

    def _clean_expanded_preferences(
        self,
        preferences: Sequence[str],
        expanded_preferences: Mapping[str, object],
    ) -> Dict[str, Tuple[str, ...]]:
        """Normalize expander output and guarantee each topic has concepts."""

        cleaned: Dict[str, Tuple[str, ...]] = {}

        for preference in preferences:
            raw_concepts = expanded_preferences.get(preference, [preference])
            if not isinstance(raw_concepts, list):
                raw_concepts = [preference]

            cleaned[preference] = tuple(
                self._clean_concepts([preference, *raw_concepts])
            )

        return cleaned

    def _clean_concepts(self, concepts: Iterable[object]) -> List[str]:
        """Trim, deduplicate, and keep concept strings stable."""

        cleaned_concepts: List[str] = []
        seen: set[str] = set()

        for concept in concepts:
            if not isinstance(concept, str):
                continue

            normalized = concept.strip()
            if not normalized:
                continue

            key = normalized.lower()
            if key in seen:
                continue

            seen.add(key)
            cleaned_concepts.append(normalized)

        return cleaned_concepts

    def _normalize_interests(
        self,
        interests: Sequence[str],
    ) -> List[str]:
        """Normalize selected topic names for semantic ranking."""

        return self._clean_concepts(interests)

    def _profile_start(self) -> float | None:
        """Return a timer start value only when profiling is enabled."""

        if not ENABLE_PROFILING:
            return None

        return perf_counter()

    def _profile_end(
        self,
        timings: Dict[str, float] | None,
        name: str,
        start: float | None,
    ) -> None:
        """Store an elapsed timing only when profiling is enabled."""

        if timings is None or start is None:
            return

        timings[name] = perf_counter() - start

    def _report_profile(self, timings: Dict[str, float] | None) -> None:
        """Emit timing details only when explicit profiling is enabled."""

        if timings is None:
            return

        print(
            "Profiling: "
            + ", ".join(
                f"{name}={elapsed:.4f}s"
                for name, elapsed in timings.items()
            )
        )

    def _string_value(self, value: object) -> str:
        """Convert nullable payload fields into safe strings."""

        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        return str(value).strip()
