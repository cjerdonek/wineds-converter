
"""
Exposes utility functions.

"""

from contextlib import contextmanager
import logging
import timeit


REPORTING_TYPE_ALL = ""
REPORTING_TYPE_ELD = "TC-Election Day Reporting"
REPORTING_TYPE_VBM = "TC-VBM Reporting"

REPORTING_KEYS_SIMPLE = (REPORTING_TYPE_ALL, )
REPORTING_KEYS_COMPLETE = (REPORTING_TYPE_ELD, REPORTING_TYPE_VBM)

REPORTING_INDICES = {
    REPORTING_TYPE_ALL: 0,
    REPORTING_TYPE_ELD: 1,
    REPORTING_TYPE_VBM: 2,
}

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