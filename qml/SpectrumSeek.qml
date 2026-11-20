import QtQuick
import QtQuick.Controls

// Seek of the visualizer full view: the music's spectrum as a row of bars (or a wave, the
// style the full view's moon button picks) standing on the seek bar, lit up to where the song
// is, with the elapsed and total time underneath. Dragging the spectrum or the bar seeks.
// Without cava (or on Windows) the spectrum dances by itself while the song plays.
Item {
    id: ss
    readonly property var s: player ? player.state : ({})
    property bool showSpectrum: true
    property bool running: true                     // false while the full view is hidden
    property string style: session ? session.visualizerStyle : "bars"
    property color litColor: Qt.tint("#ffffff", Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.4))
    property color dimColor: Qt.rgba(1, 1, 1, 0.2)
    property int spectrumHeight: 44

    readonly property bool playing: !!s.isPlaying
    readonly property real durationMs: Math.max(1, s.durationMs || 0)
    readonly property real currentMs: seekMouse.pressed ? seekMouse.dragMs : (player ? player.position : 0)
    readonly property real progress: Math.max(0, Math.min(1, currentMs / durationMs))
    readonly property real specH: showSpectrum ? spectrumHeight : 0

    implicitHeight: specH + (showSpectrum ? 4 : 0) + track.height + 20

    // ---- the spectrum -----------------------------------------------------------------------
    readonly property int bands: Math.max(24, Math.min(96, Math.floor(width / 7)))   // thin bars, about 4 px
    readonly property real rest: 0.06               // a paused song leaves a low, quiet row
    property var _level: []
    property real _time: 0
    property bool _settled: false
    onPlayingChanged: _settled = false
    onStyleChanged: spectrum.requestPaint()
    onProgressChanged: if (!anim.running) spectrum.requestPaint()

    function sampleBin(arr, pos) {
        const i0 = Math.max(0, Math.min(arr.length - 1, Math.floor(pos)))
        const i1 = Math.min(arr.length - 1, i0 + 1)
        const f = pos - i0
        return (arr[i0] || 0) * (1 - f) + (arr[i1] || 0) * f
    }

    FrameAnimation {
        id: anim
        running: ss.showSpectrum && ss.running && ss.visible && (ss.playing || !ss._settled)
        onTriggered: {
            const dt = Math.min(0.05, frameTime)
            ss._time += dt
            const N = ss.bands
            if (ss._level.length !== N) {
                const init = new Array(N)
                for (let i = 0; i < N; i++) init[i] = ss.rest
                ss._level = init
            }
            const raw = (visualizer && visualizer.active) ? (visualizer.bars || []) : []
            let peak = 0
            for (let i = 0; i < raw.length; i++) peak = Math.max(peak, raw[i] || 0)
            const live = raw.length > 1 && peak > 0.008
            const t = ss._time
            const cur = ss._level
            const attack = Math.min(1, dt * 22)
            const release = Math.min(1, dt * 8)
            let moving = 0
            for (let i = 0; i < N; i++) {
                const x = i / (N - 1)
                let v = ss.rest
                if (ss.playing && live) {
                    // the low notes on the left, like the bars of an equalizer
                    v = 0.08 + 0.92 * Math.pow(ss.sampleBin(raw, x * (raw.length - 1) * 0.85), 0.8)
                } else if (ss.playing) {
                    const beat = Math.pow(0.5 + 0.5 * Math.sin(t * 5.6), 2.4)
                    const roll = 0.5 + 0.5 * Math.sin(t * 3.1 - x * 9.0)
                    const shimmer = 0.5 + 0.5 * Math.sin(t * 7.7 + x * 23.0)
                    v = 0.16 + 0.42 * (1 - x * 0.55) * (0.4 + 0.6 * beat) * (0.5 + 0.5 * roll) + 0.14 * shimmer
                }
                v = Math.max(ss.rest, Math.min(1, v))
                const step = (v - cur[i]) * (v > cur[i] ? attack : release)
                cur[i] += step
                moving = Math.max(moving, Math.abs(step))
            }
            if (!ss.playing && moving < 0.0005)
                ss._settled = true
            spectrum.requestPaint()
        }
    }

    Canvas {
        id: spectrum
        visible: ss.showSpectrum
        width: parent.width
        height: ss.specH
        renderTarget: Canvas.FramebufferObject
        renderStrategy: Canvas.Cooperative
        onWidthChanged: requestPaint()

        function color(c, a) {
            return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + ","
                 + Math.round(c.b * 255) + "," + (c.a * a) + ")"
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            const lv = ss._level
            const N = lv.length
            if (N < 2 || width <= 0)
                return
            const px = ss.progress * width
            const lit = color(ss.litColor, 1)
            const dim = color(ss.dimColor, 1)

            if (ss.style === "wave") {
                // a soft hill line through a few averaged points of the bands, filled down to the bar
                const M = Math.max(8, Math.round(width / 26))
                const pts = []
                for (let k = 0; k < M; k++) {
                    const a = Math.floor(k / M * N), b = Math.max(a + 1, Math.floor((k + 1) / M * N))
                    let sum = 0
                    for (let i = a; i < b; i++) sum += lv[i]
                    const v = Math.min(1, sum / (b - a) * 1.25)
                    pts.push([k / (M - 1) * width, height - Math.max(2, v * (height - 2))])
                }
                const P = pts.length
                function outline() {
                    ctx.beginPath()
                    ctx.moveTo(0, height)
                    ctx.lineTo(pts[0][0], pts[0][1])
                    for (let i = 1; i < P; i++) {
                        const mx = (pts[i - 1][0] + pts[i][0]) / 2
                        const my = (pts[i - 1][1] + pts[i][1]) / 2
                        ctx.quadraticCurveTo(pts[i - 1][0], pts[i - 1][1], mx, my)
                    }
                    ctx.lineTo(pts[P - 1][0], pts[P - 1][1])
                    ctx.lineTo(width, height)
                    ctx.closePath()
                }
                for (const part of [[0, px, lit, 0.55], [px, width - px, dim, 1]]) {
                    if (part[1] <= 0)
                        continue
                    ctx.save()
                    ctx.beginPath()
                    ctx.rect(part[0], 0, part[1], height)
                    ctx.clip()
                    const grad = ctx.createLinearGradient(0, 0, 0, height)
                    grad.addColorStop(0, part[2])
                    grad.addColorStop(1, color(part[2] === lit ? ss.litColor : ss.dimColor, 0.15))
                    ctx.globalAlpha = part[3]
                    ctx.fillStyle = grad
                    outline()
                    ctx.fill()
                    ctx.globalAlpha = 1
                    ctx.strokeStyle = part[2]
                    ctx.lineWidth = 2
                    ctx.stroke()
                    ctx.restore()
                }
                return
            }

            // bars: rounded columns standing on the seek bar
            const gap = 3
            const bw = Math.max(2, (width - gap * (N - 1)) / N)
            for (let i = 0; i < N; i++) {
                const x = i * (bw + gap)
                const h = Math.max(3, lv[i] * height)
                ctx.fillStyle = x + bw / 2 <= px ? lit : dim
                const r = Math.min(bw / 2, h / 2)
                ctx.beginPath()
                ctx.moveTo(x, height)
                ctx.lineTo(x, height - h + r)
                ctx.arcTo(x, height - h, x + r, height - h, r)
                ctx.lineTo(x + bw - r, height - h)
                ctx.arcTo(x + bw, height - h, x + bw, height - h + r, r)
                ctx.lineTo(x + bw, height)
                ctx.closePath()
                ctx.fill()
            }
        }
    }

    // ---- the seek bar and the times ----------------------------------------------------------
    Item {
        id: track
        y: ss.specH + (ss.showSpectrum ? 4 : 0)
        width: parent.width
        height: 22
        SeekTrack {
            anchors.fill: parent
            // a plain line under the spectrum: a second row of bars or a wave would fight with it
            trackStyle: ss.showSpectrum ? "line" : (session ? session.seekStyle : "line")
            progress: ss.progress
            fill: ss.litColor
            rest: ss.dimColor
            knob: "#ffffff"
            engaged: seekMouse.containsMouse || seekMouse.pressed
            playing: ss.playing
            seed: ss.s.uri || ""
        }
    }

    Label {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        text: Theme.fmt(ss.currentMs)
        color: Qt.rgba(1, 1, 1, 0.72)
        font.pixelSize: 12
        font.features: { "tnum": 1 }
    }
    Label {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        text: Theme.fmt(ss.s.durationMs || 0)
        color: Qt.rgba(1, 1, 1, 0.72)
        font.pixelSize: 12
        font.features: { "tnum": 1 }
    }

    MouseArea {
        id: seekMouse
        width: parent.width
        height: track.y + track.height
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        enabled: !!ss.s.hasTrack
        property real dragMs: 0
        function updateDrag(mx) {
            dragMs = Math.max(0, Math.min(1, mx / Math.max(1, width))) * ss.durationMs
        }
        onPressed: (mouse) => updateDrag(mouse.x)
        onPositionChanged: (mouse) => { if (pressed) updateDrag(mouse.x) }
        onReleased: player.seek(dragMs)
    }
}
