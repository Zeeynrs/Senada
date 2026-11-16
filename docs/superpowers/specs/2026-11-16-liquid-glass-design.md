# Liquid Glass for Senada

Add an optional `liquid` glass mode under Settings → Appearance → Glass effect,
inspired by https://github.com/ybouane/liquidglass. Keep the existing color mode,
accent, glass opacity, and other glass modes. This is a native Qt Quick adaptation;
the web library is not embedded or copied.

Use a soft blue/violet backdrop when idle and blurred artwork when available.
Rounded navigation, content, toolbar and a floating player sample that shared
backdrop, with subtle edge refraction, highlights and translucent material.
Keep text and interactive contents sharp. Support light and dark colors.

Implement a reusable GlassSurface and a precompiled Qt shader. One shared,
downsampled backdrop texture avoids capturing the entire application repeatedly.
Software rendering uses plain translucent surfaces and highlights. Effects are
loaded only in Liquid Glass mode. No continuously running decorative animations.

Alternatives considered: extending the existing cover mode would prevent users
from keeping its current appearance; embedding the WebGL library would require
a browser and duplicate the native UI. A separate native mode fits this project.
These implementation choices are the agent's defaults for the user's request.

Check persistence and switching modes with offline unit tests; render surfaces
and the application in both color modes, at minimum and normal window sizes.
Include Indonesian copy and document how to activate the mode and rebuild shaders.
