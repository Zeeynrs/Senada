import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

// Playlist, album, liked songs and offline (downloaded) songs.
Item {
    id: page
    property string kind
    property string itemId
    readonly property string pageKey: kind + ":" + itemId
    property var info: ({})
    property bool loading: true

    function reload() {
        loading = true
        selectedGroup = null
        filterQuery = ""
        library.load(kind, itemId)
    }
    Component.onCompleted: reload()

    readonly property bool isLocal: !!info.local
    property string filterQuery: ""
    property string localView: "songs"   // songs | albums | artists | folders
    property var selectedGroup: null
    property int localGroupRev: 0
    readonly property var tracks: (kind === "local" && selectedGroup) ? (selectedGroup.tracks || []) : (info.tracks || [])
    readonly property bool showingGroups: kind === "local" && localView !== "songs" && !selectedGroup
    readonly property var localGroups: {
        const _rev = localGroupRev
        const _info = info
        if (!showingGroups) return []
        const q = filterQuery.trim().toLowerCase()
        const all = localfiles.groups(localView) || []
        if (!q) return all
        return all.filter(g => String(g.name || "").toLowerCase().includes(q)
                            || String(g.subtitle || "").toLowerCase().includes(q))
    }
    // table sorting + quick filter: "" keeps the collection's own order
    property string sortKey: ""
    property bool sortAsc: true
    readonly property var shown: {
        const q = filterQuery.trim().toLowerCase()
        const numbered = tracks.map((x, i) => Object.assign({}, x, { number: i + 1 }))
        const filtered = !q ? numbered : numbered.filter(x =>
            String(x.name || "").toLowerCase().includes(q)
            || String(x.artists || "").toLowerCase().includes(q)
            || String(x.album || "").toLowerCase().includes(q)
        )
        if (!sortKey) return filtered
        const k = sortKey, dir = sortAsc ? 1 : -1
        return filtered.sort((a, b) => {
            const x = a[k], y = b[k]
            if (typeof x === "number" || typeof y === "number") return ((x || 0) - (y || 0)) * dir
            return String(x || "").localeCompare(String(y || ""), undefined, { sensitivity: "base" }) * dir
        })
    }
    function sortBy(key) {
        if (key === "number" || (sortKey === key && !sortAsc)) { sortKey = ""; sortAsc = true }
        else if (sortKey === key) sortAsc = false
        else { sortKey = key; sortAsc = true }
    }
    readonly property bool isSpotify: itemId.indexOf("sp-") === 0
    readonly property bool isOffline: kind === "offline"
    // how many of these songs are downloaded, for the "download all" button
    readonly property int downloadedCount: (downloads.revision, downloads.downloadedCount(tracks.map(t => t.uri)))

    Connections {
        target: downloads
        function onChanged() { if (page.isOffline) library.load(page.kind, page.itemId) }
    }

    Connections {
        target: library
        function onLoaded(key, data) {
            if (key !== page.pageKey) return
            page.info = data
            page.loading = false
            if (data.error) session.toast(data.error)
        }
        // keep liked songs and own playlists in sync with edits made elsewhere
        function onLikedChanged() { if (page.kind === "liked") library.load(page.kind, page.itemId) }
        function onPlaylistsChanged() {
            if (page.isLocal && library.ownPlaylists.some(p => p.id === page.itemId))
                library.load(page.kind, page.itemId)
        }
    }
    Connections {  // the music folders were scanned again
        target: localfiles
        function onChanged() {
            if (page.kind === "local") {
                page.selectedGroup = null
                page.localGroupRev += 1
                library.load(page.kind, page.itemId)
            }
        }
    }

    Dialogs.FileDialog {
        id: exportM3uDialog
        title: I18n.t("Export playlist as M3U")
        fileMode: Dialogs.FileDialog.SaveFile
        currentFile: ((info.name || "playlist").replace(/[\\/:*?"<>|]/g, "_") + ".m3u8")
        nameFilters: [I18n.t("M3U8 playlist") + " (*.m3u8)", I18n.t("M3U playlist") + " (*.m3u)"]
        onAccepted: library.exportTracksM3u(info.name || page.kind, page.tracks, selectedFile)
    }

    function playAt(i) {
        if (sortKey || filterQuery.trim() !== "" || (page.kind === "local" && page.selectedGroup)) {  // filtered/sorted/group view
            player.playUris(shown.map(x => x.uri), i)
            return
        }
        const t = tracks
        if (info.playUri)
            player.playContext(info.playUri, t[i] ? t[i].uri : "")
        else
            player.playUris(t.map(x => x.uri), i)
    }
    function playAll() { playAt(0) }
    function shuffleAll() {
        if (info.playUri && filterQuery.trim() === "" && !(page.kind === "local" && page.selectedGroup)) {
            player.shufflePlay(info.playUri)
            return
        }
        const uris = (page.filterQuery.trim() !== "" || (page.kind === "local" && page.selectedGroup) ? shown : (info.tracks || [])).map(x => x.uri)
        for (let i = uris.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [uris[i], uris[j]] = [uris[j], uris[i]]
        }
        player.playUris(uris, 0)
    }

    ListView {
        id: list
        SmoothScroll { flickable: list }
        anchors.fill: parent
        clip: true
        currentIndex: -1  // don't auto-scroll to the first row (it would clip the header)
        // when the header grows (cover, title, "Lagu teratas" arrive later) and the user hasn't
        // scrolled yet, stay at the very top instead of letting the header slide up under the bar
        property real lastOriginY: 0
        onOriginYChanged: {
            if (!moving && contentY <= lastOriginY + 1)
                contentY = originY
            lastOriginY = originY
        }
        model: page.showingGroups ? page.localGroups : page.shown
        reuseItems: page.kind !== "local"
        bottomMargin: Theme.dockSpace
        ScrollBar.vertical: NScrollBar {}

        header: Column {
          width: list.width
          PageHeader {
            width: list.width
            info: page.info
            loading: page.loading
            fallbackIcon: page.kind === "liked" ? "heart" : page.isOffline ? "downloaded" : "note"
            canSave: page.kind !== "liked" && !page.isOffline && !page.isLocal && !page.isSpotify && !page.info.error
            canDownload: !page.isOffline && page.kind !== "local" && !page.info.error && page.tracks.length > 0
            downloadedCount: page.downloadedCount
            trackCount: page.tracks.length
            saved: (library.savedRevision, library.isSaved(page.kind, page.itemId))
            canImport: page.isSpotify && (page.info.tracks || []).length > 0
            isLocal: page.isLocal
            canSync: page.kind === "playlist" && page.isLocal && !!page.info.source
            canExport: !page.info.error && page.tracks.length > 0
            onPlayAll: page.playAll()
            onShuffleAll: page.shuffleAll()
            onSaveToggled: library.toggleSaved(page.info)
            onImportRequested: library.importCollection(page.info)
            onDownloadAll: downloads.download(page.tracks)
            onRenameRequested: Nav.renamePlaylist(page.itemId, page.info.name)
            onDeleteRequested: Nav.deletePlaylist(page.itemId, page.info.name)
            onSyncRequested: library.syncImportedPlaylist(page.itemId)
            onDedupeRequested: library.dedupePlaylist(page.itemId)
            onExportRequested: exportM3uDialog.open()
          }

          // Local files grouping tabs + track filter bar
          RowLayout {
            visible: !page.loading && !page.info.error && (page.kind === "local" || (info.tracks || []).length > 0)
            width: list.width - 32
            x: 16
            height: visible ? 46 : 0
            spacing: 8

            Row {
                visible: page.kind === "local"
                spacing: 6
                Repeater {
                    model: [
                        { key: "songs", label: I18n.t("All songs") },
                        { key: "albums", label: I18n.t("Albums") },
                        { key: "artists", label: I18n.t("Artists") },
                        { key: "folders", label: I18n.t("Folders") }
                    ]
                    Chip {
                        required property var modelData
                        text: modelData.label
                        checked: page.localView === modelData.key
                        onClicked: { page.localView = modelData.key; page.selectedGroup = null }
                    }
                }
            }

            NButton {
                visible: page.kind === "local" && !!page.selectedGroup
                iconName: "back"
                text: page.selectedGroup ? page.selectedGroup.name : ""
                implicitHeight: 32
                onClicked: page.selectedGroup = null
            }

            Item { Layout.fillWidth: true }

            NTextField {
                id: filterBox
                visible: (info.tracks || []).length > 0
                Layout.preferredWidth: 230
                implicitHeight: 34
                placeholderText: page.showingGroups ? I18n.t("Filter groups…") : I18n.t("Filter songs…")
                text: page.filterQuery
                onTextChanged: page.filterQuery = text
            }
            IconButton {
                visible: page.filterQuery.length > 0
                iconName: "close"
                size: 15
                tip: I18n.t("Clear filter")
                onClicked: page.filterQuery = ""
            }
          }
          // offline songs: what is downloading right now
          Item {
            id: downloadStrip
            visible: page.isOffline && downloads.pending > 0
            width: list.width
            height: visible ? 44 : 0
            Row {
              x: 32
              anchors.verticalCenter: parent.verticalCenter
              spacing: 12
              BusyIndicator {
                anchors.verticalCenter: parent.verticalCenter
                running: downloadStrip.visible
                implicitWidth: 22
                implicitHeight: 22
              }
              Label {
                anchors.verticalCenter: parent.verticalCenter
                text: downloads.current.name
                      ? I18n.t("Downloading “{name}” — {p}%", { name: downloads.current.name, p: downloads.current.progress })
                        + (downloads.pending > 1 ? "  ·  " + I18n.n("{n} more waiting", "{n} more waiting", downloads.pending - 1) : "")
                      : I18n.t("Getting ready to download…")
                color: Theme.dim
                font.pixelSize: 13
              }
              LinkLabel {
                anchors.verticalCenter: parent.verticalCenter
                text: I18n.t("Cancel all")
                font.pixelSize: 13
                onClicked: downloads.cancelAll()
              }
            }
          }
          TrackTableHeader {
            visible: !page.showingGroups && page.tracks.length > 0
            width: list.width
            inset: 16
            showCover: page.kind !== "album"
            showAlbum: page.kind !== "album"
            sortKey: page.sortKey
            sortAsc: page.sortAsc
            onSortBy: (key) => page.sortBy(key)
          }
        }

        Component {
            id: trackRowComp
            TrackRow {
                inset: 16
                table: true
                track: rowData
                number: rowData.number || (rowIndex + 1)
                showCover: page.kind !== "album"
                showAlbum: page.kind !== "album"
                removable: page.isLocal && page.kind === "playlist"
                movable: page.isLocal && page.kind === "playlist" && page.filterQuery.trim() === "" && page.sortKey === ""
                canMoveUp: rowIndex > 0
                canMoveDown: rowIndex < page.shown.length - 1
                onPlay: page.playAt(rowIndex)
                onRemove: library.removeFromPlaylist(page.itemId, rowData.uri)
                onMoveUp: library.moveInPlaylist(page.itemId, rowIndex, rowIndex - 1)
                onMoveDown: library.moveInPlaylist(page.itemId, rowIndex, rowIndex + 1)
            }
        }

        Component {
            id: groupRowComp
            AbstractButton {
                width: list.width - 32
                x: 16
                implicitHeight: 64
                hoverEnabled: true
                onClicked: page.selectedGroup = rowData
                background: Rectangle {
                    radius: 10
                    color: parent.hovered ? Theme.hover : "transparent"
                }
                contentItem: RowLayout {
                    spacing: 14
                    Item { Layout.preferredWidth: 6 }
                    Cover {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 46
                        round: page.localView === "artists"
                        radius: 8
                        source: rowData.imageSmall || ""
                        fallbackIcon: page.localView === "artists" ? "person" : page.localView === "albums" ? "album" : "list"
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            Layout.fillWidth: true
                            text: rowData.name || ""
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Label {
                            Layout.fillWidth: true
                            text: rowData.subtitle || ""
                            font.pixelSize: 12
                            color: Theme.dim
                            elide: Text.ElideRight
                        }
                    }
                    Icon { glyph: "chevron-right"; size: 18; color: Theme.dim }
                    Item { Layout.preferredWidth: 6 }
                }
            }
        }

        delegate: Loader {
            required property var modelData
            required property int index
            readonly property var rowData: modelData
            readonly property int rowIndex: index
            width: list.width
            sourceComponent: page.showingGroups ? groupRowComp : trackRowComp
        }

        footer: Label {
            width: list.width
            visible: !!page.info.note
            text: page.info.note || ""
            padding: 32
            wrapMode: Text.WordWrap
            color: Theme.dim
            font.pixelSize: 14
        }
    }
}
