from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import gzip
import io
import json
import re
import pandas as pd
from transformers import pipeline
import nltk
from nltk.corpus import stopwords
import uvicorn
import chardet
import os
import logging
import time
import hashlib
import urllib.parse
import urllib.request
import zipfile

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Serve static files from the 'public' directory
app.mount("/public", StaticFiles(directory="public"), name="public")
app.mount("/lib", StaticFiles(directory=os.path.join("public", "lib")), name="lib")
# Serve media files from the 'tweets_media' directory
app.mount("/tweets_media", StaticFiles(directory="tweets_media"), name="tweets_media")
if os.path.exists("twitter-backup/data"):
    app.mount(
        "/backup_media",
        StaticFiles(directory="twitter-backup/data"),
        name="backup_media",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download('stopwords', quiet=True)
stop_words = set(stopwords.words('english'))

sentiment_analyzer = None

# Store pre-processed tweets and analysis in memory
pre_processed_tweets = []
pre_processed_tweets_by_id = {}
pre_processed_analysis = {
    "topics": [],
    "sentiments": [],
    "clusters": [],
    "interests": []
}
pre_processed_date_range = {}
MEDIA_CACHE_DIR = os.path.join("tweets_media", "cache")
PUBLIC_TWEETS_PATH = os.path.join("public", "tweets.js")
COMPRESSED_PUBLIC_TWEETS_PATH = f"{PUBLIC_TWEETS_PATH}.gz"
BACKUP_MEDIA_DIRS = [
    os.path.join("twitter-backup", "data", "tweets_media"),
    os.path.join("twitter-backup", "data", "moments_tweets_media"),
    os.path.join("twitter-backup", "data", "deleted_tweets_media"),
    "tweets_media",
]
startup_status = {
    "state": "idle",
    "message": "Waiting to warm up",
    "progress": 0,
    "processed": 0,
    "total": 0,
    "ready": False,
    "error": None,
    "updatedAt": None,
}

def update_startup_status(**updates):
    startup_status.update(updates)
    startup_status["updatedAt"] = time.time()

def ensure_compressed_tweets_copy():
    """Create or refresh public/tweets.js.gz when public/tweets.js changes."""
    if not os.path.exists(PUBLIC_TWEETS_PATH):
        return False

    if (
        os.path.exists(COMPRESSED_PUBLIC_TWEETS_PATH)
        and os.path.getmtime(COMPRESSED_PUBLIC_TWEETS_PATH)
        >= os.path.getmtime(PUBLIC_TWEETS_PATH)
    ):
        return False

    with open(PUBLIC_TWEETS_PATH, "rb") as source:
        tweets_content = source.read()

    compressed_content = gzip.compress(tweets_content, compresslevel=9, mtime=0)
    with open(COMPRESSED_PUBLIC_TWEETS_PATH, "wb") as compressed:
        compressed.write(compressed_content)

    logger.info(
        "Created compressed tweets archive at %s",
        COMPRESSED_PUBLIC_TWEETS_PATH,
    )
    return True

def extract_tweets_file_content(file_content, filename="tweets.js"):
    """Return tweets.js bytes from a raw, gzip-compressed, or zip archive upload."""
    lower_name = (filename or "").lower()

    if lower_name.endswith(".gz") or file_content.startswith(b"\x1f\x8b"):
        try:
            return gzip.decompress(file_content)
        except OSError as exc:
            raise ValueError("Invalid gzip-compressed tweets.js file") from exc

    if lower_name.endswith(".zip") or zipfile.is_zipfile(io.BytesIO(file_content)):
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as archive:
                tweets_members = [
                    member for member in archive.infolist()
                    if not member.is_dir()
                    and os.path.basename(member.filename).lower() == "tweets.js"
                ]
                if not tweets_members:
                    raise ValueError("Zip archive does not contain tweets.js")
                tweets_member = min(
                    tweets_members,
                    key=lambda member: len(member.filename),
                )
                with archive.open(tweets_member) as zipped_tweets:
                    return zipped_tweets.read()
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid zip archive") from exc

    return file_content

def get_sentiment_analyzer():
    global sentiment_analyzer
    if sentiment_analyzer is None:
        sentiment_analyzer = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            revision="714eb0f",
        )
    return sentiment_analyzer

def preprocess_text(text):
    text = re.sub(r'http\S+|@\S+|#\S+', '', text)
    text = ' '.join(word for word in text.split() if word.lower() not in stop_words)
    return text

