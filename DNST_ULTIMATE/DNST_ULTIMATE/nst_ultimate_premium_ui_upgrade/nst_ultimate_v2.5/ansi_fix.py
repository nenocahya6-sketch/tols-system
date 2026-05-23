import re
from pathlib import Path
p=Path('nst_gui.py')
t=p.read_text(encoding='utf-8',errors='ignore')
old='message = re.sub(r"\\x1b\\[[0-9;]*m", "", str(message))'
new='message = re.sub(r"\\x1B(?:[@-Z\\\\-_]^|\\[[0-?]*[ -/]*[@-~])", "", str(message))'
t=t.replace(old,new)
p.write_text(t,encoding='utf-8')
