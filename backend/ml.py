from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer

from preference_expander import PreferenceExpander


@dataclass(frozen=True)
class TopicProfile:
    """Semantic representation for a single user interest topic."""

    name: str
    concepts: List[str]
    document: str
    embedding: torch.Tensor


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
        self.preference_cache: Dict[Tuple[str, ...], Dict[str, List[str]]] = {}

        # Cache topic document embeddings by their exact semantic document.
        self.embedding_cache: Dict[str, torch.Tensor] = {}

    def rank_videos(
        self,
        videos: Sequence[Mapping[str, object]],
        interests: Mapping[str, int],
    ) -> List[Dict[str, object]]:
        """Return ranked videos in the frontend-compatible response format."""

        if not videos:
            print("Returning 0 videos...")
            return []

        interest_topics = list(interests.keys())
        if not interest_topics:
            final_feed = self._mark_all_unknown(videos)
            print(f"Returning {len(final_feed)} videos...")
            return final_feed

        print("Expanding preferences...")
        expanded_preferences = self.get_expanded_preferences(interest_topics)

        topic_profiles = self._build_topic_profiles(
            interest_topics,
            expanded_preferences,
        )

        print(f"Ranking {len(videos)} videos...")
        video_embeddings = self._encode_video_batch(videos)

        categorized_videos = self._categorize_videos(
            videos,
            video_embeddings,
            topic_profiles,
            interests,
            expanded_preferences,
        )

        final_feed = self._apply_percentage_distribution(
            categorized_videos,
            interests,
            total_visible=len(videos),
        )

        print(f"Returning {len(final_feed)} videos...")
        return final_feed

    def get_expanded_preferences(
        self,
        preferences: Sequence[str],
    ) -> Dict[str, List[str]]:
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

    def _build_topic_profiles(
        self,
        topics: Sequence[str],
        expanded_preferences: Mapping[str, Sequence[str]],
    ) -> Dict[str, TopicProfile]:
        """Build one semantic document and one cached embedding per topic."""

        documents_by_topic = {
            topic: self._build_topic_document(
                topic,
                expanded_preferences.get(topic, [topic]),
            )
            for topic in topics
        }

        self._cache_missing_topic_embeddings(documents_by_topic)

        topic_profiles: Dict[str, TopicProfile] = {}
        for topic in topics:
            concepts = list(expanded_preferences.get(topic, [topic]))
            document = documents_by_topic[topic]
            topic_profiles[topic] = TopicProfile(
                name=topic,
                concepts=concepts,
                document=document,
                embedding=self.embedding_cache[document],
            )

        return topic_profiles

    def _cache_missing_topic_embeddings(
        self,
        documents_by_topic: Mapping[str, str],
    ) -> None:
        """Encode only uncached topic documents and store normalized vectors."""

        missing_documents = [
            document
            for document in documents_by_topic.values()
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

        with torch.inference_mode():
            embeddings = self.model.encode(
                list(texts),
                convert_to_tensor=True,
            )

        if embeddings.ndim == 1:
            embeddings = embeddings.unsqueeze(0)

        return F.normalize(embeddings, p=2, dim=1)

    def _categorize_videos(
        self,
        videos: Sequence[Mapping[str, object]],
        video_embeddings: torch.Tensor,
        topic_profiles: Mapping[str, TopicProfile],
        interests: Mapping[str, int],
        expanded_preferences: Mapping[str, Sequence[str]],
    ) -> Dict[str, List[Dict[str, object]]]:
        """
        Assign each video to its best topic using cosine similarity.

        Unknown videos are hidden later, but are classified here so the
        distribution step can stay focused on accepted topic buckets.
        """

        categorized_videos = {topic: [] for topic in topic_profiles}
        categorized_videos["Unknown"] = []

        topic_names = list(topic_profiles.keys())
        topic_matrix = torch.stack(
            [topic_profiles[topic].embedding for topic in topic_names]
        )

        similarity_matrix = torch.matmul(video_embeddings, topic_matrix.T)
        interest_bias = self._build_interest_bias(topic_names, interests, similarity_matrix)
        weighted_similarity_matrix = similarity_matrix * interest_bias

        for video_index, video in enumerate(videos):
            scores = similarity_matrix[video_index]
            weighted_scores = weighted_similarity_matrix[video_index]
            best_index = int(torch.argmax(weighted_scores).item())
            best_topic = topic_names[best_index]
            best_score = float(scores[best_index].item())

            if best_score < self.bge_threshold:
                categorized_videos["Unknown"].append(
                    self._build_unknown_result(
                        video,
                        confidence=best_score,
                        candidate_topic=best_topic,
                    )
                )
                continue

            categorized_videos[best_topic].append(
                self._build_accepted_result(
                    video,
                    topic=best_topic,
                    confidence=best_score,
                    matched_concepts=expanded_preferences.get(best_topic, [best_topic])[:10],
                )
            )

        return categorized_videos

    def _apply_percentage_distribution(
        self,
        categorized_videos: MutableMapping[str, List[Dict[str, object]]],
        interests: Mapping[str, int],
        total_visible: int,
    ) -> List[Dict[str, object]]:
        """
        Keep the existing percentage-distribution logic exactly:
        - target count uses the total incoming video count
        - each topic is handled independently
        - videos beyond the topic quota are hidden
        - unknown videos are always hidden
        """

        final_feed: List[Dict[str, object]] = []

        for topic, percentage in interests.items():
            target_count = int(total_visible * (percentage / 100.0))

            topic_videos = sorted(
                categorized_videos.get(topic, []),
                key=lambda video: float(video["confidence"]),
                reverse=True,
            )

            accepted_videos = topic_videos[:target_count]
            rejected_videos = topic_videos[target_count:]

            for video in accepted_videos:
                video["action"] = "Show"
                final_feed.append(video)

            for video in rejected_videos:
                video["action"] = "Hide"
                final_feed.append(video)

        for video in categorized_videos.get("Unknown", []):
            video["action"] = "Hide"
            final_feed.append(video)

        return final_feed

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
    ) -> Dict[str, object]:
        """Shape an accepted video for the existing frontend contract."""

        result = dict(video)
        result.update(
            {
                "topic": topic,
                "confidence": round(confidence, 3),
                "matched_concepts": list(matched_concepts),
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
    ) -> Dict[str, List[str]]:
        """Normalize expander output and guarantee each topic has concepts."""

        cleaned: Dict[str, List[str]] = {}

        for preference in preferences:
            raw_concepts = expanded_preferences.get(preference, [preference])
            if not isinstance(raw_concepts, list):
                raw_concepts = [preference]

            cleaned[preference] = self._clean_concepts([preference, *raw_concepts])

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

    def _build_interest_bias(
        self,
        topic_names: Sequence[str],
        interests: Mapping[str, int],
        similarity_matrix: torch.Tensor,
    ) -> torch.Tensor:
        """Build a small topic bias tensor for weighted topic selection."""

        bias_values = [
            0.8 + (float(interests.get(topic, 0)) / 500.0)
            for topic in topic_names
        ]
        return torch.tensor(
            bias_values,
            dtype=similarity_matrix.dtype,
            device=similarity_matrix.device,
        )

    def _string_value(self, value: object) -> str:
        """Convert nullable payload fields into safe strings."""

        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        return str(value).strip()
