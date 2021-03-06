# vim: set fileencoding=utf-8 :
#
# (C) 2006, 2007, 2009, 2011 Guido Guenther <agx@sigxcpu.org>
# (C) 2012 Intel Corporation <markus.lehtonen@linux.intel.com>
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, please see
#    <http://www.gnu.org/licenses/>
#
"""Common functionality for import-orig scripts"""
import contextlib
import os
import tempfile
import gbp.command_wrappers as gbpc
import gbp.log

from gbp.pkg import parse_archive_filename
from gbp.errors import GbpError
from gbp.deb.upstreamsource import DebianUpstreamSource

# Try to import readline, since that will cause raw_input to get fancy
# line editing and history capabilities. However, if readline is not
# available, raw_input will still work.
try:
    import readline
except ImportError:
    pass


def ask_package_name(default, name_validator_func, err_msg):
    """
    Ask the user for the source package name.
    @param default: The default package name to suggest to the user.
    """
    while True:
        sourcepackage = raw_input("What will be the source package name? [%s] " % default)
        if not sourcepackage: # No input, use the default.
            sourcepackage = default
        # Valid package name, return it.
        if name_validator_func(sourcepackage):
            return sourcepackage

        # Not a valid package name. Print an extra
        # newline before the error to make the output a
        # bit clearer.
        gbp.log.warn("\nNot a valid package name: '%s'.\n%s" % (sourcepackage, err_msg))


def ask_package_version(default, ver_validator_func, err_msg):
    """
    Ask the user for the upstream package version.
    @param default: The default package version to suggest to the user.
    """
    while True:
        version = raw_input("What is the upstream version? [%s] " % default)
        if not version: # No input, use the default.
            version = default
        # Valid version, return it.
        if ver_validator_func(version):
            return version

        # Not a valid upstream version. Print an extra
        # newline before the error to make the output a
        # bit clearer.
        gbp.log.warn("\nNot a valid upstream version: '%s'.\n%s" % (version, err_msg))


def download_orig(url):
    """
    Download orig tarball from given URL
    @param url: the download URL
    @type url: C{str}
    @returns: The upstream source tarball
    @rtype: DebianUpstreamSource
    @raises GbpError: on all errors
    """
    CHUNK_SIZE=4096

    try:
        import requests
    except ImportError:
        requests = None

    if requests is None:
        raise GbpError("python-requests not installed")

    tarball = os.path.basename(url)
    target = os.path.join('..', tarball)

    if os.path.exists(target):
        raise GbpError("Failed to download %s: %s already exists" % (url, target))

    try:
        with contextlib.closing(requests.get(url, verify=True, stream=True)) as r:
            with contextlib.closing(open(target, 'w', CHUNK_SIZE)) as target_fd:
                for d in r.iter_content(CHUNK_SIZE):
                    target_fd.write(d)
    except Exception as e:
        raise GbpError("Failed to download %s: %s" % (url, e))
        if os.path.exists(target):
            os.unlink(target)

    return DebianUpstreamSource(target)


def prepare_pristine_tar(source, pkg_name, pkg_version, pristine_commit_name,
                         filters=None, prefix=None, tmpdir=None):
    """
    Prepare the upstream sources for pristine-tar import

    @param source: original upstream sources
    @type source: C{UpstreamSource}
    @param pkg_name: package name
    @type pkg_name: C{str}
    @param pkg_version: upstream version of the package
    @type pkg_version: C{str}
    @param pristine_commit_name: archive filename to commit to pristine-tar
    @type pristine_commit_name: C{str} or C{None}
    @param filters: filter to exclude files
    @type filters: C{list} of C{str} or C{None}
    @param prefix: prefix (i.e. leading directory of files) to use in
                   pristine-tar, set to C{None} to not mangle orig archive
    @type prefix: C{str} or C{None}
    @param tmpdir: temporary working dir (cleanup left to caller)
    @type tmpdir: C{str}
    @return: prepared source archive
    @rtype: C{UpstreamSource}
    """
    need_repack = False
    if source.is_dir():
        if prefix is None:
            prefix = '%s-%s' % (pkg_name, pkg_version)
            gbp.log.info("Using guessed prefix '%s/' for pristine-tar" % prefix)
        need_repack = True
    else:
        if prefix is not None and prefix == source.prefix:
            prefix = None
        comp = parse_archive_filename(pristine_commit_name)[2]
        if filters or prefix is not None or source.compression != comp:
            if not source.unpacked:
                unpack_dir = tempfile.mkdtemp(prefix='pristine_unpack_',
                                              dir=tmpdir)
                source.unpack(unpack_dir)
            need_repack = True
    pristine_path = os.path.join(tmpdir, pristine_commit_name)
    if need_repack:
        gbp.log.debug("Packing '%s' from '%s' for pristine-tar" %
                        (pristine_path, source.unpacked))
        pristine = source.pack(pristine_path, filters, prefix)
    else:
        # Just create symlink for mangling the pristine tarball name
        os.symlink(source.path, pristine_path)
        pristine = source.__class__(pristine_path)

    return pristine


