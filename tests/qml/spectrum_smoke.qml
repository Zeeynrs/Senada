import QtQuick
import QtQuick.Window
import "../../qml"

// The spectrum on the seek bar of the visualizer full view, 40% into a playing song.
Window {
    id: window
    visible: true
    width: 420
    height: 120
    color: "#000000"
    Component.onCompleted: Theme.accent = "#ff0000"

    SpectrumSeek {
        id: seek
        objectName: "seek"
        x: 10
        y: 10
        width: 400
        spectrumHeight: 44
    }
}
