"""Display and interact with the official SDK's Qt window over the local bridge."""

import json
import re
import struct

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QImage, QKeySequence, QPainter, QShortcut
from PyQt6.QtNetwork import QHostAddress, QTcpSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget


FRAME = struct.Struct("<9I")
INPUT = struct.Struct("<IIii6I")
MAX_FRAME = 64 * 1024 * 1024
MOUSE_EVENTS = {
    QEvent.Type.MouseButtonPress: 2,
    QEvent.Type.MouseButtonRelease: 3,
    QEvent.Type.MouseButtonDblClick: 4,
    QEvent.Type.MouseMove: 5,
}


class LoginWindow(QWidget):
    def __init__(self, endpoint):
        super().__init__()
        self.endpoint = endpoint
        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self.authenticate)
        self.socket.disconnected.connect(self.disconnected)
        self.socket.readyRead.connect(self.read_frames)
        self.buffer = bytearray()
        self.token = b""
        self.generation = 0
        self.image = QImage()
        self.zoom = 1.0
        self.view_center = QPointF(0.5, 0.5)
        self.failure_notice = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled)
        self.setWindowTitle("蓝色星原 · 官方 SDK")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.connect_to_host)
        self.timer.start(400)
        for key, factor in (("Ctrl++", 1.25), ("Ctrl+=", 1.25), ("Ctrl+-", 0.8), ("Ctrl+0", 0)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda multiplier=factor: self.zoom_at(multiplier, QPointF(self.rect().center())))

    def connect_to_host(self):
        if self.socket.state() != QTcpSocket.SocketState.UnconnectedState:
            return
        try:
            with self.endpoint.open() as source:
                data = json.load(source)
            port, token = data["port"], data["token"]
            if data["revision"] != 2 or not 1 <= port <= 65535:
                return
            if not re.fullmatch(r"[0-9a-f]{64}", token):
                return
        except (OSError, ValueError, KeyError, TypeError):
            return
        self.token = token.encode("ascii")
        self.socket.connectToHost(QHostAddress("127.0.0.1"), port)

    def authenticate(self):
        self.socket.write(self.token)
        self.token = b""

    def disconnected(self):
        was_visible = self.isVisible()
        self.buffer.clear()
        self.image = QImage()
        self.hide()
        if was_visible:
            QTimer.singleShot(1200, self.report_host_failure)

    def report_host_failure(self):
        if self.isVisible() or self.failure_notice is not None:
            return
        if not self.endpoint.with_name("sdk-host-failure.log").is_file():
            return
        self.failure_notice = QMessageBox()
        self.failure_notice.setWindowTitle("蓝色星原 · 登录中断")
        self.failure_notice.setText("官方 SDK 在登录完成前退出。关闭游戏后可以从启动器重试。")
        self.failure_notice.show()

    def read_frames(self):
        self.buffer.extend(bytes(self.socket.readAll()))
        while len(self.buffer) >= FRAME.size:
            magic, revision, kind, width, height, _, _, size, generation = FRAME.unpack_from(self.buffer)
            if magic != 0x49555A41 or revision != 2 or size > MAX_FRAME:
                self.socket.abort()
                return
            end = FRAME.size + size
            if len(self.buffer) < end:
                return
            payload = bytes(self.buffer[FRAME.size:end])
            del self.buffer[:end]
            if kind == 2:
                self.generation = generation
                self.image = QImage()
                self.zoom = 1.0
                self.view_center = QPointF(0.5, 0.5)
                self.hide()
            if kind == 1 and 0 < width <= 4096 and 0 < height <= 4096 and size == width * height * 4:
                self.present(payload, width, height, generation)

    def present(self, pixels, width, height, generation):
        self.generation = generation
        self.image = QImage(pixels, width, height, width * 4, QImage.Format.Format_RGB32).copy()
        if not self.isVisible():
            screen = self.screen()
            area = screen.availableGeometry()
            size = self.image.size().scaled(area.size() * 0.85, Qt.AspectRatioMode.KeepAspectRatio)
            self.resize(min(width, size.width()), min(height, size.height()))
            self.move(area.center() - self.rect().center())
            self.show()
            self.raise_()
            self.activateWindow()
        self.update()

    def paintEvent(self, event):
        if self.image.isNull():
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.image_viewport(), self.image, QRectF(self.image.rect()))

    def image_viewport(self):
        if self.image.isNull():
            return QRectF()
        scale = self.zoom * min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale

        def offset(view, image, center):
            if image <= view:
                return (view - image) / 2
            return min(0.0, max(view - image, view / 2 - image * center))

        return QRectF(offset(self.width(), width, self.view_center.x()),
                      offset(self.height(), height, self.view_center.y()), width, height)

    def zoom_at(self, factor, position):
        if self.image.isNull():
            return
        if not factor:
            self.zoom = 1.0
            self.view_center = QPointF(0.5, 0.5)
        else:
            before = self.image_viewport()
            source_x = (position.x() - before.x()) / before.width()
            source_y = (position.y() - before.y()) / before.height()
            self.zoom = max(1.0, min(4.0, self.zoom * factor))
            after = self.image_viewport()
            self.view_center = QPointF(
                source_x + (self.width() / 2 - position.x()) / after.width(),
                source_y + (self.height() / 2 - position.y()) / after.height(),
            )
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120
            self.zoom_at(1.25 ** steps, event.position())
            event.accept()
        else:
            super().wheelEvent(event)

    def send_input(self, kind, x=0, y=0, button=0, buttons=0, modifiers=0, key=0, text=""):
        if self.socket.state() != QTcpSocket.SocketState.ConnectedState:
            return
        encoded = text.encode("utf-16-le")
        if len(encoded) + INPUT.size - 4 > 65536:
            return
        packet = INPUT.pack(INPUT.size - 4 + len(encoded), kind, x, y, button, buttons, modifiers,
                            key, len(encoded) // 2, self.generation)
        self.socket.write(packet + encoded)

    def mouse_input(self, event):
        viewport = self.image_viewport()
        if viewport.isEmpty():
            return
        pos = event.position() - viewport.topLeft()
        self.send_input(1, round(pos.x() * self.image.width() / viewport.width()),
                        round(pos.y() * self.image.height() / viewport.height()), event.button().value,
                        event.buttons().value, event.modifiers().value, MOUSE_EVENTS[event.type()])

    mousePressEvent = mouse_input
    mouseReleaseEvent = mouse_input
    mouseDoubleClickEvent = mouse_input
    mouseMoveEvent = mouse_input

    def keyPressEvent(self, event):
        self.send_input(2, modifiers=event.modifiers().value, key=event.key(), text=event.text())

    def keyReleaseEvent(self, event):
        self.send_input(3, modifiers=event.modifiers().value, key=event.key(), text=event.text())

    def inputMethodEvent(self, event):
        if event.commitString():
            self.send_input(2, key=0, text=event.commitString())
        event.accept()

    def closeEvent(self, event):
        self.send_input(4)
        event.ignore()


def run(endpoint):
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = LoginWindow(endpoint)
    return app.exec()
