import io
import pathlib
import logging
from fontTools import ttLib
from fontTools import cffLib
import cffsubr
import pytest


DATA_DIR = pathlib.Path(__file__).parent / "data"


def load_test_font(name):
    font = ttLib.TTFont()
    font.importXML(DATA_DIR / name)
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    return ttLib.TTFont(buf)


def recompile_font(otf):
    buf = io.BytesIO()
    otf.save(buf)
    buf.seek(0)
    return ttLib.TTFont(buf)


class TestSubroutinize:
    @pytest.mark.parametrize(
        "testfile, table_tag",
        [
            ("SourceSansPro-Regular.subset.ttx", "CFF "),
            ("SourceSansVariable-Roman.subset.ttx", "CFF2"),
        ],
    )
    def test_output_same_cff_version(self, testfile, table_tag):
        font = load_test_font(testfile)

        assert cffsubr._sniff_cff_table_format(font) == table_tag

        cffsubr.subroutinize(font)

        assert cffsubr._sniff_cff_table_format(font) == table_tag

    @pytest.mark.parametrize(
        "testfile, cff_version",
        [
            ("SourceSansPro-Regular.subset.ttx", 2),
            ("SourceSansVariable-Roman.subset.ttx", 1),
        ],
    )
    def test_output_different_cff_version(self, testfile, cff_version):
        font = load_test_font(testfile)
        table_tag = cffsubr._sniff_cff_table_format(font)

        cffsubr.subroutinize(font, cff_version=cff_version)

        assert cffsubr._sniff_cff_table_format(font) != table_tag

    @pytest.mark.parametrize(
        "testfile",
        ["SourceSansPro-Regular.subset.ttx", "SourceSansVariable-Roman.subset.ttx"],
    )
    def test_inplace(self, testfile):
        font = load_test_font(testfile)

        font2 = cffsubr.subroutinize(font, inplace=False)
        assert font is not font2

        font3 = cffsubr.subroutinize(font, inplace=True)
        assert font3 is font

    def test_keep_glyph_names(self):
        font = load_test_font("SourceSansPro-Regular.subset.ttx")
        glyph_order = font.getGlyphOrder()

        assert font["post"].formatType == 3.0
        assert font["post"].glyphOrder is None

        cffsubr.subroutinize(font, cff_version=2)

        assert font["post"].formatType == 2.0
        assert font["post"].glyphOrder == glyph_order

        font2 = recompile_font(font)

        assert font2.getGlyphOrder() == glyph_order

        # now convert from CFF2 to CFF1 and check post format is set to 3.0
        # https://github.com/adobe-type-tools/cffsubr/issues/8
        cffsubr.subroutinize(font2, cff_version=1)

        assert font2["post"].formatType == 3.0
        assert font2["post"].glyphOrder == None

        font3 = recompile_font(font2)

        assert font3.getGlyphOrder() == glyph_order

    def test_drop_glyph_names(self):
        font = load_test_font("SourceSansPro-Regular.subset.ttx")
        glyph_order = font.getGlyphOrder()

        assert font["post"].formatType == 3.0
        assert font["post"].glyphOrder is None

        cffsubr.subroutinize(font, cff_version=2, keep_glyph_names=False)

        assert font["post"].formatType == 3.0
        assert font["post"].glyphOrder is None

        buf = io.BytesIO()
        font.save(buf)
        buf.seek(0)
        font2 = ttLib.TTFont(buf)

        assert font2.getGlyphOrder() != glyph_order

    def test_non_standard_upem_mute_font_matrix_warning(self, caplog):
        # See https://github.com/adobe-type-tools/cffsubr/issues/13
        font = load_test_font("FontMatrixTest.ttx")

        assert font["CFF "].cff[0].FontMatrix == [0.0005, 0, 0, 0.0005, 0, 0]

        cffsubr.subroutinize(font, cff_version=2)

        with caplog.at_level(logging.WARNING, logger=cffLib.log.name):
            font2 = recompile_font(font)

        assert (
            "Some CFF FDArray/FontDict keys were ignored upon compile: FontMatrix"
            not in caplog.text
        )


@pytest.mark.parametrize(
    "testfile, table_tag",
    [
        ("SourceSansPro-Regular.subset.ttx", "CFF "),
        ("SourceSansVariable-Roman.subset.ttx", "CFF2"),
    ],
)
def test_sniff_cff_table_format(testfile, table_tag):
    font = load_test_font(testfile)

    assert cffsubr._sniff_cff_table_format(font) == table_tag


def test_sniff_cff_table_format_invalid():
    with pytest.raises(cffsubr.Error, match="Invalid OTF"):
        cffsubr._sniff_cff_table_format(ttLib.TTFont())


@pytest.mark.parametrize(
    "testfile",
    ["SourceSansPro-Regular.subset.ttx", "SourceSansVariable-Roman.subset.ttx"],
)
def test_has_subroutines(testfile):
    font = load_test_font(testfile)

    assert not cffsubr.has_subroutines(font)
    assert cffsubr.has_subroutines(cffsubr.subroutinize(font))


@pytest.mark.parametrize(
    "testfile",
    ["SourceSansPro-Regular.subset.ttx", "SourceSansVariable-Roman.subset.ttx"],
)
def test_desubroutinize(testfile):
    font = load_test_font(testfile)
    cffsubr.subroutinize(font)

    font2 = cffsubr.desubroutinize(font, inplace=False)

    assert cffsubr.has_subroutines(font)
    assert not cffsubr.has_subroutines(font2)
