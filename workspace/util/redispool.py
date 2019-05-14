import redis
from WeiDuAdmin.env import CACHE

pool = redis.ConnectionPool(
    host=CACHE['celery']['host'],
    port=CACHE['celery']['port'],
    password=CACHE['celery']['password'],
    db=CACHE['celery']['db'],
    decode_responses=True
)
redis_pool = redis.Redis(connection_pool=pool)
