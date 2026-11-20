import QtQuick

// Dragging a song of the queue up or down (TrackRow's `reorder`): the row follows the pointer,
// the rows it passes make room, and letting go moves the song there (player.moveInQueue).
// Near the top or bottom edge of the list it scrolls along.
QtObject {
    id: qr
    property ListView view
    property int from: -1             // the row being dragged (offset in player.queue)
    property int to: -1               // where it would land now
    property real delta: 0            // how far it has been dragged, in list content pixels
    property real step: 1             // one row, with the list's spacing
    readonly property bool active: from >= 0

    property real _startViewY: 0
    property real _startContentY: 0
    property real _viewY: 0

    function begin(index, rowHeight, viewY) {
        step = Math.max(1, rowHeight + (view ? view.spacing : 0))
        _startViewY = _viewY = viewY
        _startContentY = view ? view.contentY : 0
        delta = 0
        to = index
        from = index
    }
    function update(viewY) {
        _viewY = viewY
        _place()
    }
    function finish() {
        const f = from, t = to
        if (f >= 0 && t >= 0 && t !== f) {
            // the new queue reloads the list, which would jump back to the top: stay put
            const v = view, y = v ? v.contentY : 0
            player.moveInQueue(f, t)
            if (v) {
                v.contentY = y
                Qt.callLater(function() { v.contentY = y })
            }
        }
        from = -1
        to = -1
        delta = 0
    }
    // how far a row that is not dragged moves aside to make room
    function shift(index) {
        if (from < 0 || index === from)
            return 0
        if (from < to && index > from && index <= to)
            return -step
        if (to < from && index >= to && index < from)
            return step
        return 0
    }
    function _place() {
        delta = (_viewY - _startViewY) + ((view ? view.contentY : 0) - _startContentY)
        const last = view ? view.count - 1 : 0
        to = Math.max(0, Math.min(last, from + Math.round(delta / step)))
    }

    // scrolls along while the pointer is near an edge of the list
    property Timer _edgeScroll: Timer {
        interval: 16
        repeat: true
        running: qr.active && !!qr.view
        onTriggered: {
            const v = qr.view
            const edge = Math.min(48, v.height / 4)
            let speed = 0
            if (qr._viewY < edge)
                speed = -Math.ceil((edge - qr._viewY) / 4)
            else if (qr._viewY > v.height - edge)
                speed = Math.ceil((qr._viewY - (v.height - edge)) / 4)
            if (speed === 0)
                return
            const top = v.originY
            const bottom = Math.max(top, v.originY + v.contentHeight + v.bottomMargin - v.height)
            const y = Math.max(top, Math.min(bottom, v.contentY + speed))
            if (y !== v.contentY) {
                v.contentY = y
                qr._place()
            }
        }
    }
}
