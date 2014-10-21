
"""
Exposes utility functions.

"""

from contextlib import contextmanager
import logging
import timeit


log = logging.getLogger("wineds")


@contextmanager
def time_it(task_desc):
    """
    A context manager for timing chunks of code and logging it.

    Arguments:
      task_desc: task description for logging purposes

    """
    start_time = timeit.default_timer()
    yield
    elapsed = timeit.default_timer() - start_time
    log.info("elapsed (%s): %.4f seconds" % (task_desc, elapsed))
