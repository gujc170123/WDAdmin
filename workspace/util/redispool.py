import redis
from WeiDuAdmin.env import CACHE

pool = redis.ConnectionPool(
    host=CACHE['redis']['default']['host'],
    port=CACHE['redis']['default']['port'],
    password=CACHE['redis']['default']['password'],
    db=CACHE['redis']['default']['db'],
    decode_responses=True
)
redis_pool = redis.Redis(connection_pool=pool)
