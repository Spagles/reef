from collections.abc import Callable
from typing import Annotated, ClassVar, Literal

from beet import (
    Context,
    Drop,
    ItemModel,
    JsonFileBase,
    Model,
    NamespaceFileScope,
    ResourcePack,
    Texture,
    TextureMcmeta,
)
from PIL import Image
from pydantic import BaseModel, Field

DEFAULT_FPS = 10

type IntVec3 = tuple[int, int, int]
type FloatVec3 = tuple[float, float, float]

class BacklightKeyframeModel(BaseModel):
    time: Annotated[float, Field(ge=0)]
    color: IntVec3
    easing: Literal["linear", "ease_in", "ease_out", "ease_in_out", "ease_in_quint", "ease_out_quint", "ease_in_out_quint"]

class BacklightDefinitionModel(BaseModel):
    keyframes: list[BacklightKeyframeModel]
    fps: Annotated[int, Field(ge=0, le=20)] | None = DEFAULT_FPS
    frametime: Annotated[int, Field(ge=0)] | None = None
    interpolate: bool | None = True

def lerp_color(color_a: FloatVec3, color_b: FloatVec3, t: float):
    return tuple(color_a[i] + (color_b[i] - color_a[i]) * t for i in range(3))

def rgb_to_lab(rgb: IntVec3) -> FloatVec3:
    # https://gist.github.com/ronniebasak/e5331e54cf9414ab0fec23b4f6a27e2a
    # Step 1: Convert RGB to Linear RGB
    r = rgb[0] / 255
    g = rgb[1] / 255
    b = rgb[2] / 255
    
    linear_r = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
    linear_g = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
    linear_b = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4

    # Step 2: Linear RGB to XYZ
    x = 0.4124 * linear_r + 0.3576 * linear_g + 0.1805 * linear_b
    y = 0.2126 * linear_r + 0.7152 * linear_g + 0.0722 * linear_b
    z = 0.0193 * linear_r + 0.1192 * linear_g + 0.9505 * linear_b

    # Step 3: XYZ to Lab
    xn = 0.95047
    yn = 1.0
    zn = 1.08883

    x_norm = x / xn
    y_norm = y / yn
    z_norm = z / zn

    fx = x_norm ** (1/3) if x_norm > 0.008856 else 7.787 * x_norm + 16 / 116
    fy = y_norm ** (1/3) if y_norm > 0.008856 else 7.787 * y_norm + 16 / 116
    fz = z_norm ** (1/3) if z_norm > 0.008856 else 7.787 * z_norm + 16 / 116

    l = 116 * fy - 16
    a = 500 * (fx - fy)
    b_lab = 200 * (fy - fz)

    return (l, a, b_lab)

def lab_to_rgb(lab: FloatVec3) -> IntVec3:
    l, a, b_lab = lab

    # Step 1: Lab to XYZ
    xn = 0.95047
    yn = 1.0
    zn = 1.08883

    fy = (l + 16) / 116
    fx = a / 500 + fy
    fz = fy - b_lab / 200

    x_norm = fx ** 3 if fx ** 3 > 0.008856 else (fx - 16 / 116) / 7.787
    y_norm = fy ** 3 if fy ** 3 > 0.008856 else (fy - 16 / 116) / 7.787
    z_norm = fz ** 3 if fz ** 3 > 0.008856 else (fz - 16 / 116) / 7.787

    x = x_norm * xn
    y = y_norm * yn
    z = z_norm * zn

    # Step 2: XYZ to Linear RGB
    linear_r =  3.2406 * x - 1.5372 * y - 0.4986 * z
    linear_g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    linear_b =  0.0557 * x - 0.2040 * y + 1.0570 * z

    # Step 3: Linear RGB to RGB
    linear_r = max(0.0, min(1.0, linear_r))
    linear_g = max(0.0, min(1.0, linear_g))
    linear_b = max(0.0, min(1.0, linear_b))

    r = linear_r * 12.92 if linear_r <= 0.0031308 else 1.055 * linear_r ** (1 / 2.4) - 0.055
    g = linear_g * 12.92 if linear_g <= 0.0031308 else 1.055 * linear_g ** (1 / 2.4) - 0.055
    b = linear_b * 12.92 if linear_b <= 0.0031308 else 1.055 * linear_b ** (1 / 2.4) - 0.055

    return (round(r * 255), round(g * 255), round(b * 255))

