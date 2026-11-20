# Liquid Glass shader

Liquid Glass is temporarily disabled in the application while it is being reworked.
The components, shader and rendering tests are retained for further development.

`liquid-glass.frag` is an original native implementation inspired by the optical
effects in [LiquidGlass](https://github.com/ybouane/liquidglass). It samples only
Senada's shared decorative backdrop. Text and controls are rendered normally.

The checked-in `liquid-glass.frag.qsb` is a portable Qt 6.4-compatible shader pack
with SPIR-V, GLSL (OpenGL / GLES), HLSL (Direct3D), and MSL (Metal) variants.
Existing installers copy the entire `qml` directory, including this asset.
Qt Shader Baker is a development tool; users do not need it installed.

After changing the source, rebuild from the repository root:

```sh
qsb --glsl '100 es,120,150' --hlsl 50 --msl 12 --qsbversion 64 \
    -o qml/shaders/liquid-glass.frag.qsb qml/shaders/liquid-glass.frag
```

Depending on your Qt installation, use `/usr/lib/qt6/bin/qsb` or `pyside6-qsb`.
Commit both source and shader pack. Software rendering skips this shader and
uses the QML fill and rim in `GlassSurface.qml`.

# Cover shape shader

`rounded-cover.frag` cuts cover art into rounded corners, a circle or a scalloped badge
straight from the image's own texture (`Cover.qml`), so each cover uses one texture instead
of an image, a mask layer and an effect copy. It also crops wide images the way
`Image.PreserveAspectCrop` does and handles images placed in Qt's texture atlas.

Rebuild it the same way:

```sh
qsb --glsl '100 es,120,150' --hlsl 50 --msl 12 --qsbversion 64 \
    -o qml/shaders/rounded-cover.frag.qsb qml/shaders/rounded-cover.frag
```

The software renderer shows the plain square image. `tests/test_cover.py` checks that
fallback offscreen; `SENADA_GPU_TESTS=1` renders in a real window to check the shader.