def extract_tweets(file_content):
    result = chardet.detect(file_content)
    encoding = result['encoding'] or 'utf-8'
    content = file_content.decode(encoding)

    json_match = re.search(r'window\.YTD\.tweets\.part0\s*=\s*(\[.*\])(?:;)?', content, re.DOTALL)
    if not json_match:
        raise ValueError("Invalid tweets.js format")
    json_content = json_match.group(1)

    try:
        tweets_data = json.loads(json_content)
    except json.JSONDecodeError as e:
        prefix = 'window.YTD.tweets.part0 = '
        start_idx = content.find(prefix)
        if start_idx == -1:
            raise ValueError("Invalid tweets.js format")
        
        json_start = start_idx + len(prefix)
        json_content = content[json_start:]
        brace_count = 0
        json_end = None
        in_quotes = False
        escape_next = False
        for i, char in enumerate(json_content):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_quotes = not in_quotes
                continue
            if in_quotes:
                continue
            if char == '[':
                brace_count += 1
            elif char == ']':
                brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
        
        if json_end is None:
            raise ValueError("Invalid tweets.js format")
        
        json_content = json_content[:json_end].strip()
        try:
            tweets_data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid tweets.js format: JSON parsing failed - {str(e)}")

    return [tweet['tweet'] for tweet in tweets_data]

def interpolate_color(color1, color2, factor):
    """Interpolate between two colors (hex) based on a factor (0 to 1)."""
    r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
    r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def perform_sentiment_analysis(texts, progress_callback=None):
    sentiments = []
    analyzer = get_sentiment_analyzer()
    total = len(texts)
    batch_size = 32

    for batch_start in range(0, total, batch_size):
        batch_texts = texts[batch_start:batch_start + batch_size]
        non_empty_indexes = []
        analyzer_inputs = []

        for offset, text in enumerate(batch_texts):
            if not text.strip():
                sentiments.append('#9E9E9E')  # Neutral color (gray)
            else:
                sentiments.append(None)
                non_empty_indexes.append(batch_start + offset)
                analyzer_inputs.append(text[:512])

        try:
            results = analyzer(analyzer_inputs, batch_size=batch_size) if analyzer_inputs else []
        except Exception:
            results = []

        for result_index, absolute_index in enumerate(non_empty_indexes):
            try:
                result = results[result_index]
                label = result['label']  # 'POSITIVE' or 'NEGATIVE'
                score = result['score']  # Confidence score (0 to 1)

                if label == 'POSITIVE':
                    sentiment_value = 0.5 + (score * 0.5)
                    factor = (sentiment_value - 0.5) * 2
                    color = interpolate_color('#9E9E9E', '#4CAF50', factor)
                else:  # NEGATIVE
                    sentiment_value = score * 0.5
                    factor = sentiment_value * 2
                    color = interpolate_color('#F44336', '#9E9E9E', factor)
                sentiments[absolute_index] = color
            except Exception:
                sentiments[absolute_index] = '#9E9E9E'  # Neutral color (gray)

        idx = min(batch_start + batch_size, total) - 1

        if progress_callback and (idx == 0 or (idx + 1) % 25 == 0 or idx + 1 == total):
            progress_callback(
                "Analyzing sentiment",
                25 + int(((idx + 1) / max(total, 1)) * 60),
                idx + 1,
                total,
            )
    return [sentiment or '#9E9E9E' for sentiment in sentiments]

def make_text_preview(text, limit=180):
    """Return a compact single-line preview for list responses."""
    preview = re.sub(r'\s+', ' ', text).strip()
    if len(preview) <= limit:
        return preview
    return preview[:limit - 3].rstrip() + "..."

def build_tweet_summary(tweet):
    """Return the fields needed for list visualizations."""
    return {
        'id': tweet['id'],
        'text_preview': tweet['text_preview'],
        'created_at': tweet['created_at'],
        'created_ts': tweet['created_ts'],
        'favorite_count': tweet['favorite_count'],
        'retweet_count': tweet['retweet_count'],
        'media': tweet['media'][:1],
        'sentiment': tweet['sentiment'],
    }

def build_analysis_summary():
    """Return analysis fields used by the list UI."""
    return {
        "topics": pre_processed_analysis.get("topics", []),
        "sentiments": [],
        "clusters": pre_processed_analysis.get("clusters", []),
        "interests": pre_processed_analysis.get("interests", []),
    }

def extract_interests(tweet):
    interests = []
    if 'hashtags' in tweet['entities'] and tweet['entities']['hashtags']:
        interests.extend([hashtag['text'].lower() for hashtag in tweet['entities']['hashtags']])
    if 'user_mentions' in tweet['entities'] and tweet['entities']['user_mentions']:
        interests.extend([mention['screen_name'].lower() for mention in tweet['entities']['user_mentions']])
    return interests

