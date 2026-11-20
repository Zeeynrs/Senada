import QtQuick

// A burst of colourful music notes that fly up from a point, sway, turn and fade
// (Settings → Storage → Clear cache). Each note removes itself when its flight ends.
Item {
    id: burst
    property int count: 22
    readonly property var glyphs: ["note", "music"]
    readonly property var colors: [Theme.primary, "#6ce5bd", "#72caff", "#edc981", "#cfb7ff", "#ff8fb1"]
    readonly property int flying: notes.length
    property var notes: []

    // (x, y) in this item's coordinates
    function play(x, y) {
        for (let i = 0; i < count; i++) {
            const angle = (-160 + Math.random() * 140) * Math.PI / 180  // a fan, mostly upwards
            const distance = 80 + Math.random() * 150
            const note = noteComponent.createObject(burst, {
                originX: x,
                originY: y,
                dx: Math.cos(angle) * distance,
                dy: Math.sin(angle) * distance - 20,
                glyph: glyphs[i % glyphs.length],
                tint: colors[i % colors.length],
                size: 15 + Math.round(Math.random() * 15),
                turn: -70 + Math.random() * 140,
                sway: 4 + Math.random() * 8,
                delay: Math.round(Math.random() * 160),
                duration: 950 + Math.round(Math.random() * 550)
            })
            if (note)
                notes = notes.concat([note])
        }
    }

    Component {
        id: noteComponent
        Item {
            id: note
            objectName: "musicNote"
            property real originX
            property real originY
            property real dx
            property real dy
            property string glyph
            property color tint
            property int size
            property real turn
            property real sway
            property int delay
            property int duration
            property real t: 0          // 0 → 1 along the flight
            property bool started: false

            visible: started
            width: size
            height: size
            x: originX - size / 2 + dx * t + Math.sin(t * Math.PI * 3) * sway
            y: originY - size / 2 + dy * t + 26 * t * t   // up, then a little fall at the end
            rotation: turn * t
            scale: t < 0.18 ? 0.3 + t / 0.18 * 0.95 : 1.25 - (t - 0.18) * 0.45
            opacity: t < 0.65 ? 1 : 1 - (t - 0.65) / 0.35

            Icon {
                anchors.fill: parent
                glyph: note.glyph
                size: note.size
                color: note.tint
            }

            SequentialAnimation {
                running: true
                PauseAnimation { duration: note.delay }
                ScriptAction { script: note.started = true }
                NumberAnimation { target: note; property: "t"; from: 0; to: 1; duration: note.duration; easing.type: Easing.OutCubic }
                ScriptAction {
                    script: {
                        burst.notes = burst.notes.filter(n => n !== note)
                        note.destroy()
                    }
                }
            }
        }
    }
}
