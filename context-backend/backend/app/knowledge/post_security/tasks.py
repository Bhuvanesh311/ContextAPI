"""
tasks.py

ContextAPI
"""

from __future__ import annotations

from .context import PostSecurityContext
from .service import PostSecurityResult, PostSecurityService


class PostSecurityTask:

    def __init__(self) -> None:
        self._service = PostSecurityService()

    def execute(self, context: PostSecurityContext,) -> PostSecurityResult:
        return self._service.execute(context)