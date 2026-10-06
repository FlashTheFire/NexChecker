"""handlers/myntra_checker.py — Legacy shim.

All logic has been moved to handlers/checker.py.
This file is kept for backward compatibility only — do NOT add new code here.

Any external code that imports from this module will continue to work:
  from handlers.myntra_checker import MyntraCheckerHandler
  from handlers.myntra_checker import schedule_deferred_cancel, try_immediate_cancel
  from handlers.myntra_checker import safe_edit, _active_sessions, _session_tasks
  from handlers.myntra_checker import _refunded_markup, _result_markup, _stopped_markup, _home_markup
"""
from __future__ import annotations

# Re-export everything from the new location
from handlers.checker import (
    CheckerHandler as MyntraCheckerHandler,
    schedule_deferred_cancel,
    try_immediate_cancel,
    safe_edit,
    make_result_markup      as _result_markup,
    make_refunded_markup    as _refunded_markup,
    make_stopped_markup     as _stopped_markup,
    make_back_markup        as _home_markup,
    make_filter_markup      as _filter_markup,
    make_progress_markup    as _progress_markup,
    make_result_markup_no_cancel as _result_markup_no_cancel,
)

# Legacy session state dicts — these are now per-handler-instance.
# Importing them from here gives a reference to the MYNTRA handler's dicts,
# which is the only thing that ever used them from bot.py.
# NOTE: after refactor, bot.py no longer imports these.
_active_sessions: dict = {}
_session_tasks:   dict = {}
