
"""
Exposes utility functions.

"""

from collections import OrderedDict
from contextlib import contextmanager
import json
import logging
import timeit


REPORTING_INDEX_ALL = 0
REPORTING_INDEX_ELD = 1
REPORTING_INDEX_VBM = 2

REPORTING_INDICES_SIMPLE = (REPORTING_INDEX_ALL, )
REPORTING_INDICES_COMPLETE = (REPORTING_INDEX_ELD, REPORTING_INDEX_VBM)

_log = logging.getLogger("wineds")


class EqualityMixin:

    def __eq__(self, other):
        if type(self) != type(other):
            return False

        for name in self.equality_attrs:
            if getattr(self, name) != getattr(other, name):
                return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)


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


def prettify(obj):
    return json.dumps(obj, indent=4)


def assert_equal(actual, expected, desc=None):
    if actual == expected:
        return
    info = OrderedDict()
    if desc is not None:
        info['desc'] = desc
    info.update([
        ("actual", actual),
        ("expected", expected),
    ])
    msg = "value does not match expected:\n>>> {0}".format(prettify(info))
    raise AssertionError(msg)


def add_to_set(_set, value, set_name):
    if value in _set:
        return False
    _log.info("adding to {0}: {1}".format(set_name, value))
    _set.add(value)
    return True


def add_to_dict(mapping, key, value, desc=None):
    """Return whether a value was added."""
    try:
        old_value = mapping[key]
    except KeyError:
        mapping[key] = value
        return True
    # Otherwise, confirm that the new value matches the old.
    assert_equal(value, old_value, desc=desc)

    return False


@contextmanager
def time_it(task_desc):
    """
    A context manager for timing chunks of code and logging it.

    Arguments:
      task_desc: task description for logging purposes

    """
    start_time = timeit.default_timer()
    _log.info("begin: %s..." % task_desc)
    yield
    elapsed = timeit.default_timer() - start_time
    _log.info("elapsed (%s): %.4f seconds" % (task_desc, elapsed))
