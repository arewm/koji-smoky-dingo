#! /usr/bin/env python

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
Koji Smoky Dingo - a collection of Koji command-line features for
advanced users.

Note that this package needs the kojismokydingometa plugin to be
installed in order for the plugins to be loaded by the Koji CLI.

:author: Christopher O'Brien  <obriencj@gmail.com>
:license: GPL version 3
"""


from setuptools import setup


def command(name):
    fn_name = name.replace('-', '_')
    return "%s = kojismokydingo.cli:%s" % (name, fn_name)


setup(
    name = 'kojismokydingo',
    version = '0.9.0',

    packages = [
        'kojismokydingo',
    ],

    requires = [
        "koji",
        "six",
    ],

    # these are used by the koji meta-plugin to provide additional
    # commands, one per entry_point
    entry_points = {
        'koji_smoky_dingo': [
            command("affected-targets"),
            command("bulk-tag-builds"),
            command("check-hosts"),
            command("client-config"),
            command("latest-archives"),
            command("list-build-archives"),
            command("list-imported"),
            command("perminfo"),
            command("renum-tag-inheritance"),
            command("swap-tag-inheritance"),
            command("userinfo"),
        ],
    },

    test_suite = "tests",

    zip_safe = True,

    # PyPI metadata
    description = "A collection of Koji command-line plugins",

    author = "Christopher O'Brien",
    author_email = "obriencj@gmail.com",
    url = "https://github.com/obriencj/koji-smoky-dingo",
    license = "GNU General Public License",

    classifiers = [
        "Intended Audience :: Developers",
    ],
)


#
# The end.
