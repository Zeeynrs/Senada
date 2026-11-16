import QtQuick

// Reusable material. Controls can use the inexpensive sheen with refractive=false.
// The software renderer keeps the translucent fill and rim without loading a shader.
Rectangle {
    id: surface
    property bool refractive: true
    property color materialColor: Theme.glassFill
    property real highlight: 1
    readonly property real backdropWidth: Theme.liquidBackdrop ? Math.max(1, Theme.liquidBackdrop.width) : 1
    readonly property real backdropHeight: Theme.liquidBackdrop ? Math.max(1, Theme.liquidBackdrop.height) : 1
    radius: Theme.panelRadius
    color: materialColor
    border.color: Theme.glassRim
    border.width: 1

    readonly property point sceneOrigin: {
        // mapToItem alone does not register ancestor position changes as dependencies.
        let item = surface
        let positionDependency = 0
        while (item) {
            positionDependency += item.x + item.y
            item = item.parent
        }
        return Theme.liquidBackdrop ? surface.mapToItem(Theme.liquidBackdrop, 0, 0) : Qt.point(0, 0)
    }
    Loader {
        anchors.fill: parent
        active: Theme.liquid && surface.refractive && !!Theme.liquidSource
                && surface.GraphicsInfo.api !== GraphicsInfo.Software
        sourceComponent: ShaderEffect {
            property var source: Theme.liquidSource
            property vector4d sourceRect: Qt.vector4d(
                surface.sceneOrigin.x / surface.backdropWidth,
                surface.sceneOrigin.y / surface.backdropHeight,
                width / surface.backdropWidth,
                height / surface.backdropHeight)
            property vector2d panelSize: Qt.vector2d(width, height)
            property real cornerRadius: surface.radius
            fragmentShader: "shaders/liquid-glass.frag.qsb"
        }
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.radius
        color: surface.materialColor
        // The root supplies the fill without the shader; above it this veil keeps
        // the refracted backdrop from reducing contrast behind text and icons.
        visible: Theme.liquid && surface.refractive && !!Theme.liquidSource
                 && surface.GraphicsInfo.api !== GraphicsInfo.Software
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.radius
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, (Theme.dark ? 0.12 : 0.4) * surface.highlight) }
            GradientStop { position: 0.35; color: Qt.rgba(1, 1, 1, 0.02 * surface.highlight) }
            GradientStop { position: 0.72; color: "transparent" }
            GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0.04 * surface.highlight) }
        }
        border.width: 1
        border.color: surface.border.color
    }
}
