import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ListView {
    id: q
    SmoothScroll { flickable: q }
    clip: true
    model: player.queue
    spacing: 2
    readonly property QueueReorder reorder: QueueReorder { view: q }  // drag a song up or down
    ScrollBar.vertical: NScrollBar {}
    Component.onCompleted: player.refreshQueue()

    header: ColumnLayout {
        width: q.width
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            spacing: 8
            Label {
                text: I18n.t("Up next")
                font.pixelSize: 22
                font.weight: Font.Bold
            }
            Item { Layout.fillWidth: true }
            Label {
                text: I18n.t("Autoplay")
                color: Qt.rgba(1, 1, 1, 0.72)
                font.pixelSize: 12
            }
            NSwitch {
                checked: player ? player.autoplay : false
                onToggled: if (player) player.setAutoplay(checked)
            }
            IconButton {
                visible: q.count > 0
                iconName: "queue-add"
                size: 17
                tip: I18n.t("Save queue as playlist")
                onClicked: Nav.newPlaylist(player.fullQueue())
            }
            IconButton {
                visible: q.count > 0
                iconName: "close"
                size: 17
                tip: I18n.t("Clear queue")
                onClicked: player.clearQueue()
            }
        }
        Item { Layout.preferredHeight: 4 }
    }
    delegate: TrackRow {
        required property var modelData
        required property int index
        width: q.width
        track: modelData
        number: index + 1
        showAlbum: false
        inQueue: true
        queueOffset: index
        queueCount: q.count
        reorder: q.reorder
        onPlay: player.skip(index + 1)
    }
    Label {
        anchors.centerIn: parent
        visible: q.count === 0
        text: I18n.t("The queue is empty")
        color: Qt.rgba(1, 1, 1, 0.6)
        font.pixelSize: 16
    }
}
