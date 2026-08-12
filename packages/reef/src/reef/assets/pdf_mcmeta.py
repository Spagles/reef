import logging
from typing import ClassVar

from beet import (
    Context,
    JsonFileBase,
    NamespaceFileScope,
    configurable,
)
from pydantic import BaseModel

from ..options import ReefPluginOptions

__all__ = ["ReefPdfMcmeta", "pdf_mcmeta"]

PDF_NAMESPACE = "reef/assets/pdf.mcmeta"
logger = logging.getLogger(PDF_NAMESPACE)

class ReefPdfMcmetaModel(BaseModel):
    size: tuple[float, float]

class ReefPdfMcmeta(JsonFileBase):

    model = ReefPdfMcmetaModel
    scope: ClassVar[NamespaceFileScope] = ("reef", "pdf")
    extension: ClassVar[str] = ".pdf.mcmeta"

    def bind(self, pack, path):
        super().bind(pack, path)
        logger.warning("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        logger.warning(self.data)

@configurable("reef", validator=ReefPluginOptions)
def pdf_mcmeta(ctx: Context, opts: ReefPluginOptions):
    """Adds support for Reef PDF files to generate Reef Mini compatible files."""

    ctx.assets.extend_namespace.append(ReefPdfMcmeta)
