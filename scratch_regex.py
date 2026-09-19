import re

# Better NO_BUILTIN patterns -- greedy capture of word token before optional paren
patterns = [
    # "do not use max()"  -- capture word right before optional paren
    re.compile(r"\b(?:do\s+not|don'?t|never)\s+use\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*\(?", re.I),
    # "do not use the max function"
    re.compile(r"\b(?:do\s+not|don'?t|avoid)\s+use\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+(?:function|method|builtin|built-in)", re.I),
]

tests = [
    "Do not use max()",
    "Don't use sorted()",
    "Do not use the max function",
    "Do not use numpy",
]

for text in tests:
    for p in patterns:
        m = p.search(text)
        if m:
            print(f"{text!r} -> {m.group(1)!r}  (pattern: {p.pattern[:50]})")
            break
    else:
        print(f"{text!r} -> NO MATCH")
