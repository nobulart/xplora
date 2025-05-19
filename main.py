from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Serve static files from the 'public' directory
app.mount("/public", StaticFiles(directory="public"), name="public")
# Serve media files from the 'tweets_media' directory
app.mount("/tweets_media", StaticFiles(directory="tweets_media"), name="tweets_media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

sentiment_analyzer = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english", revision="714eb0f")

# Store pre-processed tweets and analysis in memory
pre_processed_tweets = []
pre_processed_analysis = {
    "topics": [],
    "sentiments": [],
    "clusters": [],
    "interests": []
}

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

def perform_sentiment_analysis(texts):
    sentiments = []
    for text in texts:
        if not text.strip():
            sentiments.append('#9E9E9E')  # Neutral color (gray)
            continue
        try:
            result = sentiment_analyzer(text[:512])[0]
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
            sentiments.append(color)
        except Exception as e:
            sentiments.append('#9E9E9E')  # Neutral color (gray)
    return sentiments

def extract_interests(tweet):
    interests = []
    if 'hashtags' in tweet['entities'] and tweet['entities']['hashtags']:
        interests.extend([hashtag['text'].lower() for hashtag in tweet['entities']['hashtags']])
    if 'user_mentions' in tweet['entities'] and tweet['entities']['user_mentions']:
        interests.extend([mention['screen_name'].lower() for mention in tweet['entities']['user_mentions']])
    return interests

def extract_media(tweet):
    media = []
    tweet_id = tweet['id']
    if 'media' in tweet.get('entities', {}):
        for item in tweet['entities']['media']:
            media_url = item.get('media_url_https', item.get('media_url', ''))
            media_identifier = media_url.split('/')[-1].split('.')[0] if media_url else ''
            ext = media_url.split('.')[-1] if media_url else 'jpg'
            media_type = item.get('type', 'photo')
            local_media_path = f"tweets_media/{tweet_id}-{media_identifier}.{ext}"
            if os.path.exists(local_media_path):
                media.append({
                    'url': f"/{local_media_path}",
                    'type': media_type
                })
            else:
                media.append({
                    'url': media_url,
                    'type': media_type
                })
    elif 'extended_entities' in tweet and 'media' in tweet['extended_entities']:
        for item in tweet['extended_entities']['media']:
            if item.get('type') == 'video' or item.get('type') == 'animated_gif':
                media_url = item.get('media_url_https', item.get('media_url', ''))
                media_identifier = media_url.split('/')[-1].split('.')[0] if media_url else ''
                ext = media_url.split('.')[-1] if media_url else 'jpg'
                local_media_path = f"tweets_media/{tweet_id}-{media_identifier}.{ext}"
                if os.path.exists(local_media_path):
                    media.append({
                        'url': f"/{local_media_path}",
                        'type': 'video'
                    })
                else:
                    media.append({
                        'url': media_url,
                        'type': 'video'
                    })
            else:
                media_url = item.get('media_url_https', item.get('media_url', ''))
                media_identifier = media_url.split('/')[-1].split('.')[0] if media_url else ''
                media_type = item.get('type', 'photo')
                ext = media_url.split('.')[-1] if media_url else 'jpg'
                local_media_path = f"tweets_media/{tweet_id}-{media_identifier}.{ext}"
                if os.path.exists(local_media_path):
                    media.append({
                        'url': f"/{local_media_path}",
                        'type': media_type
                    })
                else:
                    media.append({
                        'url': media_url,
                        'type': media_type
                    })
    return media

def process_tweets(file_content):
    tweets = extract_tweets(file_content)
    texts = [preprocess_text(tweet['full_text']) for tweet in tweets]
    sentiments = perform_sentiment_analysis([tweet['full_text'] for tweet in tweets])
    
    enriched_tweets = []
    for idx, (tweet, sentiment) in enumerate(zip(tweets, sentiments)):
        interests = extract_interests(tweet)
        media = extract_media(tweet)
        enriched_tweets.append({
            'id': tweet['id'],
            'full_text': tweet['full_text'],
            'created_at': tweet['created_at'],
            'favorite_count': int(tweet['favorite_count']),
            'retweet_count': int(tweet['retweet_count']),
            'user_mentions': tweet.get('entities', {}).get('user_mentions', []),
            'hashtags': tweet.get('entities', {}).get('hashtags', []),
            'media': media,
            'sentiment': sentiment,
            'interests': interests
        })
    
    return {
        "tweets": enriched_tweets,
        "analysis": {
            "topics": [],
            "sentiments": sentiments,
            "clusters": [],
            "interests": list(set([interest for tweet in enriched_tweets for interest in tweet['interests']]))
        }
    }

# Pre-process tweets.js on startup
async def pre_process_tweets():
    global pre_processed_tweets, pre_processed_analysis
    tweets_file_path = os.path.join("public", "tweets.js")
    if os.path.exists(tweets_file_path):
        with open(tweets_file_path, "rb") as f:
            file_content = f.read()
        result = process_tweets(file_content)
        pre_processed_tweets = result["tweets"]
        pre_processed_analysis = result["analysis"]
    else:
        pass

@app.on_event("startup")
async def startup_event():
    await pre_process_tweets()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global pre_processed_tweets, pre_processed_analysis
    content = await file.read()
    result = process_tweets(content)
    pre_processed_tweets = result["tweets"]
    pre_processed_analysis = result["analysis"]
    return result

@app.get("/tweets")
async def get_tweets(
    query: str = "",
    interest: str = "",
    dateStart: str = "",
    dateEnd: str = "",
    showImages: bool = False,
    showVideos: bool = False,
    showLinks: bool = False
):
    filtered_tweets = pre_processed_tweets

    # Calculate initial min/max dates
    initial_date_range = {}
    if pre_processed_tweets:
        timestamps = [pd.Timestamp(tweet['created_at']).timestamp() * 1000 for tweet in pre_processed_tweets]
        initial_date_range = {
            "minDate": int(min(timestamps)),
            "maxDate": int(max(timestamps))
        }

    if query:
        raw_query = query.lower().strip()
        filtered_tweets = [
            tweet for tweet in filtered_tweets
            if raw_query in tweet['full_text'].lower() or
            any(raw_query in mention['screen_name'].lower() for mention in tweet['user_mentions'])
        ]

    if interest:
        filtered_tweets = [
            tweet for tweet in filtered_tweets
            if interest in tweet['interests']
        ]

    if dateStart and dateEnd:
        try:
            start = int(dateStart)
            end = int(dateEnd)
            filtered_tweets = [
                tweet for tweet in filtered_tweets
                if start <= pd.Timestamp(tweet['created_at']).timestamp() * 1000 <= end
            ]
        except ValueError:
            pass

    if showImages or showVideos or showLinks:
        filtered = []
        for tweet in filtered_tweets:
            matches_filter = False
            if showImages:
                if any(m['type'] == 'photo' for m in tweet['media']):
                    matches_filter = True
            if showVideos:
                if any(
                    m['type'] in ['video', 'animated_gif'] or
                    (m['url'] and ('ext_tw_video_thumb' in m['url'] or 'amplify_video_thumb' in m['url']))
                    for m in tweet['media']
                ):
                    matches_filter = True
            if showLinks:
                if 'http://' in tweet['full_text'] or 'https://' in tweet['full_text']:
                    matches_filter = True
            if matches_filter:
                filtered.append(tweet)
        filtered_tweets = filtered

    filtered_tweets.sort(key=lambda x: pd.Timestamp(x['created_at']), reverse=True)

    return {
        "tweets": filtered_tweets,
        "analysis": pre_processed_analysis,
        "initialDateRange": initial_date_range
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)