import QtQuick
import QtQuick.Window
import "../../qml"

// The full view's queue (QueueView) with eight songs, to drag one of them up or down.
Window {
    id: window
    visible: true
    width: 480
    height: 360
    color: "#000000"

    QueueView {
        id: queue
        objectName: "queue"
        anchors.fill: parent
    }
}
