from sentence_transformers import SentenceTransformer, CrossEncoder, util
from preference_expander import PreferenceExpander
import torch


class AIRanker:

    def __init__(self):

        print("Loading AI Models...")

        # ========================================================
        # STAGE 1: BGE EMBEDDING MODEL
        # ========================================================

        self.model = SentenceTransformer(
            "BAAI/bge-base-en-v1.5"
        )

        # ========================================================
        # STAGE 2: CROSS-ENCODER
        # ========================================================

        self.cross_encoder = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L6-v2"
        )

        # ========================================================
        # ACCEPTANCE THRESHOLDS
        # ========================================================
        #
        # A video must pass BOTH thresholds.
        #
        # BGE:
        # Broad semantic similarity / candidate retrieval.
        #
        # Cross-Encoder:
        # More detailed relevance verification.
        #
        # ========================================================

        self.bge_threshold = 0.50

        self.cross_encoder_threshold = -7.0

        # Number of strongest BGE concepts sent
        # to the Cross-Encoder.

        self.top_k = 3

        # Groq preference expander.

        self.expander = PreferenceExpander()

        # ========================================================
        # CACHE COMPLETE PREFERENCE SETS
        # ========================================================

        self.preference_cache = {}


    # ============================================================
    # GET ALL EXPANDED PREFERENCES
    # ============================================================

    def get_expanded_preferences(self, preferences):

        # Create stable cache key.

        cache_key = tuple(

            sorted(

                preferences,

                key=str.lower

            )

        )


        # ========================================================
        # CHECK CACHE
        # ========================================================

        if cache_key in self.preference_cache:

            print(

                f"Using cached preference set: "
                f"{list(cache_key)}"

            )

            return self.preference_cache[cache_key]


        # ========================================================
        # CALL GROQ ONCE FOR ALL PREFERENCES
        # ========================================================

        print(

            f"Expanding preference set: "
            f"{preferences}"

        )


        expanded_preferences = (

            self.expander.expand_preferences(

                preferences

            )

        )


        # ========================================================
        # SAVE RESULT IN CACHE
        # ========================================================

        self.preference_cache[cache_key] = (

            expanded_preferences

        )


        return expanded_preferences


    # ============================================================
    # RANK VIDEOS
    # ============================================================

    def rank_videos(self, videos, interests):

        if not videos:

            return []


        # ========================================================
        # 1. PREPARE VIDEO TEXT
        # ========================================================

        video_texts = [

            (

                f"Title: {video['title']}. "

                f"Channel: {video['channel']}."

            )

            for video in videos

        ]


        # ========================================================
        # 2. GET USER INTEREST TOPICS
        # ========================================================

        interest_topics = list(

            interests.keys()

        )


        # ========================================================
        # 3. EXPAND ALL PREFERENCES
        # ========================================================

        expanded_preferences = (

            self.get_expanded_preferences(

                interest_topics

            )

        )


        # ========================================================
        # 4. GENERATE VIDEO EMBEDDINGS
        # ========================================================

        video_embeddings = self.model.encode(

            video_texts,

            convert_to_tensor=True

        )


        # ========================================================
        # 5. PREPARE CONCEPT EMBEDDINGS
        # ========================================================

        topic_data = {}


        for topic in interest_topics:

            concepts = expanded_preferences.get(

                topic,

                [topic]

            )


            concept_embeddings = self.model.encode(

                concepts,

                convert_to_tensor=True

            )


            topic_data[topic] = {

                "concepts": concepts,

                "embeddings": concept_embeddings

            }


        # ========================================================
        # 6. CREATE CATEGORY BUCKETS
        # ========================================================

        categorized_videos = {

            topic: []

            for topic in interest_topics

        }


        categorized_videos["Unknown"] = []


        # ========================================================
        # 7. ANALYZE EVERY VIDEO
        # ========================================================

        for video_index, video in enumerate(videos):

            video_embedding = video_embeddings[

                video_index

            ]


            topic_scores = {}


            # ====================================================
            # COMPARE VIDEO AGAINST EVERY USER INTEREST
            # ====================================================

            for topic in interest_topics:

                concepts = topic_data[

                    topic

                ]["concepts"]


                concept_embeddings = topic_data[

                    topic

                ]["embeddings"]


                # =================================================
                # BGE COSINE SIMILARITY
                # =================================================

                similarity_scores = util.cos_sim(

                    video_embedding,

                    concept_embeddings

                )[0]


                # =================================================
                # FIND TOP-K CONCEPTS
                # =================================================

                number_of_scores = len(

                    similarity_scores

                )


                actual_k = min(

                    self.top_k,

                    number_of_scores

                )


                top_values, top_indices = torch.topk(

                    similarity_scores,

                    k=actual_k

                )


                # =================================================
                # WEIGHTED TOP-K BGE SCORE
                # =================================================

                weights = torch.tensor(

                    [0.60, 0.25, 0.15],

                    device=top_values.device

                )


                weights = weights[:actual_k]


                weights = (

                    weights /

                    weights.sum()

                )


                final_topic_score = (

                    top_values * weights

                ).sum().item()


                # =================================================
                # SAVE STRONGEST CONCEPTS
                # =================================================

                matched_concepts = [

                    {

                        "concept":

                            concepts[index.item()],

                        "score":

                            round(

                                score.item(),

                                3

                            )

                    }

                    for score, index in zip(

                        top_values,

                        top_indices

                    )

                ]


                topic_scores[topic] = {

                    "score":

                        final_topic_score,

                    "matched_concepts":

                        matched_concepts

                }


            # ====================================================
            # 8. FIND BEST TOPIC USING BGE
            # ====================================================

            best_topic = max(

                topic_scores,

                key=lambda topic:

                    topic_scores[topic]["score"]

            )


            best_score = topic_scores[

                best_topic

            ]["score"]


            best_concepts = topic_scores[

                best_topic

            ]["matched_concepts"]


            # ====================================================
            # 9. PREPARE VIDEO TEXT FOR CROSS-ENCODER
            # ====================================================

            video_text = (

                f"Title: {video['title']}. "

                f"Channel: {video['channel']}."

            )


            # ====================================================
            # 10. CREATE CROSS-ENCODER PAIRS
            # ====================================================

            cross_encoder_pairs = [

                (

                    video_text,

                    match["concept"]

                )

                for match in best_concepts

            ]


            # ====================================================
            # 11. RUN CROSS-ENCODER
            # ====================================================

            cross_encoder_scores = (

                self.cross_encoder.predict(

                    cross_encoder_pairs

                )

            )


            # ====================================================
            # 12. SAVE CROSS-ENCODER RESULTS
            # ====================================================

            cross_encoder_results = []


            for match, score in zip(

                best_concepts,

                cross_encoder_scores

            ):

                cross_encoder_results.append({

                    "concept":

                        match["concept"],

                    "bge_score":

                        match["score"],

                    "cross_encoder_score":

                        float(score)

                })


            # ====================================================
            # 13. FIND BEST CROSS-ENCODER RESULT
            # ====================================================

            best_cross_encoder_result = max(

                cross_encoder_results,

                key=lambda result:

                    result["cross_encoder_score"]

            )


            best_cross_encoder_score = (

                best_cross_encoder_result[

                    "cross_encoder_score"

                ]

            )


            best_cross_encoder_concept = (

                best_cross_encoder_result[

                    "concept"

                ]

            )


            # ====================================================
            # 14. SHOW DEBUG INFORMATION
            # ====================================================

            print("\n" + "=" * 70)


            print(

                f"VIDEO: {video['title']}"

            )


            print(

                f"BGE BEST TOPIC: {best_topic}"

            )


            print(

                f"BGE WEIGHTED SCORE: "
                f"{best_score:.3f}"

            )


            print(

                f"BGE THRESHOLD: "
                f"{self.bge_threshold:.3f}"

            )


            print(

                "\nBGE MATCHED CONCEPTS:"

            )


            for match in best_concepts:

                print(

                    f"   {match['concept']}"

                    f" → {match['score']:.3f}"

                )


            print(

                "\nCROSS-ENCODER RESULTS:"

            )


            for result in cross_encoder_results:

                print(

                    f"   {result['concept']}"

                    f" → "

                    f"{result['cross_encoder_score']:.3f}"

                )


            print(

                f"\nBEST CROSS-ENCODER CONCEPT: "

                f"{best_cross_encoder_concept}"

            )


            print(

                f"BEST CROSS-ENCODER SCORE: "

                f"{best_cross_encoder_score:.3f}"

            )


            print(

                f"CROSS-ENCODER THRESHOLD: "

                f"{self.cross_encoder_threshold:.3f}"

            )


            # ====================================================
            # 15. CHECK BOTH THRESHOLDS
            # ====================================================

            passed_bge = (

                best_score >= self.bge_threshold

            )


            passed_cross_encoder = (

                best_cross_encoder_score

                >=

                self.cross_encoder_threshold

            )


            print(

                f"\nBGE CHECK: "

                f"{'PASS' if passed_bge else 'FAIL'}"

            )


            print(

                f"CROSS-ENCODER CHECK: "

                f"{'PASS' if passed_cross_encoder else 'FAIL'}"

            )


            # ====================================================
            # 16. FINAL ACCEPTANCE DECISION
            # ====================================================
            #
            # BOTH models must agree.
            #
            # BGE FAIL → UNKNOWN
            #
            # Cross-Encoder FAIL → UNKNOWN
            #
            # BOTH PASS → ACCEPTED
            #
            # ====================================================

            if (

                passed_bge

                and

                passed_cross_encoder

            ):


                video_data = {

                    **video,

                    "topic":

                        best_topic,

                    "confidence":

                        round(

                            best_score,

                            3

                        ),

                    "cross_encoder_score":

                        round(

                            best_cross_encoder_score,

                            3

                        ),

                    "cross_encoder_concept":

                        best_cross_encoder_concept,

                    "cross_encoder_results":

                        cross_encoder_results,

                    "matched_concepts":

                        best_concepts

                }


                categorized_videos[

                    best_topic

                ].append(

                    video_data

                )


                print(

                    "FINAL RESULT: ACCEPTED"

                )


            else:


                video_data = {

                    **video,

                    "topic":

                        "Unknown",

                    "confidence":

                        round(

                            best_score,

                            3

                        ),

                    "candidate_topic":

                        best_topic,

                    "cross_encoder_score":

                        round(

                            best_cross_encoder_score,

                            3

                        ),

                    "cross_encoder_concept":

                        best_cross_encoder_concept,

                    "cross_encoder_results":

                        cross_encoder_results,

                    "matched_concepts":

                        best_concepts

                }


                categorized_videos[

                    "Unknown"

                ].append(

                    video_data

                )


                # ================================================
                # SHOW EXACT REJECTION REASON
                # ================================================

                if not passed_bge:

                    print(

                        "REJECTION REASON: BGE FAILED"

                    )


                elif not passed_cross_encoder:

                    print(

                        "REJECTION REASON: CROSS-ENCODER FAILED"

                    )


                print(

                    "FINAL RESULT: UNKNOWN"

                )


        # ========================================================
        # 17. APPLY USER PERCENTAGE DISTRIBUTION
        # ========================================================

        total_visible = len(videos)


        final_feed = []


        for topic, percentage in interests.items():

            target_count = int(

                total_visible *

                (percentage / 100.0)

            )


            # ====================================================
            # SORT ACCEPTED VIDEOS
            # ====================================================
            #
            # Primary sorting:
            # BGE confidence.
            #
            # Secondary sorting:
            # Cross-Encoder score.
            #
            # ====================================================

            topic_videos = sorted(

                categorized_videos[topic],

                key=lambda video: (

                    video["confidence"],

                    video["cross_encoder_score"]

                ),

                reverse=True

            )


            # ====================================================
            # VIDEOS INSIDE PERCENTAGE LIMIT
            # ====================================================

            accepted = topic_videos[

                :target_count

            ]


            for video in accepted:

                video["action"] = "Show"

                final_feed.append(

                    video

                )


            # ====================================================
            # VIDEOS EXCEEDING PERCENTAGE LIMIT
            # ====================================================

            rejected = topic_videos[

                target_count:

            ]


            for video in rejected:

                video["action"] = "Hide"

                final_feed.append(

                    video

                )


        # ========================================================
        # 18. HIDE UNKNOWN VIDEOS
        # ========================================================

        for video in categorized_videos["Unknown"]:

            video["action"] = "Hide"

            final_feed.append(

                video

            )


        return final_feed