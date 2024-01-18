"""Custom PEP 517 build backend to provide different dependencies for wheel and sdist builds.

See: https://setuptools.pypa.io/en/latest/build_meta.html#dynamic-build-dependencies-and-other-build-meta-tweaks
"""

from setuptools import build_meta as _orig
from setuptools.build_meta import *


def get_requires_for_build_sdist(config_settings=None):
    return _orig.get_requires_for_build_sdist(config_settings) + [
        # Finds all git tracked files including submodules, when making sdist MANIFEST
        "setuptools-git-ls-files"
    ]

def get_requires_for_build_wheel(config_settings=None):
    return _orig.get_requires_for_build_wheel(config_settings) + [
        # required for building the 'tx' executable from afdko package
        "cmake",
        "ninja",
        "scikit-build",
    ]

