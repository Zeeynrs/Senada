import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property int days: 0
    property int best: 0
    property bool activeToday: false
    readonly property bool compact: width < 440
    readonly property int nextMilestone: emblem.nextMilestone
    implicitHeight: content.implicitHeight + 36
    radius: 20
    color: Theme.surface
    border.color: activeToday ? Theme.alpha(emblem.energyColor, Theme.dark ? 0.35 : 0.5) : Theme.line

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 20
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: card.compact ? 12 : 20
            StreakEmblem {
                id: emblem
                Layout.preferredWidth: card.compact ? 92 : 120
                Layout.preferredHeight: card.compact ? 92 : 120
                days: card.days
                lit: card.activeToday
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 3
                Label {
                    text: I18n.t("Daily streak")
                    color: Theme.dim
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.fillWidth: true
                    text: I18n.n("{n} day", "{n} days", card.days)
                    font.pixelSize: card.compact ? 28 : 34
                    font.weight: Font.Black
                    font.features: { "tnum": 1 }
                    elide: Text.ElideRight
                }
                Label {
                    Layout.fillWidth: true
                    text: emblem.stageTitle
                    color: card.activeToday ? (Theme.dark ? emblem.energyColor : Theme.mix(emblem.energyColor, "#000000", 0.55)) : Theme.dim
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 6; Layout.preferredHeight: 6
                        radius: 3
                        color: card.activeToday ? Theme.ok : Theme.faint
                    }
                    Label {
                        Layout.fillWidth: true
                        text: card.activeToday ? I18n.t("Active today") : I18n.t("Waiting for today's music")
                        color: Theme.dim
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Label {
                    Layout.fillWidth: true
                    text: card.nextMilestone > 0
                        ? I18n.n("Next evolution: {n} day", "Next evolution: {n} days", card.nextMilestone)
                        : I18n.t("Final evolution reached")
                    font.pixelSize: 12
                    color: Theme.dim
                    wrapMode: Text.WordWrap
                }
                Label {
                    text: I18n.n("Best: {n} day", "Best: {n} days", card.best)
                    font.pixelSize: 12
                    color: Theme.dim
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 4
                radius: 2
                color: Theme.line
                Rectangle {
                    height: parent.height
                    radius: 2
                    width: parent.width * (card.nextMilestone > 0 ? Math.max(0, Math.min(1, card.days / card.nextMilestone)) : 1)
                    color: card.activeToday ? emblem.energyColor : Theme.faint
                }
            }
            Label {
                Layout.fillWidth: true
                Layout.minimumHeight: card.compact ? 28 : 14
                text: card.activeToday ? I18n.t("Today's listening is counted. Keep your rhythm going.")
                    : I18n.t("Listen for 30 seconds, or half of a shorter song, to light it up.")
                color: Theme.dim
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
}
