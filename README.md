# Xplora

Xplora is a compact web app for exploring an X/Twitter archive. It loads a
default compressed `tweets.js` archive from `public/tweets.js.gz`, processes it
with a FastAPI backend, and presents the results as an interactive bubble cloud
or card grid.

## Features

- Default startup archive from `public/tweets.js.gz`
- Automatic gzip refresh when a local `public/tweets.js` is newer
- Manual uploads for `tweets.js`, `tweets.js.gz`, and `.zip` archives containing
  `tweets.js`
- Bubble, radial cloud, timeline, and card views
- Search, interest, date, media, and sort filters
- Scientific palette controls for coloring bubbles by engagement, likes,
  retweets, date, or media type
- Persisted UI preferences with `localStorage`
- Larger tweet detail modal for desktop and UHD displays
- Server-side processed archive caching and client-side API response caching
- Optional local media resolution from `twitter-backup/data` or `tweets_media`

## Repository Data Policy

The repository is intended to contain app code plus the compact default archive:

- Commit: `public/tweets.js.gz`
- Do not commit: raw `public/tweets.js`
- Do not commit: extracted Twitter archives, media folders, logs, pid files,
  scratch analysis JSON, local caches, or `node_modules`

The raw archive may live locally at `public/tweets.js`. On startup, Xplora
creates or refreshes `public/tweets.js.gz` if the compressed copy is missing or
older than the raw file. Docker builds exclude the raw file and include the gzip
copy.

## Project Structure

```text
xplora/
├── Dockerfile
├── README.md
├── main.py
├── manage_app.sh
├── requirements.txt
├── public/
│   ├── index.html
│   ├── output.css
│   ├── tweets.js.gz
│   ├── favicon.ico
│   ├── bmc-logo.svg
│   └── lib/react-window.umd.min.js
└── tweets_media/.gitkeep
```

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run both local servers:

```bash
./manage_app.sh start
```

Open `http://127.0.0.1:3000`.

Stop them with:

```bash
./manage_app.sh stop
```

## Single-Port App Server

The FastAPI server can also serve the frontend directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Docker

Build:

```bash
docker buildx build -t sunbear73/xplora:latest .
```

Run:

```bash
docker run --rm -p 8000:8000 sunbear73/xplora:latest
```

Open `http://127.0.0.1:8000`.

Publish:

```bash
docker push sunbear73/xplora:latest
```

The image is designed to ship with `public/tweets.js.gz` and without raw archive
or volatile user data.

## Railway

Railway deploys from the root `Dockerfile` and reads `railway.toml` for
deployment settings. The container command listens on Railway's injected `PORT`
environment variable, falling back to `8000` locally. The configured healthcheck
path is `/health`, which returns HTTP 200 as soon as the FastAPI server is live;
archive warmup continues in the background and can be watched at
`/startup-status`.

Deploy from a linked Railway project:

```bash
railway up
```

Recommended Railway settings:

- Builder: Dockerfile
- Healthcheck path: `/health`
- Healthcheck timeout: 300 seconds or higher for slower cold starts
- Public service port: Railway-managed `PORT`

## API

- `GET /health`: service status and warmup state
- `GET /startup-status`: current archive warmup progress
- `POST /upload`: upload `tweets.js`, `tweets.js.gz`, or a `.zip` containing
  `tweets.js`
- `GET /tweets`: filtered tweet summaries
- `GET /tweets/{tweet_id}`: full tweet detail
- `GET /media-cache?url=...`: optional local cache/proxy endpoint for trusted
  remote media URLs; the default UI loads remote media directly in the browser
  so Railway does not pay image/video bandwidth

Common `/tweets` query parameters:

- `query`
- `queryMode`: `all` or `any`
- `interest`
- `dateStart`
- `dateEnd`
- `showImages`
- `showVideos`
- `showLinks`
- `sortBy`: `date`, `engagement`, `likes`, `retweets`
- `sortOrder`: `asc` or `desc`

## Performance Notes

Xplora intentionally avoids heavyweight ML processing during startup. Archive
warmup parses and enriches tweet metadata only, then stores processed results in
`/tmp/xplora-cache` by default. The Docker image precomputes the bundled archive
cache at build time under `/app/.cache/xplora`, so production containers can load
ready-to-serve summaries immediately. API responses use ETags and browser-side
`localStorage` caching so repeat UI loads can paint from cache while the server
revalidates data in the background.

Railway cost controls:

- The image uses a small Python slim base and installs only FastAPI, Uvicorn,
  multipart upload support, and their direct dependencies.
- Uvicorn runs one worker, disables access logs, and defaults app logging to
  warnings through `XPLORA_LOG_LEVEL=WARNING`.
- The frontend stops polling `/startup-status` after warmup completes.
- The bundled archive cache is prebuilt during Docker build, reducing cold-start
  CPU on Railway.
