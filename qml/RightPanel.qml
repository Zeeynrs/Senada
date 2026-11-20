import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Right panel next to the page: synced lyrics or the play queue.
Rectangle {
    id: rp
    property string panel: "lyrics"   // "lyrics" | "queue"
    signal select(string name)
    signal close()
    readonly property var s: player.state

    color: Theme.liquid ? "transparent" : Theme.sidebar
    radius: Theme.panelRadius
    clip: true

    Loader {
        anchors.fill: parent
        active: Theme.liquid
        sourceComponent: GlassSurface {}
    }
    Rectangle { visible: !Theme.liquid; width: 1; height: parent.height; color: Theme.line }

    // header: two tabs and a close button
    RowLayout {
        id: head
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 16
        anchors.rightMargin: 8
        height: 46
        spacing: 16
        Repeater {
            model: [{ key: "lyrics", label: I18n.t("LYRICS") }, { key: "queue", label: I18n.t("QUEUE") }]
            Label {
                required property var modelData
                text: modelData.label
                color: rp.panel === modelData.key ? Theme.text : tabHover.hovered ? Theme.dim : Theme.faint
                font.pixelSize: 12
                font.weight: Font.Bold
                font.letterSpacing: 1.2
                HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: rp.select(modelData.key) }
            }
        }
        Item { Layout.fillWidth: true }
        IconButton { iconName: "close"; size: 16; tint: Theme.dim; tip: I18n.t("Close panel"); onClicked: rp.close() }
    }
    Rectangle { anchors.top: head.bottom; x: 1; width: parent.width - 1; height: 1; color: Theme.line }

    Loader {
        anchors.top: head.bottom
        anchors.topMargin: 1
        anchors.left: parent.left
        anchors.leftMargin: 1
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.floatInset   // clear of the floating player bar
        sourceComponent: rp.panel === "queue" ? queueComp : lyricsComp
    }

    // ---- lyrics -----------------------------------------------------------------------
    Component {
        id: lyricsComp
        Item {
            Label {
                anchors.centerIn: lines
                width: parent.width - 48
                visible: lyrics.status !== "ready"
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: Theme.dim
                font.pixelSize: 14
                text: lyrics.status === "loading" ? I18n.t("Looking for lyrics…")
                    : lyrics.status === "idle" ? I18n.t("Play a song to see its lyrics.")
                    : lyrics.status === "error" ? I18n.t("Lyrics could not be loaded. Check the internet connection.")
                    : lyrics.source === "auto" ? I18n.t("No lyrics for this song yet.")
                    : I18n.t("No lyrics for this song from this source. Try another source below.")
            }
            ListView {
                id: lines
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: sourceBar.top
                visible: lyrics.status === "ready"
                clip: true
                model: lyrics.lines
                spacing: 6
                topMargin: height * 0.3
                bottomMargin: height * 0.5
                currentIndex: lyrics.synced ? lyrics.current : -1
                // keep the sung line in view, unless the user is scrolling by hand
                highlightRangeMode: lyrics.synced && !userScroll.running ? ListView.ApplyRange : ListView.NoHighlightRange
                preferredHighlightBegin: height * 0.3
                preferredHighlightEnd: height * 0.3 + 60
                highlightMoveDuration: 380
                ScrollBar.vertical: NScrollBar {}
                SmoothScroll { flickable: lines }
                onMovementStarted: userScroll.restart()
                Timer { id: userScroll; interval: 3500 }
                // a new song starts at the top; new lines for the same song (a translation that
                // came in) keep the sung line in view
                onModelChanged: lyrics.synced && lyrics.current >= 0 ? positionViewAtIndex(lyrics.current, ListView.Center)
                                                                     : positionViewAtBeginning()

                delegate: Column {
                    id: lyricItem
                    required property var modelData
                    required property int index
                    width: lines.width
                    spacing: 0
                    LyricLine {
                        id: lyricRow
                        readonly property var modelData: lyricItem.modelData
                        readonly property int index: lyricItem.index
                        width: lines.width
                        leftPadding: 18
                        rightPadding: 18
                        topPadding: 4
                        bottomPadding: lyricItem.modelData.sub ? 0 : 4
                        line: modelData
                        nextT: index + 1 < lyrics.lines.length ? lyrics.lines[index + 1].t : -1
                        synced: lyrics.synced
                        current: lyrics.synced && index === lyrics.current
                        past: lyrics.synced && index < lyrics.current
                        baseSize: lyrics.synced ? 20 : 16
                        font.weight: lyrics.synced ? Font.Bold : Font.Normal
                        activeColor: Theme.accentInk
                        // on the light theme: the unsung part a pale tint, and a fainter glow
                        unsungColor: Theme.mix(Theme.accentInk, Theme.bgSolid, Theme.dark ? 0.55 : 0.62)
                        glowOpacity: Theme.dark ? 0.85 : 0.35
                        restColor: !lyrics.synced ? Theme.text : lineHover.hovered ? Theme.dim : Theme.alpha(Theme.text, 0.42)
                        pastColor: lineHover.hovered ? Theme.dim : Theme.alpha(Theme.text, 0.32)
                        Behavior on color { ColorAnimation { duration: 200 } }
                        HoverHandler { id: lineHover; cursorShape: lyrics.synced ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        TapHandler { onTapped: if (lyrics.synced) player.seek(lyricRow.modelData.t) }
                    }
                    // its romanization or translation (Settings → Lyrics → Under each line)
                    Label {
                        visible: !!lyricItem.modelData.sub
                        width: lines.width
                        leftPadding: 18
                        rightPadding: 18
                        bottomPadding: 6
                        text: lyricItem.modelData.sub || ""
                        wrapMode: Text.WordWrap
                        horizontalAlignment: lyricRow.horizontalAlignment
                        font.pixelSize: Math.round(lyricRow.font.pixelSize * 0.66)
                        color: lyricRow.current ? Theme.dim : Theme.alpha(Theme.text, 0.32)
                    }
                }
            }
            // which source the lyrics come from, and a menu to pick another one
            Item {
                id: sourceBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: lyrics.status === "idle" ? 0 : 38
                visible: height > 0
                Rectangle { width: parent.width; height: 1; color: Theme.line }
                LyricsSourceButton {
                    anchors.left: parent.left
                    anchors.leftMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                }
                Row {
                    visible: lyrics.synced && lyrics.status === "ready"
                    anchors.right: shareLyricsBtn.left
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    IconButton {
                        iconName: "previous"
                        size: 13; tint: Theme.dim
                        tip: I18n.t("Lyrics earlier (-0.5s)")
                        onClicked: lyrics.adjustOffset(-500)
                    }
                    AbstractButton {
                        implicitHeight: 24
                        implicitWidth: Math.max(40, rpOffsetLbl.implicitWidth + 10)
                        anchors.verticalCenter: parent.verticalCenter
                        hoverEnabled: true
                        onClicked: lyrics.resetOffset()
                        ToolTip.visible: hovered
                        ToolTip.text: I18n.t("Reset lyrics timing")
                        background: Rectangle { radius: 12; color: parent.hovered ? Theme.hover : "transparent" }
                        contentItem: Label {
                            id: rpOffsetLbl
                            text: (lyrics.offset === 0 ? "0.0s" : (lyrics.offset > 0 ? "+" : "") + (lyrics.offset / 1000).toFixed(1) + "s")
                            font.pixelSize: 11
                            color: lyrics.offset === 0 ? Theme.dim : Theme.primary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    IconButton {
                        iconName: "next"
                        size: 13; tint: Theme.dim
                        tip: I18n.t("Lyrics later (+0.5s)")
                        onClicked: lyrics.adjustOffset(500)
                    }
                }
                IconButton {
                    id: shareLyricsBtn
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    visible: lyrics.status === "ready"
                    iconName: "share"; size: 16; tint: Theme.dim
                    tip: I18n.t("Share lyrics as a picture")
                    onClicked: Nav.shareLyrics(-1)
                }
            }
        }
    }

    // ---- queue -------------------------------------------------------------------------
    Component {
        id: queueComp
        ListView {
            id: q
            clip: true
            model: player.queue
            spacing: 0
            readonly property QueueReorder reorder: QueueReorder { view: q }  // drag a song up or down
            ScrollBar.vertical: NScrollBar {}
            SmoothScroll { flickable: q }
            Component.onCompleted: player.refreshQueue()
            bottomMargin: 16

            header: Column {
                width: q.width
                topPadding: 12
                spacing: 4
                SectionLabel { text: I18n.t("NOW PLAYING") }
                Label {
                    visible: !rp.s.hasTrack
                    leftPadding: 16
                    text: I18n.t("Nothing playing yet.")
                    color: Theme.dim
                    font.pixelSize: 13
                }
                TrackRow {
                    visible: !!rp.s.hasTrack
                    width: q.width
                    track: rp.s.hasTrack ? rp.s : ({})
                    compact: true
                    onPlay: player.togglePlay()
                }
                Item { width: 1; height: 10 }
                RowLayout {
                    width: q.width - 16
                    x: 8
                    spacing: 4
                    Label {
                        leftPadding: 8
                        text: I18n.t("UP NEXT")
                        color: Theme.faint
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        font.letterSpacing: 1.2
                        visible: q.count > 0 || !!rp.s.hasTrack
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: I18n.t("Autoplay")
                        color: Theme.dim
                        font.pixelSize: 11
                    }
                    NSwitch {
                        scale: 0.82
                        checked: player ? player.autoplay : false
                        onToggled: if (player) player.setAutoplay(checked)
                    }
                    IconButton {
                        visible: q.count > 0
                        iconName: "queue-add"
                        size: 15
                        tip: I18n.t("Save queue as playlist")
                        onClicked: Nav.newPlaylist(player.fullQueue())
                    }
                    IconButton {
                        visible: q.count > 0
                        iconName: "close"
                        size: 15
                        tip: I18n.t("Clear queue")
                        onClicked: player.clearQueue()
                    }
                }
                Label {
                    visible: q.count === 0
                    leftPadding: 16
                    text: I18n.t("The queue is empty. Play an album or playlist, or choose “Add to queue” on any song.")
                    width: q.width - 16
                    wrapMode: Text.WordWrap
                    color: Theme.dim
                    font.pixelSize: 13
                }
            }
            delegate: TrackRow {
                required property var modelData
                required property int index
                width: q.width
                track: modelData
                compact: true
                inQueue: true
                queueOffset: index
                queueCount: q.count
                reorder: q.reorder
                onPlay: player.skip(index + 1)
            }
        }
    }

    component SectionLabel: Label {
        leftPadding: 16
        bottomPadding: 4
        color: Theme.faint
        font.pixelSize: 11
        font.weight: Font.Bold
        font.letterSpacing: 1.2
    }
}
