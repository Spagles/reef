import json
import logging
from typing import Annotated, Any, ClassVar, Literal

from beet import (
    Context,
    DataPack,
    Drop,
    Function,
    JsonFileBase,
    NamespaceFileScope,
    configurable,
)
from pydantic import BaseModel, Field, RootModel

from .. import state
from ..models import NumberString, ResourceLocation
from ..options import ReefPluginOptions
from .page import ElementModel, PageModel, ReefPageData
from .slideshow import ReefSlideshowData

__all__ = ["ReefSpecialData", "special"]

SPECIAL_NAMESPACE = "reef/data/special"
logger = logging.getLogger(SPECIAL_NAMESPACE)

class ReefBaseSpecialDataModel(BaseModel):
    transition: ResourceLocation | None = None
    """Resource location of a transition"""

    page_count: int
    """Page count of the slideshow"""

    overrides: dict[NumberString, ReefSpecialDataPdfPageModel] | None = None
    """Content overrides for specific pages."""

class ReefSpecialDataPdfPageModel(PageModel):
    sequence: list[list[ElementModel]] | None = None

class ReefSpecialDataPdfModel(ReefBaseSpecialDataModel):
    """A Reef Mini definition using PDF files."""

    type: Literal["reef:pdf"]
    """A Reef Mini definition using PDF files."""

    pdf: ResourceLocation
    """Resource location pointing to the PDF file in `assets/<namespace>/reef/<path>`."""

class ReefSpecialDataItemModelModel(ReefBaseSpecialDataModel):
    """A Reef Mini definition using an item model definition file."""

    type: Literal["reef:item_model"]
    """A Reef Mini definition using an item model definition file."""

    item_model: ResourceLocation
    """Resource location pointing to the item model definition in `assets/<namespace>/items/<path>`."""

class ReefSpecialDataModel(RootModel[Annotated[
    ReefSpecialDataPdfModel | ReefSpecialDataItemModelModel,
    Field(discriminator="type")
]]):
    pass

class ReefSpecialData(JsonFileBase):
    """Class representing Reef Special files in data/ns/reef/special"""

    model = ReefSpecialDataModel
    scope: ClassVar[NamespaceFileScope] = ("reef", "special")
    extension: ClassVar[str] = ".json"

    def bind(self, pack: DataPack, path: str):
        super().bind(pack, path)
        namespace, _, path = path.partition(":")
        json_data: ReefSpecialDataPdfModel | ReefSpecialDataItemModelModel = self.data.root

        model_identifier: str

        match(json_data.type):
            case "reef:item_model":
                model_identifier = json_data.item_model
            case "reef:pdf":
                pdf_namespace, _, pdf_path = json_data.pdf.partition(":")
                model_identifier = f"{pdf_namespace}:reef/mini/{pdf_path}"

        if json_data.overrides is not None:
            self.generate_full_reef_with_overrides(pack, namespace, path, model_identifier)
        else:
            self.generate_reef_mini_functions(pack, namespace, path, model_identifier)

        raise Drop()

    def generate_full_reef_with_overrides(
        self,
        pack: DataPack,
        namespace: str,
        path: str,
        model_identifier: str
    ):
        """Generates the function files for a PDF special reef file."""
        identifier = f"{namespace}:{path}"
        json_data: ReefSpecialDataPdfModel = self.data.root

        slideshow = []

        for i in range(json_data.page_count):
            page_id = f"{identifier}/{i}"
            page: dict[str, Any] = {
                "sequence": [[{
                    "type": "graphic",
                    "model": model_identifier,
                    "components": {"minecraft:custom_model_data": {"floats": [i]}},
                    "pos": [0,0,0]
                }]]
            }

            if json_data.transition is not None: page["transition"] = json_data.transition

            if json_data.overrides is not None and str(i) in json_data.overrides is not None:
                page_override = json_data.overrides[str(i)].model_dump()

                if page_override.get("sequence") is not None: 
                    page["sequence"][0].extend(page_override["sequence"][0])
                    page["sequence"].extend(page_override["sequence"][1:])
                if page_override.get("commands") is not None: page["commands"] = page_override["commands"]
                if page_override.get("transition") is not None: page["transition"] = page_override["transition"]

            slideshow.append(page_id)
            pack[ReefPageData][page_id] = ReefPageData(json.dumps(page))

        pack[ReefSlideshowData][identifier] = ReefSlideshowData(json.dumps(slideshow))


    def generate_reef_mini_functions(
        self,
        pack: DataPack,
        namespace: str,
        path: str,
        model_identifier: str
    ):
        """Generates the function files to register a Reef Mini definition."""

        identifier = f"{namespace}:{path}"
        storage = f"{namespace}:reef"
        nbt_path = f'register.mini."{identifier}"'

        json_data: ReefSpecialDataPdfModel | ReefSpecialDataItemModelModel = self.data.root

        logger.debug("Building data %s", f"{namespace}:reef/{path}")

        log_prefix = ["", {"text": "[", "color": "#6e3787"}, {"text": "reef", "color": "#ed2de3"}, {"text": "] ", "color": "#6e3787"}]
        register_main = pack[namespace].functions.setdefault("reef/register_namespace", Function([
            f"tellraw @a[tag=reef.permissions.see_debug] {json.dumps([*log_prefix, {"text": f"Registering data for namespace '{namespace}'", "color": "#77d6ff"}])}",
        ]))

        mini_definition = {
            "page_count": json_data.page_count,
            "model": model_identifier,
            **({"transition": json_data.transition} if json_data.transition is not None else {})
        }

        function_contents = Function([
            f'data modify storage {storage} {nbt_path} set value {json.dumps(mini_definition)}',
            f'function reef:api/register/mini {{identifier: "{identifier}", storage_path: \'{storage} {nbt_path}\'}}'
        ])

        if not state.opts.compress_functions:
            pack[namespace].functions[f"reef/register/page/{path}"] = function_contents

            register_main.append([
                f"function {namespace}:reef/register/page/{path}"
            ])
        else:
            register_main.append(function_contents)

@configurable("reef", validator=ReefPluginOptions)
def special(ctx: Context, opts: ReefPluginOptions):
    """Adds support for Reef special JSON files."""

    ctx.data.extend_namespace.append(ReefSpecialData)
