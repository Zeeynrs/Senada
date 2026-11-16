import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: p
    width: 340
    padding: 16
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    property bool showSaveRow: false

    background: Rectangle {
        color: Theme.surface2
        radius: 22
        border.color: Theme.line
    }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }

    contentItem: ColumnLayout {
        spacing: 12

        // Header: Equalizer switch
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: I18n.t("Equalizer")
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            IconButton {
                iconName: "refresh"
                size: 16
                tip: I18n.t("Reset equalizer")
                onClicked: effects.reset()
            }
            NSwitch {
                checked: effects.enabled
                onToggled: effects.setEnabled(checked)
            }
        }

        // Preset chooser + save/delete custom preset
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            NCombo {
                Layout.fillWidth: true
                implicitHeight: 34
                model: {
                    const list = effects.presetNames.map(n => ({ key: n, label: n }))
                    if (effects.preset === "Custom" && effects.presetNames.indexOf("Custom") < 0)
                        list.unshift({ key: "Custom", label: I18n.t("Custom") })
                    return list
                }
                value: effects.preset
                onPicked: (key) => { if (key !== "Custom") effects.usePreset(key) }
            }
            IconButton {
                iconName: "add"
                size: 17
                tip: I18n.t("Save custom preset")
                onClicked: p.showSaveRow = !p.showSaveRow
            }
            IconButton {
                visible: effects.isCustomPreset(effects.preset)
                iconName: "close"
                size: 16
                tip: I18n.t("Delete preset")
                onClicked: effects.deletePreset(effects.preset)
            }
        }

        RowLayout {
            visible: p.showSaveRow
            Layout.fillWidth: true
            spacing: 6
            NTextField {
                id: presetNameField
                Layout.fillWidth: true
                implicitHeight: 34
                placeholderText: I18n.t("Preset name…")
                onAccepted: if (effects.savePreset(text)) { text = ""; p.showSaveRow = false }
            }
            NButton {
                text: I18n.t("Save")
                primary: true
                implicitHeight: 34
                onClicked: if (effects.savePreset(presetNameField.text)) { presetNameField.text = ""; p.showSaveRow = false }
            }
        }

        // 6-band EQ sliders (-12dB to +12dB normalized -1..1)
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            spacing: 6
            opacity: effects.enabled ? 1.0 : 0.45

            Repeater {
                model: effects.bandLabels.length
                ColumnLayout {
                    required property int index
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 4

                    Slider {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillHeight: true
                        orientation: Qt.Vertical
                        from: -1.0
                        to: 1.0
                        stepSize: 0.05
                        value: (effects.bands && index < effects.bands.length) ? effects.bands[index] : 0
                        onMoved: effects.setBand(index, value)
                        ToolTip.visible: hovered || pressed
                        ToolTip.text: Math.round(value * 12) + " dB"
                    }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: effects.bandLabels[index]
                        font.pixelSize: 10
                        color: Theme.dim
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.alpha(Theme.text, 0.08) }

        // Playback speed & Keep Pitch & Normalize
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                text: I18n.t("Speed")
                font.pixelSize: 13
                color: Theme.dim
            }
            NSlider {
                Layout.fillWidth: true
                from: 0.5
                to: 2.0
                stepSize: 0.05
                value: effects.tempo
                onMoved: effects.setTempo(Math.round(value * 20) / 20)
            }
            AbstractButton {
                implicitWidth: 44
                implicitHeight: 26
                onClicked: effects.setTempo(1.0)
                ToolTip.visible: hovered
                ToolTip.text: I18n.t("Reset speed")
                background: Rectangle { radius: 13; color: Theme.hover }
                contentItem: Label {
                    text: Number(effects.tempo.toFixed(2)) + "×"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { Layout.fillWidth: true; text: I18n.t("Keep original pitch"); font.pixelSize: 13 }
            NSwitch { checked: effects.keepPitch; onToggled: effects.setKeepPitch(checked) }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { Layout.fillWidth: true; text: I18n.t("Even out loudness"); font.pixelSize: 13 }
            NSwitch { checked: effects.normalize; onToggled: effects.setNormalize(checked) }
        }

        NButton {
            Layout.fillWidth: true
            text: I18n.t("Audio settings…")
            iconName: "settings"
            onClicked: { p.close(); Nav.go("settings", "audio") }
        }
    }
}