def get_backup_media_url(tweet_id, media_identifier, ext):
    """Return a locally served media URL if the archive has this asset."""
    if not media_identifier:
        return None

    candidate_name = f"{tweet_id}-{media_identifier}.{ext}"
    for media_dir in BACKUP_MEDIA_DIRS:
        candidate_path = os.path.join(media_dir, candidate_name)
        if os.path.exists(candidate_path):
            if media_dir.startswith(os.path.join("twitter-backup", "data")):
                relative_path = os.path.relpath(
                    candidate_path,
                    os.path.join("twitter-backup", "data"),
                )
                return f"/backup_media/{relative_path.replace(os.sep, '/')}"
            return f"/{candidate_path.replace(os.sep, '/')}"
    return None

def get_cached_media_url(remote_url):
    """Return an on-demand cache URL for trusted remote media."""
    if not remote_url:
        return ""
    return f"/media-cache?url={urllib.parse.quote(remote_url, safe='')}"

def resolve_media_url(tweet_id, media_url):
    media_identifier = media_url.split('/')[-1].split('.')[0] if media_url else ''
    ext = media_url.split('.')[-1].split('?')[0] if media_url else 'jpg'
    local_url = get_backup_media_url(tweet_id, media_identifier, ext)
    if local_url:
        return local_url
    return get_cached_media_url(media_url)

def extract_media(tweet):
    media = []
    tweet_id = tweet['id']
    if 'media' in tweet.get('entities', {}):
        for item in tweet['entities']['media']:
            media_url = item.get('media_url_https', item.get('media_url', ''))
            media_type = item.get('type', 'photo')
            media.append({
                'url': resolve_media_url(tweet_id, media_url),
                'type': media_type
            })
    elif 'extended_entities' in tweet and 'media' in tweet['extended_entities']:
        for item in tweet['extended_entities']['media']:
            if item.get('type') == 'video' or item.get('type') == 'animated_gif':
                media_url = item.get('media_url_https', item.get('media_url', ''))
                media.append({
                    'url': resolve_media_url(tweet_id, media_url),
                    'type': 'video'
                })
            else:
                media_url = item.get('media_url_https', item.get('media_url', ''))
                media_type = item.get('type', 'photo')
                media.append({
                    'url': resolve_media_url(tweet_id, media_url),
                    'type': media_type
                })
    return media

def process_tweets(file_content, progress_callback=None):
    if progress_callback:
        progress_callback("Reading tweets archive", 5, 0, 0)
    tweets = extract_tweets(file_content)
    total = len(tweets)
    if progress_callback:
        progress_callback("Preparing tweet text", 15, 0, total)
    if progress_callback:
        progress_callback("Loading sentiment model", 20, 0, total)
    sentiments = perform_sentiment_analysis(
        [tweet['full_text'] for tweet in tweets],
        progress_callback=progress_callback,
    )
    
    enriched_tweets = []
    for idx, (tweet, sentiment) in enumerate(zip(tweets, sentiments)):
        interests = extract_interests(tweet)
        media = extract_media(tweet)
        full_text = tweet['full_text']
        user_mentions = tweet.get('entities', {}).get('user_mentions', [])
        hashtags = tweet.get('entities', {}).get('hashtags', [])
        created_ts = int(pd.Timestamp(tweet['created_at']).timestamp() * 1000)
        media_types = {item.get('type') for item in media}
        has_images = 'photo' in media_types
        has_videos = any(
            item.get('type') in ['video', 'animated_gif'] or
            (item.get('url') and (
                'ext_tw_video_thumb' in item['url'] or
                'amplify_video_thumb' in item['url']
            ))
            for item in media
        )
        has_links = 'http://' in full_text or 'https://' in full_text
        enriched_tweets.append({
            'id': tweet['id'],
            'full_text': full_text,
            'text_preview': make_text_preview(full_text),
            'created_at': tweet['created_at'],
            'created_ts': created_ts,
            'favorite_count': int(tweet['favorite_count']),
            'retweet_count': int(tweet['retweet_count']),
            'user_mentions': user_mentions,
            'hashtags': hashtags,
            'media': media,
            'sentiment': sentiment,
            'interests': interests,
            'search_text': full_text.lower(),
            'mention_search_text': ' '.join(
                mention['screen_name'].lower() for mention in user_mentions
            ),
            'has_images': has_images,
            'has_videos': has_videos,
            'has_links': has_links,
        })

        if progress_callback and (idx == 0 or (idx + 1) % 100 == 0 or idx + 1 == total):
            progress_callback("Preparing visualization data", 85 + int(((idx + 1) / max(total, 1)) * 13), idx + 1, total)
    
    enriched_tweets.sort(key=lambda item: item['created_ts'], reverse=True)
    timestamps = [tweet['created_ts'] for tweet in enriched_tweets]

    return {
        "tweets": enriched_tweets,
        "date_range": {
            "minDate": min(timestamps) if timestamps else None,
            "maxDate": max(timestamps) if timestamps else None,
        } if timestamps else {},
        "analysis": {
            "topics": [],
            "sentiments": sentiments,
            "clusters": [],
            "interests": sorted(set(
                interest for tweet in enriched_tweets for interest in tweet['interests']
            ))
        }
    }

