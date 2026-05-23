import re
from pathlib import Path
p=Path("nst_gui.py")
t=p.read_text(encoding="utf-8",errors="ignore")
t=t.replace(chr(27),"")
p.write_text(t,encoding="utf-8")