def prepare_sources(source, pkg_name, pkg_version, pristine_commit_name,
                    filters, filter_pristine, prefix, tmpdir):
    """
    Prepare upstream sources for importing

    Unpack, filter and repack sources for importing to git and to pristine-tar.

    @param source: original upstream sources
    @type source: C{UpstreamSource}
    @param pkg_name: package name
    @type pkg_name: C{str}
    @param pkg_version: upstream version of the package
    @type pkg_version: C{str}
    @param pristine_commit_name: archive filename to commit to pristine-tar
    @type pristine_commit_name: C{str} or C{None}
    @param filters: filter to exclude files
    @type filters: C{list} of C{str}
    @param filter_pristine: filter pristine-tar, too
    @type filter_pristine: C{bool}
    @param prefix: prefix (i.e. leading directory of files) to use in
                   pristine-tar, set to C{None} to not mangle orig archive
    @type prefix: C{str} or C{None}
    @param tmpdir: temporary working dir (cleanup left to caller)
    @type tmpdir: C{str}
    @return: path to prepared source tree and tarball to commit to pristine-tar
    @rtype: C{tuple} of C{str}
    """
    pristine = None
    # Determine parameters for pristine tar
    pristine_filters = filters if filters and filter_pristine else None
    pristine_prefix = None
    if prefix is not None and prefix != 'auto':
        prefix_subst = {'name': pkg_name,
                        'version': pkg_version,
                        'upstreamversion': pkg_version}
        pristine_prefix = prefix % prefix_subst
    # Handle unpacked sources, i.e. importing a directory
    if source.is_dir():
        if pristine_commit_name:
            gbp.log.warn('Preparing unpacked sources for pristine-tar')
            pristine = prepare_pristine_tar(source, pkg_name, pkg_version,
                                            pristine_commit_name,
                                            pristine_filters, pristine_prefix,
                                            tmpdir)
        if filters:
            # Re-use sources packed for pristine-tar, if available
            if pristine:
                packed = pristine
            else:
                packed_fn = tempfile.mkstemp(prefix="packed_", dir=tmpdir,
                                             suffix='.tar')[1]
                gbp.log.debug("Packing '%s' to '%s'" % (source.path, packed_fn))
                packed = source.pack(packed_fn)
            unpack_dir = tempfile.mkdtemp(prefix='filtered_', dir=tmpdir)
            filtered = packed.unpack(unpack_dir, filters)
        else:
            filtered = source
    # Handle source archives
    else:
        unpack_dir = tempfile.mkdtemp(prefix='filtered_', dir=tmpdir)
        gbp.log.debug("Unpacking '%s' to '%s'" % (source.path, unpack_dir))
        filtered = source.unpack(unpack_dir, filters)
        if pristine_commit_name:
            pristine = prepare_pristine_tar(source, pkg_name, pkg_version,
                                            pristine_commit_name,
                                            pristine_filters, pristine_prefix,
                                            tmpdir)
    pristine_path = pristine.path if pristine else ''
    return (filtered.unpacked, pristine_path)

