from __future__ import annotations

from typing import Any, Awaitable, Callable, Coroutine, TypeVar
from anyio import create_task_group, from_thread, get_cancelled_exc_class
from collections import deque
from app.core.meta import SingletonMeta

T = TypeVar("T")


class TaskQueue(metaclass=SingletonMeta):
    """A thread-safe task queue for handling coroutines from synchronous code.

    This queue allows coroutines to be enqueued from synchronous code and executed
    within FastAPI's event loop using AnyIO primitives. It maintains the event loop
    context and prevents blocking.
    """

    def __init__(self) -> None:
        self._queue: deque[Callable[[], Awaitable[Any]]] = deque()
        self._running = False

    def enqueue(self, coro: Coroutine[Any, Any, T]) -> None:
        """
        Enqueue a coroutine to be executed asynchronously.
        This method is thread-safe and can be called from synchronous code.

        Args:
            coro: The coroutine to be executed
        """
        # Wrap the coroutine in a function to prevent it from starting immediately
        self._queue.append(lambda: coro)

        # If the queue isn't being processed, start processing
        if not self._running:
            self._running = True
            # Use AnyIO's from_thread to safely run in the event loop
            from_thread.run(self._process_queue)

    async def _process_queue(self) -> None:
        """Process queued coroutines within a task group."""
        try:
            async with create_task_group() as tg:
                while self._queue:
                    # Get the next coroutine from the queue
                    coro_fn = self._queue.popleft()

                    # Create an async wrapper function that awaits the coroutine
                    async def run_coro() -> None:
                        await coro_fn()

                    # Start the wrapper function in the task group
                    tg.start_soon(run_coro)
        except get_cancelled_exc_class():
            # Handle cancellation gracefully
            pass
        finally:
            self._running = False
