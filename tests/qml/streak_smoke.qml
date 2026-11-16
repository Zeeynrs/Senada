import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../qml"

ApplicationWindow {
    id: window
    width: 1020
    height: 650
    visible: true
    color: Theme.bgSolid
    palette.windowText: Theme.text
    property int currentStreak: 100
    property bool activeToday: false
    property string colorMode: "dark"
    Binding { target: Theme; property: "mode"; value: window.colorMode }
    StreakCard {
        id: card
        objectName: "streakCard"
        x: 20; y: 20
        width: Math.min(620, window.width - 40)
        days: window.currentStreak
        best: 500
        activeToday: window.activeToday
    }
    Label {
        x: 20; y: card.y + card.height + 24
        text: "SENADA · STREAK EVOLUTIONS"
        color: Theme.dim
        font.pixelSize: 13
        font.letterSpacing: 1.2
    }
    GridLayout {
        visible: window.width > 700
        x: 20; y: card.y + card.height + 55
        columns: 7
        columnSpacing: 8
        Repeater {
            model: [0, 1, 7, 30, 100, 200, 500]
            ColumnLayout {
                required property int modelData
                spacing: 6
                StreakEmblem {
                    id: sample
                    Layout.preferredWidth: 128
                    Layout.preferredHeight: 128
                    days: modelData
                    lit: modelData > 0
                    animate: false
                }
                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: modelData > 0 ? I18n.n("{n} day", "{n} days", modelData) : "Dormant"
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: Font.Bold
                }
                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: sample.stageTitle
                    color: Theme.dim
                    font.pixelSize: 12
                }
            }
        }
    }
}
