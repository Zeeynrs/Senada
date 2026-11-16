import QtQuick
import QtQuick.Effects

// A single static ambient scene shared by all refractive surfaces. Artwork replaces
// the idle colours when it is ready; neither case needs a decorative animation loop.
Item {
    id: backdrop
    property url artwork

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.dark ? "#17253e" : "#ddeaf7" }
            GradientStop { position: 0.5; color: Theme.dark ? "#292640" : "#ece5f5" }
            GradientStop { position: 1; color: Theme.dark ? "#102e36" : "#d8eeed" }
        }
    }
    Item {
        id: pools
        anchors.fill: parent
        visible: false
        Rectangle {
            x: -width * 0.25; y: -height * 0.35
            width: backdrop.width * 0.75; height: backdrop.height * 0.9
            radius: width / 2
            color: Theme.dark ? "#244a72" : "#b0d5f1"
        }
        Rectangle {
            x: backdrop.width * 0.55; y: backdrop.height * 0.02
            width: backdrop.width * 0.65; height: backdrop.height * 0.8
            radius: width / 2
            color: Theme.dark ? "#4c315c" : "#dcc5ee"
        }
        Rectangle {
            x: backdrop.width * 0.25; y: backdrop.height * 0.6
            width: backdrop.width * 0.6; height: backdrop.height * 0.8
            radius: width / 2
            color: Theme.dark ? "#145059" : "#a9dcd6"
        }
    }
    MultiEffect {
        anchors.fill: parent
        source: pools
        blurEnabled: true
        blur: 1
        blurMax: 64
        autoPaddingEnabled: false
    }
    Image {
        id: cover
        anchors.fill: parent
        source: backdrop.artwork
        sourceSize: Qt.size(256, 256)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: cover
        blurEnabled: true
        blur: 1
        blurMax: 64
        autoPaddingEnabled: false
        saturation: 0.2
        brightness: Theme.dark ? -0.18 : 0.15
        opacity: cover.status === Image.Ready ? 0.8 : 0
        Behavior on opacity { NumberAnimation { duration: 650 } }
    }
    Rectangle {
        anchors.fill: parent
        color: Theme.dark ? "#101729" : "#f5f8ff"
        opacity: Theme.dark ? 0.3 : 0.24
    }
}
