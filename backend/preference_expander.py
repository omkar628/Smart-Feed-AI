import os
import json
import time

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


class PreferenceExpander:

    def __init__(self):

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY was not found in the .env file."
            )

        self.client = Groq(api_key=api_key)

        print("Groq Preference Expander initialized.")


    # ============================================================
    # EXPAND ALL PREFERENCES TOGETHER
    # ============================================================

    def expand_preferences(self, preferences):

        if not preferences:
            return {}

        # Remove duplicates while preserving order.

        preferences = list(dict.fromkeys(preferences))


        prompt = f"""
You are helping build an AI-powered semantic YouTube feed filter.

The user has selected these interests:

{json.dumps(preferences, indent=2)}

Your job is to generate semantic concepts for EACH user interest.

The concepts will later be used by an embedding model to classify
YouTube videos.

IMPORTANT:

All user interests are being classified at the same time.

Therefore, concepts belonging to different interests should be as
distinct and non-overlapping as reasonably possible.

For each preference, generate exactly 30 concepts.

RULES:

1. Include the original preference.

2. Include directly related:
   - topics
   - subtopics
   - terminology
   - technologies
   - activities
   - content types

3. Concepts should help identify actual YouTube video titles.

4. Avoid vague concepts.

5. Avoid overly broad concepts.

6. Avoid concepts that could incorrectly match unrelated YouTube videos.

7. Do NOT add a concept to one preference if it primarily belongs
   to another user preference.

8. Reduce semantic overlap between the different preferences.

9. Think about all preferences together before generating concepts.

10. Each concept must be meaningful on its own.

11. Return ONLY a valid JSON object.

12. Do not use markdown.

13. Do not provide explanations.


EXAMPLE INPUT:

[
    "DSA",
    "editing",
    "music"
]


EXAMPLE OUTPUT:

{{
    "DSA": [
        "DSA",
        "Data Structures and Algorithms",
        "LeetCode",
        "Coding Interview Problems",
        "Competitive Programming",
        "Algorithm Analysis",
        "Time Complexity",
        "Space Complexity",
        "Arrays",
        "Linked Lists",
        "Stacks",
        "Queues",
        "Hash Tables",
        "Binary Trees",
        "Binary Search Trees",
        "Heaps",
        "Graphs",
        "Graph Algorithms",
        "Breadth-First Search",
        "Depth-First Search",
        "Dynamic Programming",
        "Greedy Algorithms",
        "Recursion",
        "Backtracking",
        "Sorting Algorithms",
        "Searching Algorithms",
        "Sliding Window",
        "Two Pointers",
        "Disjoint Set Union",
        "Topological Sorting"
    ],

    "editing": [
        "editing",
        "Video Editing",
        "Adobe After Effects",
        "Adobe Premiere Pro",
        "DaVinci Resolve",
        "Motion Graphics",
        "Motion Design",
        "Visual Effects",
        "VFX Tutorial",
        "Video Transitions",
        "Color Grading",
        "Cinematic Editing",
        "Timeline Editing",
        "Keyframe Animation",
        "Masking",
        "Rotoscoping",
        "Compositing",
        "Green Screen Editing",
        "Text Animation",
        "Logo Animation",
        "3D Motion Design",
        "Video Effects",
        "Editing Workflow",
        "Video Editing Tutorial",
        "After Effects Tutorial",
        "Premiere Pro Tutorial",
        "DaVinci Resolve Tutorial",
        "Motion Graphics Tutorial",
        "Cinematic Video Editing",
        "Post Production"
    ],

    "music": [
        "music",
        "Songs",
        "Music Videos",
        "Official Audio",
        "Official Music Video",
        "Albums",
        "Singles",
        "Hip Hop Music",
        "Rap Music",
        "Pop Music",
        "Rock Music",
        "Electronic Music",
        "Classical Music",
        "Jazz Music",
        "R&B Music",
        "Indie Music",
        "Instrumental Music",
        "Live Music Performance",
        "Concert Performance",
        "Music Artist",
        "Singer",
        "Rapper",
        "Band",
        "Album Release",
        "Song Release",
        "Music Playlist",
        "Lyric Video",
        "Acoustic Performance",
        "Remix",
        "Music Track"
    ]
}}


Now generate concepts for these user preferences:

{json.dumps(preferences, indent=2)}
"""


        max_retries = 3


        # ========================================================
        # CALL GROQ
        # ========================================================

        for attempt in range(max_retries):

            try:

                print(
                    f"Calling Groq for preferences: "
                    f"{preferences} "
                    f"(Attempt {attempt + 1}/{max_retries})"
                )


                response = self.client.chat.completions.create(

                    model="llama-3.3-70b-versatile",

                    messages=[

                        {
                            "role": "system",
                            "content": (
                                "You generate distinct semantic concepts "
                                "for an AI-powered YouTube recommendation "
                                "system. You must consider all user "
                                "preferences together and minimize concept "
                                "overlap between categories. Always return "
                                "only valid JSON."
                            )
                        },

                        {
                            "role": "user",
                            "content": prompt
                        }

                    ],

                    temperature=0.1

                )


                raw_text = (
                    response
                    .choices[0]
                    .message
                    .content
                    .strip()
                )


                # =================================================
                # REMOVE POSSIBLE MARKDOWN
                # =================================================

                raw_text = raw_text.replace(
                    "```json",
                    ""
                )

                raw_text = raw_text.replace(
                    "```",
                    ""
                )

                raw_text = raw_text.strip()


                # =================================================
                # CONVERT JSON INTO PYTHON DICTIONARY
                # =================================================

                try:

                    expanded_preferences = json.loads(
                        raw_text
                    )

                except json.JSONDecodeError:

                    print(
                        "Groq returned invalid JSON:"
                    )

                    print(raw_text)

                    continue


                # =================================================
                # VALIDATE RESPONSE
                # =================================================

                if not isinstance(
                    expanded_preferences,
                    dict
                ):

                    print(
                        "Groq response was not a dictionary."
                    )

                    continue


                cleaned_preferences = {}


                # =================================================
                # CLEAN EVERY PREFERENCE
                # =================================================

                for preference in preferences:


                    # Try exact key first.

                    concepts = expanded_preferences.get(
                        preference
                    )


                    # If exact key was not found,
                    # try case-insensitive matching.

                    if concepts is None:

                        for key, value in expanded_preferences.items():

                            if (
                                key.lower()
                                == preference.lower()
                            ):

                                concepts = value

                                break


                    # If Groq forgot the preference,
                    # use original preference.

                    if not isinstance(concepts, list):

                        print(
                            f"No valid concepts returned for "
                            f"'{preference}'. Using fallback."
                        )

                        cleaned_preferences[
                            preference
                        ] = [preference]

                        continue


                    cleaned_concepts = []


                    # =============================================
                    # CLEAN CONCEPT STRINGS
                    # =============================================

                    for concept in concepts:

                        if isinstance(concept, str):

                            concept = concept.strip()

                            if concept:

                                cleaned_concepts.append(
                                    concept
                                )


                    # =============================================
                    # REMOVE DUPLICATES INSIDE CATEGORY
                    # =============================================

                    unique_concepts = []

                    seen_concepts = set()


                    for concept in cleaned_concepts:

                        normalized = concept.lower()


                        if normalized not in seen_concepts:

                            seen_concepts.add(
                                normalized
                            )

                            unique_concepts.append(
                                concept
                            )


                    # =============================================
                    # MAKE SURE ORIGINAL PREFERENCE EXISTS
                    # =============================================

                    preference_exists = any(

                        concept.lower()
                        == preference.lower()

                        for concept in unique_concepts

                    )


                    if not preference_exists:

                        unique_concepts.insert(
                            0,
                            preference
                        )


                    # Keep maximum 30 concepts.

                    unique_concepts = unique_concepts[:30]


                    cleaned_preferences[
                        preference
                    ] = unique_concepts


                # =================================================
                # PRINT RESULTS
                # =================================================

                print(
                    "\nSuccessfully expanded all preferences."
                )


                for preference, concepts in (
                    cleaned_preferences.items()
                ):

                    print(
                        f"\nEXPANDED {preference}:"
                    )


                    for concept in concepts:

                        print(
                            f"  - {concept}"
                        )


                print()


                return cleaned_preferences


            # ====================================================
            # HANDLE API ERROR
            # ====================================================

            except Exception as error:

                print(
                    f"Groq API error on attempt "
                    f"{attempt + 1}: {error}"
                )


                if attempt < max_retries - 1:

                    wait_time = 2 ** attempt


                    print(
                        f"Waiting {wait_time} seconds "
                        f"before retry..."
                    )


                    time.sleep(
                        wait_time
                    )


        # ========================================================
        # FALLBACK
        # ========================================================

        print(
            f"Groq failed after {max_retries} attempts."
        )


        print(
            "Using original preferences as fallback."
        )


        return {

            preference: [preference]

            for preference in preferences

        }