import redis
from WeiDuAdmin.env import CACHE

pool = redis.ConnectionPool(
    host=CACHE['redis']['celery']['host'],
    port=CACHE['redis']['celery']['port'],
    password=CACHE['redis']['celery']['password'],
    db=CACHE['redis']['celery']['db'],
    decode_responses=True
)
redis_pool = redis.Redis(connection_pool=pool)