def pre_process_tweets_sync():
    global pre_processed_tweets, pre_processed_tweets_by_id
    global pre_processed_analysis, pre_processed_date_range
    compressed_refreshed = ensure_compressed_tweets_copy()
    if os.path.exists(PUBLIC_TWEETS_PATH) or os.path.exists(COMPRESSED_PUBLIC_TWEETS_PATH):
        source_path = (
            PUBLIC_TWEETS_PATH
            if os.path.exists(PUBLIC_TWEETS_PATH)
            else COMPRESSED_PUBLIC_TWEETS_PATH
        )
        source_name = os.path.basename(source_path)
        message = f"Loading {source_name} from public directory"
        if compressed_refreshed:
            message = f"Compressed tweets.js and loading {source_name} from public directory"
        update_startup_status(
            state="warming",
            message=message,
            progress=2,
            processed=0,
            total=0,
            ready=False,
            error=None,
        )
        logger.info("Loading %s from public directory", source_name)
        with open(source_path, "rb") as f:
            file_content = extract_tweets_file_content(f.read(), source_name)
        logger.info("Processing tweets")

        def progress(message, percent, processed, total):
            update_startup_status(
                state="warming",
                message=message,
                progress=percent,
                processed=processed,
                total=total,
                ready=False,
                error=None,
            )

        result = process_tweets(file_content, progress_callback=progress)
        pre_processed_tweets = result["tweets"]
        pre_processed_tweets_by_id = {
            tweet['id']: tweet for tweet in pre_processed_tweets
        }
        pre_processed_analysis = result["analysis"]
        pre_processed_date_range = result["date_range"]
        update_startup_status(
            state="ready",
            message=f"Warmup complete: {len(pre_processed_tweets)} tweets loaded",
            progress=100,
            processed=len(pre_processed_tweets),
            total=len(pre_processed_tweets),
            ready=True,
            error=None,
        )
        logger.info("Tweets processing completed")
    else:
        update_startup_status(
            state="ready",
            message="tweets.js or tweets.js.gz not found in public directory",
            progress=100,
            processed=0,
            total=0,
            ready=True,
            error=None,
        )
        logger.warning("tweets.js or tweets.js.gz not found in public directory")

async def pre_process_tweets():
    try:
        await asyncio.to_thread(pre_process_tweets_sync)
    except Exception as e:
        logger.exception("Startup warmup failed")
        update_startup_status(
            state="error",
            message="Startup warmup failed",
            progress=100,
            ready=False,
            error=str(e),
        )

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Xplora application")
    update_startup_status(
        state="starting",
        message="Starting background warmup",
        progress=0,
        processed=0,
        total=0,
        ready=False,
        error=None,
    )
    asyncio.create_task(pre_process_tweets())

@app.get("/health")
async def health_check():
    """Return a simple readiness response for local startup scripts."""
    return {"status": "ok", "warmup": startup_status}

@app.get("/")
async def root():
    """Serve the frontend shell from the API server."""
    return FileResponse(os.path.join("public", "index.html"))

@app.get("/output.css")
async def output_css():
    return FileResponse(os.path.join("public", "output.css"))

@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join("public", "favicon.ico"))

@app.get("/bmc-logo.svg")
async def bmc_logo():
    return FileResponse(os.path.join("public", "bmc-logo.svg"))

