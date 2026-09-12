class BestOfN:
 def __init__(self,orchestrator): self.orchestrator=orchestrator
 def run(self,task,n=3):
  candidates=[]
  for i in range(max(2,min(n,5))):
   try:candidates.append(self.orchestrator.call("architect",f"Produce independent solution #{i+1} for:\n{task}"))
   except Exception as e:candidates.append("ERROR: "+str(e))
  judge=self.orchestrator.call("judge","Compare candidates, score correctness, completeness, risk and implementation cost. Return the winner and a synthesized plan.\n\n" + "\n\n--- CANDIDATE ---\n".join(candidates))
  return {"status":"completed","candidates":candidates,"judge":judge}
