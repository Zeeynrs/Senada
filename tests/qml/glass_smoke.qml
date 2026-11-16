import QtQuick
import QtQuick.Controls
import "../../qml"

ApplicationWindow {
    id: window
    visible: true
    width: 640
    height: 360
    color: "#203040"
    property string glassMode: "liquid"
    property string colorMode: "dark"
    property real thickness: 0.3
    readonly property real materialOpacity: material.materialColor.a
    readonly property bool dark: Theme.dark
    Binding { target: Theme; property: "glassMode"; value: window.glassMode }
    Binding { target: Theme; property: "mode"; value: window.colorMode }
    Binding { target: Theme; property: "glassOpacity"; value: window.thickness }

    TopBar { x: 20; y: 20; width: 600 }
    GlassSurface { id: material; x: 20; y: 100; width: 300; height: 180 }
}
