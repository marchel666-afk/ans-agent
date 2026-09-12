import os
import uvicorn
if __name__=="__main__":
    uvicorn.run("app:app",host=os.getenv("ANS_HOST","127.0.0.1"),port=int(os.getenv("ANS_PORT","8080")),reload=False)
