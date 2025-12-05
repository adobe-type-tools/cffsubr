from setuptools import setup, find_packages, Extension
from setuptools.command.build_ext import build_ext
from distutils.file_util import copy_file
from distutils.dir_util import mkpath
from distutils import log
import os
import subprocess
import sys


cmdclass = {}
try:
    from wheel.bdist_wheel import bdist_wheel
except ImportError:
    pass
else:

    class UniversalBdistWheel(bdist_wheel):
        def get_tag(self):
            return ("py3", "none") + bdist_wheel.get_tag(self)[2:]

    cmdclass["bdist_wheel"] = UniversalBdistWheel


class Executable(Extension):
    if os.name == "nt":
        suffix = ".exe"
    else:
        suffix = ""

    def __init__(self, name, build_cmd, output_dir=".", cwd=None, env=None):
        Extension.__init__(self, name, sources=[])
        self.target = self.name.split(".")[-1] + self.suffix
        self.build_cmd = build_cmd
        self.output_dir = output_dir
        self.cwd = cwd
        self.env = env


class ExecutableBuildExt(build_ext):
    def get_ext_filename(self, ext_name):
        for ext in self.extensions:
            if isinstance(ext, Executable):
                return os.path.join(*ext_name.split(".")) + ext.suffix
        return build_ext.get_ext_filename(self, ext_name)

    def build_extension(self, ext):
        if not isinstance(ext, Executable):
            build_ext.build_extension(self, ext)
            return

        exe_fullpath = os.path.join(ext.output_dir, ext.target)
        cmd = ext.build_cmd
        log.debug("running '{}'".format(cmd))
        if not self.dry_run:
            env = dict(os.environ)
            if ext.env:
                env.update(ext.env)
            p = subprocess.run(cmd, cwd=ext.cwd, env=env, shell=True)
            if p.returncode != 0:
                from distutils.errors import DistutilsExecError

                raise DistutilsExecError(
                    "running '{}' command failed".format(ext.build_cmd)
                )

        dest_path = self.get_ext_fullpath(ext.name)
        mkpath(os.path.dirname(dest_path), verbose=self.verbose, dry_run=self.dry_run)

        copy_file(exe_fullpath, dest_path, verbose=self.verbose, dry_run=self.dry_run)


cmdclass["build_ext"] = ExecutableBuildExt

afdko_root_dir = os.path.join("external", "afdko")
afdko_output_dir = os.path.join(afdko_root_dir, "build", "bin")
build_release_cmd = f"{sys.executable} setup.py build --build-scripts build/bin"

tx = Executable(
    "cffsubr.tx",
    build_cmd=build_release_cmd,
    cwd=afdko_root_dir,
    output_dir=afdko_output_dir,
    # we don't care about the precise afdko version, but we need *some* version
    # otherwise building a wheel from a cffsubr sdist tarball fails because the
    # afdko submodule in the unzipped sdist isn't recognized as a git repo
    env={"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_AFDKO": "0.0.0"},
)

with open("README.md", "r", encoding="utf-8") as readme:
    long_description = readme.read()

setup(
    name="cffsubr",
    use_scm_version={"write_to": "src/cffsubr/_version.py"},
    description=("Standalone CFF subroutinizer based on the AFDKO tx tool"),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Cosimo Lupo",
    author_email="cosimo@anthrotype.com",
    url="https://github.com/adobe-type-tools/cffsubr",
    license="Apache 2.0",
    platforms=["posix", "nt"],
    package_dir={"": "src"},
    packages=find_packages("src"),
    entry_points={"console_scripts": ["cffsubr = cffsubr.__main__:main"]},
    ext_modules=[tx],
    zip_safe=False,
    cmdclass=cmdclass,
    install_requires=[
        "fontTools >= 4.10.2",
    ],
    extras_require={"testing": ["pytest"]},
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Text Processing :: Fonts",
        "Topic :: Multimedia :: Graphics",
    ],
)