@app.get("/startup-status")
async def get_startup_status():
    return startup_status

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global pre_processed_tweets, pre_processed_tweets_by_id
    global pre_processed_analysis, pre_processed_date_range
    try:
        content = extract_tweets_file_content(await file.read(), file.filename)
        result = process_tweets(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pre_processed_tweets = result["tweets"]
    pre_processed_tweets_by_id = {
        tweet['id']: tweet for tweet in pre_processed_tweets
    }
    pre_processed_analysis = result["analysis"]
    pre_processed_date_range = result["date_range"]
    update_startup_status(
        state="ready",
        message=f"Upload complete: {len(pre_processed_tweets)} tweets loaded",
        progress=100,
        processed=len(pre_processed_tweets),
        total=len(pre_processed_tweets),
        ready=True,
        error=None,
    )
    return {
        "tweets": [build_tweet_summary(tweet) for tweet in pre_processed_tweets],
        "analysis": build_analysis_summary(),
        "initialDateRange": pre_processed_date_range,
        "startupStatus": startup_status
    }

@app.get("/tweets")
async def get_tweets(
    query: str = "",
    queryMode: str = "all",
    interest: str = "",
    dateStart: str = "",
    dateEnd: str = "",
    showImages: bool = False,
    showVideos: bool = False,
    showLinks: bool = False,
    showAll: bool = False,
    sortBy: str = "date",
    sortOrder: str = "desc",
):
    filtered_tweets = pre_processed_tweets

    # Apply query filter
    if query:
        raw_query = query.lower().strip()
        query_terms = [term for term in raw_query.split() if term]
        filtered_tweets = [
            tweet for tweet in filtered_tweets
            if (
                raw_query in tweet['search_text'] or
                raw_query in tweet['mention_search_text'] or
                (
                    queryMode == "any" and
                    any(term in tweet['search_text'] or term in tweet['mention_search_text'] for term in query_terms)
                ) or
                (
                    queryMode != "any" and
                    all(term in tweet['search_text'] or term in tweet['mention_search_text'] for term in query_terms)
                )
            )
        ]

    # Apply interest filter
    if interest:
        filtered_tweets = [
            tweet for tweet in filtered_tweets
            if interest in tweet['interests']
        ]

    # Apply date range filter
    if dateStart and dateEnd:
        try:
            start = int(dateStart)
            end = int(dateEnd)
            filtered_tweets = [
                tweet for tweet in filtered_tweets
                if start <= tweet['created_ts'] <= end
            ]
        except ValueError:
            pass

    # Apply media filters only if showAll is False
    if not showAll and (showImages or showVideos or showLinks):
        filtered = []
        for tweet in filtered_tweets:
            matches_filter = False
            if showImages:
                if tweet['has_images']:
                    matches_filter = True
            if showVideos:
                if tweet['has_videos']:
                    matches_filter = True
            if showLinks:
                if tweet['has_links']:
                    matches_filter = True
            if matches_filter:
                filtered.append(tweet)
        filtered_tweets = filtered

    sort_key_map = {
        "date": lambda tweet: tweet['created_ts'],
        "engagement": lambda tweet: tweet['favorite_count'] + tweet['retweet_count'],
        "likes": lambda tweet: tweet['favorite_count'],
        "retweets": lambda tweet: tweet['retweet_count'],
    }
    sort_key = sort_key_map.get(sortBy, sort_key_map["date"])
    reverse_sort = sortOrder != "asc"
    if sortBy != "date" or sortOrder == "asc":
        filtered_tweets = sorted(filtered_tweets, key=sort_key, reverse=reverse_sort)

    return {
        "tweets": [build_tweet_summary(tweet) for tweet in filtered_tweets],
        "analysis": build_analysis_summary(),
        "initialDateRange": pre_processed_date_range,
        "startupStatus": startup_status
    }

@app.get("/tweets/{tweet_id}")
async def get_tweet(tweet_id: str):
    tweet = pre_processed_tweets_by_id.get(tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Tweet not found")

    return {
        key: value
        for key, value in tweet.items()
        if key not in {"search_text", "mention_search_text"}
    }

@app.get("/media-cache")
async def media_cache(url: str):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Unsupported media URL")
    if parsed.netloc not in {"pbs.twimg.com", "video.twimg.com"}:
        raise HTTPException(status_code=400, detail="Unsupported media host")

    os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)
    ext = os.path.splitext(parsed.path)[1] or ".jpg"
    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cache_path = os.path.join(MEDIA_CACHE_DIR, f"{cache_key}{ext}")

    if not os.path.exists(cache_path):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Xplora/1.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                content = response.read()
            with open(cache_path, "wb") as cache_file:
                cache_file.write(content)
        except Exception as exc:
            logger.warning("Failed to cache remote media %s: %s", url, exc)
            raise HTTPException(status_code=502, detail="Could not retrieve media")

    return RedirectResponse(url=f"/tweets_media/cache/{os.path.basename(cache_path)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
