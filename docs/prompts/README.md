# Prompt Library

All LLM prompts live under this directory so changes can be tracked, reviewed, and rolled back independently from code. Each stage (parsing, cleaning, summarization) stores both system and user templates:

```
prompts/
├── parsing/
│   ├── system.md
│   └── user.md
├── cleaning/
│   ├── system.md
│   └── user.md
└── summarization/
    └── system.md
```

Guidelines:
- Keep templates declarative. When you need to describe behavior or include JSON schema examples, use fenced code blocks.
- Document any version-specific notes (e.g., "requires GPT-4o-mini" or "optimized for internal LLM") at the top of each file.
- When experimenting, copy the current prompt into `docs/prompts/archive/` (optional) so we have a history.
