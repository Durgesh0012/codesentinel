"""
CodeSentinel Agent — Specialized Code Review & Bug-Fixing Agent
Powered by Anthropic Claude API

This agent specializes in:
- Deep code review with actionable feedback
- Bug detection and automated fix suggestions
- Security vulnerability scanning
- Performance bottleneck identification
- Refactoring recommendations with explanations
"""

import os
import json
import re
from typing import Optional
from anthropic import Anthropic

# ─── Client ────────────────────────────────────────────────────────────────────
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are CodeSentinel, an elite code review and bug-fixing AI agent.

## Your Specialization
You are laser-focused on three tasks:
1. **Bug Detection** — Find logic errors, null-pointer risks, off-by-one errors, race conditions, and edge-case failures.
2. **Security Analysis** — Identify injection flaws, insecure defaults, exposed secrets, and OWASP Top-10 risks.
3. **Performance Review** — Spot N+1 queries, memory leaks, blocking I/O, and unnecessary recomputation.

## Your Output Format
Always respond in this structured format:

### 🔴 CRITICAL BUGS
List each bug with:
- **Location**: file:line (if known) or description
- **Issue**: What is wrong
- **Fix**: Exact corrected code snippet

### 🟡 WARNINGS
Security or performance concerns that need attention.

### 🟢 SUGGESTIONS
Refactoring and style improvements.

### ✅ SCORE
Rate the code: X/100 with a one-line summary.

## Rules
- Be precise. No vague advice like "consider improving error handling" — show the fix.
- If code is safe and clean, say so confidently.
- Prioritize actionable output over lengthy explanations.
- When fixing bugs, show a before/after diff-style comparison.
- Never hallucinate bugs that aren't there. Accuracy over quantity.
"""

# ─── Conversation Memory ───────────────────────────────────────────────────────
conversation_history: list[dict] = []

def chat(user_message: str, code_context: Optional[str] = None) -> str:
    """
    Send a message to CodeSentinel and get a structured code review response.
    
    Args:
        user_message: The user's question or request
        code_context: Optional code snippet to analyze
    
    Returns:
        Agent's response as a string
    """
    # Build the content — optionally embed code context
    content = user_message
    if code_context:
        content = f"{user_message}\n\n```\n{code_context}\n```"

    conversation_history.append({"role": "user", "content": content})

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=conversation_history,
    )

    assistant_message = response.content[0].text
    conversation_history.append({"role": "assistant", "content": assistant_message})

    return assistant_message


def reset_session():
    """Clear conversation history to start a fresh review session."""
    global conversation_history
    conversation_history = []
    print("🔄 Session reset. Starting fresh code review.")


def review_file(filepath: str) -> str:
    """
    Review a local code file.
    
    Args:
        filepath: Path to the file to review
    
    Returns:
        Agent's full review as a string
    """
    if not os.path.exists(filepath):
        return f"❌ File not found: {filepath}"

    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    ext = os.path.splitext(filepath)[1]
    lang_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".go": "Go", ".rs": "Rust", ".java": "Java", ".cpp": "C++",
        ".c": "C", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    }
    lang = lang_map.get(ext, "code")

    prompt = f"Please review this {lang} file: `{os.path.basename(filepath)}`"
    return chat(prompt, code_context=code)


# ─── CLI Interface ─────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  🛡️  CodeSentinel — AI Code Review Agent")
    print("=" * 60)
    print("Commands:")
    print("  review <filepath>  — Review a local file")
    print("  reset              — Clear session memory")
    print("  exit               — Quit")
    print("  Or just paste code / ask a question directly.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n🧑 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("👋 Goodbye!")
            break

        elif user_input.lower() == "reset":
            reset_session()

        elif user_input.lower().startswith("review "):
            filepath = user_input[7:].strip()
            print(f"\n📂 Reviewing: {filepath}\n")
            response = review_file(filepath)
            print(f"🤖 CodeSentinel:\n{response}")

        else:
            response = chat(user_input)
            print(f"\n🤖 CodeSentinel:\n{response}")


if __name__ == "__main__":
    main()
