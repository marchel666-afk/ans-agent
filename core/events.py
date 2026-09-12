import asyncio
class EventBus:
    def __init__(self): self.queues={}
    def subscribe(self,sid):
        q=asyncio.Queue(); self.queues.setdefault(sid,[]).append(q); return q
    def publish(self,sid,event):
        for q in self.queues.get(sid,[]): q.put_nowait(event)
    def close(self,sid): self.queues.pop(sid,None)
