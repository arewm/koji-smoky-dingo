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


from __future__ import print_function

import sys

from abc import ABCMeta, abstractmethod
from argparse import ArgumentParser
from collections import OrderedDict
from functools import partial
from koji import Fault, GenericError
from koji_cli.lib import activate_session
from os.path import basename
from six import add_metaclass
from six.moves import range as xrange, zip as izip


class BadDingo(Exception):
    complaint = "Something bad"


class NoSuchTag(BadDingo):
    complaint = "No such tag"


class NoSuchTask(BadDingo):
    complaint = "No such task"


class NoSuchBuild(BadDingo):
    complaint = "No such build"


class NoSuchUser(BadDingo):
    complaint = "No such user"


class PermissionException(BadDingo):
    complaint = "Insufficient permissions"


printerr = partial(print, file=sys.stderr)


def unique(sequence):
    return list(OrderedDict((s, None) for s in sequence))


def chunkseq(seq, chunksize):
    try:
        seqlen = len(seq)
    except TypeError:
        seq = list(seq)
        seqlen = len(seq)

    return (seq[offset:offset + chunksize] for
            offset in xrange(0, seqlen, chunksize))


def _bulk_load(session, loadfn, keys, size):
    for key_chunk in chunkseq(keys, size):
        session.multicall = True

        for key, info in izip(key_chunk, session.multiCall()):
            if info:
                if "faultCode" in info:
                    raise session.convertFault(Fault(**info))
                else:
                    yield key, info[0]
            else:
                yield key, None


def bulk_load_builds(session, nvrs, err=True, size=100, results=None):
    results = OrderedDict() if results is None else results

    for key, info in _bulk_load(session, session.getBuild, nvrs, size):
        if err and not info:
            raise NoSuchBuild(key)
        else:
            results[key] = info

    return results


def bulk_load_tasks(session, tasks, err=True, size=100, results=None):
    results = OrderedDict() if results is None else results

    for key, info in _bulk_load(session, session.getTask, tasks, size):
        if err and not info:
            raise NoSuchTask(key)
        else:
            results[key] = info

    return results


def bulk_load_tags(session, tags, err=True, size=100, results=None):
    results = OrderedDict() if results is None else results

    for key, info in _bulk_load(session, session.getTag, tags, size):
        if err and not info:
            raise NoSuchTag(key)
        else:
            results[key] = info

    return results


def read_clean_lines(filename="-"):

    if not filename:
        return []

    elif filename == "-":
        fin = sys.stdin

    else:
        fin = open(filename, "r")

    lines = [line for line in (l.strip() for l in fin) if line]

    if filename != "-":
        fin.close()

    return lines


@add_metaclass(ABCMeta)
class SmokyDingo(object):

    group = "cli"
    description = "A CLI Plugin"

    # this is necessary for koji to recognize us as a cli command
    exported_cli = True


    def __init__(self, name):
        self.name = name

        # these will be populated once the command instance is
        # actually called
        self.goptions = None
        self.session = None

        # this is used to register the command with koji in a manner
        # that it expects to deal with
        self.__name__ = "handle_" + name.replace("-", "_")

        # allow a docstr to be specified on subclasses, but if absent
        # let's set it based on the group and description.
        if getattr(self, "__doc__", None) is None:
            self.__doc__ = "[%s] %s" % (self.group, self.description)


    def parser(self):
        invoke = " ".join((basename(sys.argv[0]), self.name))
        return ArgumentParser(prog=invoke, description=self.description)


    def pre_handle(self, options):
        pass


    @abstractmethod
    def handle(self, options):
        pass


    def validate(self, parser, options):
        pass


    def __call__(self, goptions, session, args):
        self.goptions = goptions
        self.session = session

        parser = self.parser()
        options = parser.parse_args(args)

        self.validate(parser, options)

        try:
            activate_session(session, goptions)

            self.pre_handle(options)
            return self.handle(options) or 0

        except KeyboardInterrupt:
            print(file=sys.stderr)
            return 130

        except GenericError as kge:
            printerr(kge)
            return -1

        except BadDingo as bad:
            printerr(": ".join((bad.complaint, str(bad))))
            return -2

        except Exception:
            import traceback
            traceback.print_exc()
            raise


class AdminSmokyDingo(SmokyDingo):

    group = "admin"


    def pre_handle(self, options):
        # before attempting to actually perform the command task,
        # ensure that the user has the appropriate admin permissions,
        # to prevent it failing at a strange point

        session = self.session

        userinfo = session.getLoggedInUser()
        userperms = session.getUserPerms(userinfo["id"]) or ()

        if "admin" not in userperms:
            msg = "command %s requires admin permissions" % self.name
            raise PermissionException(msg)


class AnonSmokyDingo(SmokyDingo):

    group = "info"


    def __init__(self, name):
        super(AnonSmokyDingo, self).__init__(name)
        self.__name__ = "anon_handle_" + self.name.replace("-", "_")


#
# The end.
