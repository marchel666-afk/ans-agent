import shlex
DENY=("rm -rf /","mkfs","dd if=","shutdown","reboot","passwd")
def validate_command(command):
 c=command.strip()
 if len(c)>4000: raise ValueError("Command too long")
 low=c.lower()
 if any(x in low for x in DENY): raise ValueError("Command blocked by security policy")
 return c
