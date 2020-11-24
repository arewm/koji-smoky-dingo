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
Koji Smoky Dingo - Sifty Dingo filtering for Koji Builds

This module provides sieves for filtering through koji build info
dicts.

:author: Christopher O'Brien <obriencj@gmail.com>
:license: GPL v3
"""


import operator

from koji import BUILD_STATES
from operator import itemgetter
from six import iteritems, itervalues
from six.moves import filter, map

from . import (
    DEFAULT_SIEVES,
    ItemSieve, Sieve, Sifter, SifterError, VariadicSieve,
    ensure_all_matcher, ensure_all_int_or_str,
    ensure_int_or_str, ensure_str, )
from .. import (
    as_taginfo, bulk_load_builds, bulk_load_tags, bulk_load_users,
    iter_bulk_load, )
from ..builds import (
    build_dedup, decorate_builds_btypes, decorate_builds_cg_list,
    decorate_builds_maven, gather_rpm_sigkeys, gavgetter,
    iter_latest_maven_builds, )
from ..common import rpm_evr_compare, unique
from ..tags import gather_tag_ids


__all__ = (
    "DEFAULT_BUILD_INFO_SIEVES",

    "CGImportedSieve",
    "EpochSieve",
    "EVRCompareEQ",
    "EVRCompareNE",
    "EVRCompareLT",
    "EVRCompareLE",
    "EVRCompareGT",
    "EVRCompareGE",
    "ImportedSieve",
    "InheritedSieve",
    "LatestSieve",
    "LatestMavenSieve",
    "NameSieve",
    "NVRSieve",
    "OwnerSieve",
    "PkgAllowedSieve",
    "PkgBlockedSieve",
    "ReleaseSieve",
    "SignedSieve",
    "StateSieve",
    "TaggedSieve",
    "TypeSieve",
    "VersionSieve",

    "build_info_sieves",
    "build_info_sifter",
    "sift_builds",
    "sift_nvrs",
)


class NVRSieve(ItemSieve):
    """
    Usage: ``(nvr NVR [NVR...])``

    filters for dict infos whose `nvr` key matches any of the given
    NVR matchers.
    """

    name = field = "nvr"


class NameSieve(ItemSieve):
    """
    Usage: ``(name NAME [NAME...])``

    filters for dict infos whose `name` key matches any of the given
    NAME matchers.
    """

    name = field = "name"


class VersionSieve(ItemSieve):
    """
    Usage: ``(version VER [VER...])``

    filters for dict infos whose `version` key matches any of the given
    VER matchers.
    """

    name = field = "version"


class ReleaseSieve(ItemSieve):
    """
    Usage: ``(release REL [REL...])``

    filters for dict infos whose `release` key matches any of the given
    REL matchers.
    """

    name = field = "release"


class EpochSieve(ItemSieve):
    """
    Usage: ``(epoch EPOCH [EPOCH...])``

    filters for dict infos whose `epoch` key matches any of the given
    EPOCH matchers.
    """

    name = field = "epoch"


class StateSieve(ItemSieve):
    """
    Usage: ``(state BUILD_STATE [BUILD_STATE...])``

    filters for dict infos whose `state` key matches any of the given
    koji build states. Build states may be specified as either an integer
    or one of the following strings or symbols

    * ``BUILDING``
    * ``COMPLETE``
    * ``DELETED``
    * ``FAILED``
    * ``CANCELED``
    """

    name = field = "state"


    def __init__(self, sifter, pattern):
        state = ensure_int_or_str(pattern)

        found = BUILD_STATES.get(state)
        if found is None:
            raise SifterError("Unknown build state: %r" % pattern)

        if isinstance(state, str):
            state = found

        super(ItemSieve, self).__init__(sifter, state)


class OwnerSieve(Sieve):
    """
    Usage: ``(owner USER [USER...])```

    filters for builds whose `owner_name` or `owner_id` key matches
    any of the given USERs.

    The users will be validated at the time of the sieve's first
    invocation, which may result in a NoSuchUser error.
    """

    name = "owner"


    def __init__(self, sifter, user, *users):
        usernames = [user]
        usernames.extend(users)
        usernames = ensure_all_int_or_str(usernames)

        super(OwnerSieve, self).__init__(sifter, *usernames)
        self._user_ids = None


    def prep(self, session, _build_infos):
        if self._user_ids is None:
            loaded = bulk_load_users(session, self.tokens)
            self._user_ids = set(u["id"] for u in itervalues(loaded))


    def check(self, session, binfo):
        return binfo.get("owner_id") in self._user_ids


class ImportedSieve(Sieve):
    """
    Usage: ``(imported)``

    filters for build info dicts whose task ID is empty or null.
    """

    name = "imported"


    def check(self, session, binfo):
        return not binfo.get("task_id")


OPMAP = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


class EVRCompare(Sieve):
    """
    Valid comparison values are

    * ``==``
    * ``!=``
    * ``>``
    * ``>=``
    * ``<``
    * ``<=``
    """

    def __init__(self, sifter, version):
        version = ensure_str(version)
        super(EVRCompare, self).__init__(sifter, version)
        self.token = version

        if ":" in version:
            epoch, version = version.split(":", 1)
        else:
            epoch = "0"

        if "-" in version:
            version, release = version.split("-", 1)
        else:
            release = None

        self.epoch = epoch
        self.version = version
        self.release = release

        self.op = OPMAP[self.name]


    def check(self, session, binfo):
        other = (binfo["epoch"], binfo["version"], binfo["release"])
        other = tuple((str(x) if x else "0") for x in other)

        ours = (self.epoch, self.version, self.release or other[2])

        relative = rpm_evr_compare(other, ours)
        return self.op(relative, 0)


    def __repr__(self):
        # we don't want to auto-quote the token which the default
        # Sieve impl does.
        return "".join(("(", self.name, " ", self.token, ")"))


class EVRCompareEQ(EVRCompare):
    """
    Usage: ``(== VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = "=="


class EVRCompareNE(EVRCompare):
    """
    Usage: ``(!= VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = "!="


class EVRCompareGT(EVRCompare):
    """
    Usage: ``(> VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = ">"


class EVRCompareGE(EVRCompare):
    """
    Usage: ``(>= VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = ">="


class EVRCompareLT(EVRCompare):
    """
    Usage: ``(< VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = "<"


class EVRCompareLE(EVRCompare):
    """
    Usage: ``(<= VER)``

    ``VER`` can be in any of the following forms

    * ``EPOCH:VERSION``
    * ``EPOCH:VERSION-RELEASE``
    * ``VERSION``
    * ``VERSION-RELEASE``

    If ``EPOCH`` is omitted, it is presumed to be ``0``.
    If ``RELEASE`` is omitted, it is presumed to be equivalent.

    Passes builds whose EVR compares as requested.
    """

    name = "<="


class TaggedSieve(Sieve):
    """
    usage: (tagged [TAG...])

    If no TAG patterns are specified, matches builds which have any
    tags at all.

    If TAG patterns are specified, then only matches builds which have
    a tag that matches any of the given patterns.
    """

    name = "tagged"


    def __init__(self, sifter, *tagnames):
        tagnames = ensure_all_matcher(tagnames)
        super(TaggedSieve, self).__init__(sifter, *tagnames)


    def prep(self, session, binfos):

        needed = {}
        for binfo in binfos:
            cache = self.get_cache(binfo)
            if "tag_names" not in cache:
                needed[binfo["id"]] = cache

        if needed:
            fn = lambda i: session.listTags(build=i)
            for bid, tags in iter_bulk_load(session, fn, needed):
                cache = needed[bid]
                cache["tag_names"] = [t["name"] for t in tags]
                cache["tag_ids"] = [t["id"] for t in tags]


    def check(self, session, binfo):
        cache = self.get_cache(binfo)

        tag_names = cache.get("tag_names", ())
        tag_ids = cache.get("tag_ids", ())

        if not self.tokens:
            # when used as simply (tagged) then we're checking that
            # there are ANY tags.
            return bool(tag_names)

        for match in self.tokens:
            # try to validate all of our potential matchers against
            # both names and IDs
            if match in tag_names or match in tag_ids:
                return True

        return False


class InheritedSieve(Sieve):
    """
    usage: (inherited TAG [TAG...])

    Matches builds which are tagged into any of the given tags or
    their parent tags. Each TAG must be a tag name or tag ID, patterns
    are not allowed.
    """

    name = "inherited"


    def __init__(self, sifter, tagname, *tagnames):
        tags = [tagname]
        tags.extend(tagnames)
        tags = ensure_all_int_or_str(tags)

        super(InheritedSieve, self).__init__(sifter, *tags)
        self.tag_ids = None


    def get_cache(self, binfo):
        # let's use the same caches that the Tagged sieve uses
        return self.sifter.get_cache("tagged", binfo)


    def prep(self, session, binfos):
        if self.tag_ids is None:
            self.tag_ids = gather_tag_ids(session, deep=self.tokens)

        needed = {}
        for binfo in binfos:
            cache = self.get_cache(binfo)
            if "tag_names" not in cache:
                needed[binfo["id"]] = cache

        if needed:
            fn = lambda i: session.listTags(build=i)
            for bid, tags in iter_bulk_load(session, fn, needed):
                cache = needed[bid]
                cache["tag_names"] = [t["name"] for t in tags]
                cache["tag_ids"] = [t["id"] for t in tags]


    def check(self, session, binfo):
        inheritance = self.tag_ids
        cache = self.get_cache(binfo)

        for tid in cache.get("tag_ids", ()):
            if tid in inheritance:
                return True

        return False


class PkgSieve(Sieve):

    def __init__(self, sifter, tagname, *tagnames):
        tags = [tagname]
        tags.extend(tagnames)
        tags = ensure_all_int_or_str(tags)

        super(PkgSieve, self).__init__(sifter, *tags)

        self.tag_ids = None


    @staticmethod
    def tag_pkglist(cache={}):
        """
        ``{tag_id: {"allowed": set(...), "blocked": set(...)}, ...}``

        Shared across all PkgSieve instances. Populated during
        instance prep from the package listing of their tags
        """

        return cache


    def prep(self, session, binfos):
        # look up our tags
        tids = self.tag_ids
        if tids is None:
            loaded = bulk_load_tags(session, self.tokens, err=True)
            self.tag_ids = tids = set(t["id"] for t in itervalues(loaded))

        # see if we are missing a package listing for any of our tags. It
        # may have been loaded by another instance of a PkgSieve
        cache = self.tag_pkglist()
        needed = [tid for tid in tids if tid not in cache]

        if not needed:
            return

        fn = lambda t: session.listPackages(t, inherited=True)
        for tid, pkgs in iter_bulk_load(session, fn, needed):
            allowed = set()
            blocked = set()

            for pkg in pkgs:
                if pkg["blocked"]:
                    blocked.add(pkg["package_name"])
                else:
                    allowed.add(pkg["package_name"])

            cache[tid] = {
                "allowed": allowed,
                "blocked": blocked
            }


class PkgAllowedSieve(PkgSieve):
    """
    usage: (pkg-allowed TAG [TAG...])

    Matches builds which are have their package listing present and
    not blocked in and of the given tags or their parents.
    """

    name = "pkg-allowed"


    def check(self, session, binfo):
        cache = self.tag_pkglist()
        pkg = binfo["name"]

        for tid in self.tag_ids:
            if pkg in cache[tid]["allowed"]:
                return True

        return False


class PkgBlockedSieve(PkgSieve):
    """
    usage: (pkg-blocked TAG [TAG...])

    Matches builds which are have their package name blocked in and of the
    given tags or their parents.
    """

    name = "pkg-blocked"


    def check(self, session, binfo):
        cache = self.tag_pkglist()
        pkg = binfo["name"]

        for tid in self.tag_ids:
            if pkg in cache[tid]["blocked"]:
                return True

        return False


class TypeSieve(Sieve):
    """
    usage: (type BTYPE [BTYPE...])

    Passes build infos that have archives of the given btype. Normal
    btypes are rpm, maven, image, and win.
    """

    name = "type"


    def __init__(self, sifter, btype, *btypes):
        bts = [btype]
        bts.extend(btypes)
        bts = ensure_all_matcher(bts)

        super(TypeSieve, self).__init__(sifter, *bts)


    def prep(self, session, binfos):
        decorate_builds_btypes(session, binfos)


    def check(self, session, binfo):
        bt_names = binfo.get("archive_btype_names", ())
        bt_ids = binfo.get("archive_btype_ids", ())

        for t in self.tokens:
            if t in bt_names or t in bt_ids:
                return True
        return False


class CGImportedSieve(Sieve):
    """
    usage: (cg-imported [CGNAME...])

    Passes build infos that have been produced via a cg-import by any
    of the named content generators. If no CGs are named, then passes
    build infos that have been produced by any content generator.
    """

    name = "cg-imported"


    def __init__(self, sifter, *cgnames):
        cgnames = ensure_all_matcher(cgnames)
        super(CGImportedSieve, self).__init__(sifter, *cgnames)


    def prep(self, session, binfos):
        decorate_builds_cg_list(session, binfos)


    def check(self, session, binfo):
        cg_names = binfo.get("archive_cg_names", ())
        cg_ids = binfo.get("archive_cg_ids", ())

        tokens = self.tokens
        if tokens:
            for t in tokens:
                if t in cg_names or t in cg_ids:
                    return True
            return False

        else:
            return bool(cg_names)


class LatestSieve(Sieve):
    """
    usage: (latest TAG [TAG...])

    Passes build infos that are the latest build of their package name in
    any of the tags.
    """

    name = "latest"


    @staticmethod
    def latest_ids(cache={}):
        """
        This is a cache mapping a tag ID to latest build IDs in that
        tag. It's populated by all the LatestSieve instances when they
        run their prep.
        """

        return cache


    def __init__(self, sifter, tagname, *tagnames):
        tags = [tagname]
        tags.extend(tagnames)
        tags = ensure_all_int_or_str(tags)

        super(LatestSieve, self).__init__(sifter, *tags)
        self.tag_ids = None


    def prep(self, session, binfos):

        # first we need to convert our tokens into tag IDs
        tids = self.tag_ids
        if tids is None:
            tags = bulk_load_tags(session, self.tokens, err=True)
            self.tag_ids = tids = unique(t["id"] for t in itervalues(tags))

        # for each tag ID, we look through the cache to see if we've
        # already loaded the latest build IDs
        cache = self.latest_ids()
        for tid in tids:
            if tid not in cache:
                # if not already loaded, find the latest builds in the tag
                # and store their IDs
                cache[tid] = self.load_latest_ids(session, tid)


    def load_latest_ids(self, session, tagid):
        sought = session.getLatestBuilds(tagid)
        return set(map(itemgetter("id"), sought))


    def check(self, session, binfo):
        cache = self.latest_ids()
        for tid in self.tag_ids:
            if binfo["id"] in cache[tid]:
                return True
        return False


class LatestMavenSieve(VariadicSieve):
    """
    usage: (latest-maven TAG [TAG...])

    Passes build infos that have btype maven and are the build of their
    GAV in any of the tags.
    """

    name = "latest-maven"


    def __init__(self, sifter, tag):
        super(LatestMavenSieve, self).__init__(sifter, tag)
        self.tag = ensure_str(tag)

        # mapping (G,A,V):ID for the latest GAV builds
        # in tag
        self.cache = None


    def prep(self, session, binfos):

        tag = self.tag = as_taginfo(session, self.tag)

        # in order to perform the GAV comparisons, we need to have
        # loaded the various binfos with their maven fields. This
        # corrects any which were not loaded this way.
        decorate_builds_maven(session, binfos)

        if self.cache is None:
            sought = iter_latest_maven_builds(session, tag, inherit=True)
            self.cache = dict((gav, bld["id"]) for gav, bld in sought)


    def check(self, session, binfo):
        return ("maven_group_id" in binfo and
                self.cache.get(gavgetter(binfo)) == binfo["id"])


class SignedSieve(Sieve):
    """
    usage: ``(signed [KEY...])``

    Passes builds which have RPMs signed with any of the given
    keys. If no keys are specified then passes builds which have RPMs
    signed with any key at all.
    """

    name = "signed"


    def __init__(self, sifter, *keys):
        keys = ensure_all_matcher(keys)
        super(SignedSieve, self).__init__(sifter, *keys)
        self.keys = keys or None


    def prep(self, session, binfos):
        needed = {}
        for binfo in binfos:
            cache = self.get_cache(binfo)
            if "rpmsigs" not in cache:
                needed[binfo["id"]] = cache

        if not needed:
            return

        for bid, sigs in iteritems(gather_rpm_sigkeys(session, needed)):
            # we need to drop the unsigned key, which is an empty
            # string
            cache = needed[bid]
            cache["rpmsigs"] = list(filter(None, sigs)) or None


    def check(self, session, binfo):
        want_keys = self.keys
        build_keys = self.get_cache(binfo).get("rpmsigs")

        if want_keys is None:
            return bool(build_keys)
        elif build_keys is None:
            return False
        else:
            for wanted in want_keys:
                if wanted in build_keys:
                    return True
            return False


DEFAULT_BUILD_INFO_SIEVES = [
    CGImportedSieve,
    EpochSieve,
    EVRCompareEQ,
    EVRCompareNE,
    EVRCompareGT,
    EVRCompareGE,
    EVRCompareLT,
    EVRCompareLE,
    ImportedSieve,
    InheritedSieve,
    LatestSieve,
    LatestMavenSieve,
    NameSieve,
    NVRSieve,
    OwnerSieve,
    PkgAllowedSieve,
    PkgBlockedSieve,
    ReleaseSieve,
    SignedSieve,
    StateSieve,
    TaggedSieve,
    TypeSieve,
    VersionSieve,
]


def build_info_sieves():
    """
    A new list containing the default build-info sieve classes.

    This function is used by `build_info_sifter` when creating its
    `Sifter` instance.

    :rtype: list[type[Sieve]]
    """

    sieves = []

    # TODO: grab some more via entry_points
    sieves.extend(DEFAULT_SIEVES)
    sieves.extend(DEFAULT_BUILD_INFO_SIEVES)

    return sieves


def build_info_sifter(source, params=None):
    """
    Create a Sifter from the source using the default build-info
    Sieves.

    :param source: sieve expressions source
    :type source: stream or str

    :rtype: Sifter
    """

    return Sifter(build_info_sieves(), source, "id", params)


def sift_builds(session, src_str, build_infos, params=None):
    """
    :param src_str: sieve expressions source
    :type src_str: src

    :param build_infos: list of build info dicts to filter
    :type build_infos: list[dict]

    :rtype: dict[str,list[dict]]
    """

    sifter = build_info_sifter(src_str, params)
    return sifter(session, build_infos)


def sift_nvrs(session, src_str, nvrs, params=None):
    """
    :param src_str: sieve expressions source
    :type src_str: src

    :param nvrs: list of NVRs to load and filter
    :type nvrs: list[str]

    :rtype: dict[str,list[dict]]
    """

    loaded = bulk_load_builds(session, nvrs, err=False)
    builds = build_dedup(itervalues(loaded))
    return sift_builds(session, src_str, builds, params)


#
# The end.