EASINGS: dict[str, Callable[[float], float]] = {
    "linear": lambda t: t,
    "ease_in": lambda t: t ** 2,
    "ease_out": lambda t: 1 - ((1 - t) ** 2),
    "ease_in_out": lambda t: 2 * (t ** 2) if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2,
    "ease_in_quint": lambda t: t ** 5,
    "ease_out_quint": lambda t: 1 - ((1 - t) ** 5),
    "ease_in_out_quint": lambda t: 16 * (t ** 5) if t < 0.5 else 1 - ((-2 * t + 2) ** 5) / 2
}

class BacklightDefinitionFile(JsonFileBase):

    model = BacklightDefinitionModel
    scope: ClassVar[NamespaceFileScope] = ("backlight",)
    extension: ClassVar[str] = ".json"

    def bind(self, pack: ResourcePack, path: str):
        namespace, _, path = path.partition(":")

        json_data: BacklightDefinitionModel = self.data
        keyframes: list[BacklightKeyframeModel] = sorted(json_data.keyframes, key=lambda keyframe: keyframe.time)

        max_time = keyframes[-1].time
        total_frames = int(max_time * self.data.fps) + 1

        spritesheet = Image.new("RGB", (1, total_frames))

        for i in range(total_frames):
            color = self.calculate_color_from_frame(i, keyframes)
            spritesheet.putpixel((0, i), color)

        pack[namespace].textures[f"item/backlight/{path}"] = Texture(spritesheet)
        pack[namespace].textures_mcmeta[f"item/backlight/{path}"] = TextureMcmeta({
            "animation": {
                "frametime": 20 - (self.data.fps - 1) if self.data.frametime is None else self.data.frametime,
                "interpolate": self.data.interpolate,
                "width": 1,
                "height": 1
            }
        })

        pack[namespace].models[f"item/backlight/{path}"] = Model({
            "parent": "summit_stages:item/backlight_template",
            "textures": {
                "spritesheet": f"{namespace}:item/backlight/{path}"
            }
        })

        pack[namespace].item_models[f"backlight/{path}"] = ItemModel({
            "model": {
                "type": "minecraft:model",
                "model": f"{namespace}:item/backlight/{path}",
                "tints": [{
                    "type": "minecraft:constant",
                    "value": 66046
                }]
            }
        })

        raise Drop()

    def calculate_color_from_frame(self, frame: int, keyframes: list[BacklightKeyframeModel]) -> IntVec3:
        current_time = frame / self.data.fps

        prev_keyframe = next((keyframe for keyframe in reversed(keyframes) if keyframe.time <= current_time), keyframes[0])
        next_keyframe = next((keyframe for keyframe in keyframes if keyframe.time > current_time), None)
        
        if next_keyframe is None or next_keyframe.time == prev_keyframe.time:
            return prev_keyframe.color

        current_blend_time = (current_time - prev_keyframe.time) / (next_keyframe.time - prev_keyframe.time)
        prev_keyframe_color_in_oklch = rgb_to_lab(prev_keyframe.color)
        next_keyframe_color_in_oklch = rgb_to_lab(next_keyframe.color)
        easing = prev_keyframe.easing
        color = lerp_color(prev_keyframe_color_in_oklch, next_keyframe_color_in_oklch, EASINGS[easing](current_blend_time))

        return lab_to_rgb(color)

def custom_resource(ctx: Context):
    """Registers the backlight custom resource for panels."""
    ctx.assets.extend_namespace += [BacklightDefinitionFile]