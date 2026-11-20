import QtQuick
import QtQuick.Window
import "../../qml"

// Covers of a wide image (blue | green | red thirds): a cover crops it to the green middle.
Window {
    id: window
    visible: true
    width: 760
    height: 420
    color: "#000000"
    property url wide
    property url big
    readonly property bool loaded: rounded.ready && round.ready && plain.ready && large.ready

    Cover { id: rounded; x: 10; y: 10; width: 100; height: 100; radius: 20; source: window.wide }
    Cover { id: round; x: 130; y: 10; width: 100; height: 100; round: true; source: window.wide }
    Cover { id: plain; x: 250; y: 10; width: 100; height: 100; simple: true; source: window.wide }
    Cover { id: large; x: 370; y: 10; width: 380; height: 380; radius: 30; source: window.big }
}
