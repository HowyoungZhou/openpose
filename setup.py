#!/usr/bin/env python

import os
import platform
import sys
import subprocess
import shlex
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from distutils.errors import DistutilsExecError, DistutilsFileError
from distutils.command.install_data import install_data as _install_data
from distutils import log
from distutils.util import change_root, convert_path


class CMakeExtension(Extension):
    def __init__(self, name, source_dir='.', **kwargs):
        Extension.__init__(self, name, sources=[], **kwargs)
        self.cmake_source_dir = os.path.abspath(source_dir)


class cmake_build_ext(build_ext):
    """Build extensions using CMake."""

    user_options = [
        *build_ext.user_options,
        ('cmake-config-args=', None, ''),
        ('cmake-build-args=', None, '')
    ]

    def initialize_options(self):
        build_ext.initialize_options(self)
        self.cmake_config_args = ''
        self.cmake_build_args = ''

    def finalize_options(self):
        build_ext.finalize_options(self)
        self.cmake_config_args = shlex.split(self.cmake_config_args)
        self.cmake_build_args = shlex.split(self.cmake_build_args)

    def spawn(self, cmd, dry_run=False, cwd=None):
        cmd = list(cmd)

        log.info(' '.join(cmd))
        if dry_run:
            return

        try:
            exitcode = subprocess.call(cmd, cwd=cwd)
        except OSError as exc:
            raise DistutilsExecError(
                "command %r failed: %s" % (cmd, exc.args[-1])) from exc

        if exitcode:
            raise DistutilsExecError(
                "command %r failed with exit code %s" % (cmd, exitcode))

    def build_extensions(self):
        # Ensure that CMake is present and working
        try:
            self.spawn(['cmake', '--version'])
        except DistutilsExecError:
            raise DistutilsExecError('cannot find CMake executable')

        for ext in self.extensions:

            extdir = os.path.join(os.path.abspath(os.path.dirname(
                self.get_ext_fullpath(ext.name))), 'openpose')
            cfg = 'Debug' if self.debug else 'Release'
            cfg = 'Release'

            cmake_args = [
                '-DCMAKE_BUILD_TYPE=%s' % cfg,
                # Ask CMake to place the resulting library in the directory
                # containing the extension
                '-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(
                    cfg.upper(), extdir),
                # Other intermediate static libraries are placed in a
                # temporary build directory instead
                '-DCMAKE_ARCHIVE_OUTPUT_DIRECTORY_{}={}'.format(
                    cfg.upper(), self.build_temp),
                # Hint CMake to use the same Python executable that
                # is launching the build, prevents possible mismatching if
                # multiple versions of Python are installed
                '-DPYTHON_EXECUTABLE={}'.format(sys.executable),
                '-DBUILD_PYTHON=ON'
            ]

            # We can handle some platform-specific settings at our discretion
            if platform.system() == 'Windows':
                plat = ('x64' if platform.architecture()
                        [0] == '64bit' else 'Win32')
                cmake_args += [
                    # These options are likely to be needed under Windows
                    '-DCMAKE_WINDOWS_EXPORT_ALL_SYMBOLS=TRUE',
                    '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_{}={}'.format(
                        cfg.upper(), extdir),
                ]
                # Assuming that Visual Studio and MinGW are supported compilers
                if self.compiler.compiler_type == 'msvc':
                    cmake_args += [
                        '-DCMAKE_GENERATOR_PLATFORM=%s' % plat,
                    ]

            os.makedirs(self.build_temp, exist_ok=True)

            # Config
            self.spawn(['cmake', ext.cmake_source_dir] + cmake_args + self.cmake_config_args, dry_run=self.dry_run,
                       cwd=self.build_temp)

            # Build
            self.spawn(['cmake', '--build', '.', '--config', cfg] + self.cmake_build_args, dry_run=self.dry_run,
                       cwd=self.build_temp)


class install_data(_install_data):
    """Patch the install_data command from distutils to support copying directories."""

    def copy_to(self, file_or_dir, dst_dir):
        if os.path.isdir(file_or_dir):
            return self.copy_tree(file_or_dir, os.path.join(dst_dir, os.path.basename(file_or_dir))), 1
        elif os.path.isfile(file_or_dir):
            return self.copy_file(file_or_dir, dst_dir)
        else:
            raise DistutilsFileError(
                "can't copy '%s': doesn't exist or not a regular file or a directory" % file_or_dir)

    def run(self):
        self.mkpath(self.install_dir)
        for f in self.data_files:
            if isinstance(f, str):
                # it's a simple file, so copy it
                f = convert_path(f)
                if self.warn_dir:
                    self.warn("setup script did not provide a directory for "
                              "'%s' -- installing right in '%s'" %
                              (f, self.install_dir))
                (out, _) = self.copy_to(f, self.install_dir)
                self.outfiles.append(out)
            else:
                # it's a tuple with path to install to and a list of files
                dir = convert_path(f[0])
                if not os.path.isabs(dir):
                    dir = os.path.join(self.install_dir, dir)
                elif self.root:
                    dir = change_root(self.root, dir)
                self.mkpath(dir)

                if f[1] == []:
                    # If there are no files listed, the user must be
                    # trying to create an empty directory, so add the
                    # directory to the list of output files.
                    self.outfiles.append(dir)
                else:
                    # Copy files, adding them to the list of output files.
                    for data in f[1]:
                        data = convert_path(data)
                        (out, _) = self.copy_to(data, dir)
                        self.outfiles.append(out)


setup(name='OpenPose',
      version='1.6.0',
      description='OpenPose: Real-time multi-person keypoint detection library for body, face, hands, and foot estimation',
      author='CMU Perceptual Computing Lab',
      url='https://github.com/CMU-Perceptual-Computing-Lab/openpose',
      packages=['openpose'],
      package_dir={'': 'python'},
      data_files=[('openpose', ['models'])],
      ext_modules=[CMakeExtension('openpose')],
      cmdclass={'build_ext': cmake_build_ext, 'install_data': install_data},
      )
