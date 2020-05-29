import copy
import enum
import io
import subprocess
import os
import tempfile
from typing import BinaryIO, Optional, Union
import sys

try:
    from importlib.resources import path
except ImportError:
    # use backport for python < 3.7
    from importlib_resources import path

from fontTools import ttLib


__all__ = ["subroutinize", "desubroutinize", "has_subroutines", "Error"]


try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"


class CFFTableTag(str, enum.Enum):
    CFF = "CFF "
    CFF2 = "CFF2"

    def __str__(self):
        return self.value

    @classmethod
    def from_version(cls, value: int) -> "CFFTableTag":
        if value == 1:
            return cls.CFF
        elif value == 2:
            return cls.CFF2
        else:
            raise ValueError(f"{value} is not a valid CFF table version")


class Error(Exception):
    pass


def _run_embedded_tx(*args, **kwargs):
    """Run the embedded tx executable with the list of positional arguments.

    All keyword arguments are forwarded to subprocess.run function.

    Return:
        subprocess.CompletedProcess object with the following attributes:
        args, returncode, stdout, stderr.
    """
    with path(__name__, "tx") as tx_cli:
        return subprocess.run([str(tx_cli)] + list(args), **kwargs)


def _tx_subroutinize(data: bytes, output_format: str = CFFTableTag.CFF) -> bytes:
    """Run tx subroutinizer on OTF or CFF table raw data.

    Args:
        data (bytes): CFF 1.0 table data, or an entire OTF sfnt data containing
            either 'CFF ' or 'CFF2' table.
        output_format (str): the format of the output table, 'CFF ' or 'CFF2'.

    Returns:
        (bytes) Compressed CFF or CFF2 table data. NOTE: Even when a whole OTF
        is passed in as input, just a single CFF or CFF2 table data is returned.

    Raises:
        cffsubr.Error if subroutinization process fails.
    """
    if not isinstance(data, bytes):
        raise TypeError(f"expected bytes, found {type(data).__name__}")
    output_format = CFFTableTag(output_format.rjust(4))
    # We can't read from stdin because of this issue:
    # https://github.com/adobe-type-tools/afdko/issues/937
    with tempfile.NamedTemporaryFile(prefix="tx-", delete=False) as input_tmp:
        input_tmp.write(data)

    args = [f"-{output_format.rstrip().lower()}", "+S", "+b"]
    kwargs = dict(check=True, stderr=subprocess.PIPE)

    if sys.platform == "win32":
        # On Windows, we also can't write to stdout and capture output, because tx
        # doesn't seem to correctly handle binary data in stdout.
        # https://github.com/adobe-type-tools/cffsubr/pull/4#issuecomment-635624491
        with tempfile.NamedTemporaryFile(prefix="tx-", delete=False) as output_tmp:
            output_tmp.write(data)
        args.extend(["-o", output_tmp.name])
    else:
        # On Unix we write to stdout and capture output
        kwargs["stdout"] = subprocess.PIPE
        output_tmp = None

    args.append(input_tmp.name)

    try:
        result = _run_embedded_tx(*args, **kwargs)
    except subprocess.CalledProcessError as e:
        raise Error(e.stderr.decode())
    else:
        if output_tmp is not None:
            with open(output_tmp.name, "rb") as fp:
                output_data = fp.read()
        else:
            output_data = result.stdout
    finally:
        os.remove(input_tmp.name)
        if output_tmp is not None:
            os.remove(output_tmp.name)

    return output_data


def _sniff_cff_table_format(otf: ttLib.TTFont) -> CFFTableTag:
    cff_tag = next(
        (
            CFFTableTag(tag)
            for tag in otf.keys()
            if tag in CFFTableTag.__members__.values()
        ),
        None,
    )
    if not cff_tag:
        raise Error("Invalid OTF: no 'CFF ' or 'CFF2' tables found")
    return cff_tag


