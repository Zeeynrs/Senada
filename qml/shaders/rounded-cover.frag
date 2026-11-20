#version 440
// Cover art with rounded corners, a circle or a scalloped badge, cut in one pass:
// no mask layer and no copy of the image, so a cover costs a single texture.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 qt_SubRect_source;  // where the image sits in a texture atlas
    vec4 crop;               // part of the image shown (PreserveAspectCrop): offset xy, size zw
    vec2 itemSize;           // logical pixels
    float radius;            // corner radius (logical pixels)
    float edge;              // anti-aliased edge width (logical pixels)
    float scallops;          // 0: rounded rectangle or circle
    float scallopDepth;
};
layout(binding = 1) uniform sampler2D source;

float roundedBox(vec2 p, vec2 halfSize, float r) {
    vec2 q = abs(p) - halfSize + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void main() {
    vec2 local = (qt_TexCoord0 - qt_SubRect_source.xy) / qt_SubRect_source.zw;
    vec2 size = max(itemSize, vec2(1.0));
    vec2 p = (local - 0.5) * size;
    float d;
    if (scallops > 0.5) {
        float half_ = min(size.x, size.y) * 0.5;
        float a = atan(p.y, p.x);
        float r = half_ * (1.0 - scallopDepth) + half_ * scallopDepth * cos(scallops * a);
        d = length(p) - r;
    } else {
        d = roundedBox(p, size * 0.5, min(radius, min(size.x, size.y) * 0.5));
    }
    float coverage = 1.0 - smoothstep(-edge * 0.5, edge * 0.5, d);
    vec2 uv = qt_SubRect_source.xy + (crop.xy + clamp(local, 0.0, 1.0) * crop.zw) * qt_SubRect_source.zw;
    fragColor = texture(source, uv) * coverage * qt_Opacity;
}
