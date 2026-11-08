from slowapi import Limiter
from slowapi.util import get_remote_address

# Behind a proxy, uvicorn --proxy-headers makes request.client the real client IP.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
