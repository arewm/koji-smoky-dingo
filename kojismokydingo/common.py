# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, see <http://www.gnu.org/licenses/>.


"""
Koji Smoky Dingo - Common Utils

Some simple functions used by the other modules.

:author: Christopher O'Brien <obriencj@gmail.com>
:license: GPL v3
"""


import re

from collections import OrderedDict
from fnmatch import fnmatchcase
from six.moves import filter, filterfalse, range, zip_longest


def unique(sequence):
    """
    Given a sequence, de-duplicate it into a new list, preserving order.

    :param sequence: series of hashable objects
    :type sequence: list

    :rtype: list
    """

    return list(OrderedDict.fromkeys(sequence))


def chunkseq(seq, chunksize):
    """
    Chop up a sequence into sub-sequences of up-to chunksize in length.

    :param seq: a sequence to chunk up
    :type seq: list

    :param chunksize: max length for chunks
    :type chunksize: int

    :rtype: iterator[list]
    """

    try:
        seqlen = len(seq)
    except TypeError:
        seq = list(seq)
        seqlen = len(seq)

    return (seq[offset:offset + chunksize] for
            offset in range(0, seqlen, chunksize))


def fnmatches(s, patterns, ignore_case=False):
    """
    Checks s against multiple glob patterns. Returns True if any match.

    :param s: string to be matched
    :type s: str

    :param patterns: list of patterns
    :type patterns: list[str]

    :param ignore_case: if True case is normalized, Default False
    :type ignore_case: bool, optional

    :rtype: bool
    """

    if ignore_case:
        s = s.lower()
        patterns = [p.lower() for p in patterns]

    for pattern in patterns:
        if fnmatchcase(s, pattern):
            return True

    return False


def globfilter(seq, patterns,
               key=None, invert=False, ignore_case=False):
    """
    Generator yielding members of sequence seq which match any of the
    glob patterns specified.

    Patterns must be a list of glob-style pattern strings.

    If key is specified, it must be a unary callable which translates a
    given sequence item into a string for comparison with the patterns.

    If invert is True, yields the non-matches rather than the matches.

    If ignore_case is True, the pattern comparison is case normalized.

    :param seq: series of objects to be filtered. Normally strings, but
    may be any type provided the key parameter is specified to provide
    a string for matching based on the given object.
    :type seq: list

    :param patterns: list of glob-style pattern strings. Members of
    seq which match any of these patterns are yielded.
    :type patterns: list[str]

    :param key: A unary callable which translates individual items on
    seq into the value to be matched against the patterns. Default, None
    :type key: Callable[[obj], str], optional

    :param invert: Invert the logic, yield the non-matches rather than
    the matches. Default, False
    :type invert: bool, optional

    :param ignore_case: pattern comparison is case normalized if
    True. Default, False
    :type ignore_case: bool, optional

    :rtype: Iterable[obj]
    """

    def test(s):
        return fnmatches(key(s) if key else s,
                         patterns, ignore_case=ignore_case)

    return filterfalse(test, seq) if invert else filter(test, seq)


def _rpm_str_split(s, _split=re.compile(r"(~?(?:\d+|[a-zA-Z]+))").split):
    """
    Split an E, V, or R string for comparison by its segments
    """

    return tuple(i for i in _split(s) if (i.isalnum() or i.startswith("~")))


def _rpm_str_compare(left, right):
    left = _rpm_str_split(left)
    right = _rpm_str_split(right)

    for lp, rp in zip_longest(left, right, fillvalue=""):

        # Special comparison for tilde segments
        if lp.startswith("~"):
            # left is tilde

            if rp.startswith("~"):
                # right also is tilde, let's just chop off the tilde
                # and fall through to non-tilde comparisons below

                lp = lp[1:]
                rp = rp[1:]

            else:
                # right is not tilde, therefore right is greater
                return -1

        elif rp.startswith("~"):
            # left is not tilde, but right is, therefore left is greater
            return 1

        # Special comparison for digits vs. alphabetical
        if lp.isdigit():
            # left is numeric

            if rp.isdigit():
                # left and right are both numeric, convert and fall
                # through
                lp = int(lp)
                rp = int(rp)

            else:
                # right is alphabetical or absent, left is greater
                return 1

        elif rp.isdigit():
            # left is alphabetical but right is not, right is greater
            return -1

        # Final comparison for segment
        if lp == rp:
            # left and right are equivalent, check next segment
            continue
        else:
            # left and right are not equivalent
            return 1 if lp > rp else -1

    else:
        # ran out of segments to check, must be equivalent
        return 0


def rpm_evr_compare(left_evr, right_evr):
    """
    Compare two (Epoch, Version, Release) tuples.

    Returns  1 if left_evr is greater-than right_evr
             0 if left_evr is equal-to right_evr
            -1 if left_evr is less-than right_evr

    :rtype: int
    """

    for lp, rp in zip_longest(left_evr, right_evr, fillvalue="0"):
        if lp == rp:
            # fast check to potentially skip all the matching
            continue

        compared = _rpm_str_compare(lp, rp)
        if compared:
            # non zero comparison for segment, done checking
            return compared

    else:
        # ran out of segments to check, must be equivalent
        return 0


class NEVRCompare(object):
    """
    An adapter for Name, Epoch, Version, Release comparisons of a
    build info dictionary. Used by the nevr_sort_builds function.
    """

    def __init__(self, binfo):
        self.build = binfo
        self.n = binfo["name"]

        evr = (binfo["epoch"], binfo["version"], binfo["release"])
        self.evr = tuple(("0" if x is None else str(x)) for x in evr)


    def __cmp__(self, other):
        # cmp is a python2-ism, and has no replacement in python3 via
        # six, so we'll have to create our own simplistic behavior
        # similarly

        if self.n == other.n:
            return rpm_evr_compare(self.evr, other.evr)

        elif self.n < other.n:
            return -1

        else:
            return 1


    def __eq__(self, other):
        return self.__cmp__(other) == 0


    def __lt__(self, other):
        return self.__cmp__(other) < 0


    def __gt__(self, other):
        return self.__cmp__(other) > 0


#
# The end.
