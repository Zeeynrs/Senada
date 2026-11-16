# Liquid Glass shader

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
