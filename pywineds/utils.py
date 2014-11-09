
"""
Exposes utility functions.

"""

from contextlib import contextmanager
import logging
import timeit


REPORTING_INDEX_ALL = 0
REPORTING_INDEX_ELD = 1
REPORTING_INDEX_VBM = 2

REPORTING_INDICES_SIMPLE = (REPORTING_INDEX_ALL, )
REPORTING_INDICES_COMPLETE = (REPORTING_INDEX_ELD, REPORTING_INDEX_VBM)

log = logging.getLogger("wineds")


# This method allows the reporting type field to be either
# "TC-Election Day Reporting" or "Election Day".
def get_reporting_index(reporting_field):
    if not reporting_field:
        reporting_index = REPORTING_INDEX_ALL
    elif "Election Day" in reporting_field:
        reporting_index = REPORTING_INDEX_ELD
    elif "VBM" in reporting_field:
        reporting_index = REPORTING_INDEX_VBM
    else:
        raise Exception("unrecognized reporting-type field: %r" % reporting_field)
    return reporting_index


@contextmanager
def time_it(task_desc):
    """
    A context manager for timing chunks of code and logging it.

    Arguments:
      task_desc: task description for logging purposes

    """
    start_time = timeit.default_timer()
    log.info("begin: %s..." % task_desc)
    yield
    elapsed = timeit.default_timer() - start_time
    log.info("elapsed (%s): %.4f seconds" % (task_desc, elapsed))
