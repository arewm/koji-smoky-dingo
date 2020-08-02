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
from functools import partial
from json import dump
from koji import GenericError
from koji_cli.lib import activate_session, ensure_connection
from os.path import basename
from six import add_metaclass

from kojismokydingo import BadDingo, NotPermitted


JSON_PRETTY_OPTIONS = {
    "indent": 4,
    "separators": (",", ": "),
    "sort_keys": True,
}


def pretty_json(data, output=sys.stdout, pretty=JSON_PRETTY_OPTIONS):
    """
    Presents JSON in a pretty way.
    """

    dump(data, output, **pretty)
    print(file=output)


def resplit(arglist, sep=","):
    """
    Collapses comma-separated and multi-specified items into a single
    list. Useful with action="append" in an argparse argument.

    this allows arguments like:
    -x 1 -x 2, -x 3,4,5 -x ,6,7, -x 8

    to become
    x = [1, 2, 3, 4, 5, 6, 7, 8]
    """

    work = (a.strip() for a in sep.join(arglist).split(sep))
    return [a for a in work if a]


def read_clean_lines(filename="-"):

    if not filename:
        return []

    elif filename == "-":
        fin = sys.stdin

    else:
        fin = open(filename, "r")

    lines = [line for line in (l.strip() for l in fin) if line]
    # lines = list(filter(None, map(str.strip, fin)))

    if filename != "-":
        fin.close()

    return lines


printerr = partial(print, file=sys.stderr)


@add_metaclass(ABCMeta)
class SmokyDingo(object):

    group = "misc"
    description = "A CLI Plugin"

    # set of permission names that can grant use of this command. None
    # or empty for anonymous access. Checked in pre_handle
    permission = None


    def __init__(self, name):
        self.name = name

        # this is used to register the command with koji in a manner
        # that it expects to deal with
        self.__name__ = "handle_" + name.replace("-", "_")

        # this is necessary for koji to recognize us as a cli command
        self.exported_cli = True

        # allow a docstr to be specified on subclasses, but if absent
        # let's set it based on the group and description.
        if getattr(self, "__doc__", None) is None:
            self.__doc__ = "[%s] %s" % (self.group, self.description)

        # these will be populated once the command instance is
        # actually called
        self.goptions = None
        self.session = None


    def parser(self):
        """
        Override to provide an ArgumentParser instance with all the
        relevant positional arguments and options added.
        """

        invoke = " ".join((basename(sys.argv[0]), self.name))
        return ArgumentParser(prog=invoke, description=self.description)


    def validate(self, parser, options):
        """
        Override to perform validation on options values. Return value is
        ignored, use parser.error if needed.
        """

        pass


    def pre_handle(self, options):
        """
        Verify necessary permissions are in place before attempting any
        further calls.
        """

        if self.permission:
            session = self.session
            userinfo = session.getLoggedInUser()
            userperms = session.getUserPerms(userinfo["id"]) or ()

            if not (self.permission in userperms or "admin" in userperms):
                msg = "Insufficient permissions for command %s" % self.name
                raise NotPermitted(msg)


    @abstractmethod
    def handle(self, options):
        """
        Perform the full set of actions for this command.
        """

        pass


    def activate(self):
        return activate_session(self.session, self.goptions)


    def __call__(self, goptions, session, args):
        """
        This is the koji CLI handler interface. The global options, the
        session, and the unparsed command arguments are provided.
        """

        self.goptions = goptions
        self.session = session

        parser = self.parser()
        options = parser.parse_args(args)

        self.validate(parser, options)

        try:
            self.activate()
            self.pre_handle(options)
            return self.handle(options) or 0

        except KeyboardInterrupt:
            print(file=sys.stderr)
            return 130

        except GenericError as kge:
            printerr(kge)
            return -1

        except BadDingo as bad:
            printerr(bad)
            return -2

        except Exception:
            # koji CLI hides tracebacks from us. If something goes
            # wrong, we want to see it
            import traceback
            traceback.print_exc()
            raise


class AnonSmokyDingo(SmokyDingo):

    group = "info"
    permission = None


    def __init__(self, name):
        super(AnonSmokyDingo, self).__init__(name)

        # koji won't even bother fully authenticating our session for
        # this command if we tweak the name like this. Since
        # subclasses of this are meant to be anonymous commands
        # anyway, we may as well omit the session init
        self.__name__ = "anon_handle_" + self.name.replace("-", "_")


    def activate(self):
        # rather than logging on, we only open a connection
        ensure_connection(self.session)


    def pre_handle(self, options):
        # do not check permissions at all, we won't be logged in
        pass


class AdminSmokyDingo(SmokyDingo):

    group = "admin"
    permission = "admin"


class TagSmokyDingo(SmokyDingo):

    group = "admin"
    permission = "tag"


class TargetSmokyDingo(SmokyDingo):

    group = "admin"
    permission = "target"


class HostSmokyDingo(SmokyDingo):

    group = "admin"
    permission = "host"


#
# The end.