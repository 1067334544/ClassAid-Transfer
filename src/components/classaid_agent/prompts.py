# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Feedback prompts for the ClassAid TA Agent (CS2 / Java adaptation).

Correspondence to the ClassAid paper (CHI '26) and deliberate differences:

- SYSTEM (system.v1): the context-setting prompt of §4.2.4 (1) ("a helpful and
  encouraging teaching assistant for a Vega-Lite data visualization course..."),
  rewritten for a CS2 data structures course in Java.

- HEURISTIC_USER (heuristic.user.v1): §4.2.4 (2) user-triggered heuristic feedback
  ("one open-ended question, 2-3 concise thinking prompts, an optional code snippet,
  and a supportive tone (under 100 words)"), Table 2 (Socratic / constructivist), and
  Appendix F "Heuristic Mode" rules ("encourage self-correction and exploration
  without directly giving answers").  Added for the CS2 setting: the optional snippet
  is limited to 5 lines and must not be a complete solution or a corrected method.

- TECHNICAL_USER (technical.user.v1): §4.2.4 (3) user-triggered technical feedback
  ("a detailed explanation of the issue, a complete code correction, and reasoning for
  why it works") and Appendix F Case 2 (user-initiated technical prompt).

- AUTO_SELECT (auto.select.v1): Appendix G (selecting heuristic vs. technical feedback),
  using its decision principles ("Apply level or above, mostly logic/design errors,
  steady progress -> heuristic; lower levels, frequent syntax errors, inconsistent
  progress -> technical").

Differences from the paper, recorded in design.md:
  * P1 generates ONE response of the selected type; the paper generates three
    candidates per type (six in Auto) and ranks them (Appendix F/G).  Added in P2.
  * Auto selection here is one model call applying Appendix G's principles; the
    weighted scheme (50/20/30) computed in code, Bloom-level and error analyses, and
    candidate ranking (40/20/20/15/5) arrive with the six-stage pipeline in P2.
  * Responses may use Markdown with fenced code blocks (the ClassAid workspace renders
    Markdown); the paper's Appendix F prompts require plain text.
  * Proactive (auto-triggered) templates are not part of P1.

Changing any template text requires bumping its version id; generation records store
the version used.
"""

from components.classaid_tasks.model import TaskConfig

SYSTEM_VERSION = 'system.v1'
SYSTEM = """\
You are a helpful and encouraging teaching assistant for a CS2 data structures course taught in Java. \
Students are working on short programming tasks during class, and the instructor decides what kind of \
help you give.  Base your help on the task, the student's current code, and their latest run or test \
results.  Never reveal or guess at the instructor's hidden tests.  Respond in the same language as the \
student's question."""

HEURISTIC_USER_VERSION = 'heuristic.user.v1'
HEURISTIC_USER = """\
FEEDBACK MODE: HEURISTIC.  Guide the student to find and fix the problem themselves.

Write your reply as:
- one open-ended question that points the student toward the source of the problem;
- two or three concise thinking prompts (e.g., what to trace, which case to test, what a variable holds at a given moment);
- optionally, a code snippet of at most 5 lines that illustrates an idea;
- a supportive tone.

Rules:
- Keep it under 100 words.
- Do NOT give a complete solution, a corrected version of the student's method, or code that completes the task.
- If the student asks you to just give the answer, do not; instead help them take the next step themselves."""

TECHNICAL_USER_VERSION = 'technical.user.v1'
TECHNICAL_USER = """\
FEEDBACK MODE: TECHNICAL.  Give direct, task-specific help so the student can move forward.

In your reply:
1. Directly answer the student's question, explaining the cause of the problem.
2. Give concrete steps to fix it, with working Java code (a complete correction of the relevant code is allowed).
3. Explain why the corrected code works for this task.
4. Build on what the student has already written and asked.

Keep explanations concise.  Use fenced code blocks for code."""

AUTO_SELECT_VERSION = 'auto.select.v1'
AUTO_SELECT = """\
You are deciding which kind of feedback best fits a student's current situation, before any feedback is written.

- HEURISTIC feedback guides the student with questions and hints, without giving the solution.
- TECHNICAL feedback explains the problem directly and gives corrected code.

Decision principles:
- Prefer HEURISTIC if the student is working at the Apply level of Bloom's taxonomy or above, has mostly logic or design errors, and is making steady progress, or if the question is vague and the student would benefit from reflecting first.
- Prefer TECHNICAL if the student is at a lower cognitive level, has frequent syntax or compile errors, shows inconsistent progress or is stuck on the same error, or the issue is a concrete, obvious fix.

Answer with only a JSON object, no other text:
{"selected_type": "heuristic" or "technical", "reason": "<one or two sentences explaining the choice>"}"""


def format_files(files: dict[str, str]) -> str:
    return '\n\n'.join(f"// File: {name}\n{content}" for name, content in sorted(files.items()))


def format_result(result: dict[str, object] | None) -> str:
    """ A compact, student-visible summary of the latest Run / Run Tests result. """
    if result is None:
        return "The student has not run their code yet."
    lines = [f"Latest {'test run' if result.get('kind') == 'tests' else 'run'}: status {result.get('status')}"]
    compile_info = result.get('compile')
    if isinstance(compile_info, dict):
        for d in compile_info.get('diagnostics', []):
            where = f"{d['file']}:{d['line']}:{d['column']}" if d.get('file') else "(in the instructor's tests)"
            lines.append(f"  compile {d['kind']} at {where}: {d['message']}")
    exception = result.get('exception')
    if isinstance(exception, dict):
        frames = ', '.join(f"{f['file']}:{f['line']}" for f in exception.get('frames', []))
        lines.append(f"  exception {exception['type']}: {exception.get('message')} at {frames or '(no student frames)'}")
    tests = result.get('tests')
    if isinstance(tests, list):
        for t in tests:
            message = f" -- {t['message']}" if t.get('message') else ''
            lines.append(f"  test {t['name']}: {t['status']}{message}")
        lines.append(f"  score: {result.get('score')} / 5")
    if result.get('kind') == 'run' and result.get('stdout'):
        lines.append(f"  program output:\n{str(result['stdout'])[:2000]}")
    if result.get('limit_exceeded'):
        lines.append(f"  limit exceeded: {result['limit_exceeded']}")
    return '\n'.join(lines)


def context_message(task: TaskConfig, files: dict[str, str], last_result: dict[str, object] | None, question: str) -> str:
    """ The final user message: task (student-visible parts only), current code, latest result, and the question. """
    parts = [
        f"<task title=\"{task.name}\">\n{task.spec.description}\n</task>",
    ]
    if task.spec.examples:
        parts.append(f"<examples>\n{task.spec.examples}\n</examples>")
    parts += [
        f"<student_code>\n{format_files(files)}\n</student_code>",
        f"<latest_result>\n{format_result(last_result)}\n</latest_result>",
        f"<student_question>\n{question}\n</student_question>",
    ]
    return '\n\n'.join(parts)


__all__ = [
    "AUTO_SELECT",
    "AUTO_SELECT_VERSION",
    "HEURISTIC_USER",
    "HEURISTIC_USER_VERSION",
    "SYSTEM",
    "SYSTEM_VERSION",
    "TECHNICAL_USER",
    "TECHNICAL_USER_VERSION",
    "context_message",
    "format_result",
]
