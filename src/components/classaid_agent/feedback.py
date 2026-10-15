# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Feedback generation for student questions (user-triggered / "passive" triggers).

The request thread records the question and resolves the LLM configuration (which
depends on the logged-in user and class); a background job then reads the student's
effective mode *when processing starts* and either suppresses feedback (Silent),
reports a configuration error, or generates feedback of the mode's type (Auto
selects heuristic or technical first).  Every attempt leaves a classaid_generations
record and an event, so it can later be reconstructed why which help was given.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import msgspec

from components.classaid_core import JobOwner, submit_job
from components.classaid_core.api import ClassContext
from components.classaid_core.jobs import JobFn
from components.classaid_core.log import log_event
from components.classaid_tasks.data import get_task
from components.classaid_tasks.model import TaskConfig
from components.classaid_tasks.runner import RunResult
from components.classaid_tasks.runs import student_result
from gened.db import get_db
from gened.llm import (
    LLM,
    ChatMessage,
    LLMConfigError,
    NoKeyFoundError,
    NoTokensError,
    get_llm,
)

from . import prompts
from .messages import MessageInfo, Thread, add_message, conversation_before
from .modes import EffectiveMode, get_effective_mode

FeedbackType = Literal['heuristic', 'technical']

SILENT_NOTICE = "AI feedback is currently paused by your instructor.  Keep working: try tracing your code or running the tests."
NO_KEY_NOTICE = "Your instructor has not set up the AI service for this class yet, so AI feedback is not available."
ERROR_NOTICE = "The AI assistant could not respond right now.  Please try again in a moment."

_TEMPLATES: dict[FeedbackType, tuple[str, str]] = {
    'heuristic': (prompts.HEURISTIC_USER, prompts.HEURISTIC_USER_VERSION),
    'technical': (prompts.TECHNICAL_USER, prompts.TECHNICAL_USER_VERSION),
}


class Selection(msgspec.Struct, kw_only=True):
    selected_type: FeedbackType
    reason: str
    fallback: bool = False


class ModelCall(msgspec.Struct, kw_only=True):
    purpose: Literal['select', 'generate']
    prompt_version: str
    messages: list[dict[str, str]]
    raw: dict[str, Any]
    text: str
    latency_ms: int

    @property
    def failed(self) -> bool:
        return 'error' in self.raw


@dataclass(frozen=True)
class FeedbackInput:
    """ Everything the model may see for one question: student-visible material only
    (never the instructor's tests).
    """
    task: TaskConfig
    files: dict[str, str]
    last_result: dict[str, Any] | None
    history: list[dict[str, str]]
    question: str

    def messages(self, instructions: str) -> list[ChatMessage]:
        messages: list[ChatMessage] = [{'role': 'system', 'content': f"{prompts.SYSTEM}\n\n{instructions}"}]
        for h in self.history:
            if h['role'] == 'assistant':
                messages.append({'role': 'assistant', 'content': h['content']})
            else:
                messages.append({'role': 'user', 'content': h['content']})
        messages.append({'role': 'user', 'content': prompts.context_message(self.task, self.files, self.last_result, self.question)})
        return messages


class Outcome(msgspec.Struct, kw_only=True):
    status: Literal['generated', 'suppressed', 'failed']
    calls: list[ModelCall] = msgspec.field(default_factory=list)
    selection: Selection | None = None
    selected_type: FeedbackType | None = None
    prompt_version: str | None = None
    text: str | None = None
    error: str | None = None


def resolve_llm() -> tuple[LLM | None, str | None]:
    """ (llm, None) or (None, error kind).  Must run in the request (it uses the logged-in user/class). """
    try:
        return get_llm(use_system_key=False, spend_token=False), None
    except (NoKeyFoundError, NoTokensError):
        return None, 'no_key'
    except LLMConfigError as e:
        return None, type(e).__name__


