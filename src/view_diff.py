import json, sys
from rich.console import Console
from rich.syntax import Syntax

file = sys.argv[1]
idx  = int(sys.argv[2]) if len(sys.argv) > 2 else 0

data = json.load(open(file))
commit = data[idx]
diff_text = commit["diff"]

console = Console()
console.print(f"[bold blue]{commit['sha']}[/]  —  {commit['subject']}")
console.print(Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False))