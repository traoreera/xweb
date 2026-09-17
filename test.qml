import QtQuick
import QtQuick.Controls

ApplicationWindow {
    visible: true
    width: 400
    height: 300
    title: "Mon Bureau KDE & QML"

    Rectangle {
        anchors.fill: parent
        color: "#232629" // La couleur sombre par défaut de KDE Breeze

        Column {
            anchors.centerIn: parent
            spacing: 20

            Text {
                text: "Bonjour depuis KDE Plasma !"
                color: "white"
                font.pointSize: 18
                anchors.horizontalCenter: parent
            }

            Button {
                text: "Cliquez ici"
                anchors.horizontalCenter: parent
                onClicked: print("Bouton cliqué !")
            }
        }
    }
}
