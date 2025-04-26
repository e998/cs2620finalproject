import redis
import json
import datetime

# Connect to local Redis server
r = redis.Redis(host='localhost', port=5000, db=0, decode_responses=True)

LOG_KEY = "log_list"  # Key, all logs are stored

def add_log(message):
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "event": message
    }
    r.rpush(LOG_KEY, json.dumps(log_entry))  # JSON string to Redis list

def collect_logs():
    logs = r.lrange(LOG_KEY, 0, -1)  # All logs
    return [json.loads(log) for log in logs]

def clear_logs():
    r.delete(LOG_KEY)