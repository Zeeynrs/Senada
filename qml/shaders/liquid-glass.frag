#version 440
// Original Qt Quick implementation inspired by optical glass: rounded edge
// refraction, a restrained RGB fringe and directional rim lighting.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 sourceRect;
    vec2 panelSize;
    float cornerRadius;
};
layout(binding = 1) uniform sampler2D source;

float roundedBox(vec2 p, vec2 halfSize, float radius) {
    vec2 q = abs(p) - halfSize + radius;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main() {
    vec2 size = max(panelSize, vec2(1.0));
    vec2 p = (qt_TexCoord0 - 0.5) * size;
    float radius = min(cornerRadius, min(size.x, size.y) * 0.5);
    float d = roundedBox(p, size * 0.5 - 1.0, radius);
    float coverage = 1.0 - smoothstep(-0.75, 0.75, d);
    vec2 normal = normalize(vec2(
        roundedBox(p + vec2(0.5, 0), size * 0.5 - 1.0, radius) -
        roundedBox(p - vec2(0.5, 0), size * 0.5 - 1.0, radius),
        roundedBox(p + vec2(0, 0.5), size * 0.5 - 1.0, radius) -
        roundedBox(p - vec2(0, 0.5), size * 0.5 - 1.0, radius)) + vec2(0.00001));
    float bevel = 1.0 - smoothstep(0.0, 18.0, max(-d, 0.0));
    vec2 offset = normal * bevel * bevel * 7.0 / size * sourceRect.zw;
    vec2 uv = sourceRect.xy + qt_TexCoord0 * sourceRect.zw - offset;
    vec2 fringe = offset * 0.07;
    vec3 col = vec3(texture(source, clamp(uv + fringe, 0.001, 0.999)).r,
                    texture(source, clamp(uv, 0.001, 0.999)).g,
                    texture(source, clamp(uv - fringe, 0.001, 0.999)).b);
    float rim = (1.0 - smoothstep(0.0, 2.2, abs(d + 1.0))) *
                (0.45 + 0.55 * max(dot(normal, normalize(vec2(-0.6, -0.8))), 0.0));
    col = mix(col, vec3(1.0), rim * 0.32);
    fragColor = vec4(col * coverage, coverage) * qt_Opacity;
}
