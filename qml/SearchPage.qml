import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    readonly property string pageKey: "search"
    property var results: ({})
    property var localHits: ({})
    property bool searching: false
    property string lastQuery: ""
    property string filter: "all"  // all | tracks | albums | artists | playlists
    readonly property var tracks: results.tracks || []
    readonly property var localTracks: results.localTracks || localHits.tracks || []
    readonly property var localPlaylists: results.localPlaylists || localHits.playlists || []
    readonly property bool hasLocal: localTracks.length + localPlaylists.length > 0
    readonly property bool hasResults: tracks.length + (results.albums || []).length
                                       + (results.artists || []).length + (results.playlists || []).length
                                       + localTracks.length + localPlaylists.length > 0
    readonly property var browsePrompts: [
        "Top hits Indonesia", I18n.t("Chill lo-fi"), "Dangdut koplo", I18n.t("Late night jazz"),
        "K-Pop", I18n.t("Sad songs"), I18n.t("Indonesian indie"), I18n.t("Focus music")
    ]

    readonly property var disc: library.discover
    readonly property bool typed: field.text.trim() !== ""

    function runSearch(q, saveHistory) {
        const clean = (q || "").trim()
        if (!clean) { page.results = {}; page.localHits = {}; library.suggest(""); return }
        page.localHits = library.localSearch(clean)
        page.lastQuery = clean
        page.searching = true
        if (saveHistory) library.addSearchHistory(clean)
        library.search(clean)
    }

    Component.onCompleted: { field.forceActiveFocus(); library.refreshDiscover(false) }
    onVisibleChanged: if (visible) library.refreshDiscover(false)

    Connections {
        target: library
        function onSearchFinished(query, data) {
            if (query !== page.lastQuery) return
            page.searching = false
            page.results = data
            if (data.error) session.toast(data.error)
        }
    }

    Timer {
        id: suggestDebounce
        interval: 180
        onTriggered: library.suggest(field.text)
    }
    Timer {
        id: debounce
        interval: 350
        onTriggered: page.runSearch(field.text, false)
    }

    Flickable {
        id: flick
        SmoothScroll { flickable: flick }
        anchors.fill: parent
        contentHeight: col.implicitHeight + Theme.dockSpace
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: NScrollBar {}

        Column {
            id: col
            x: 28
            y: 24
            width: flick.width - 56
            spacing: 22

            Label { text: I18n.t("Search"); font.pixelSize: 34; font.weight: Font.Black; font.letterSpacing: -0.6 }

            // search field
            Item {
                width: parent.width
                height: 50
                NTextField {
                    id: field
                    width: Math.min(720, parent.width)
                    height: 50
                    font.pixelSize: 15
                    iconName: "search"
                    placeholderText: I18n.t("What do you want to hear? (or paste a Spotify/YouTube Music link)")
                    onTextChanged: {
                        suggestDebounce.restart()
                        debounce.restart()
                        if (!text.trim()) { page.localHits = {}; page.results = {} }
                    }
                    Keys.onReturnPressed: { debounce.stop(); suggestDebounce.stop(); page.runSearch(field.text, true) }
                    Keys.onEnterPressed: { debounce.stop(); suggestDebounce.stop(); page.runSearch(field.text, true) }
                    Keys.onEscapePressed: { text = ""; library.suggest("") }
                }
                BusyIndicator {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: field.right
                    anchors.rightMargin: 10
                    running: page.searching
                    visible: running
                    implicitWidth: 32; implicitHeight: 32
                }
            }

            // live autocomplete suggestions while typing
            Flow {
                width: Math.min(720, parent.width)
                visible: page.typed && !field.text.trim().startsWith("http") && !field.text.trim().startsWith("spotify:") && (library.suggestions || []).length > 0
                spacing: 8
                Repeater {
                    model: library.suggestions || []
                    Chip {
                        required property string modelData
                        text: modelData
                        onClicked: {
                            debounce.stop()
                            suggestDebounce.stop()
                            field.text = modelData
                            page.runSearch(modelData, true)
                        }
                    }
                }
            }

            // filters
            Row {
                spacing: 8
                visible: page.hasResults
                Repeater {
                    model: [
                        { key: "all", label: I18n.t("All") },
                        { key: "tracks", label: I18n.t("Songs") },
                        { key: "albums", label: I18n.t("Albums") },
                        { key: "artists", label: I18n.t("Artists") },
                        { key: "playlists", label: I18n.t("Playlists") }
                    ]
                    Chip {
                        text: modelData.label
                        checked: page.filter === modelData.key
                        onClicked: page.filter = modelData.key
                    }
                }
            }

            Label {
                visible: page.typed && !page.hasResults && !page.searching
                text: I18n.t("No results.")
                color: Theme.dim
                font.pixelSize: 15
            }

            Label {
                visible: page.typed && !!page.results.offline
                text: I18n.t("Offline — showing matches from your library")
                color: Theme.dim
                font.pixelSize: 13
            }

            // nothing typed: recent search history pills
            Column {
                width: parent.width
                visible: !page.typed && (library.searchHistory || []).length > 0
                spacing: 12
                RowLayout {
                    width: parent.width
                    Label {
                        text: I18n.t("Recent searches")
                        font.pixelSize: 18
                        font.weight: Font.Bold
                    }
                    Item { Layout.fillWidth: true }
                    LinkLabel {
                        text: I18n.t("Clear")
                        font.pixelSize: 13
                        onClicked: library.clearSearchHistory()
                    }
                }
                Flow {
                    width: parent.width
                    spacing: 8
                    Repeater {
                        model: library.searchHistory || []
                        delegate: Rectangle {
                            id: histPill
                            required property string modelData
                            height: 34
                            width: Math.min(parent.width, histRow.implicitWidth + 20)
                            radius: 17
                            color: histMouse.containsMouse ? Theme.hover : Theme.surface
                            border.color: histMouse.containsMouse ? Theme.lineStrong : Theme.line
                            RowLayout {
                                id: histRow
                                anchors.centerIn: parent
                                spacing: 6
                                Icon { glyph: "clock"; size: 13; color: Theme.dim }
                                Label {
                                    text: histPill.modelData
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                    Layout.maximumWidth: 220
                                }
                                IconButton {
                                    iconName: "close"
                                    size: 12
                                    tip: I18n.t("Remove")
                                    onClicked: library.removeSearchHistory(histPill.modelData)
                                }
                            }
                            MouseArea {
                                id: histMouse
                                anchors.fill: parent
                                anchors.rightMargin: 28
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    debounce.stop()
                                    suggestDebounce.stop()
                                    field.text = histPill.modelData
                                    page.runSearch(histPill.modelData, true)
                                }
                            }
                        }
                    }
                }
            }

            // nothing typed: recommendations from what you listen to (or what is popular)
            Column {
                width: parent.width
                visible: !page.typed
                spacing: 22

                RowLayout {
                    width: parent.width
                    spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            text: page.disc.personal ? I18n.t("Recommended for you") : I18n.t("Popular right now")
                            font.pixelSize: 22
                            font.weight: Font.Black
                        }
                        Label {
                            Layout.fillWidth: true
                            text: page.disc.personal ? I18n.t("Based on the songs you play and like.")
                                                     : I18n.t("Play a few songs and these become your own recommendations.")
                            color: Theme.dim
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }
                    BusyIndicator {
                        running: page.disc.loading
                        visible: running
                        implicitWidth: 28; implicitHeight: 28
                    }
                    IconButton {
                        visible: !page.disc.loading
                        iconName: "refresh"
                        size: 18
                        tip: I18n.t("New recommendations")
                        onClicked: library.refreshDiscover(true)
                    }
                }
                Label {
                    visible: !!page.disc.error && !page.disc.loading && (page.disc.tracks || []).length === 0
                    width: parent.width
                    text: page.disc.error || ""
                    color: Theme.dim
                    wrapMode: Text.WordWrap
                }
                TrackSection {
                    width: parent.width
                    wide: width > 900
                    title: I18n.t("Songs for you")
                    tracks: page.disc.tracks || []
                }
                Carousel {
                    width: parent.width
                    title: I18n.t("Artists you might like")
                    items: page.disc.artists || []
                }
                Carousel {
                    width: parent.width
                    title: I18n.t("Albums for you")
                    items: page.disc.albums || []
                }
            }

            // nothing typed: a few searches to start from
            Column {
                width: parent.width
                visible: !page.typed
                spacing: 14
                Label {
                    text: I18n.t("Browse")
                    font.pixelSize: 18
                    font.weight: Font.Bold
                }
                Label {
                    text: I18n.t("Try one of these, or paste a Spotify or YouTube Music playlist link.")
                    color: Theme.dim
                    font.pixelSize: 13
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: page.browsePrompts
                        AbstractButton {
                            id: sug
                            width: 200; height: 64
                            hoverEnabled: true
                            focusPolicy: Qt.NoFocus
                            onClicked: {
                                debounce.stop()
                                suggestDebounce.stop()
                                field.text = modelData
                                page.runSearch(modelData, true)
                            }
                            background: Rectangle {
                                radius: 14
                                color: sug.hovered ? Theme.hover : "transparent"
                                border.color: sug.hovered ? Theme.lineStrong : Theme.line
                            }
                            contentItem: RowLayout {
                                spacing: 12
                                Rectangle {
                                    Layout.leftMargin: 12
                                    implicitWidth: 36; implicitHeight: 36; radius: 18
                                    color: Theme.hover
                                    Icon { anchors.centerIn: parent; glyph: "search"; size: 16; color: Theme.text }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    Layout.rightMargin: 12
                                    text: modelData
                                    elide: Text.ElideRight
                                    font.pixelSize: 14
                                    font.weight: Font.Bold
                                }
                            }
                        }
                    }
                }
            }

            // "Di perpustakaanmu": local files, downloads, liked songs, and own playlists
            Column {
                width: parent.width
                visible: page.typed && page.localTracks.length > 0 && (page.filter === "all" || page.filter === "tracks")
                spacing: 4
                Label {
                    text: I18n.t("In your library")
                    font.pixelSize: 18
                    font.weight: Font.Bold
                    bottomPadding: 4
                }
                Repeater {
                    model: page.filter === "tracks" ? page.localTracks : page.localTracks.slice(0, 5)
                    TrackRow {
                        width: parent.width
                        track: modelData
                        number: index + 1
                        onPlay: {
                            library.addSearchHistory(page.lastQuery || field.text.trim())
                            player.playUris(page.localTracks.map(x => x.uri), index)
                        }
                    }
                }
            }

            // "Semua": top result next to the first songs
            GridLayout {
                width: parent.width
                visible: page.filter === "all" && page.tracks.length > 0
                columns: width > 980 ? 2 : 1
                columnSpacing: 20
                rowSpacing: 12

                Rectangle {
                    id: topCard
                    Layout.preferredWidth: parent.columns === 2 ? parent.width * 0.38 : parent.width
                    Layout.fillHeight: parent.columns === 2
                    implicitHeight: 250
                    radius: 16
                    color: Theme.surface
                    border.color: Theme.line
                    readonly property var hit: page.tracks[0] || ({})
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 6
                        Label { text: I18n.t("Top result"); color: Theme.dim; font.pixelSize: 12; font.weight: Font.Bold }
                        Cover {
                            Layout.topMargin: 8
                            Layout.preferredWidth: 104; Layout.preferredHeight: 104
                            radius: 10
                            source: topCard.hit.image || topCard.hit.imageSmall || ""
                        }
                        Label {
                            Layout.fillWidth: true
                            Layout.topMargin: 6
                            text: topCard.hit.name || ""
                            font.pixelSize: 26; font.weight: Font.Black
                            elide: Text.ElideRight
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            LinkLabel {
                                Layout.fillWidth: true
                                text: (topCard.hit.artists || "") + (topCard.hit.album ? " • " + topCard.hit.album : "")
                                font.pixelSize: 14
                                onClicked: Nav.goArtist(topCard.hit)
                            }
                            IconButton {
                                iconName: "play"
                                size: 24
                                filled: true
                                tip: I18n.t("Play")
                                onClicked: {
                                    library.addSearchHistory(page.lastQuery || field.text.trim())
                                    player.playUris(page.tracks.map(x => x.uri), 0)
                                }
                            }
                        }
                    }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 0
                    Label { text: I18n.t("Songs"); font.pixelSize: 18; font.weight: Font.Bold; bottomPadding: 6 }
                    Repeater {
                        model: page.tracks.slice(0, 5)
                        TrackRow {
                            width: parent.width
                            track: modelData
                            number: index + 1
                            showAlbum: false
                            onPlay: {
                                library.addSearchHistory(page.lastQuery || field.text.trim())
                                player.playUris(page.tracks.map(x => x.uri), index)
                            }
                        }
                    }
                }
            }

            // "Lagu": the full list
            Column {
                width: parent.width
                visible: page.filter === "tracks" && page.tracks.length > 0
                Repeater {
                    model: page.filter === "tracks" ? page.tracks : []
                    TrackRow {
                        width: col.width
                        track: modelData
                        number: index + 1
                        onPlay: {
                            library.addSearchHistory(page.lastQuery || field.text.trim())
                            player.playUris(page.tracks.map(x => x.uri), index)
                        }
                    }
                }
            }

            // shelves (Semua) or grids (single filter)
            Carousel { width: parent.width; visible: page.typed && page.filter === "all" && items.length > 0; title: I18n.t("Your playlists"); items: page.localPlaylists }
            Carousel { width: parent.width; visible: page.filter === "all" && items.length > 0; title: I18n.t("Artists"); items: page.results.artists || [] }
            Carousel { width: parent.width; visible: page.filter === "all" && items.length > 0; title: I18n.t("Albums"); items: page.results.albums || [] }
            Carousel { width: parent.width; visible: page.filter === "all" && items.length > 0; title: I18n.t("Playlists"); items: page.results.playlists || [] }
            CardGrid {
                width: parent.width
                visible: page.filter !== "all" && page.filter !== "tracks" && items.length > 0
                items: page.filter === "albums" ? (page.results.albums || [])
                     : page.filter === "artists" ? (page.results.artists || [])
                     : page.filter === "playlists" ? page.localPlaylists.concat(page.results.playlists || []) : []
                rows: 99
                expanded: true
            }
        }
    }
}
