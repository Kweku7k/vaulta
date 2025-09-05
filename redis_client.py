import os
from dotenv import load_dotenv
import redis

load_dotenv() 

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

r = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,   # get strings, not bytes
)