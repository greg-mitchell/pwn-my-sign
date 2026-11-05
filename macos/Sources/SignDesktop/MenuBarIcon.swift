import AppKit

enum MenuBarIcon {
    static func make() -> NSImage {
        let image = NSImage(size: NSSize(width: 24, height: 18), flipped: true) { bounds in
            NSGraphicsContext.saveGraphicsState()
            defer { NSGraphicsContext.restoreGraphicsState() }

            // Align the visible artwork rather than its uneven transparent padding.
            let placement = NSAffineTransform()
            placement.translateX(by: bounds.midX, yBy: bounds.midY)
            placement.scale(by: 1.3)
            placement.translateX(by: -9, yBy: -8.75)
            placement.concat()
            NSColor.black.set()

            let frame = NSBezierPath(
                roundedRect: NSRect(x: 1, y: 4, width: 16, height: 9.5), xRadius: 1.6, yRadius: 1.6
            )
            frame.lineWidth = 1.25
            frame.stroke()

            let ink = NSBezierPath()
            ink.lineWidth = 1
            ink.lineCapStyle = .round
            ink.lineJoinStyle = .round
            ink.move(to: NSPoint(x: 3.2, y: 11))
            ink.line(to: NSPoint(x: 5.2, y: 8.8))
            ink.line(to: NSPoint(x: 7.6, y: 11))
            ink.move(to: NSPoint(x: 10.2, y: 7.3))
            ink.line(to: NSPoint(x: 14.5, y: 7.3))
            ink.move(to: NSPoint(x: 10.2, y: 10.2))
            ink.line(to: NSPoint(x: 13.2, y: 10.2))
            ink.stroke()

            NSBezierPath(ovalIn: NSRect(x: 6.25, y: 6.35, width: 1.1, height: 1.1)).fill()
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = "My Sign"
        return image
    }
}
