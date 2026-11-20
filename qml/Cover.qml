import QtQuick
import QtQuick.Window

// Album/artist art with rounded corners (or scalloped badge) and a placeholder while loading.
Item {
    id: root
    property url source
    property real radius: 8
    property bool round: false
    property bool scalloped: false
    property int scallops: 24
    property real scallopDepth: 0.038
    property bool simple: false  // plain square image, cheaper for long lists
    property string fallbackIcon: "note"
    property url fallback                 // shown instead when `source` cannot be loaded
    property bool failed: false
    onSourceChanged: failed = false
    // covers from the internet are loaded from the copy on disk (senada/imagecache.py);
    // "" while that copy is being downloaded
    readonly property string remote: failed && fallback.toString() !== "" ? fallback.toString() : source.toString()
    property string shown: ""
    function refresh() { shown = typeof images === "undefined" ? remote : images.cached(remote) }
    onRemoteChanged: refresh()
    Component.onCompleted: refresh()
    Connections {
        target: typeof images === "undefined" ? null : images
        function onStored(url) { if (url === root.remote) root.refresh() }
    }
    readonly property bool ready: img.status === Image.Ready
    readonly property real cornerRadius: (round || scalloped) ? width / 2 : radius
    readonly property int loadSize: Math.ceil(Math.max(width, height) * Screen.devicePixelRatio)
    // rounded, round or scalloped through the shader; the software renderer has no shaders
    // and shows the plain square image instead
    readonly property bool shaped: !simple && GraphicsInfo.api !== GraphicsInfo.Software

    Rectangle {
        id: placeholderRect
        anchors.fill: parent
        radius: root.cornerRadius
        color: Theme.surface3
        visible: !root.ready && !root.scalloped
        Icon {
            anchors.centerIn: parent
            glyph: root.fallbackIcon
            size: Math.max(14, Math.min(root.width * 0.38, 64))
            color: Theme.faint
        }
    }

    // scalloped placeholder, drawn only for scalloped covers that are still loading
    Loader {
        anchors.fill: parent
        active: !root.ready && root.scalloped
        sourceComponent: Canvas {
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const cx = width / 2
                const cy = height / 2
                const rBase = Math.min(cx, cy) * (1 - root.scallopDepth)
                const amp = Math.min(cx, cy) * root.scallopDepth
                const N = root.scallops
                ctx.fillStyle = Theme.surface3
                ctx.beginPath()
                const steps = 360
                for (let i = 0; i <= steps; i++) {
                    const a = (i / steps) * Math.PI * 2
                    const r = rBase + amp * Math.cos(N * a)
                    const x = cx + Math.cos(a) * r
                    const y = cy + Math.sin(a) * r
                    if (i === 0) ctx.moveTo(x, y)
                    else ctx.lineTo(x, y)
                }
                ctx.closePath()
                ctx.fill()
            }
            Icon {
                anchors.centerIn: parent
                glyph: root.fallbackIcon
                size: Math.max(14, Math.min(root.width * 0.38, 64))
                color: Theme.faint
            }
        }
    }

    Image {
        id: img
        anchors.fill: parent
        source: root.shown
        onStatusChanged: {
            if (status !== Image.Error)
                return
            if (root.shown !== root.remote && typeof images !== "undefined") {
                images.forget(root.remote)  // a damaged saved copy: try the address itself
                root.refresh()
            } else if (!root.failed) {
                root.failed = true
            }
        }
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: root.loadSize
        sourceSize.height: root.loadSize
        visible: !root.shaped && root.ready
        smooth: true
    }

    // the shape is cut by a small shader straight from the image's texture: one texture per cover
    // (a mask layer plus an effect copy of the image needed three)
    Loader {
        anchors.fill: parent
        active: root.shaped && root.ready
        sourceComponent: ShaderEffect {
            readonly property real imageAspect: img.implicitHeight > 0 ? img.implicitWidth / img.implicitHeight : 1
            readonly property real itemAspect: height > 0 ? width / height : 1
            readonly property real cropW: imageAspect > itemAspect ? itemAspect / imageAspect : 1
            readonly property real cropH: imageAspect > itemAspect ? 1 : imageAspect / itemAspect
            property var source: img
            property vector4d crop: Qt.vector4d((1 - cropW) / 2, (1 - cropH) / 2, cropW, cropH)
            property vector2d itemSize: Qt.vector2d(width, height)
            property real radius: root.cornerRadius
            property real edge: 1 / Math.max(1, Screen.devicePixelRatio)
            property real scallops: root.scalloped ? root.scallops : 0
            property real scallopDepth: root.scallopDepth
            supportsAtlasTextures: true
            fragmentShader: "shaders/rounded-cover.frag.qsb"
            NumberAnimation on opacity { from: 0; to: 1; duration: 220 }
        }
    }
}
