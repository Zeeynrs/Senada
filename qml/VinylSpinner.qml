import QtQuick

// A small vinyl record that spins while something works, then pops with a ring of the accent
// colour when it is done (Settings → Storage → Clear cache).
Item {
    id: vinyl
    property bool spinning: false
    signal popped()              // the pop has finished: time for whatever comes next
    implicitWidth: 30
    implicitHeight: 30

    function pop() {
        spin.stop()
        popAnim.restart()
    }
    function reset() {
        popAnim.stop()
        disc.scale = 1
        disc.opacity = 1
        disc.rotation = 0
        ring.scale = 0.6
        ring.opacity = 0
    }
    onSpinningChanged: if (spinning) { reset(); spin.restart() }

    // the record: black disc, two grooves, a label in the accent colour and the hole
    Item {
        id: disc
        anchors.fill: parent
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Theme.dark ? "#0b0b0b" : "#1c1c1c"
            border.width: 1.5
            border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.32) : "#000000"
        }
        Repeater {
            model: [0.78, 0.6]
            Rectangle {
                required property real modelData
                anchors.centerIn: parent
                width: disc.width * modelData
                height: width
                radius: width / 2
                color: "transparent"
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.2)
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: disc.width * 0.38
            height: width
            radius: width / 2
            color: Theme.primary
            // a light glint, so the turning can be seen
            Rectangle {
                x: parent.width * 0.18; y: parent.height * 0.14
                width: parent.width * 0.3; height: width; radius: width / 2
                color: Qt.rgba(1, 1, 1, 0.55)
            }
            Rectangle {
                anchors.centerIn: parent
                width: 3; height: 3; radius: 1.5
                color: Theme.dark ? "#0b0b0b" : "#1c1c1c"
            }
        }
    }

    // the shock ring of the pop
    Rectangle {
        id: ring
        anchors.centerIn: parent
        width: vinyl.width * 1.2
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.primary
        opacity: 0
        scale: 0.6
    }

    RotationAnimator {
        id: spin
        target: disc
        from: 0
        to: 360
        duration: 700
        loops: Animation.Infinite
    }

    SequentialAnimation {
        id: popAnim
        ParallelAnimation {
            NumberAnimation { target: disc; property: "scale"; to: 1.45; duration: 170; easing.type: Easing.OutBack }
            NumberAnimation { target: ring; property: "opacity"; from: 0.9; to: 0.9; duration: 1 }
        }
        ParallelAnimation {
            NumberAnimation { target: disc; property: "scale"; to: 0.2; duration: 180; easing.type: Easing.InBack }
            NumberAnimation { target: disc; property: "opacity"; to: 0; duration: 180 }
            NumberAnimation { target: ring; property: "scale"; from: 0.6; to: 2.6; duration: 520; easing.type: Easing.OutCubic }
            NumberAnimation { target: ring; property: "opacity"; from: 0.9; to: 0; duration: 520; easing.type: Easing.OutQuad }
        }
        ScriptAction { script: vinyl.popped() }
    }
}
