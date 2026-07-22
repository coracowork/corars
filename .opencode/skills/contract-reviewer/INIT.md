---
name: contract-reviewer
version: 1.0.0
---

# Initialization

Analyze contracts for red flags, missing clauses, and potential issues. Plain-English explanations of legal terms.

## Structure

This skill contains:
- `SKILL.md` - Main skill prompt with instructions

## Files to Generate

None (prompt-only skill - copy SKILL.md content directly)

## Dependencies

None

## Post-Init Steps

### Claude Code
```bash
# Copy to your skills directory
cp -r contract-reviewer/ ~/.claude/skills/contract-reviewer/
```

### Other AI Assistants
1. Open `SKILL.md`
2. Copy the content after the frontmatter (after the second `---`)
3. Paste into your AI assistant's system prompt or chat

## Compatibility

Tested with: claude, chatgpt, gemini, copilot

## Variables

Customize these placeholders in the skill:

| Variable | Default | Description |
|----------|---------|-------------|
| `{{contract_type}}` | `service-agreement` | Type of contract |

---
Downloaded from [Find Skill.ai](https://findskill.ai)