def last_run_result(user_id: int, task_id: int) -> dict[str, Any] | None:
    """ The student-visible version of the student's latest Run / Run Tests result on the task. """
    row = get_db().execute("""
        SELECT payload FROM classaid_events
        WHERE user_id=? AND task_id=? AND type IN ('run', 'test_run') AND json_extract(payload, '$.result') IS NOT NULL
        ORDER BY id DESC LIMIT 1
    """, [user_id, task_id]).fetchone()
    if row is None:
        return None
    result = msgspec.convert(msgspec.json.decode(row['payload'])['result'], RunResult)
    return student_result(result)


def call_model(llm: LLM, purpose: Literal['select', 'generate'], version: str, messages: list[ChatMessage]) -> ModelCall:
    start = time.monotonic()
    raw, text = asyncio.run(llm.get_completion(messages=messages))
    return ModelCall(
        purpose=purpose, prompt_version=version,
        messages=[{'role': str(m['role']), 'content': str(m.get('content', ''))} for m in messages],
        raw=raw, text=text, latency_ms=int((time.monotonic() - start) * 1000),
    )


_JSON_OBJECT_RE = re.compile(r'\{.*\}', re.DOTALL)


def parse_selection(text: str) -> Selection | None:
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        return msgspec.json.decode(match.group(0), type=Selection)
    except (msgspec.DecodeError, msgspec.ValidationError):
        return None


def fallback_selection(last_result: dict[str, Any] | None) -> Selection:
    """ Deterministic Auto-mode choice used when the selection call fails or is unparseable:
    concrete compile/runtime errors -> technical; otherwise heuristic.
    """
    status = (last_result or {}).get('status')
    if status in ('compile_error', 'runtime_error'):
        return Selection(selected_type='technical', reason=f"Fallback rule: latest result is a {status}.", fallback=True)
    return Selection(selected_type='heuristic', reason="Fallback rule: no compile or runtime error in the latest result.", fallback=True)


def generate(llm: LLM, eff: EffectiveMode, fb: FeedbackInput) -> Outcome:
    """ Generate feedback for a non-Silent mode (Auto selects the type first). """
    calls: list[ModelCall] = []
    selection: Selection | None = None
    if eff.mode == 'auto':
        select_call = call_model(llm, 'select', prompts.AUTO_SELECT_VERSION, fb.messages(prompts.AUTO_SELECT))
        calls.append(select_call)
        selection = (None if select_call.failed else parse_selection(select_call.text)) or fallback_selection(fb.last_result)
        feedback_type: FeedbackType = selection.selected_type
    else:
        assert eff.mode in ('heuristic', 'technical')
        feedback_type = eff.mode

    template, version = _TEMPLATES[feedback_type]
    call = call_model(llm, 'generate', version, fb.messages(template))
    calls.append(call)
    if call.failed or not call.text:
        return Outcome(status='failed', calls=calls, selection=selection, selected_type=feedback_type,
                       prompt_version=version, error=str(call.raw.get('error', 'empty response')))
    return Outcome(status='generated', calls=calls, selection=selection, selected_type=feedback_type,
                   prompt_version=version, text=call.text)


@dataclass(frozen=True)
class QuestionJob:
    """ The (JSON-serializable) job request for one question. """
    ctx: ClassContext
    task_id: int
    progress_id: int
    question_id: int
    trigger_event_id: int
    question: str
    files: dict[str, str]

    def to_request(self) -> dict[str, Any]:
        return msgspec.to_builtins(self)  # type: ignore[no-any-return]

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> 'QuestionJob':
        return msgspec.convert(request, cls)


