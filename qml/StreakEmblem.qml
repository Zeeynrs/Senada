import QtQuick

// Original Senada streak mark: a vinyl record with an equalizer at its heart.
// Each evolution keeps that silhouette and adds sound-wave/orbit details.
Item {
    id: emblem
    property int days: 0
    property bool lit: false
    property bool animate: true
    readonly property int stage: days >= 500 ? 5 : days >= 200 ? 4 : days >= 100 ? 3
                                 : days >= 30 ? 2 : days >= 7 ? 1 : 0
    readonly property var milestones: [1, 7, 30, 100, 200, 500]
    readonly property var titles: ["First spin", "In rhythm", "On repeat", "Resonance", "Headliner", "Legend"]
    readonly property string stageTitle: I18n.t(titles[stage])
    readonly property int nextMilestone: milestones.find(n => n > days) || 0
    readonly property color energyColor: ["#6ce5bd", "#5bdfdf", "#72caff", "#edc981", "#cfb7ff", "#91f5df"][stage]
    readonly property bool dark: Theme.dark
    property real illumination: lit ? 1 : 0
    Behavior on illumination {
        enabled: emblem.animate
        NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
    }
    implicitWidth: 128
    implicitHeight: 128
    Accessible.ignored: true  // the containing card provides the day count and state
    onStageChanged: art.requestPaint()
    onIlluminationChanged: art.requestPaint()
    onDarkChanged: art.requestPaint()

    Canvas {
        id: art
        anchors.fill: parent
        canvasSize: Qt.size(Math.max(1, Math.round(width)), Math.max(1, Math.round(height)))
        antialiasing: true
        onCanvasSizeChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            if (!ctx) return
            ctx.reset()
            const side = Math.min(canvasSize.width, canvasSize.height)
            ctx.translate((canvasSize.width - side) / 2, (canvasSize.height - side) / 2)
            ctx.scale(side / 240, side / 240)
            const power = emblem.illumination
            const stage = emblem.stage
            const energy = Theme.mix(Theme.faint, emblem.energyColor, power)
            function ink(color, alpha) {
                return "rgba(" + Math.round(color.r * 255) + "," + Math.round(color.g * 255)
                       + "," + Math.round(color.b * 255) + "," + alpha + ")"
            }
            function circle(x, y, r, fill) {
                ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2)
                ctx.fillStyle = fill; ctx.fill()
            }
            function arc(r, start, end, color, thickness) {
                ctx.beginPath(); ctx.arc(120, 120, r, start, end)
                ctx.strokeStyle = color; ctx.lineWidth = thickness; ctx.lineCap = "round"; ctx.stroke()
            }
            function star(x, y, radius, color) {
                ctx.beginPath(); ctx.moveTo(x, y - radius)
                ctx.quadraticCurveTo(x + 1, y - 1, x + radius, y)
                ctx.quadraticCurveTo(x + 1, y + 1, x, y + radius)
                ctx.quadraticCurveTo(x - 1, y + 1, x - radius, y)
                ctx.quadraticCurveTo(x - 1, y - 1, x, y - radius)
                ctx.fillStyle = color; ctx.fill()
            }

            // Radial light is drawn directly, with no continuously running effect.
            if (power > 0) {
                const glow = ctx.createRadialGradient(120, 120, 24, 120, 120, 116)
                glow.addColorStop(0, ink(emblem.energyColor, 0.24 * power))
                glow.addColorStop(0.64, ink(emblem.energyColor, 0.14 * power))
                glow.addColorStop(1, ink(emblem.energyColor, 0))
                circle(120, 120, 116, glow)
            }
            if (stage >= 1) {
                arc(86, -2.8, -0.65, ink(energy, 0.3 + power * 0.45), 4)
                arc(86, 0.35, 2.5, ink(energy, 0.2 + power * 0.4), 4)
                circle(120 + Math.cos(-0.65) * 86, 120 + Math.sin(-0.65) * 86, 4, ink(energy, 0.8))
            }
            if (stage >= 2) {
                arc(99, -1.9, -0.3, ink(energy, 0.22 + power * 0.3), 2)
                arc(99, 1.05, 2.7, ink(energy, 0.22 + power * 0.3), 2)
            }
            if (stage >= 4) {
                ctx.save()
                ctx.translate(120, 120); ctx.rotate(-0.55); ctx.scale(1, 0.5)
                ctx.beginPath(); ctx.arc(0, 0, 111, 0, Math.PI * 2)
                ctx.lineWidth = 3
                ctx.strokeStyle = ink(energy, 0.2 + power * 0.45)
                ctx.stroke(); ctx.restore()
            }

            // Grooves and two restrained reflections keep it recognizable as vinyl.
            const disc = ctx.createLinearGradient(65, 52, 177, 185)
            disc.addColorStop(0, emblem.dark ? "#505863" : "#69727c")
            disc.addColorStop(0.28, "#242a33")
            disc.addColorStop(0.58, "#10151c")
            disc.addColorStop(1, "#363f4c")
            circle(120, 120, 70, disc)
            arc(69, 0, Math.PI * 2, ink(energy, 0.2 + power * 0.35), 1.5)
            for (let r = 34; r <= 62; r += 7)
                arc(r, 0, Math.PI * 2, "rgba(193,207,221,0.13)", 1)
            arc(61, -2.6, -1.25, "rgba(235,244,255,0.28)", 2)
            arc(48, -2.6, -1.25, "rgba(235,244,255,0.16)", 1.5)
            arc(60, 0.55, 1.5, ink(energy, 0.15 + power * 0.2), 2)

            const label = ctx.createLinearGradient(100, 94, 141, 148)
            label.addColorStop(0, ink(energy, 0.55 + power * 0.4))
            label.addColorStop(1, ink(energy, 0.18 + power * 0.3))
            circle(120, 120, 27, label)
            arc(28, -2.6, -0.4, ink(energy, 0.35 + power * 0.5), 1.5)
            ctx.strokeStyle = power > 0.5 ? "#effffb" : "#a4a9b2"
            ctx.lineWidth = 4; ctx.lineCap = "round"
            const heights = [8 + power * 3, 8 + power * 13, 8 + power * 7]
            for (let i = 0; i < 3; i++) {
                const x = 112 + i * 8
                ctx.beginPath(); ctx.moveTo(x, 120 - heights[i] / 2)
                ctx.lineTo(x, 120 + heights[i] / 2); ctx.stroke()
            }
            circle(120, 137, 2.3, "#18232a")

            if (stage >= 3) {
                const wave = [12, 28, 18]
                ctx.strokeStyle = ink(energy, 0.3 + power * 0.65)
                ctx.lineWidth = 4
                for (let i = 0; i < 3; i++) {
                    for (const x of [22 + i * 7, 218 - i * 7]) {
                        ctx.beginPath(); ctx.moveTo(x, 120 - wave[i] / 2)
                        ctx.lineTo(x, 120 + wave[i] / 2); ctx.stroke()
                    }
                }
            }
            if (stage >= 4) {
                const glint = power > 0.5 ? "#ffe5b6" : ink(energy, 0.55)
                star(49, 56, 6, glint)
                star(191, 184, 5, glint)
            }
            if (stage >= 5) {
                arc(75, -2.5, -0.65, power > 0.5 ? "#f5d69c" : ink(energy, 0.45), 2)
                arc(108, 0.25, 0.9, ink(energy, 0.6), 2)
                star(182, 29, 8, power > 0.5 ? "#e5d4ff" : ink(energy, 0.55))
                star(49, 201, 7, ink(energy, 0.6 + power * 0.4))
                circle(113, 19, 2.5, ink(energy, 0.8))
            }
        }
    }
}
