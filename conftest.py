import os
os.environ["USER_REPOSITORY_BACKEND"]="inmemory"
os.environ["REVOKED_TOKEN_STORE_BACKEND"]="inmemory"
os.environ["IDEMPOTENCY_STORE_BACKEND"]="inmemory"