def subroutinize(
    otf: ttLib.TTFont,
    cff_version: Optional[int] = None,
    keep_glyph_names: bool = True,
    inplace: bool = True,
) -> ttLib.TTFont:
    """Run subroutinizer on a FontTools TTFont's 'CFF ' or 'CFF2' table.

    Args:
        otf (TTFont): the input CFF-flavored OTF as a FontTools TTFont. It should
            contain either 'CFF ' or 'CFF2' table.
        cff_version (Optional[str]): the output table format version, 1 for 'CFF ',
            2 for 'CFF2'. By default, it's the same as the input table format.
        keep_glyph_names (bool): CFF 1.0 stores the postscript glyph names and uses
            the more compact post table format 3.0. CFF2 does not contain glyph names.
            When converting from CFF to CFF2, the post table will be set to format 2.0
            to preserve the glyph names. If you prefer instead to drop all glyph names
            and keep the post format 3.0, set keep_glyph_names=False.
        inplace (bool): whether to create a copy or modify the input font. By default
            the input font is modified.

    Returns:
        The modified font containing the subroutinized CFF or CFF2 table.
        This will be a different TTFont object if inplace=False.

    Raises:
        cffsubr.Error if the font doesn't contain 'CFF ' or 'CFF2' table,
        or if subroutinization process fails.
    """
    input_format = _sniff_cff_table_format(otf)

    if cff_version is None:
        output_format = input_format
    else:
        output_format = CFFTableTag.from_version(cff_version)

    if not inplace:
        otf = copy.deepcopy(otf)

    glyphOrder = otf.getGlyphOrder()

    buf = io.BytesIO()
    otf.save(buf)
    otf_data = buf.getvalue()

    compressed_cff_data = _tx_subroutinize(otf_data, output_format)

    cff_table = ttLib.newTable(output_format)
    cff_table.decompile(compressed_cff_data, otf)

    del otf[input_format]
    otf[output_format] = cff_table

    if (
        input_format == CFFTableTag.CFF
        and output_format == CFFTableTag.CFF2
        and keep_glyph_names
    ):
        # set 'post' to format 2 to keep the glyph names dropped from CFF2
        post_table = otf.get("post")
        if post_table and post_table.formatType != 2.0:
            post_table.formatType = 2.0
            post_table.extraNames = []
            post_table.mapping = {}
            post_table.glyphOrder = glyphOrder

    return otf


def has_subroutines(otf: ttLib.TTFont) -> bool:
    """Return True if the font's CFF or CFF2 table contains any subroutines."""
    table_tag = _sniff_cff_table_format(otf)
    top_dict = otf[table_tag].cff.topDictIndex[0]
    all_subrs = [top_dict.GlobalSubrs]
    if hasattr(top_dict, "FDArray"):
        all_subrs.extend(
            fd.Private.Subrs for fd in top_dict.FDArray if hasattr(fd.Private, "Subrs")
        )
    elif hasattr(top_dict.Private, "Subrs"):
        all_subrs.append(top_dict.Private.Subrs)
    return any(all_subrs)


def desubroutinize(otf: ttLib.TTFont, inplace=True) -> ttLib.TTFont:
    """Remove all subroutines from the font.

    Args:
        otf (ttLib.TTFont): the input font object.
        inplace (bool): whether to create a copy or modify the input font. By default
            the input font is modified.

    Returns:
        The modified font containing the desubroutinized CFF or CFF2 table.
        This will be a different TTFont object if inplace=False.

    Raises:
        cffsubr.Error if the font doesn't contain 'CFF ' or 'CFF2' table,
        or if desubroutinization process fails.
    """
    # the 'desubroutinize' method is dynamically added to the CFF table class
    # as a side-effect of importing the fontTools.subset.cff module...
    from fontTools.subset import cff as _

    if not inplace:
        otf = copy.deepcopy(otf)

    table_tag = _sniff_cff_table_format(otf)
    try:
        otf[table_tag].desubroutinize()
    except Exception as e:
        raise Error("Desubroutinization failed") from e

    return otf
