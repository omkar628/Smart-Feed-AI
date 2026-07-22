# SmartFeed AI

SmartFeed AI is a Chrome extension backed by a FastAPI service that reshapes the YouTube home feed around the topics a user actually cares about.

Instead of relying on exact keyword matches, the system expands selected interests into related concepts, compares those concepts against live YouTube recommendations with semantic embeddings, and keeps the videos with the strongest semantic relevance.

## Overview

Most recommendation filters break down when the wording in a video title does not exactly match the user's interests. SmartFeed AI addresses that by using semantic search.

The product flow is simple:

1. The user selects topics inside the Chrome extension, such as `Programming`, `AI`, and `Startups`.
2. The extension reads visible cards from the YouTube home feed.
3. The backend expands each topic into related concepts using Groq.
4. Video metadata and expanded concepts are embedded with `BAAI/bge-base-en-v1.5`.
5. Each video is assigned to the strongest matching topic.
6. Low-confidence matches are removed, and accepted cards are returned in global confidence order.

The result is a more intentional home feed that reflects what the user wants to see right now.

## Before And After

Before filtering, the YouTube home page contains a broad mix of unrelated recommendations.

After SmartFeed AI runs, the feed is narrowed to the user's preferred categories, matched cards are visually highlighted, and off-topic content is removed from view.

This makes the extension especially useful for focused browsing sessions such as study, coding, interview prep, research, or hobby-specific discovery.

## Key Features

- Selected-topic filtering for the YouTube home feed
- Semantic topic matching instead of raw keyword comparison
- Groq-powered preference expansion for richer topic coverage
- FastAPI backend for ranking and classification
- Chrome extension popup for saving selected topics
- Visual AI match badges for accepted videos
- Automatic removal of low-relevance videos
- Railway-ready backend deployment with Docker support

## How It Works

### 1. Preference Capture

The extension popup lets the user choose topics without assigning percentages or weights.

Example:

```json
[
  "Programming",
  "AI",
  "Startups"
]
```

These preferences are stored locally in the browser and used whenever the user opens YouTube.

### 2. Feed Extraction

The content script scans the YouTube home page, extracts newly rendered video cards, and builds a payload containing:

- `video_id`
- `title`
- `channel`
- `description`

### 3. Semantic Expansion

The backend sends the selected interests to Groq and asks for distinct, non-overlapping related concepts for each topic.

For example, `Programming` may expand into concepts such as:

- `Software Development`
- `Coding Tutorial`
- `Python Project`
- `Algorithm Practice`

This improves recall without reducing topical precision.

### 4. Embedding And Matching

SmartFeed AI uses `BAAI/bge-base-en-v1.5` to encode:

- each video as a semantic document
- each topic plus its expanded concepts as a semantic document

The backend then:

- computes cosine similarity between videos and topics
- chooses the best matching topic per video
- keeps videos above the relevance threshold
- hides videos below the relevance threshold
- sorts all accepted videos globally by confidence

### 5. Feed Refinement

Accepted videos remain visible and receive a match badge such as:

```text
PROGRAMMING MATCH 62.7%
```

Rejected videos are removed from the page with a transition, and the remaining cards are reflowed smoothly.

## Architecture

```text
Chrome Extension
  |- popup/
  |  `- collects selected topics
  |- scripts/content.js
  |  `- extracts YouTube cards and applies UI changes
  `- scripts/background.js
     `- sends feed data to the backend

FastAPI Backend
  |- main.py
  |  `- request validation and API endpoints
  |- ml.py
  |  `- semantic ranking pipeline
  `- preference_expander.py
     `- Groq-based topic expansion
```

## Tech Stack

- Chrome Extension Manifest V3
- FastAPI
- Pydantic
- Sentence Transformers
- `BAAI/bge-base-en-v1.5`
- PyTorch
- Groq API
- Docker
- Railway

## Repository Structure

```text
Smart-AI-Filter/
|-- backend/
|   |-- main.py
|   |-- ml.py
|   |-- preference_expander.py
|   |-- requirements.txt
|   |-- requirements.docker.txt
|   `-- Dockerfile
|-- chrome_extension/
|   |-- manifest.json
|   |-- popup/
|   `-- scripts/
`-- README.md
```

## Getting Started

### Prerequisites

- Python 3.10 or newer
- Google Chrome
- A Groq API key

### 1. Run The Backend Locally

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Start the API:

```powershell
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Available endpoints:

- `GET /`
- `GET /health`
- `POST /api/v1/rank-feed`

### 2. Load The Chrome Extension

1. Open `chrome://extensions/`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select the `chrome_extension` folder
5. Open YouTube
6. Configure your selected topics in the extension popup

## API Example

### Request

```json
{
  "interests": [
    "Programming",
    "AI",
    "Startups"
  ],
  "videos": [
    {
      "video_id": "abc123",
      "title": "Top 10 Dynamic Programming Problems",
      "description": "",
      "channel": "CodeBasics"
    }
  ]
}
```

### Response Shape

```json
{
  "ranked_videos": [
    {
      "video_id": "abc123",
      "title": "Top 10 Dynamic Programming Problems",
      "description": "",
      "channel": "CodeBasics",
      "topic": "Programming",
      "confidence": 0.627,
      "matched_concepts": [
        "Programming",
        "Software Development",
        "Coding Tutorial"
      ],
      "action": "Show"
    }
  ]
}
```

## Deployment

The backend is prepared for Railway deployment through `backend/Dockerfile`.

Recommended settings:

- Root directory: repository root
- Dockerfile path: `backend/Dockerfile`

Required environment variables:

- `GROQ_API_KEY`

Notes:

- The Dockerfile supports Railway's injected `PORT`
- A root-level `.dockerignore` keeps the build context smaller
- `/health` can be used as a simple post-deploy health check

## Local Development Notes

- `chrome_extension/scripts/content.js` runs on YouTube pages and processes newly loaded cards
- `chrome_extension/scripts/background.js` tries the deployed Railway API first, then falls back to `http://localhost:8000`
- `backend/ml.py` contains the semantic ranking and threshold logic
- `backend/preference_expander.py` handles concept generation through Groq

## Current Scope

SmartFeed AI currently focuses on the YouTube home feed experience. It is designed to:

- keep high-confidence topic matches visible
- remove low-confidence or off-topic recommendations
- rank accepted videos globally by confidence

It is not yet positioned as a full recommendation replacement or a cross-platform filtering system.

## Troubleshooting

### Backend returns `503`

Check the following:

- `GROQ_API_KEY` is present and valid
- model downloads are allowed in the environment
- the runtime has enough memory for the embedding model

### Extension cannot reach the backend

The extension currently attempts these endpoints:

- `https://smart-ai-filter-production.up.railway.app/api/v1/rank-feed`
- `http://localhost:8000/api/v1/rank-feed`

If both are unavailable, the request will fail.

### No changes appear on YouTube

Check the following:

- the extension is loaded successfully
- your preferences were saved in the popup
- you are on the YouTube home page

## Summary

SmartFeed AI combines a Chrome extension, a FastAPI service, semantic embeddings, and LLM-based preference expansion to turn YouTube's generic home feed into a focused, user-shaped content experience.
