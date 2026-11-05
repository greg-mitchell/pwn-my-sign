import AppKit
import Testing
@testable import SignDesktop

@MainActor
private func visibleBounds(_ image: NSImage) throws -> NSRect {
    let scale = 2
    let width = Int(image.size.width) * scale
    let height = Int(image.size.height) * scale
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    ), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw NSError(domain: "MenuBarIconRendering", code: 1)
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.cgContext.scaleBy(x: CGFloat(scale), y: CGFloat(scale))
    image.draw(in: NSRect(origin: .zero, size: image.size))
    NSGraphicsContext.restoreGraphicsState()

    var left = width
    var top = height
    var right = -1
    var bottom = -1
    for y in 0..<height {
        for x in 0..<width where (bitmap.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.1 {
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)
        }
    }
    guard right >= left, bottom >= top else {
        throw NSError(domain: "MenuBarIconRendering", code: 2)
    }
    return NSRect(
        x: CGFloat(left) / CGFloat(scale), y: CGFloat(top) / CGFloat(scale),
        width: CGFloat(right - left + 1) / CGFloat(scale),
        height: CGFloat(bottom - top + 1) / CGFloat(scale)
    )
}

@Test @MainActor
func test_make_when_rendered_returns_legible_menu_bar_height() throws {
    let image = MenuBarIcon.make()

    let bounds = try visibleBounds(image)

    #expect(bounds.height >= 13.5)
}

@Test @MainActor
func test_make_when_rendered_returns_vertically_centered_artwork() throws {
    let image = MenuBarIcon.make()

    let bounds = try visibleBounds(image)

    #expect(abs(bounds.midY - image.size.height / 2) < 0.1)
}
