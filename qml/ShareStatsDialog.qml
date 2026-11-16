import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Build a shareable 1080x1350 listening recap picture and copy or save it.
Dialog {
    id: dlg
    property var info: ({})
    property string period: "month"
    property string look: "midnight"   // midnight | accent | emerald
    property bool showStreak: true
    property string savedPath: ""

    readonly property var topSongs: (info.topSongs || []).slice(0, 5)
    readonly property var topArtists: (info.topArtists || []).slice(0, 3)
    readonly property var topAlbum: (info.topAlbums || [])[0] || null
    readonly property int peakHour: {
        const hrs = info.byHour || []
        let bestH = -1, bestM = 0
        for (let i = 0; i < hrs.length; i++) {
            const m = (hrs[i].minutes || 0) * 1000 + (hrs[i].plays || 0)
            if (m > bestM) { bestM = m; bestH = hrs[i].hour }
        }
        return bestH
    }

    function openWith(statsInfo, periodKey) {
        info = statsInfo || ({})
        period = periodKey || "month"
        savedPath = ""
        open()
    }
    function periodLabel(p) {
        if (p === "week") return I18n.t("Last 7 days")
        if (p === "year") return I18n.t("This year")
        if (p === "all") return I18n.t("All time")
        return I18n.t("Last 30 days")
    }
    function minutesText(m) {
        return m >= 120 ? I18n.t("{n} h", { n: Math.round(m / 60) }) : I18n.t("{n} min", { n: m })
    }
    function hourText(h) {
        if (h < 0) return "—"
        return (h < 10 ? "0" : "") + h + ":00"
    }
    function fileName() {
        return "Senada - " + I18n.t("Stats") + " (" + periodLabel(period) + ")"
    }
    function grab(then) {
        card.grabToImage(result => then(result), Qt.size(card.width, card.height))
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(940, parent ? parent.width - 48 : 940)
    height: Math.min(680, parent ? parent.height - 64 : 680)
    modal: true
    focus: true
    padding: 24
    background: Rectangle { radius: 16; color: Theme.surface2; border.color: Theme.line }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }

    contentItem: RowLayout {
        spacing: 24

        // ---- 1080x1350 card scaled down into the preview ---------------------------
        Item {
            id: previewBox
            Layout.fillHeight: true
            Layout.preferredWidth: height * card.width / card.height
            Item {
                anchors.centerIn: parent
                width: card.width * scale
                height: card.height * scale
                scale: previewBox.height / card.height
                transformOrigin: Item.TopLeft

                Item {
                    id: card
                    width: 1080
                    height: 1350
                    clip: true

                    Rectangle {
                        anchors.fill: parent
                        gradient: Gradient {
                            GradientStop {
                                position: 0
                                color: dlg.look === "accent" ? Qt.darker(Theme.primary, 1.5)
                                     : dlg.look === "emerald" ? "#0d3527" : "#181924"
                            }
                            GradientStop {
                                position: 1
                                color: dlg.look === "accent" ? "#090a0f"
                                     : dlg.look === "emerald" ? "#050b09" : "#07070b"
                            }
                        }
                    }

                    // subtle decorative glow orb top-right
                    Rectangle {
                        width: 640; height: 640; radius: 320
                        x: card.width - 360; y: -220
                        color: dlg.look === "emerald" ? "#10b981" : Theme.primary
                        opacity: 0.16
                    }

                    Column {
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 80 }
                        spacing: 36

                        // Period + title header
                        Column {
                            width: parent.width
                            spacing: 10
                            Label {
                                text: dlg.periodLabel(dlg.period).toUpperCase()
                                color: "#ffffff"
                                opacity: 0.72
                                font.pixelSize: 22
                                font.weight: Font.Bold
                                font.letterSpacing: 3
                            }
                            Label {
                                text: I18n.t("Listening Recap")
                                color: "#ffffff"
                                font.pixelSize: 64
                                font.weight: Font.Black
                                font.letterSpacing: -1.2
                            }
                        }

                        // KPI summary tiles
                        Row {
                            width: parent.width
                            spacing: 20
                            readonly property int cols: dlg.showStreak ? 3 : 2
                            readonly property real cardW: (width - spacing * (cols - 1)) / cols

                            Rectangle {
                                width: parent.cardW; height: 152; radius: 22
                                color: "#1cffffff"; border.color: "#2affffff"
                                Column {
                                    anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
                                    spacing: 4
                                    Label { text: dlg.minutesText(dlg.info.minutes || 0); color: "#ffffff"; font.pixelSize: 46; font.weight: Font.Black }
                                    Label { text: I18n.t("listened"); color: "#b3ffffff"; font.pixelSize: 22 }
                                }
                            }
                            Rectangle {
                                width: parent.cardW; height: 152; radius: 22
                                color: "#1cffffff"; border.color: "#2affffff"
                                Column {
                                    anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
                                    spacing: 4
                                    Label { text: String(dlg.info.plays || 0); color: "#ffffff"; font.pixelSize: 46; font.weight: Font.Black }
                                    Label { text: I18n.t("plays"); color: "#b3ffffff"; font.pixelSize: 22 }
                                }
                            }
                            Rectangle {
                                visible: dlg.showStreak
                                width: parent.cardW; height: 152; radius: 22
                                color: "#1cffffff"; border.color: "#2affffff"
                                Column {
                                    anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
                                    spacing: 4
                                    Label {
                                        text: (dlg.info.streakDays || 0) > 0
                                              ? I18n.n("{n} day", "{n} days", dlg.info.streakDays || 0)
                                              : dlg.hourText(dlg.peakHour)
                                        color: "#ffffff"; font.pixelSize: 42; font.weight: Font.Black
                                    }
                                    Label {
                                        text: (dlg.info.streakDays || 0) > 0 ? I18n.t("current streak") : I18n.t("peak hour")
                                        color: "#b3ffffff"; font.pixelSize: 22
                                    }
                                }
                            }
                        }

                        // Top songs block
                        Column {
                            width: parent.width
                            spacing: 16
                            Label {
                                text: I18n.t("Top songs")
                                color: "#d9ffffff"
                                font.pixelSize: 28
                                font.weight: Font.Bold
                            }
                            Repeater {
                                model: dlg.topSongs
                                delegate: Row {
                                    required property var modelData
                                    required property int index
                                    width: parent.width
                                    height: 76
                                    spacing: 20

                                    Label {
                                        width: 34
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: String(index + 1)
                                        color: "#99ffffff"
                                        font.pixelSize: 28
                                        font.weight: Font.Bold
                                    }
                                    Rectangle {
                                        width: 68; height: 68; radius: 12; clip: true
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: "#22ffffff"
                                        Image {
                                            anchors.fill: parent
                                            source: modelData.imageSmall || ""
                                            fillMode: Image.PreserveAspectCrop
                                        }
                                    }
                                    Column {
                                        width: parent.width - 34 - 68 - 170 - 60
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 2
                                        Label {
                                            width: parent.width
                                            text: modelData.name || ""
                                            color: "#ffffff"
                                            font.pixelSize: 26
                                            font.weight: Font.Bold
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            width: parent.width
                                            text: modelData.artists || ""
                                            color: "#b3ffffff"
                                            font.pixelSize: 21
                                            elide: Text.ElideRight
                                        }
                                    }
                                    Label {
                                        width: 170
                                        anchors.verticalCenter: parent.verticalCenter
                                        horizontalAlignment: Text.AlignRight
                                        text: I18n.n("{n} play", "{n} plays", modelData.plays || 0)
                                        color: "#ccffffff"
                                        font.pixelSize: 22
                                    }
                                }
                            }
                        }

                        // Top artists + peak highlight
                        Row {
                            width: parent.width
                            spacing: 24
                            visible: dlg.topArtists.length > 0 || dlg.topAlbum !== null
                            Column {
                                width: parent.width * 0.56
                                spacing: 8
                                visible: dlg.topArtists.length > 0
                                Label {
                                    text: I18n.t("Top artists")
                                    color: "#d9ffffff"
                                    font.pixelSize: 24
                                    font.weight: Font.Bold
                                }
                                Label {
                                    width: parent.width
                                    text: dlg.topArtists.map(a => a.name).join("  ·  ")
                                    color: "#ffffff"
                                    font.pixelSize: 26
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                            }
                            Column {
                                width: parent.width * 0.41
                                spacing: 8
                                visible: dlg.topAlbum !== null
                                Label {
                                    text: I18n.t("Top album")
                                    color: "#d9ffffff"
                                    font.pixelSize: 24
                                    font.weight: Font.Bold
                                }
                                Label {
                                    width: parent.width
                                    text: dlg.topAlbum ? dlg.topAlbum.name : ""
                                    color: "#ffffff"
                                    font.pixelSize: 26
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    // the Senada mark at the bottom
                    Row {
                        anchors { left: parent.left; bottom: parent.bottom; leftMargin: 80; bottomMargin: 70 }
                        spacing: 16
                        LogoMark { size: 44; colors: ["#ffffff"]; anchors.verticalCenter: parent.verticalCenter }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Senada"
                            color: "#ffffff"
                            opacity: 0.9
                            font.pixelSize: 34
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }
        }

        // ---- right-side controls ---------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: I18n.t("Share stats")
                    font.pixelSize: 20
                    font.weight: Font.Bold
                }
                IconButton { iconName: "close"; size: 18; tip: I18n.t("Close"); onClicked: dlg.close() }
            }
            Label {
                Layout.fillWidth: true
                text: I18n.t("Create a summary card of your listening stats to copy or save as an image.")
                color: Theme.dim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Label { text: I18n.t("Background"); color: Theme.dim; font.pixelSize: 13 }
                Repeater {
                    model: [
                        { key: "midnight", label: I18n.t("Midnight") },
                        { key: "accent", label: I18n.t("Accent") },
                        { key: "emerald", label: I18n.t("Emerald") }
                    ]
                    delegate: Chip {
                        required property var modelData
                        text: modelData.label
                        checked: dlg.look === modelData.key
                        onClicked: dlg.look = modelData.key
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                NSwitch {
                    checked: dlg.showStreak
                    onToggled: dlg.showStreak = checked
                }
                Label {
                    Layout.fillWidth: true
                    text: I18n.t("Show streak / peak hour tile")
                    font.pixelSize: 13
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                NButton {
                    text: I18n.t("Copy image")
                    enabled: (dlg.info.plays || 0) > 0
                    onClicked: dlg.grab(r => session.copyImage(r.image))
                }
                NButton {
                    primary: true
                    text: I18n.t("Save image")
                    enabled: (dlg.info.plays || 0) > 0
                    onClicked: {
                        const path = session.picturePath(dlg.fileName())
                        dlg.grab(r => {
                            if (r.saveToFile(path)) {
                                dlg.savedPath = path
                                session.toast(I18n.t("Saved in Pictures/Senada"))
                            } else {
                                session.toast(I18n.t("The picture could not be saved"))
                            }
                        })
                    }
                }
                LinkLabel {
                    visible: dlg.savedPath !== ""
                    text: I18n.t("Show in folder")
                    onClicked: session.showFile(dlg.savedPath)
                }
                Item { Layout.fillWidth: true }
            }
        }
    }
}