def make_feedback_job(llm: LLM | None, llm_error: str | None) -> JobFn:
    """ The job function for one question.  `llm` (with its key) is captured in the closure,
    so keys never enter the job record.
    """
    def feedback_job(_job_id: int, request: dict[str, Any]) -> dict[str, Any]:
        job = QuestionJob.from_request(request)
        task = get_task(job.task_id, job.ctx.class_id, available_only=False)
        if task is None:
            msg = f"Task {job.task_id} no longer exists."
            raise RuntimeError(msg)
        eff = get_effective_mode(job.ctx.class_id, job.ctx.user_id)  # the mode when processing starts
        start = time.monotonic()

        if eff.mode == 'silent':
            outcome = Outcome(status='suppressed')
        elif llm is None:
            outcome = Outcome(status='failed', error=llm_error or 'llm_unavailable')
        else:
            fb = FeedbackInput(
                task=task,
                files=job.files,
                last_result=last_run_result(job.ctx.user_id, job.task_id),
                history=conversation_before(job.progress_id, job.question_id),
                question=job.question,
            )
            outcome = generate(llm, eff, fb)

        latency_ms = int((time.monotonic() - start) * 1000)
        model = llm.shortname if llm and outcome.calls else None
        return record_outcome(job, eff, outcome, model, latency_ms)

    return feedback_job


def record_outcome(job: QuestionJob, eff: EffectiveMode, outcome: Outcome, model: str | None, latency_ms: int) -> dict[str, Any]:
    """ Store the generation record, the reply (AI message or notice), and an event -- atomically. """
    ctx = job.ctx
    db = get_db()
    cur = db.execute("""
        INSERT INTO classaid_generations
            (user_id, class_id, task_id, question_id, trigger_event_id, effective_mode, mode_source, status,
             selected_type, selection, model, prompt_version, calls, displayed_text, error, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ctx.user_id, ctx.class_id, job.task_id, job.question_id, job.trigger_event_id,
        eff.mode, eff.source, outcome.status, outcome.selected_type,
        msgspec.json.encode(outcome.selection).decode() if outcome.selection else None,
        model, outcome.prompt_version, msgspec.json.encode(outcome.calls).decode(), outcome.text, outcome.error, latency_ms,
    ])
    generation_id = cur.lastrowid
    assert generation_id is not None

    thread = Thread(job.progress_id, ctx.user_id, ctx.class_id, job.task_id)
    if outcome.status == 'generated':
        assert outcome.text is not None
        info = MessageInfo(feedback_type=outcome.selected_type, origin='user_triggered', reply_to=job.question_id, generation_id=generation_id)
        message_id = add_message(thread, 'assistant', outcome.text, info)
        event_type = 'feedback_generated'
    elif outcome.status == 'suppressed':
        info = MessageInfo(notice_kind='silent', reply_to=job.question_id, generation_id=generation_id)
        message_id = add_message(thread, 'notice', SILENT_NOTICE, info)
        event_type = 'feedback_suppressed'
    else:
        info = MessageInfo(notice_kind='error', reply_to=job.question_id, generation_id=generation_id)
        message_id = add_message(thread, 'notice', NO_KEY_NOTICE if outcome.error == 'no_key' else ERROR_NOTICE, info)
        event_type = 'feedback_failed'

    log_event(ctx, event_type, task_id=job.task_id, payload={
        'generation_id': generation_id,
        'question_id': job.question_id,
        'message_id': message_id,
        'effective_mode': eff.mode,
        'mode_source': eff.source,
        'selected_type': outcome.selected_type,
        'error': outcome.error,
    })
    db.commit()
    return {'generation_id': generation_id, 'message_id': message_id, 'status': outcome.status}


def submit_question(ctx: ClassContext, task: TaskConfig, progress_id: int, files: dict[str, str], question: str) -> tuple[int, int]:
    """ Record the student's question and schedule feedback generation.
    Returns (question message id, job id).
    """
    assert task.row_id is not None
    db = get_db()
    question_id = add_message(Thread(progress_id, ctx.user_id, ctx.class_id, task.row_id), 'student', question)
    event_id = log_event(ctx, 'question', task_id=task.row_id, payload={'message_id': question_id, 'question': question}, files=files)
    db.commit()

    llm, llm_error = resolve_llm()
    job = QuestionJob(ctx=ctx, task_id=task.row_id, progress_id=progress_id, question_id=question_id,
                      trigger_event_id=event_id, question=question, files=files)
    job_id = submit_job('feedback', 'llm', make_feedback_job(llm, llm_error), job.to_request(), JobOwner(ctx.user_id, ctx.class_id, task.row_id))
    return question_id, job_id
