import os, secrets, hashlib
TOKEN_FILE=os.getenv("ANS_AUTH_TOKEN_FILE","./data/auth.token")
def get_token():
 os.makedirs(os.path.dirname(os.path.abspath(TOKEN_FILE)),exist_ok=True)
 if os.path.exists(TOKEN_FILE): return open(TOKEN_FILE).read().strip()
 token=secrets.token_urlsafe(32); open(TOKEN_FILE,"w").write(token); os.chmod(TOKEN_FILE,0o600); return token
def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
